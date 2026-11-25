"""
CivicTwin-R — Comprehensive Verification Suite for Final Release Modules

Tests:
  1. SpatialExposureEngine controlled synthetic geometry intersections in EPSG:32644:
       - Partial building intersection, zero duplicate counting across cells
       - Multi-cell road projected length calculation without duplication
       - Self-intersecting invalid polygon repair (make_valid)
       - Out-of-domain exclusion & configurable depth thresholds
  2. Real Chennai Infrastructure & Official Boundary (Watersheds / GCC Wards) consistency.
  3. Copernicus 3D Terrarium elevation RGB tile generation & decoding verification.
  4. Tank MAE discrepancy audit fix (`evaluate_telemetry_window`) across gaps & piecewise inflow.
  5. Bounded parameter sensitivity, scenario CRUD, zero-safe compare, & offline PDF/CSV reports.
  6. Export filename sanitization against path/CRLF injection.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.main import app, _safe_filename_slug
from digital_twin.exposure_engine import SpatialExposureEngine
from digital_twin.tank_twin import (
    PhysicalTankModel,
    TankGeometry,
    evaluate_telemetry_window,
)


def _box_wgs84(tf_to_wgs, x0: float, y0: float, x1: float, y1: float) -> dict:
    p00 = list(tf_to_wgs.transform(x0, y0))
    p10 = list(tf_to_wgs.transform(x1, y0))
    p11 = list(tf_to_wgs.transform(x1, y1))
    p01 = list(tf_to_wgs.transform(x0, y1))
    return {"type": "Polygon", "coordinates": [[p00, p10, p11, p01, p00]]}


class TestSyntheticSpatialExposure:
    """Deterministic EPSG:32644 geometry checks against analytical intersection expectations."""

    @pytest.fixture
    def synthetic_engine(self):
        # 2x2 grid in UTM 44N around South Chennai, 150 m per cell
        x_min = 410000.0
        y_max = 1436000.0
        dx = 150.0
        tf_wgs = Transformer.from_crs("EPSG:32644", "EPSG:4326", always_xy=True)

        # Row 0: [410000..410150, 410150..410300] x [1435850..1436000]
        # Row 1: [410000..410150, 410150..410300] x [1435700..1435850]
        b1_geom = _box_wgs84(tf_wgs, 410100.0, 1435900.0, 410200.0, 1435950.0)  # 100m x 50m = 5000m2 spanning (0,0) and (0,1) evenly!
        b2_outside = _box_wgs84(tf_wgs, 411000.0, 1436500.0, 411050.0, 1436550.0)  # strictly outside 2x2 grid

        # Self-intersecting bowtie polygon inside (0,1): valid area = two triangles = 2 * 0.5 * 40 * 20? Using [x,y] coordinates
        p_a = list(tf_wgs.transform(410170.0, 1435900.0))
        p_b = list(tf_wgs.transform(410210.0, 1435940.0))
        p_c = list(tf_wgs.transform(410210.0, 1435900.0))
        p_d = list(tf_wgs.transform(410170.0, 1435940.0))
        b3_invalid = {"type": "Polygon", "coordinates": [[p_a, p_b, p_c, p_d, p_a]]}

        # Road crossing cells (1,0) and (1,1): 100 m in cell (1,0) + 100 m in cell (1,1) = 200 m
        r0 = list(tf_wgs.transform(410050.0, 1435775.0))
        r1 = list(tf_wgs.transform(410250.0, 1435775.0))
        roads_gj = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"osm_id": 1001, "name": "Test Ave", "highway": "primary"}, "geometry": {"type": "LineString", "coordinates": [r0, r1]}},
                # Duplicate osm_id must NEVER double count
                {"type": "Feature", "properties": {"osm_id": 1001, "name": "Test Ave", "highway": "primary"}, "geometry": {"type": "LineString", "coordinates": [r0, r1]}},
            ],
        }
        bldgs_gj = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"osm_id": 1, "building_type": "hospital", "name": "Clinic One"}, "geometry": b1_geom},
                {"type": "Feature", "properties": {"osm_id": 2, "building_type": "house", "name": "Outside Villa"}, "geometry": b2_outside},
                {"type": "Feature", "properties": {"osm_id": 3, "building_type": "school", "name": "Bowtie School"}, "geometry": b3_invalid},
            ],
        }
        wards_gj = {
            "type": "FeatureCollection",
            "features": [
                # Partially inside [410150..410450, 1435700..1436000]: 50% inside right column of grid!
                {"type": "Feature", "properties": {"id": 1, "zone_": 13, "ward": 175}, "geometry": _box_wgs84(tf_wgs, 410150.0, 1435700.0, 410450.0, 1436000.0)},
            ],
        }

        eng = SpatialExposureEngine(
            rows=2,
            cols=2,
            x_min=x_min,
            y_max=y_max,
            dx_m=dx,
            valid_land_mask=np.ones((2, 2), dtype=bool),
            perm_water_mask=np.zeros((2, 2), dtype=bool),
            buildings_geojson=bldgs_gj,
            roads_geojson=roads_gj,
            bridges_geojson={"type": "FeatureCollection", "features": []},
            watersheds_geojson={"type": "FeatureCollection", "features": []},
            wards_geojson=wards_gj,
            stations_list=[],
            waterways_geojson={"type": "FeatureCollection", "features": []},
        )
        return eng

    def test_partial_building_intersection_and_no_double_counting(self, synthetic_engine):
        # Wet only in column 1 -> (0,1)=0.25 m, (1,1)=0.40 m; column 0 dry (0.01 m)
        depth = np.array([[0.01, 0.25], [0.01, 0.40]], dtype=np.float64)
        exp = synthetic_engine.evaluate_scenario_exposure(depth, "test_1", "Synthetic Wet Col 1", threshold_m=0.15)

        assert exp["assessment_label"] == "modelled_potential_exposure"
        assert exp["coverage"]["buildings_total"] == 3
        assert exp["coverage"]["buildings_in_domain"] == 2
        assert exp["coverage"]["buildings_outside_domain"] == 1

        # Both in-domain buildings (b1 spanning half into col1 + b3 bowtie inside col1) hit once each!
        assert exp["buildings"]["exposed_count"] == 2
        # b1 wet half area ~2500 m2 + repaired b3 bowtie area ~800 m2 = ~3300 m2
        assert 3100.0 <= exp["buildings"]["exposed_footprint_area_m2"] <= 3500.0
        assert exp["buildings"]["critical_civic_facilities"]["by_type"] == {"hospital": 1, "school": 1}

        # Road 1001 runs 100 m in (1,0) dry + 100 m in (1,1) wet; duplicate skipped -> ~100 m (0.100 km)
        assert exp["roads"]["exposed_segments_count"] == 1
        assert abs(exp["roads"]["exposed_length_km"] - 0.100) < 0.005

        # Threshold sensitivity: >= 0.30 m leaves only cell (1,1), excluding row 0 buildings while keeping (1,1) road segment
        exp_high = synthetic_engine.evaluate_scenario_exposure(depth, "test_2", "High Threshold", threshold_m=0.30)
        assert exp_high["buildings"]["exposed_count"] == 0
        assert abs(exp_high["roads"]["exposed_length_km"] - 0.100) < 0.005

    def test_ward_coverage_vs_inundation_percentage(self, synthetic_engine):
        depth = np.array([[0.0, 0.25], [0.0, 0.25]], dtype=np.float64)
        nb = synthetic_engine.evaluate_neighbourhoods(depth, "test_1", "Synthetic", boundary_type="wards", threshold_m=0.15)
        assert len(nb["regions"]) == 1
        ward = nb["regions"][0]
        # Total polygon 300x300m = 0.09 km2; half inside 2x2 grid = 0.045 km2 (50% coverage)
        assert abs(ward["total_area_km2"] - 0.09) < 0.003
        assert abs(ward["in_domain_area_km2"] - 0.045) < 0.003
        assert abs(ward["domain_coverage_pct"] - 50.0) < 1.5
        # Entire in-domain portion (col 1) is wet (0.25m >= 0.15m) -> 100% of in-domain inundated!
        assert abs(ward["inundated_pct_of_in_domain"] - 100.0) < 1.5


class TestTankMaeAuditAndCausalFix:
    """Verifies causal dt_i and piecewise Q_in fix eliminating transition jump MAE spikes."""

    def test_causal_segment_isolation_eliminates_reset_discontinuity_error(self):
        geom = TankGeometry("tank_01", "node_01", "Tank 1", diameter_cm=19.54, max_height_cm=50.0)
        model = PhysicalTankModel(geom, drainage_k=4.5, initial_level_cm=15.0, default_q_in_cm3_s=25.0)
        sim_truth = PhysicalTankModel(geom, drainage_k=4.5, initial_level_cm=28.0, default_q_in_cm3_s=45.0)

        t0 = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
        rows = []
        # Pre-reset stale regime (8 samples)
        for i in range(8):
            rows.append({
                "device_id": "node_01",
                "zone_id": "zone_01",
                "event_timestamp": (t0 + timedelta(seconds=i * 5)).isoformat(),
                "water_level_cm": 15.0,
                "inflow_cm3_s": 25.0,
                "sensor_status": "valid",
                "source": "PYTHON_SIMULATED",
            })
        # Non-physical historical contamination in zone_01 + live_integration_test flag (must be ignored!)
        rows.append({
            "device_id": "chennai_historical_station_01",
            "zone_id": "zone_01",
            "event_timestamp": (t0 + timedelta(seconds=42)).isoformat(),
            "water_level_cm": 2.0,
            "sensor_status": "valid",
            "source": "REPLAYED_HISTORICAL",
        })
        rows.append({
            "device_id": "node_01",
            "zone_id": "zone_01",
            "event_timestamp": (t0 + timedelta(seconds=43)).isoformat(),
            "water_level_cm": 48.0,
            "sensor_status": "valid",
            "quality_flags": ["live_integration_test"],
            "source": "PYTHON_SIMULATED",
        })
        # Reset jump (+13 cm jump to 28.0 cm matching scenario transition + gap > 30s) followed by 12 clean surge samples
        for j in range(12):
            cur_t = t0 + timedelta(seconds=120 + j * 5)
            rows.append({
                "device_id": "node_01",
                "zone_id": "zone_01",
                "event_timestamp": cur_t.isoformat(),
                "water_level_cm": round(sim_truth.current_level_cm, 3),
                "inflow_cm3_s": 45.0,
                "sensor_status": "valid",
                "source": "PYTHON_SIMULATED",
            })
            sim_truth.step_rk4(5.0, q_in=45.0)

        res = evaluate_telemetry_window(model, rows)
        assert res["insufficient_records"] is False
        assert res["discontinuities_isolated"] >= 1
        assert res["mae_cm"] < 0.05
        assert res["one_step_tracking"]["mae_cm"] < 0.05
        assert "unavailable" in res["physical_validation"].lower()


class TestUrbanIntelligenceAPIs:
    """End-to-end offline TestClient coverage for terrain tiles, exposure, sensitivity, CRUD & PDF reports."""

    @pytest.fixture(scope="module")
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_terrarium_elevation_tile_offline(self, client):
        # South Chennai tile at z=12 (80.18°E, 12.98°N -> x=2960, y=1899 covering Pallavaram Hill & Velachery)
        r = client.get("/api/urban/geo/terrain_tiles/12/2960/1899.png")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        img = Image.open(BytesIO(r.content))
        assert img.size == (256, 256) and img.mode == "RGB"
        arr = np.asarray(img, dtype=np.float64)
        elev = (arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0) - 32768.0
        assert float(elev.min()) >= -1.0
        assert float(elev.max()) > 20.0  # Pallavaram & terrain hills rise > 20m

        r_bad = client.get("/api/urban/geo/terrain_tiles/20/0/0.png")
        assert r_bad.status_code == 400

    def test_exposure_and_neighbourhood_endpoints_ordering(self, client):
        r_low = client.get("/api/urban/exposure?scenario_id=improved_drainage&threshold_m=0.15&include_geojson=false")
        r_high = client.get("/api/urban/exposure?scenario_id=reduced_drainage&threshold_m=0.15&include_geojson=false")
        assert r_low.status_code == 200 and r_high.status_code == 200
        dl, dh = r_low.json(), r_high.json()
        assert dh["buildings"]["exposed_count"] > dl["buildings"]["exposed_count"]
        assert dh["roads"]["exposed_length_km"] > dl["roads"]["exposed_length_km"]

        r_ws = client.get("/api/urban/neighbourhoods?scenario_id=heavy_rainfall&boundary_type=watersheds")
        r_wd = client.get("/api/urban/neighbourhoods?scenario_id=heavy_rainfall&boundary_type=wards")
        assert r_ws.status_code == 200 and r_wd.status_code == 200
        assert r_ws.json()["in_domain_regions_count"] > 0
        assert r_wd.json()["outside_domain_regions_count"] > 50  # Northern GCC wards strictly outside South pilot

    def test_sensitivity_analysis_monotonic_and_bounded(self, client):
        r_bad = client.post("/api/urban/sensitivity", json={"parameter": "rainfall_intensity_mm_hr", "min_val": -10, "max_val": 500, "steps": 5})
        assert r_bad.status_code == 422

        r = client.post(
            "/api/urban/sensitivity",
            json={"parameter": "rainfall_intensity_mm_hr", "min_val": 10, "max_val": 90, "steps": 3, "base_scenario_id": "heavy_rainfall", "include_exposure": True},
        )
        assert r.status_code == 200
        pts = r.json()["points"]
        assert len(pts) == 3
        assert pts[0]["stored_water_volume_mcm"] < pts[1]["stored_water_volume_mcm"] < pts[2]["stored_water_volume_mcm"]
        assert pts[0]["exposed_buildings_count"] <= pts[1]["exposed_buildings_count"] <= pts[2]["exposed_buildings_count"]

    def test_zero_denominator_compare_and_saved_crud(self, client):
        # Normal baseline has 0.0 volume & area -> percentage deltas must cleanly return None (no ZeroDivisionError)
        rc = client.post("/api/urban/scenario/compare", json={"baseline_id": "normal", "alternate_id": "heavy_rainfall", "include_exposure": True})
        assert rc.status_code == 200
        dc = rc.json()
        assert dc["pct_delta_stored_volume"] is None
        assert dc["delta_stored_volume_mcm"] > 10.0
        assert dc["delta_raster_png_data_url"].startswith("data:image/png;base64,")

        # Saved scenario CRUD
        r_save = client.post("/api/urban/scenario/save", json={"saved_name": "Pytest CRUD Test", "rainfall_intensity_mm_hr": 50.0, "initial_depth_m": 0.1})
        assert r_save.status_code == 200
        sid = r_save.json()["id"]
        assert client.get(f"/api/urban/scenario/{sid}").status_code == 200
        r_dup = client.post(f"/api/urban/scenarios/saved/{sid}/duplicate")
        assert r_dup.status_code == 200
        dup_id = r_dup.json()["id"]
        r_ren = client.patch(f"/api/urban/scenarios/saved/{dup_id}", json={"new_name": "Pytest Renamed"})
        assert r_ren.status_code == 200
        ren_id = r_ren.json()["id"]
        assert client.delete(f"/api/urban/scenarios/saved/{sid}").status_code == 200
        assert client.delete(f"/api/urban/scenarios/saved/{ren_id}").status_code == 200

    def test_engineering_pdf_csv_report_and_filename_sanitization(self, client):
        r_pdf = client.get("/api/urban/report/pdf?scenario_id=heavy_rainfall&compare_id=reduced_drainage")
        assert r_pdf.status_code == 200
        assert r_pdf.headers["content-type"] == "application/pdf"
        assert r_pdf.content.startswith(b"%PDF")
        assert len(r_pdf.content) > 40000
        assert "X-CivicTwin-Report-Id" in r_pdf.headers

        r_csv = client.get("/api/urban/report/csv?scenario_id=heavy_rainfall")
        assert r_csv.status_code == 200
        assert "exposed_buildings_count" in r_csv.text

        # Header injection sanitization guard
        assert _safe_filename_slug('../../bad\r\nname.pdf') == 'bad_name.pdf'
