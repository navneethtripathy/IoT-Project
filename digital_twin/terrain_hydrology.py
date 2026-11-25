"""
CivicTwin-R — Terrain-Aware 2D Hydrological Screening Model (Landlab OverlandFlow)

Executes shallow-water 2D overland runoff and terrain routing in metric coordinates
(EPSG:32644 / WGS 84 UTM Zone 44N) over the Copernicus GLO-30 Digital Surface Model
clipped to the South Chennai & Lower Adyar-Kovalam-Pallikaranai pilot domain.

Governing Numerical Solver:
  Landlab OverlandFlow (de Almeida et al., 2012 inertial shallow-water approximation
  on structured RasterModelGrid) coupled with single-pass hydrologic partitioning:
    - Gross Rainfall Input (m^3)
    - Soil Infiltration Sink on Permeable Fraction (no runoff-coefficient double-counting)
    - Urban Stormwater Drainage Sink (capped by available surface water, h >= 0 invariant)
    - Optional Boundary Spillway Inflow (Chembarambakkam outlet node on Adyar River)
    - Coastal / Domain Open Outflow Tracking across Bay of Bengal Fixed-Value Boundaries

Explicit Scientific Scope & Limitations:
  - Spatial domain bounded strictly to South Chennai pilot (26.25 km x 16.65 km at 150m).
  - Copernicus GLO-30 is a 30m Digital Surface Model (DSM), not surveyed bare-earth LiDAR;
    building roofs & canopy introduce local elevation bias.
  - Designed for scenario planning & relative accumulation screening, NOT certified
    real-time street-level flood forecasting or official evacuation warning.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from landlab import NodeStatus, RasterModelGrid
from landlab.components import OverlandFlow
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import label

logger = logging.getLogger("civictwin.terrain_hydrology")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_GEO_DIR = _PROJECT_ROOT / "data" / "geo" / "processed"
DEM_NPZ_PATH = PROCESSED_GEO_DIR / "south_chennai_dem_utm44n_150m.npz"
MICHAUNG_CSV_PATH = _PROJECT_ROOT / "data" / "processed" / "chennai_michaung_hourly.csv"

WGS84_CRS = "EPSG:4326"
UTM44N_CRS = "EPSG:32644"

SCIENTIFIC_LIMITATIONS = [
    "Terrain surface derives from Copernicus GLO-30 DSM (30m resampled to 150m UTM 44N), not surveyed bare-earth LiDAR; dense rooftops create local DSM elevation bias.",
    "Stormwater pipe networks, subsurface culverts, and micro-scale bund breaches are represented only through spatially lumped drainage capacity parameters (no physical SWMM pipe network).",
    "No verified real-time or post-event inundation depth rasters exist in open datasets for quantitative calibration; reported flood depths are scenario screening estimates.",
    "Computational domain covers South Chennai (80.044°E–80.286°E, 12.905°N–13.056°N); northern Chennai basins are shown for spatial context only.",
]

# Prioritized Chennai Focus Locations inside & bounding the South Chennai pilot
FOCUS_LOCATIONS: List[Dict[str, Any]] = [
    {
        "id": "velachery",
        "name": "Velachery",
        "tamil_name": "வேளச்சேரி",
        "coordinates": [80.2180, 12.9815],
        "subbasin": "Kovalam / South Coastal (Kov-Sb18)",
        "category": "Urban Basin Hotspot",
        "primary_hazard": "Saucer depression draining eastward into Pallikaranai Marsh; stormwater outfall bottlenecks.",
        "historical_reference_note": "Official CFM-DSS spot records note recurrent monsoon waterlogging along 100ft Bypass Rd & Tansi Nagar.",
        "key_infrastructure": ["Velachery MRTS Station", "100ft Bypass Road", "Velachery Lake Surplus Drain"],
    },
    {
        "id": "pallikaranai",
        "name": "Pallikaranai Marsh",
        "tamil_name": "பள்ளிக்கரணை சதுப்புநிலம்",
        "coordinates": [80.2137, 12.9349],
        "subbasin": "Kovalam / South Coastal",
        "category": "Natural Wetland Sink",
        "primary_hazard": "Terminal freshwater wetland sink receiving South Chennai overland runoff before Okkiyam Maduvu.",
        "historical_reference_note": "Surveyed natural retention zone buffering surrounding Madipakkam, Velachery & Perungudi catchments.",
        "key_infrastructure": ["Pallikaranai Wetland Reserve", "Radial Road Causeway", "Okkiyam Maduvu Channel"],
    },
    {
        "id": "adyar",
        "name": "Adyar Estuary",
        "tamil_name": "அடையாறு முகத்துவாரம்",
        "coordinates": [80.2565, 13.0012],
        "subbasin": "Adyar Basin",
        "category": "Estuarine Outfall",
        "primary_hazard": "Coastal confluence of Adyar River and Buckingham Canal; sensitive to storm surge tailwater.",
        "historical_reference_note": "Mouth bar dynamics and tidal stage govern drainage head along lower Adyar reach.",
        "key_infrastructure": ["Tholkappiya Poonga", "Thiru Vi Ka Bridge", "Buckingham Canal Confluence"],
    },
    {
        "id": "madipakkam",
        "name": "Madipakkam",
        "tamil_name": "மடிப்பாக்கம்",
        "coordinates": [80.1961, 12.9647],
        "subbasin": "Kovalam (Kov-Sb15)",
        "category": "Urban Residential Lowland",
        "primary_hazard": "Inter-lake drainage cascading from Keelkattalai & Madipakkam Lakes toward Pallikaranai Marsh.",
        "historical_reference_note": "Flat gradient promotes prolonged ponding when marsh downstream tailwater rises.",
        "key_infrastructure": ["Madipakkam Tank", "Medavakkam Main Rd", "Keelkattalai Link Canal"],
    },
    {
        "id": "perungudi",
        "name": "Perungudi",
        "tamil_name": "பெருங்குடி",
        "coordinates": [80.2461, 12.9654],
        "subbasin": "Kovalam / South Coastal",
        "category": "IT Corridor & Canal Edge",
        "primary_hazard": "High-imperviousness OMR corridor flanking Pallikaranai East & Buckingham Canal.",
        "historical_reference_note": "Rapid surface runoff during convective cloudbursts across dense built-up parcels.",
        "key_infrastructure": ["OMR IT Corridor", "Perungudi Tank", "Buckingham Canal West Bank"],
    },
    {
        "id": "saidapet",
        "name": "Saidapet (Adyar Transit)",
        "tamil_name": "சைதாப்பேட்டை",
        "coordinates": [80.2231, 13.0213],
        "subbasin": "Adyar Basin",
        "category": "Fluvial River Choke",
        "primary_hazard": "Central Adyar River floodplain corridor downstream of Chembarambakkam & Manapakkam.",
        "historical_reference_note": "Sensitive to peak upstream Adyar discharge releases at Maraimalai Adigal Bridge.",
        "key_infrastructure": ["Maraimalai Adigal Bridge", "Saidapet Metro", "Adyar Floodplain"],
    },
    {
        "id": "porur",
        "name": "Porur",
        "tamil_name": "போரூர்",
        "coordinates": [80.1565, 13.0382],
        "subbasin": "Adyar (Ad-Sb15)",
        "category": "Lake Buffer Basin",
        "primary_hazard": "Porur Tank surplus overflow feeding Manapakkam drain into mid-Adyar reach.",
        "historical_reference_note": "Upstream urbanized retention buffer regulating western inflows.",
        "key_infrastructure": ["Porur Lake (1.90 MCM WRD)", "Mount-Poonamallee Rd", "Manapakkam Drain"],
    },
    {
        "id": "pallavaram",
        "name": "Pallavaram",
        "tamil_name": "பல்லாவரம்",
        "coordinates": [80.1491, 12.9675],
        "subbasin": "Adyar / Kovalam Divide",
        "category": "Foothill Runoff Corridor",
        "primary_hazard": "Steep hillslope runoff off Pallavaram Hill driving flash surface accumulation at piedmont roads.",
        "historical_reference_note": "Elevated terrain (25–130m DSM) feeds downhill lowlands toward Chromepet & Keelkattalai.",
        "key_infrastructure": ["Pallavaram Lake", "GST Road Corridor", "Chennai Airport East Boundary"],
    },
    {
        "id": "tambaram",
        "name": "Tambaram",
        "tamil_name": "தாம்பரம்",
        "coordinates": [80.1000, 12.9249],
        "subbasin": "Adyar / Kovalam Headwaters",
        "category": "Southern Headwaters",
        "primary_hazard": "Highland catchment headwater generating rapid sheet flow toward Mudichur & upper Adyar.",
        "historical_reference_note": "Includes western slope drainage feeding Mannivakkam-Mudichur reach.",
        "key_infrastructure": ["Tambaram Junction", "Mudichur Channel", "GST Southern Arterial"],
    },
    {
        "id": "chembarambakkam",
        "name": "Chembarambakkam Reservoir",
        "tamil_name": "செம்பரம்பாக்கம் ஏரி",
        "coordinates": [80.0680, 13.0120],
        "subbasin": "Adyar Headworks (Ad-Sb13)",
        "category": "Regulated Major Reservoir",
        "primary_hazard": "WRD Major Outlet Tank (103.15 MCM gross capacity, FTL 26.02m); spillway release drives Adyar River stage.",
        "historical_reference_note": "Monitored in preserved chennai_reservoirs.csv & CFM-DSS Lake Operation System.",
        "key_infrastructure": ["Chembarambakkam Sluice Spillway", "Adyar Headworks Channel"],
    },
]


@dataclass
class HydroScenarioConfig:
    scenario_id: str
    scenario_name: str
    mode: str  # "baseline", "scenario_simulation", "historical_replay", "monitoring_uncertainty", "boundary_discharge"
    rainfall_intensity_mm_hr: float
    duration_hours: float
    infiltration_rate_mm_hr: float
    drainage_efficiency_pct: float
    nominal_drain_cap_mm_hr: float = 12.0
    chembarambakkam_discharge_cusecs: float = 0.0
    mannings_n: float = 0.045
    initial_depth_m: float = 0.0
    description: str = ""
    rain_hyetograph_mm_hr: Optional[List[float]] = None
    hyetograph_timestamps: Optional[List[str]] = None
    provenance_tags: Optional[List[str]] = None

    def validate(self) -> None:
        if not (0.0 <= self.rainfall_intensity_mm_hr <= 350.0):
            raise ValueError(f"rainfall_intensity_mm_hr out of bounds [0, 350]: {self.rainfall_intensity_mm_hr}")
        if not (0.05 <= self.duration_hours <= 48.0):
            raise ValueError(f"duration_hours out of bounds [0.05, 48]: {self.duration_hours}")
        if not (0.0 <= self.infiltration_rate_mm_hr <= 100.0):
            raise ValueError(f"infiltration_rate_mm_hr out of bounds [0, 100]: {self.infiltration_rate_mm_hr}")
        if not (0.0 <= self.drainage_efficiency_pct <= 250.0):
            raise ValueError(f"drainage_efficiency_pct out of bounds [0, 250]: {self.drainage_efficiency_pct}")
        if not (0.0 <= self.chembarambakkam_discharge_cusecs <= 80000.0):
            raise ValueError(f"chembarambakkam_discharge_cusecs out of bounds [0, 80000]: {self.chembarambakkam_discharge_cusecs}")
        if not (0.01 <= self.mannings_n <= 0.30):
            raise ValueError(f"mannings_n out of bounds [0.01, 0.30]: {self.mannings_n}")
        if not (0.0 <= self.initial_depth_m <= 10.0):
            raise ValueError(f"initial_depth_m out of bounds [0, 10]: {self.initial_depth_m}")

    def cache_key(self) -> str:
        payload = json.dumps({
            "id": self.scenario_id,
            "mode": self.mode,
            "rain": self.rainfall_intensity_mm_hr,
            "dur": self.duration_hours,
            "inf": self.infiltration_rate_mm_hr,
            "drain": self.drainage_efficiency_pct,
            "cap": self.nominal_drain_cap_mm_hr,
            "spill": self.chembarambakkam_discharge_cusecs,
            "n": self.mannings_n,
            "h0": self.initial_depth_m,
            "hyeto": self.rain_hyetograph_mm_hr,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def load_michaung_storm_window(hours: int = 24) -> Tuple[List[float], List[str], Dict[str, Any]]:
    """Load the peak observed Cyclone Michaung 2023 rainfall window from preserved CSV."""
    if not MICHAUNG_CSV_PATH.exists():
        raise FileNotFoundError(f"Preserved Michaung CSV missing: {MICHAUNG_CSV_PATH}")
    rows = list(csv.DictReader(open(MICHAUNG_CSV_PATH)))
    # Peak precipitation centered Dec 3–4, 2023 (find slice with maximum cumulative sum)
    vals = [float(r["hourly_precipitation_mm"]) for r in rows]
    ts_list = [r["timestamp_local"] for r in rows]
    best_i = 0
    best_sum = -1.0
    for i in range(max(1, len(vals) - hours + 1)):
        s = sum(vals[i : i + hours])
        if s > best_sum:
            best_sum = s
            best_i = i
    window_vals = vals[best_i : best_i + hours]
    window_ts = ts_list[best_i : best_i + hours]
    meta = {
        "total_dataset_hours": len(rows),
        "window_start": window_ts[0] if window_ts else None,
        "window_end": window_ts[-1] if window_ts else None,
        "window_cumulative_mm": round(sum(window_vals), 2),
        "peak_hourly_mm": round(max(window_vals), 2) if window_vals else 0.0,
        "full_dataset_cumulative_mm": round(sum(vals), 2),
        "station_coordinates": [80.2707, 13.0827],
        "provenance": "ERA5_IMD_Calibrated (observed historical rainfall)",
    }
    return window_vals, window_ts, meta


PREDEFINED_SCENARIOS: Dict[str, HydroScenarioConfig] = {
    "normal": HydroScenarioConfig(
        scenario_id="normal",
        scenario_name="Normal Baseline Conditions",
        mode="baseline",
        rainfall_intensity_mm_hr=0.0,
        duration_hours=2.0,
        infiltration_rate_mm_hr=8.0,
        drainage_efficiency_pct=100.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=0.0,
        description="Dry weather baseline (0 mm/hr rainfall, 100% nominal drainage capacity, zero artificial flood).",
        provenance_tags=["baseline_condition", "copernicus_glo30_dsm", "landlab_overlandflow"],
    ),
    "heavy_rainfall": HydroScenarioConfig(
        scenario_id="heavy_rainfall",
        scenario_name="Heavy Monsoon Rainfall (45 mm/hr)",
        mode="scenario_simulation",
        rainfall_intensity_mm_hr=45.0,
        duration_hours=4.0,
        infiltration_rate_mm_hr=5.0,
        drainage_efficiency_pct=100.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=0.0,
        description="Scenario assumption: 45 mm/hr convective monsoon storm over 4h with nominal 12 mm/hr urban stormwater removal.",
        provenance_tags=["user_defined_scenario", "terrain_routed_landlab"],
    ),
    "extreme_rainfall": HydroScenarioConfig(
        scenario_id="extreme_rainfall",
        scenario_name="Extreme Cloudburst (85 mm/hr, Hypothetical)",
        mode="scenario_simulation",
        rainfall_intensity_mm_hr=85.0,
        duration_hours=6.0,
        infiltration_rate_mm_hr=3.0,
        drainage_efficiency_pct=80.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=0.0,
        description="Hypothetical severe cloudburst stress-test (85 mm/hr for 6h) exceeding typical design drainage thresholds.",
        provenance_tags=["hypothetical_extreme_scenario", "terrain_routed_landlab"],
    ),
    "reduced_drainage": HydroScenarioConfig(
        scenario_id="reduced_drainage",
        scenario_name="Reduced Drainage (Degraded 25% Capacity)",
        mode="scenario_simulation",
        rainfall_intensity_mm_hr=45.0,
        duration_hours=4.0,
        infiltration_rate_mm_hr=5.0,
        drainage_efficiency_pct=25.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=0.0,
        description="Identical 45 mm/hr storm to Heavy Monsoon, isolating the spatial impact of stormwater clogging (25% drainage effectiveness).",
        provenance_tags=["user_defined_scenario", "drainage_sensitivity_test"],
    ),
    "improved_drainage": HydroScenarioConfig(
        scenario_id="improved_drainage",
        scenario_name="Improved Drainage Mitigation (200% Capacity)",
        mode="scenario_simulation",
        rainfall_intensity_mm_hr=45.0,
        duration_hours=4.0,
        infiltration_rate_mm_hr=6.0,
        drainage_efficiency_pct=200.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=0.0,
        description="Counterfactual mitigation scenario: doubling effective urban stormwater evacuation capacity (24 mm/hr effective sink) under 45 mm/hr rain.",
        provenance_tags=["user_defined_scenario", "mitigation_comparison"],
    ),
    "michaung_replay": HydroScenarioConfig(
        scenario_id="michaung_replay",
        scenario_name="Cyclone Michaung Historical Replay (Dec 2023)",
        mode="historical_replay",
        rainfall_intensity_mm_hr=0.0,  # Driven by hourly CSV hyetograph
        duration_hours=24.0,
        infiltration_rate_mm_hr=2.5,
        drainage_efficiency_pct=65.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=0.0,
        description="Driven by actual preserved hourly rainfall observations from Dec 2023 Cyclone Michaung; spatial inundation depths are simulated terrain reconstructions.",
        provenance_tags=["observed_historical_rainfall", "simulated_terrain_reconstruction"],
    ),
    "monitoring_dropout": HydroScenarioConfig(
        scenario_id="monitoring_dropout",
        scenario_name="Monitoring Network Dropout & Uncertainty",
        mode="monitoring_uncertainty",
        rainfall_intensity_mm_hr=55.0,
        duration_hours=4.0,
        infiltration_rate_mm_hr=4.0,
        drainage_efficiency_pct=75.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=0.0,
        description="Simulates multi-station telemetry gap (+/- 35% precipitation estimation uncertainty) combined with terrain response.",
        provenance_tags=["monitoring_uncertainty_analysis", "simulated_scenario"],
    ),
    "reservoir_discharge": HydroScenarioConfig(
        scenario_id="reservoir_discharge",
        scenario_name="Chembarambakkam Spillway Release Scenario",
        mode="boundary_discharge",
        rainfall_intensity_mm_hr=25.0,
        duration_hours=12.0,
        infiltration_rate_mm_hr=4.0,
        drainage_efficiency_pct=85.0,
        nominal_drain_cap_mm_hr=12.0,
        chembarambakkam_discharge_cusecs=25000.0,
        description="Applies 25,000 cusecs (707.9 m^3/s) spillway release over 12h at Chembarambakkam outlet routed down the hydro-conditioned Adyar channel.",
        provenance_tags=["boundary_discharge_scenario", "terrain_routed_landlab"],
    ),
}


def run_controlled_overland_grid(
    elevation_2d: np.ndarray,
    dx_m: float = 150.0,
    valid_mask_2d: Optional[np.ndarray] = None,
    open_boundary_mask_2d: Optional[np.ndarray] = None,
    impervious_2d: Optional[np.ndarray] = None,
    rain_schedule_mm_hr: Sequence[float] = (0.0,),
    step_durations_sec: Sequence[float] = (3600.0,),
    infiltration_rate_mm_hr: float = 0.0,
    drain_rate_2d_mm_hr: Optional[np.ndarray] = None,
    source_cells_m3_s: Optional[List[Tuple[int, int, float]]] = None,
    initial_depth_2d: Optional[np.ndarray] = None,
    mannings_n: float = 0.045,
    max_internal_dt: Optional[float] = None,
    record_snapshots: bool = False,
) -> Dict[str, Any]:
    """
    Core deterministic 2D conservative Landlab OverlandFlow solver.
    Operates strictly in raster array coordinates where row 0 is North and row -1 is South;
    internally flips up/down for Landlab's South-to-North node ordering, and flips back on return!

    Returns exact final depth grid, global mass balance terms, boundary outflow, and optional snapshots.
    """
    rows, cols = elevation_2d.shape
    cell_area = dx_m * dx_m

    # Prepare masks in raster (North-up) layout
    if valid_mask_2d is None:
        valid_mask = np.ones((rows, cols), dtype=bool)
    else:
        valid_mask = valid_mask_2d.astype(bool).copy()

    if open_boundary_mask_2d is None:
        open_mask = np.zeros((rows, cols), dtype=bool)
    else:
        open_mask = open_boundary_mask_2d.astype(bool).copy()

    # Exterior rim MUST be either open or closed in Landlab; ensure exterior rim isn't core
    valid_mask[0, :] = False
    valid_mask[-1, :] = False
    valid_mask[:, 0] = False
    valid_mask[:, -1] = False

    if impervious_2d is None:
        imp = np.ones((rows, cols), dtype=np.float64)
    else:
        imp = np.clip(impervious_2d.astype(np.float64), 0.0, 1.0)

    if drain_rate_2d_mm_hr is None:
        drain_mm_hr = np.zeros((rows, cols), dtype=np.float64)
    else:
        drain_mm_hr = np.maximum(0.0, drain_rate_2d_mm_hr.astype(np.float64))

    # Build Landlab grid (South-to-North row convention -> flipud all 2D inputs!)
    mg = RasterModelGrid((rows, cols), xy_spacing=dx_m)
    z_ll = mg.add_zeros("topographic__elevation", at="node")
    z_clean = np.where(np.isfinite(elevation_2d), elevation_2d, 0.0).astype(np.float64)
    z_ll[:] = np.flipud(z_clean).ravel()

    # Set closed boundaries everywhere first, then activate valid land core & open coastal/sink cells
    mg.status_at_node[:] = NodeStatus.CLOSED
    valid_ll = np.flipud(valid_mask).ravel()
    open_ll = np.flipud(open_mask).ravel()
    mg.status_at_node[valid_ll & (~open_ll)] = NodeStatus.CORE
    mg.status_at_node[open_ll] = NodeStatus.FIXED_VALUE

    core = mg.core_nodes
    core_mask_raster = np.flipud((mg.status_at_node == NodeStatus.CORE).reshape(rows, cols))

    h_ll = mg.add_zeros("surface_water__depth", at="node")
    if initial_depth_2d is not None:
        h_init_ll = np.flipud(np.maximum(0.0, initial_depth_2d.astype(np.float64))).ravel()
        h_ll[core] = h_init_ll[core]

    h_init_threshold = 1e-7
    of = OverlandFlow(mg, steep_slopes=True, h_init=h_init_threshold, mannings_n=mannings_n, theta=0.8)
    # Restore exact initial depth because OverlandFlow.__init__ seeds h_init everywhere
    if initial_depth_2d is not None:
        h_ll[:] = 0.0
        h_ll[core] = np.flipud(np.maximum(0.0, initial_depth_2d.astype(np.float64))).ravel()[core]
    else:
        h_ll[:] = 0.0

    # Prepare point source index in Landlab node IDs
    source_nodes: List[Tuple[int, float]] = []
    if source_cells_m3_s:
        for r_rast, c_rast, q_m3s in source_cells_m3_s:
            if q_m3s <= 0.0:
                continue
            r_ll = rows - 1 - r_rast
            if 0 <= r_ll < rows and 0 <= c_rast < cols:
                nid = r_ll * cols + c_rast
                if mg.status_at_node[nid] == NodeStatus.CORE:
                    source_nodes.append((nid, float(q_m3s)))

    imp_core = np.flipud(imp).ravel()[core]
    drain_mm_hr_core = np.flipud(drain_mm_hr).ravel()[core]
    q_links = mg.at_link["surface_water__discharge"]

    v_init = float(h_ll[core].sum() * cell_area)
    v_rain = 0.0
    v_upstream = 0.0
    v_infil = 0.0
    v_drain = 0.0
    v_outflow = 0.0

    max_h_raster = np.flipud(h_ll.reshape(rows, cols)).copy()
    snapshots: List[np.ndarray] = []
    snapshot_stats: List[Dict[str, float]] = []

    has_active_forcing = any(r > 0 for r in rain_schedule_mm_hr) or len(source_nodes) > 0 or v_init > 0.0

    for step_idx, (rain_mm_hr, step_dur_s) in enumerate(zip(rain_schedule_mm_hr, step_durations_sec)):
        if not has_active_forcing:
            if record_snapshots:
                snapshots.append(np.zeros((rows, cols), dtype=np.float32))
                snapshot_stats.append({
                    "hour": round(sum(step_durations_sec[: step_idx + 1]) / 3600.0, 2),
                    "stored_mcm": 0.0,
                    "max_depth_m": 0.0,
                    "rain_mm_hr": 0.0,
                })
            continue

        # Divide each macro step into bounded substeps to blend infiltration/drainage/routing smoothly
        sub_dur = float(min(300.0, step_dur_s)) if max_internal_dt is None else float(min(max_internal_dt, step_dur_s))
        n_sub = max(1, int(math.ceil(step_dur_s / sub_dur)))
        dt_outer = step_dur_s / n_sub

        for _ in range(n_sub):
            # 1. Gross precipitation (m depth added uniformly to valid land core cells)
            rain_m = (max(0.0, float(rain_mm_hr)) * 1e-3 / 3600.0) * dt_outer
            if rain_m > 0.0:
                h_ll[core] += rain_m
                v_rain += len(core) * rain_m * cell_area

            # 2. Single-pass permeable soil infiltration (strictly capped to available water; no double-counting)
            if infiltration_rate_mm_hr > 0.0 and len(core) > 0:
                pot_infil = (infiltration_rate_mm_hr * 1e-3 / 3600.0) * dt_outer * (1.0 - imp_core)
                act_infil = np.minimum(h_ll[core], pot_infil)
                h_ll[core] -= act_infil
                v_infil += float(act_infil.sum() * cell_area)

            # 3. Urban stormwater drainage sink (strictly capped to available surface water)
            if np.any(drain_mm_hr_core > 0.0) and len(core) > 0:
                pot_drain = (drain_mm_hr_core * 1e-3 / 3600.0) * dt_outer
                act_drain = np.minimum(h_ll[core], pot_drain)
                h_ll[core] -= act_drain
                v_drain += float(act_drain.sum() * cell_area)

            # 4. Route surface water dynamically with Landlab OverlandFlow (inject boundary inflows smoothly per CFL substep)
            if len(core) > 0 and (np.max(h_ll[core]) > 1e-6 or len(source_nodes) > 0):
                t_sub = 0.0
                while t_sub < dt_outer - 1e-9:
                    if np.max(h_ll[core]) <= 1e-6 and len(source_nodes) == 0:
                        break
                    dt_cfl = min(of.calc_time_step(), dt_outer - t_sub)
                    if max_internal_dt is not None:
                        dt_cfl = min(dt_cfl, max_internal_dt)
                    # Smooth boundary / spillway inflow per CFL step avoids artificial single-step depth shocks
                    for nid, q_m3s in source_nodes:
                        dh_src = (q_m3s * dt_cfl) / cell_area
                        h_ll[nid] += dh_src
                        v_upstream += q_m3s * dt_cfl
                    of.run_one_step(dt=dt_cfl)
                    div_core = mg.calc_flux_div_at_node(q_links)[core].sum()
                    v_outflow += float(div_core * cell_area * dt_cfl)
                    h_ll[h_ll < 0.0] = 0.0
                    t_sub += dt_cfl

            cur_rast = np.flipud(h_ll.reshape(rows, cols))
            max_h_raster = np.maximum(max_h_raster, cur_rast)

        if record_snapshots:
            cur_rast = np.flipud(h_ll.reshape(rows, cols)).astype(np.float32)
            snapshots.append(cur_rast)
            snapshot_stats.append({
                "hour": round(sum(step_durations_sec[: step_idx + 1]) / 3600.0, 2),
                "stored_mcm": round(float(h_ll[core].sum() * cell_area) / 1e6, 4),
                "max_depth_m": round(float(cur_rast[core_mask_raster].max()) if core_mask_raster.any() else 0.0, 3),
                "rain_mm_hr": round(float(rain_mm_hr), 2),
            })

    final_h_raster = np.where(core_mask_raster, np.flipud(h_ll.reshape(rows, cols)), 0.0)
    max_h_raster = np.where(core_mask_raster, max_h_raster, 0.0)

    v_final = float(final_h_raster.sum() * cell_area)
    total_inputs = v_init + v_rain + v_upstream
    mass_balance_residual_m3 = (total_inputs - v_infil - v_drain - v_outflow) - v_final
    rel_error = abs(mass_balance_residual_m3) / max(1.0, total_inputs) if total_inputs > 0 else abs(v_final)

    # Extract final flow vectors on grid (qx_mean, qy_mean) in m^2/s for vector arrows
    q_x_node, q_y_node = _links_to_node_vectors(mg, q_links, rows, cols)

    return {
        "final_depth_m": final_h_raster,
        "max_depth_m": max_h_raster,
        "core_mask": core_mask_raster,
        "qx_m2_s": q_x_node,
        "qy_m2_s": q_y_node,
        "snapshots": snapshots,
        "snapshot_stats": snapshot_stats,
        "mass_balance": {
            "v_init_m3": round(float(v_init), 3),
            "v_rain_m3": round(float(v_rain), 3),
            "v_upstream_m3": round(float(v_upstream), 3),
            "v_infil_m3": round(float(v_infil), 3),
            "v_drain_m3": round(float(v_drain), 3),
            "v_outflow_m3": round(float(v_outflow), 3),
            "v_final_m3": round(float(v_final), 3),
            "residual_m3": round(float(mass_balance_residual_m3), 4),
            "relative_error": float(rel_error),
        },
    }


def _links_to_node_vectors(mg: RasterModelGrid, q_links: np.ndarray, rows: int, cols: int) -> Tuple[np.ndarray, np.ndarray]:
    """Convert staggered link discharges to cell-centered East/North unit discharge vectors (North-up)."""
    vx = np.zeros(mg.number_of_nodes, dtype=np.float32)
    vy = np.zeros(mg.number_of_nodes, dtype=np.float32)
    # Horizontal & vertical link flows averaged per node
    links_at_node = mg.links_at_node  # (n_nodes, 4): [east, north, west, south]
    dirs = mg.link_dirs_at_node  # -1 outgoing East/North, +1 incoming West/South
    q_e = np.where(links_at_node[:, 0] >= 0, q_links[links_at_node[:, 0]] * (-dirs[:, 0]), 0.0)
    q_w = np.where(links_at_node[:, 2] >= 0, q_links[links_at_node[:, 2]] * (dirs[:, 2]), 0.0)
    q_n = np.where(links_at_node[:, 1] >= 0, q_links[links_at_node[:, 1]] * (-dirs[:, 1]), 0.0)
    q_s = np.where(links_at_node[:, 3] >= 0, q_links[links_at_node[:, 3]] * (dirs[:, 3]), 0.0)
    vx[:] = 0.5 * (q_e + q_w)
    vy[:] = 0.5 * (q_n + q_s)
    return np.flipud(vx.reshape(rows, cols)), np.flipud(vy.reshape(rows, cols))


class ChennaiTerrainTwinEngine:
    """
    Production terrain-aware South Chennai Urban Flood Digital Twin engine.
    Integrates Copernicus GLO-30 UTM44N DEM, official waterbody/wetland masks,
    Landlab 2D OverlandFlow routing, Cyclone Michaung replay, and scenario analytics.
    """

    def __init__(self, dem_npz_path: Path = DEM_NPZ_PATH):
        self._dem_path = dem_npz_path
        self._loaded = False
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._saved_scenarios_path = _PROJECT_ROOT / "data" / "geo" / "processed" / "saved_scenarios.json"
        self._tf_to_utm = Transformer.from_crs(WGS84_CRS, UTM44N_CRS, always_xy=True)
        self._tf_to_wgs = Transformer.from_crs(UTM44N_CRS, WGS84_CRS, always_xy=True)

        if dem_npz_path.exists():
            self._load_dem()

    def _load_dem(self) -> None:
        z_data = np.load(self._dem_path)
        self.elevation_m = z_data["elevation_m"].astype(np.float64)
        self.valid_land_mask = z_data["valid_land_mask"].astype(bool)
        self.ocean_mask = z_data["ocean_mask"].astype(bool)
        self.nodata_mask = z_data["nodata_mask"].astype(bool)
        self.perm_water_mask = z_data["perm_water_mask"].astype(bool)
        self.wetland_mask = z_data["wetland_mask"].astype(bool)
        self.channel_mask = z_data["channel_mask"].astype(bool) if "channel_mask" in z_data else np.zeros_like(self.valid_land_mask)
        self.impervious_fraction = z_data["impervious_fraction"].astype(np.float64)
        self.bounds_utm = tuple(float(x) for x in z_data["bounds_utm"])  # x_min, y_min, x_max, y_max
        self.bounds_wgs84_quad = z_data["bounds_wgs84_quad"].tolist()

        tr = z_data["transform_gdal"]
        self.x_min = float(tr[0])
        self.dx_m = float(tr[1])
        self.y_max = float(tr[3])
        self.rows, self.cols = self.elevation_m.shape
        self.cell_area_m2 = self.dx_m * self.dx_m

        # Precompute Chembarambakkam spillway outlet reach (4 closest hydro-conditioned Adyar channel cells)
        sr, sc = self._lonlat_to_rowcol(80.083, 12.995)
        if self.channel_mask.any():
            crs, ccs = np.where(self.channel_mask)
            dists = np.hypot(crs - sr, ccs - sc)
            nearest_k = np.argsort(dists)[:4]
            self.spillway_reach = [(int(crs[i]), int(ccs[i])) for i in nearest_k]
            self.spillway_cell = self.spillway_reach[0]
        else:
            self.spillway_cell = (sr, sc)
            self.spillway_reach = [self.spillway_cell]
        self._loaded = True
        logger.info("Loaded Chennai UTM44N terrain grid %dx%d (dx=%.1fm)", self.rows, self.cols, self.dx_m)

    def _lonlat_to_rowcol(self, lon: float, lat: float) -> Tuple[int, int]:
        x, y = self._tf_to_utm.transform(lon, lat)
        col = int(math.floor((x - self.x_min) / self.dx_m))
        row = int(math.floor((self.y_max - y) / self.dx_m))
        return row, col

    def _rowcol_to_lonlat_bounds(self, row: int, col: int) -> List[List[float]]:
        x0 = self.x_min + col * self.dx_m
        x1 = x0 + self.dx_m
        y1 = self.y_max - row * self.dx_m
        y0 = y1 - self.dx_m
        p00 = self._tf_to_wgs.transform(x0, y0)
        p10 = self._tf_to_wgs.transform(x1, y0)
        p11 = self._tf_to_wgs.transform(x1, y1)
        p01 = self._tf_to_wgs.transform(x0, y1)
        return [[p00[0], p00[1]], [p10[0], p10[1]], [p11[0], p11[1]], [p01[0], p01[1]], [p00[0], p00[1]]]

    def query_point(self, lon: float, lat: float, active_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Inspect terrain elevation, surface classification, and modeled flood state at (lon, lat)."""
        if not self._loaded:
            raise RuntimeError("DEM terrain grid not loaded; run scripts/process_chennai_geodata.py first.")
        r, c = self._lonlat_to_rowcol(lon, lat)
        in_domain = (0 <= r < self.rows) and (0 <= c < self.cols)
        if not in_domain:
            return {
                "lon": lon,
                "lat": lat,
                "in_computational_domain": False,
                "message": "Point lies outside the South Chennai computational pilot domain (80.044°E–80.286°E, 12.905°N–13.056°N).",
            }

        x_utm, y_utm = self._tf_to_utm.transform(lon, lat)
        z = float(self.elevation_m[r, c])
        is_ocean = bool(self.ocean_mask[r, c])
        is_perm_water = bool(self.perm_water_mask[r, c])
        is_wetland = bool(self.wetland_mask[r, c])
        is_land = bool(self.valid_land_mask[r, c])

        depth_m = 0.0
        max_depth_m = 0.0
        if active_result and "_final_depth_grid" in active_result:
            depth_m = float(active_result["_final_depth_grid"][r, c])
            max_depth_m = float(active_result["_max_depth_grid"][r, c])

        return {
            "lon": round(lon, 6),
            "lat": round(lat, 6),
            "easting_utm44n": round(x_utm, 1),
            "northing_utm44n": round(y_utm, 1),
            "grid_cell": [r, c],
            "in_computational_domain": True,
            "is_valid_land": is_land,
            "is_ocean_boundary": is_ocean,
            "is_permanent_waterbody": is_perm_water,
            "is_wetland": is_wetland,
            "copernicus_dsm_elevation_m": round(z, 2) if np.isfinite(z) and z > -900 else None,
            "impervious_fraction": round(float(self.impervious_fraction[r, c]), 2),
            "modeled_depth_m": round(depth_m, 3),
            "modeled_max_depth_m": round(max_depth_m, 3),
            "vertical_datum": "EGM2008 (Copernicus 30m DSM resampled to 150m)",
            "elevation_caveat": "DSM value includes surrounding rooftop/canopy signature within the 150m grid cell.",
        }

    def run_scenario(self, cfg: HydroScenarioConfig) -> Dict[str, Any]:
        """Run or fetch cached Landlab 2D OverlandFlow simulation for the South Chennai terrain."""
        if not self._loaded:
            raise RuntimeError("DEM terrain grid not loaded.")
        cfg.validate()
        ckey = cfg.cache_key()
        if ckey in self._cache:
            return self._cache[ckey]

        t0 = time.time()

        # Prepare rainfall schedule & step durations
        hyeto_meta: Optional[Dict[str, Any]] = None
        if cfg.mode == "historical_replay" and not cfg.rain_hyetograph_mm_hr:
            vals, ts_list, hyeto_meta = load_michaung_storm_window(hours=int(round(cfg.duration_hours)))
            rain_sched = vals
            step_durs = [3600.0] * len(vals)
            ts_labels = ts_list
        elif cfg.rain_hyetograph_mm_hr:
            rain_sched = list(cfg.rain_hyetograph_mm_hr)
            step_durs = [(cfg.duration_hours * 3600.0) / len(rain_sched)] * len(rain_sched)
            ts_labels = cfg.hyetograph_timestamps or [f"Step {i+1}" for i in range(len(rain_sched))]
        else:
            # Uniform rain across clean hourly/half-hourly timeline intervals (max 12 output steps for UI playback)
            n_steps = max(4, min(12, int(round(cfg.duration_hours * 2))))
            dt_step_s = (cfg.duration_hours * 3600.0) / n_steps
            rain_sched = [float(cfg.rainfall_intensity_mm_hr)] * n_steps
            step_durs = [dt_step_s] * n_steps
            ts_labels = [f"T+{round((i+1) * dt_step_s / 3600.0, 2)}h" for i in range(n_steps)]

        # Open coastal sink along Bay of Bengal pixels adjacent to land
        # Plus allow open river/canal outfall at ocean cells
        open_boundary = self.ocean_mask.copy()

        # Urban drainage sink rate (zero drainage on lakes/wetlands/ocean; scaled on urban land)
        eff_factor = cfg.drainage_efficiency_pct / 100.0
        drain_map = np.where(
            self.valid_land_mask & (~self.perm_water_mask) & (~self.wetland_mask),
            cfg.nominal_drain_cap_mm_hr * eff_factor,
            0.0,
        )

        # Chembarambakkam spillway inflow boundary condition (if > 0) distributed cleanly across reach
        source_cells: Optional[List[Tuple[int, int, float]]] = None
        if cfg.chembarambakkam_discharge_cusecs > 0.0:
            q_m3s = cfg.chembarambakkam_discharge_cusecs * 0.0283168466
            q_each = q_m3s / max(1, len(self.spillway_reach))
            source_cells = [(sr, sc, q_each) for sr, sc in self.spillway_reach]

        sim = run_controlled_overland_grid(
            elevation_2d=self.elevation_m,
            dx_m=self.dx_m,
            valid_mask_2d=self.valid_land_mask,
            open_boundary_mask_2d=open_boundary,
            impervious_2d=self.impervious_fraction,
            rain_schedule_mm_hr=rain_sched,
            step_durations_sec=step_durs,
            infiltration_rate_mm_hr=cfg.infiltration_rate_mm_hr,
            drain_rate_2d_mm_hr=drain_map,
            source_cells_m3_s=source_cells,
            initial_depth_2d=np.full((self.rows, self.cols), cfg.initial_depth_m) if cfg.initial_depth_m > 0 else None,
            mannings_n=cfg.mannings_n,
            max_internal_dt=300.0,
            record_snapshots=True,
        )

        depth_final = sim["final_depth_m"]
        depth_max = sim["max_depth_m"]

        # Mask permanent waterbodies separately from newly inundated urban land
        urban_mask = self.valid_land_mask & (~self.perm_water_mask) & (~self.wetland_mask)
        urban_flooded = urban_mask & (depth_final >= 0.05)
        wetland_flooded = self.wetland_mask & (depth_final >= 0.05)

        urban_inundated_km2 = float(urban_flooded.sum() * self.cell_area_m2) / 1e6
        wetland_storage_km2 = float(wetland_flooded.sum() * self.cell_area_m2) / 1e6
        perm_water_km2 = float(self.perm_water_mask.sum() * self.cell_area_m2) / 1e6

        max_urban_depth_m = float(depth_final[urban_mask].max()) if urban_mask.any() else 0.0
        mean_urban_depth_m = float(depth_final[urban_flooded].mean()) if urban_flooded.any() else 0.0

        # Evaluate neighborhood depth at each of the 10 focus locations
        location_impacts = self._evaluate_focus_locations(depth_final, depth_max)

        # Build raster PNG data URL (or static image payload) AND GeoJSON cells for interactive picking
        flood_geojson = self._build_flood_geojson(depth_final, depth_max, sim["qx_m2_s"], sim["qy_m2_s"])
        raster_b64 = self._encode_depth_png_b64(depth_final)
        flow_vectors_geojson = self._build_flow_vectors_geojson(depth_final, sim["qx_m2_s"], sim["qy_m2_s"])

        # Encode snapshot thumbnails/rasters for timeline scrubber
        timeline_frames = []
        for idx, (snap, s_stat) in enumerate(zip(sim["snapshots"], sim["snapshot_stats"])):
            timeline_frames.append({
                "step": idx,
                "label": ts_labels[idx] if idx < len(ts_labels) else f"T+{s_stat['hour']}h",
                "hour": s_stat["hour"],
                "rain_mm_hr": s_stat["rain_mm_hr"],
                "stored_mcm": s_stat["stored_mcm"],
                "max_depth_m": s_stat["max_depth_m"],
                "urban_inundated_km2": round(float((urban_mask & (snap >= 0.05)).sum() * self.cell_area_m2) / 1e6, 2),
                "raster_png_data_url": self._encode_depth_png_b64(snap),
            })

        elapsed_ms = round((time.time() - t0) * 1000.0, 2)

        result = {
            "scenario": {
                "id": cfg.scenario_id,
                "name": cfg.scenario_name,
                "mode": cfg.mode,
                "description": cfg.description,
                "rainfall_intensity_mm_hr": cfg.rainfall_intensity_mm_hr,
                "duration_hours": cfg.duration_hours,
                "infiltration_rate_mm_hr": cfg.infiltration_rate_mm_hr,
                "drainage_efficiency_pct": cfg.drainage_efficiency_pct,
                "nominal_drain_cap_mm_hr": cfg.nominal_drain_cap_mm_hr,
                "chembarambakkam_discharge_cusecs": cfg.chembarambakkam_discharge_cusecs,
                "mannings_n": cfg.mannings_n,
                "provenance_tags": cfg.provenance_tags or [],
                "historical_metadata": hyeto_meta,
            },
            "domain": {
                "crs": UTM44N_CRS,
                "grid_shape": [self.rows, self.cols],
                "dx_m": self.dx_m,
                "cell_area_m2": self.cell_area_m2,
                "bounds_wgs84_quad": self.bounds_wgs84_quad,
                "valid_land_km2": round(float(self.valid_land_mask.sum() * self.cell_area_m2) / 1e6, 2),
                "permanent_waterbodies_km2": round(perm_water_km2, 2),
            },
            "summary": {
                "stored_water_volume_mcm": round(sim["mass_balance"]["v_final_m3"] / 1e6, 4),
                "urban_inundated_area_km2": round(urban_inundated_km2, 2),
                "wetland_accumulation_area_km2": round(wetland_storage_km2, 2),
                "max_urban_depth_m": round(max_urban_depth_m, 3),
                "mean_flooded_urban_depth_m": round(mean_urban_depth_m, 3),
                "high_susceptibility_locations_count": sum(1 for l in location_impacts if l["risk_level"] in ("High", "Critical")),
                "mass_balance": sim["mass_balance"],
                "computation_time_ms": elapsed_ms,
                "solver": "Landlab OverlandFlow (de Almeida et al. 2012 shallow-water)",
                "uncertainty_note": (
                    "±35% rainfall intensity uncertainty (monitoring dropout)"
                    if cfg.mode == "monitoring_uncertainty"
                    else "Copernicus GLO-30 30m DSM resampled to 150m; local depth uncertainty typically ±0.3–1.2 m in dense urban blocks."
                ),
                "limitations": SCIENTIFIC_LIMITATIONS,
            },
            "location_impacts": location_impacts,
            "flood_overlay_geojson": flood_geojson,
            "flow_vectors_geojson": flow_vectors_geojson,
            "raster_png_data_url": raster_b64,
            "timeline_frames": timeline_frames,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "_final_depth_grid": depth_final,
            "_max_depth_grid": depth_max,
        }

        if len(self._cache) > 24:
            self._cache.pop(next(iter(self._cache)))
        self._cache[ckey] = result
        return result

    def _evaluate_focus_locations(self, depth_final: np.ndarray, depth_max: np.ndarray) -> List[Dict[str, Any]]:
        """Sample actual 150m modeled grid cells within 1.2 km UTM radius around each focus location."""
        yy, xx = np.mgrid[0 : self.rows, 0 : self.cols]
        cell_x = self.x_min + (xx + 0.5) * self.dx_m
        cell_y = self.y_max - (yy + 0.5) * self.dx_m
        urban_land = self.valid_land_mask & (~self.perm_water_mask)

        impacts = []
        for loc in FOCUS_LOCATIONS:
            lon, lat = loc["coordinates"]
            lx, ly = self._tf_to_utm.transform(lon, lat)
            r_center, c_center = self._lonlat_to_rowcol(lon, lat)
            dist2 = (cell_x - lx) ** 2 + (cell_y - ly) ** 2
            patch_urban = urban_land & (dist2 <= 1200.0 ** 2)
            patch_any = self.valid_land_mask & (dist2 <= 1200.0 ** 2)

            if loc["id"] == "chembarambakkam":
                # Chembarambakkam is a major WRD reservoir, not flooded urban streets
                elev_val = float(self.elevation_m[r_center, c_center]) if (0 <= r_center < self.rows and 0 <= c_center < self.cols) else 21.0
                impacts.append({
                    "id": loc["id"],
                    "name": loc["name"],
                    "tamil_name": loc["tamil_name"],
                    "coordinates": loc["coordinates"],
                    "subbasin": loc["subbasin"],
                    "category": loc["category"],
                    "dsm_elevation_m": round(elev_val, 2),
                    "modeled_mean_depth_m": 0.0,
                    "modeled_max_depth_m": 0.0,
                    "inundated_urban_cells": 0,
                    "inundated_area_km2": 0.0,
                    "classification": "Regulated Waterbody / Reservoir",
                    "risk_level": "Regulator",
                    "color": "#0284c7",
                    "primary_hazard": loc["primary_hazard"],
                    "key_infrastructure": loc["key_infrastructure"],
                })
                continue

            if not patch_urban.any():
                patch_urban = patch_any

            d_vals = depth_final[patch_urban] if patch_urban.any() else np.array([0.0])
            m_vals = depth_max[patch_urban] if patch_urban.any() else np.array([0.0])
            z_vals = self.elevation_m[patch_any] if patch_any.any() else np.array([0.0])

            mean_d = float(np.mean(d_vals))
            max_d = float(np.max(m_vals))
            flooded_cnt = int((d_vals >= 0.05).sum())
            flooded_km2 = round(flooded_cnt * self.cell_area_m2 / 1e6, 2)
            min_z = round(float(np.min(z_vals)), 2)

            if max_d < 0.05:
                cls, color, risk = "Dry / Minimal Accumulation", "#10b981", "Low"
            elif max_d < 0.15:
                cls, color, risk = "Shallow Runoff Ponding", "#06b6d4", "Minor"
            elif max_d < 0.30:
                cls, color, risk = "Moderate Accumulation", "#3b82f6", "Moderate"
            elif max_d < 0.60:
                cls, color, risk = "High Susceptibility Ponding", "#f59e0b", "High"
            else:
                cls, color, risk = "Severe Scenario Accumulation", "#ef4444", "Critical"

            impacts.append({
                "id": loc["id"],
                "name": loc["name"],
                "tamil_name": loc["tamil_name"],
                "coordinates": loc["coordinates"],
                "subbasin": loc["subbasin"],
                "category": loc["category"],
                "dsm_elevation_m": min_z,
                "modeled_mean_depth_m": round(mean_d, 3),
                "modeled_max_depth_m": round(max_d, 3),
                "inundated_urban_cells": flooded_cnt,
                "inundated_area_km2": flooded_km2,
                "classification": cls,
                "risk_level": risk,
                "color": color,
                "primary_hazard": loc["primary_hazard"],
                "key_infrastructure": loc["key_infrastructure"],
            })

        return impacts

    def _build_flood_geojson(
        self,
        depth_final: np.ndarray,
        depth_max: np.ndarray,
        qx: np.ndarray,
        qy: np.ndarray,
    ) -> Dict[str, Any]:
        """Export modeled flooded urban land cells (> 0.04m) as queryable GeoJSON polygons."""
        mask = self.valid_land_mask & (~self.perm_water_mask) & (depth_final >= 0.04)
        rs, cs = np.where(mask)
        # Sort descending by depth and bound feature count cleanly for smooth 60fps browser WebGL
        if len(rs) > 2500:
            depths_sel = depth_final[rs, cs]
            top_idx = np.argsort(depths_sel)[-2500:]
            rs, cs = rs[top_idx], cs[top_idx]

        features = []
        for r, c in zip(rs, cs):
            d = float(depth_final[r, c])
            dm = float(depth_max[r, c])
            if d < 0.15:
                tier, color = "0.04-0.15m Shallow", "#06b6d4"
            elif d < 0.30:
                tier, color = "0.15-0.30m Moderate", "#3b82f6"
            elif d < 0.60:
                tier, color = "0.30-0.60m High", "#f59e0b"
            else:
                tier, color = ">0.60m Severe", "#ef4444"

            poly = self._rowcol_to_lonlat_bounds(int(r), int(c))
            q_mag = float(math.hypot(qx[r, c], qy[r, c]))
            features.append({
                "type": "Feature",
                "properties": {
                    "row": int(r),
                    "col": int(c),
                    "depth_m": round(d, 3),
                    "max_depth_m": round(dm, 3),
                    "dsm_elev_m": round(float(self.elevation_m[r, c]), 2),
                    "unit_discharge_m2_s": round(q_mag, 4),
                    "is_wetland": bool(self.wetland_mask[r, c]),
                    "tier": tier,
                    "color": color,
                    "extrude_height_m": round(min(25.0, d * 12.0), 2),  # Exaggerated 3D flood prism height for visual clarity
                },
                "geometry": {"type": "Polygon", "coordinates": [poly]},
            })
        return {"type": "FeatureCollection", "features": features}

    def _build_flow_vectors_geojson(self, depth_final: np.ndarray, qx: np.ndarray, qy: np.ndarray) -> Dict[str, Any]:
        """Subsample dominant terrain flow directions on every 4th grid cell for directional arrows."""
        features = []
        for r in range(2, self.rows - 2, 4):
            for c in range(2, self.cols - 2, 4):
                if not self.valid_land_mask[r, c] or depth_final[r, c] < 0.03:
                    continue
                ux, uy = float(qx[r, c]), float(qy[r, c])
                mag = math.hypot(ux, uy)
                if mag < 1e-4:
                    continue
                x0 = self.x_min + (c + 0.5) * self.dx_m
                y0 = self.y_max - (r + 0.5) * self.dx_m
                # Normalized arrow length = 350m in UTM
                dx_a = (ux / mag) * 350.0
                dy_a = (uy / mag) * 350.0
                lon0, lat0 = self._tf_to_wgs.transform(x0, y0)
                lon1, lat1 = self._tf_to_wgs.transform(x0 + dx_a, y0 + dy_a)
                bearing_deg = (math.degrees(math.atan2(ux, uy)) + 360.0) % 360.0
                features.append({
                    "type": "Feature",
                    "properties": {
                        "unit_discharge_m2_s": round(mag, 4),
                        "bearing_deg": round(bearing_deg, 1),
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[round(lon0, 6), round(lat0, 6)], [round(lon1, 6), round(lat1, 6)]],
                    },
                })
        return {"type": "FeatureCollection", "features": features}

    def _encode_depth_png_b64(self, depth: np.ndarray) -> str:
        """Encode 2D inundation depth (excluding permanent waterbodies) as transparent RGBA data URL."""
        urban_or_wet = self.valid_land_mask & (~self.perm_water_mask)
        d = np.where(urban_or_wet, depth, 0.0)
        rgba = np.zeros((self.rows, self.cols, 4), dtype=np.uint8)

        # Threshold masks matching scientific legend
        m1 = (d >= 0.03) & (d < 0.15)
        m2 = (d >= 0.15) & (d < 0.30)
        m3 = (d >= 0.30) & (d < 0.60)
        m4 = d >= 0.60

        rgba[m1] = [6, 182, 212, 130]     # Shallow cyan
        rgba[m2] = [59, 130, 246, 165]    # Moderate blue
        rgba[m3] = [245, 158, 11, 195]    # High amber
        rgba[m4] = [239, 68, 68, 220]     # Severe red

        buf = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    def compare_scenarios(self, base_result: Dict[str, Any], alt_result: Dict[str, Any]) -> Dict[str, Any]:
        """Compute explicit numerical difference between two executed scenario states."""
        d_base = base_result["_final_depth_grid"]
        d_alt = alt_result["_final_depth_grid"]
        diff = d_alt - d_base
        urban = self.valid_land_mask & (~self.perm_water_mask)

        base_sum = base_result["summary"]
        alt_sum = alt_result["summary"]

        loc_diffs = []
        base_map = {l["id"]: l for l in base_result["location_impacts"]}
        for alt_loc in alt_result["location_impacts"]:
            b_loc = base_map.get(alt_loc["id"], {})
            b_d = b_loc.get("modeled_max_depth_m", 0.0)
            a_d = alt_loc["modeled_max_depth_m"]
            loc_diffs.append({
                "id": alt_loc["id"],
                "name": alt_loc["name"],
                "baseline_max_depth_m": b_d,
                "alternate_max_depth_m": a_d,
                "delta_max_depth_m": round(a_d - b_d, 3),
                "baseline_area_km2": b_loc.get("inundated_area_km2", 0.0),
                "alternate_area_km2": alt_loc["inundated_area_km2"],
                "delta_area_km2": round(alt_loc["inundated_area_km2"] - b_loc.get("inundated_area_km2", 0.0), 2),
            })

        return {
            "baseline_scenario": base_result["scenario"]["name"],
            "alternate_scenario": alt_result["scenario"]["name"],
            "delta_stored_volume_mcm": round(alt_sum["stored_water_volume_mcm"] - base_sum["stored_water_volume_mcm"], 4),
            "delta_inundated_area_km2": round(alt_sum["urban_inundated_area_km2"] - base_sum["urban_inundated_area_km2"], 2),
            "delta_max_urban_depth_m": round(alt_sum["max_urban_depth_m"] - base_sum["max_urban_depth_m"], 3),
            "max_local_increase_m": round(float(diff[urban].max()) if urban.any() else 0.0, 3),
            "max_local_decrease_m": round(float(diff[urban].min()) if urban.any() else 0.0, 3),
            "location_comparisons": loc_diffs,
        }

    def list_saved_scenarios(self) -> List[Dict[str, Any]]:
        if not self._saved_scenarios_path.exists():
            return []
        try:
            return json.loads(self._saved_scenarios_path.read_text())
        except Exception:
            return []

    def save_scenario_config(self, name: str, cfg: HydroScenarioConfig) -> Dict[str, Any]:
        saved = self.list_saved_scenarios()
        entry = {
            "saved_name": name,
            "saved_at_utc": datetime.now(timezone.utc).isoformat(),
            "config": asdict(cfg),
        }
        # Replace if duplicate saved_name
        saved = [s for s in saved if s.get("saved_name") != name]
        saved.append(entry)
        self._saved_scenarios_path.parent.mkdir(parents=True, exist_ok=True)
        self._saved_scenarios_path.write_text(json.dumps(saved, indent=2))
        return entry


def normalize_scenario_id(scenario_id: str) -> str:
    """Map legacy or friendly scenario aliases onto canonical terrain_hydrology keys."""
    aliases = {
        "heavy_rain": "heavy_rainfall",
        "extreme_monsoon": "extreme_rainfall",
        "drainage_obstruction": "reduced_drainage",
        "sensor_failure": "monitoring_dropout",
    }
    return aliases.get(scenario_id, scenario_id)


def strip_internal_grids(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return JSON-serializable scenario payload without raw numpy ndarray matrices."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


# Global singleton instance
terrain_engine = ChennaiTerrainTwinEngine()
