"""
CivicTwin-R — Urban Hydrological Screening & Scenario Planning Model
Implements a mass-balance, terrain-aware screening model for Chennai sub-catchments.

Governing Equation:
  dV/dt = Q_rain + Q_upstream - Q_drain - Q_infil

Where:
  Q_rain     = P_rain (mm/hr) * 1e-3 * Area (m^2) * C_runoff (m^3/hr)
  Q_infil    = I_infil (mm/hr) * 1e-3 * Area (m^2) * (1 - C_runoff) (m^3/hr)
  Q_drain    = Q_drain_nominal * (drainage_capacity_pct / 100) (m^3/hr)
  Q_upstream = Upstream contributing discharge (e.g. Chembarambakkam sluice release)

Water depth h (m) is derived from accumulated volume over topographic depression storage.
"""

from __future__ import annotations
import math
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from digital_twin.chennai_geo_data import (
    CHENNAI_LOCATIONS,
    CHENNAI_RESERVOIRS,
    RAINFALL_STATIONS,
    WATERWAYS_GEOJSON,
    CATCHMENTS_GEOJSON,
)


@dataclass
class UrbanScenarioParams:
    scenario_id: str
    scenario_name: str
    rainfall_intensity_mm_hr: float
    duration_hours: float
    runoff_coefficient: float
    drainage_capacity_pct: float
    infiltration_rate_mm_hr: float
    chembarambakkam_discharge_cusecs: float
    description: str


PREDEFINED_SCENARIOS: Dict[str, UrbanScenarioParams] = {
    "normal": UrbanScenarioParams(
        scenario_id="normal",
        scenario_name="Normal Baseline Conditions",
        rainfall_intensity_mm_hr=0.0,
        duration_hours=1.0,
        runoff_coefficient=0.75,
        drainage_capacity_pct=100.0,
        infiltration_rate_mm_hr=8.0,
        chembarambakkam_discharge_cusecs=250.0,
        description="Dry weather baseline with fully operational drainage and nominal river baseflow.",
    ),
    "heavy_rain": UrbanScenarioParams(
        scenario_id="heavy_rain",
        scenario_name="Heavy Monsoon Rainfall",
        rainfall_intensity_mm_hr=45.0,
        duration_hours=4.0,
        runoff_coefficient=0.82,
        drainage_capacity_pct=85.0,
        infiltration_rate_mm_hr=4.0,
        chembarambakkam_discharge_cusecs=3500.0,
        description="Typical Northeast Monsoon intense convective downpour leading to localized curb ponding.",
    ),
    "extreme_monsoon": UrbanScenarioParams(
        scenario_id="extreme_monsoon",
        scenario_name="Extreme Cyclonic Downpour",
        rainfall_intensity_mm_hr=85.0,
        duration_hours=8.0,
        runoff_coefficient=0.90,
        drainage_capacity_pct=65.0,
        infiltration_rate_mm_hr=2.0,
        chembarambakkam_discharge_cusecs=15000.0,
        description="Severe cyclonic storm causing significant surface waterlogging and Adyar River bank fullness.",
    ),
    "drainage_obstruction": UrbanScenarioParams(
        scenario_id="drainage_obstruction",
        scenario_name="Drainage & Canal Obstruction",
        rainfall_intensity_mm_hr=50.0,
        duration_hours=6.0,
        runoff_coefficient=0.85,
        drainage_capacity_pct=25.0,
        infiltration_rate_mm_hr=3.0,
        chembarambakkam_discharge_cusecs=4000.0,
        description="Buckingham Canal and Okkiyam Maduvu choked with solid debris; drainage efficiency cut by 75%.",
    ),
    "reservoir_discharge": UrbanScenarioParams(
        scenario_id="reservoir_discharge",
        scenario_name="Chembarambakkam Sluice Surge",
        rainfall_intensity_mm_hr=35.0,
        duration_hours=6.0,
        runoff_coefficient=0.80,
        drainage_capacity_pct=75.0,
        infiltration_rate_mm_hr=3.0,
        chembarambakkam_discharge_cusecs=25000.0,
        description="Emergency surplus discharge from Chembarambakkam Reservoir into Adyar River corridor.",
    ),
    "michaung_replay": UrbanScenarioParams(
        scenario_id="michaung_replay",
        scenario_name="Cyclone Michaung Dec 2023 Storm Replay",
        rainfall_intensity_mm_hr=68.5,
        duration_hours=12.0,
        runoff_coefficient=0.92,
        drainage_capacity_pct=50.0,
        infiltration_rate_mm_hr=1.5,
        chembarambakkam_discharge_cusecs=18000.0,
        description="Historical reconstruction of the Dec 3-4, 2023 cyclonic storm with saturated catchment conditions.",
    ),
    "sensor_failure": UrbanScenarioParams(
        scenario_id="sensor_failure",
        scenario_name="Monitoring Network Dropout",
        rainfall_intensity_mm_hr=55.0,
        duration_hours=4.0,
        runoff_coefficient=0.85,
        drainage_capacity_pct=80.0,
        infiltration_rate_mm_hr=3.0,
        chembarambakkam_discharge_cusecs=5000.0,
        description="Telemetry dropouts simulated at 4 stations, demonstrating uncertainty bounds and digital twin recovery.",
    ),
}


class ChennaiUrbanHydrologyEngine:
    """Terrain-aware hydrological mass-balance screening model for Chennai."""

    def __init__(self):
        self._locations = {loc["id"]: dict(loc) for loc in CHENNAI_LOCATIONS}
        self._reservoirs = {r["tank_id"]: dict(r) for r in CHENNAI_RESERVOIRS}
        self._active_scenario: UrbanScenarioParams = PREDEFINED_SCENARIOS["normal"]
        self._cached_results: Dict[str, Any] = {}

    def get_locations(self) -> List[Dict[str, Any]]:
        return list(self._locations.values())

    def get_location_by_id(self, loc_id: str) -> Optional[Dict[str, Any]]:
        return self._locations.get(loc_id)

    def get_rainfall_stations(self) -> List[Dict[str, Any]]:
        return RAINFALL_STATIONS

    def get_reservoirs(self) -> List[Dict[str, Any]]:
        return list(self._reservoirs.values())

    def run_scenario(self, params: UrbanScenarioParams) -> Dict[str, Any]:
        """
        Executes hydrological mass-balance screening model across Chennai's sub-basins.
        Returns calculated water volume, estimated inundation depth, location impacts, and GeoJSON overlays.
        """
        self._active_scenario = params
        t0 = time.time()

        # Unit conversions
        # P_rain: mm/hr -> m/hr = P * 1e-3
        p_rain_m_hr = params.rainfall_intensity_mm_hr * 1e-3
        infil_m_hr = params.infiltration_rate_mm_hr * 1e-3
        drain_factor = max(0.05, min(1.0, params.drainage_capacity_pct / 100.0))
        duration = max(0.5, float(params.duration_hours))

        # Chembarambakkam discharge: cusecs -> m^3/hr
        # 1 cusec = 0.0283168 m^3/s = 101.94 m^3/hr
        chembarambakkam_q_m3_hr = params.chembarambakkam_discharge_cusecs * 101.9406

        total_volume_m3 = 0.0
        total_inundated_area_km2 = 0.0
        location_impacts: List[Dict[str, Any]] = []
        flood_polygons_features: List[Dict[str, Any]] = []

        # Iterate over each Chennai focus location
        for loc_id, loc in self._locations.items():
            area_m2 = loc["area_km2"] * 1e6
            c_eff = params.runoff_coefficient if params.runoff_coefficient > 0 else loc["runoff_coefficient"]
            elev = loc["elevation_m"]

            # Topographic depression fraction & drainage coefficient based on elevation
            # Saucer bowls (Pallikaranai at 3.1m, Madipakkam at 5.4m, Velachery at 6.2m) collect water
            if elev < 5.0:
                f_depression = 0.35
                f_drain_rate = 0.40  # Flat terrain drains slowly
                upstream_contribution_pct = 0.30  # Receives cascading water
            elif elev < 10.0:
                f_depression = 0.25
                f_drain_rate = 0.65
                upstream_contribution_pct = 0.15
            elif elev < 20.0:
                f_depression = 0.15
                f_drain_rate = 0.85
                upstream_contribution_pct = 0.05
            else:
                f_depression = 0.10
                f_drain_rate = 0.95
                upstream_contribution_pct = 0.00

            # Mass Balance Rates (m^3 / hr)
            q_rain = p_rain_m_hr * area_m2 * c_eff
            q_infil = infil_m_hr * area_m2 * (1.0 - c_eff)

            # Nominal drainage capacity (m^3/hr) scaled by drainage effectiveness
            q_drain_nominal = area_m2 * 0.008 * f_drain_rate  # 8mm/hr nominal design storm drainage
            q_drain = q_drain_nominal * drain_factor

            # Upstream flume additions (e.g. Chembarambakkam adds to Adyar river corridor)
            q_upstream = 0.0
            if loc_id in ["saidapet", "adyar", "porur"]:
                q_upstream = chembarambakkam_q_m3_hr * (0.60 if loc_id == "saidapet" else 0.40)
            elif loc_id in ["pallikaranai", "velachery", "madipakkam"]:
                # Pallikaranai marsh receives cascading runoff from southern catchments
                q_upstream = (p_rain_m_hr * 40e6 * 0.70) * upstream_contribution_pct

            # Net accumulation rate (m^3 / hr)
            net_rate_m3_hr = max(0.0, (q_rain + q_upstream) - (q_drain + q_infil))
            accumulated_volume_m3 = net_rate_m3_hr * duration

            # Water depth over depression area
            depression_area_m2 = area_m2 * f_depression
            estimated_depth_m = accumulated_volume_m3 / depression_area_m2 if depression_area_m2 > 0 else 0.0

            # Special case for normal baseline
            if params.rainfall_intensity_mm_hr <= 0.0 and params.chembarambakkam_discharge_cusecs <= 500:
                estimated_depth_m = 0.0
                accumulated_volume_m3 = 0.0

            # Severity Classification
            if estimated_depth_m < 0.05:
                classification = "Normal / Dry"
                color = "#10b981"  # Emerald Green
                risk_level = "Low"
            elif estimated_depth_m < 0.15:
                classification = "Shallow Waterlogging"
                color = "#06b6d4"  # Cyan
                risk_level = "Minor"
            elif estimated_depth_m < 0.30:
                classification = "Moderate Curb Ponding"
                color = "#3b82f6"  # Blue
                risk_level = "Moderate"
            elif estimated_depth_m < 0.60:
                classification = "High Street Inundation"
                color = "#f59e0b"  # Amber
                risk_level = "High"
            else:
                classification = "Severe Ground-Floor Inundation"
                color = "#ef4444"  # Red
                risk_level = "Critical"

            loc_inundated_km2 = (loc["area_km2"] * f_depression) if estimated_depth_m > 0.05 else 0.0
            total_volume_m3 += accumulated_volume_m3
            total_inundated_area_km2 += loc_inundated_km2

            loc_summary = {
                "id": loc_id,
                "name": loc["name"],
                "coordinates": loc["coordinates"],
                "elevation_m": elev,
                "estimated_depth_m": round(estimated_depth_m, 2),
                "estimated_depth_cm": round(estimated_depth_m * 100.0, 1),
                "classification": classification,
                "risk_level": risk_level,
                "color": color,
                "accumulated_volume_mcm": round(accumulated_volume_m3 / 1e6, 3),
                "inundated_area_km2": round(loc_inundated_km2, 2),
                "affected_population_estimate": int(loc["population_estimate"] * min(1.0, estimated_depth_m / 0.8)) if estimated_depth_m > 0.1 else 0,
                "drainage_status": f"{int(params.drainage_capacity_pct)}% capacity",
            }
            location_impacts.append(loc_summary)

            # Generate geo-polygon for visualization if inundated
            if estimated_depth_m > 0.02:
                lon, lat = loc["coordinates"]
                # Create a local bounding box around the center
                delta = 0.008 + (loc["area_km2"] * 0.0003)
                poly_coords = [
                    [
                        [lon - delta, lat - delta],
                        [lon + delta, lat - delta],
                        [lon + delta, lat + delta],
                        [lon - delta, lat + delta],
                        [lon - delta, lat - delta],
                    ]
                ]
                flood_polygons_features.append({
                    "type": "Feature",
                    "properties": {
                        "location_id": loc_id,
                        "location_name": loc["name"],
                        "depth_m": round(estimated_depth_m, 2),
                        "classification": classification,
                        "color": color,
                        "fill_opacity": min(0.75, 0.25 + (estimated_depth_m / 1.5) * 0.5),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": poly_coords,
                    },
                })

        computation_time_ms = round((time.time() - t0) * 1000, 2)

        result = {
            "scenario": {
                "id": params.scenario_id,
                "name": params.scenario_name,
                "description": params.description,
                "rainfall_intensity_mm_hr": params.rainfall_intensity_mm_hr,
                "duration_hours": params.duration_hours,
                "runoff_coefficient": params.runoff_coefficient,
                "drainage_capacity_pct": params.drainage_capacity_pct,
                "infiltration_rate_mm_hr": params.infiltration_rate_mm_hr,
                "chembarambakkam_discharge_cusecs": params.chembarambakkam_discharge_cusecs,
            },
            "summary": {
                "total_accumulated_volume_mcm": round(total_volume_m3 / 1e6, 3),
                "total_inundated_area_km2": round(total_inundated_area_km2, 2),
                "high_risk_locations_count": sum(1 for l in location_impacts if l["risk_level"] in ["High", "Critical"]),
                "max_depth_m": max((l["estimated_depth_m"] for l in location_impacts), default=0.0),
                "computation_time_ms": computation_time_ms,
                "provenance": "SIMULATED_SCREENING_MODEL",
                "scientific_caveat": "Mass-balance terrain depression screening approximation; not a 2D Navier-Stokes/SWMM solver.",
            },
            "location_impacts": location_impacts,
            "flood_overlay_geojson": {
                "type": "FeatureCollection",
                "features": flood_polygons_features,
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        self._cached_results[params.scenario_id] = result
        return result


# Global singleton instance
urban_engine = ChennaiUrbanHydrologyEngine()
