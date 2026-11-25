"""
CivicTwin-R — Real Geospatial & 2D Hydrological Digital Twin Test Suite

Validates:
  1. Official Copernicus GLO-30 UTM44N DEM bundle, GeoTIFF bounds, ocean/land/channel masks.
  2. Real TN CFM-DSS WFS layers (GCC boundary, watersheds, waterways, waterbodies, 56 verified stations).
  3. Real OpenStreetMap PBF extracts (18k+ buildings with honest height provenance, roads, bridges, parks, places).
  4. Physical separation: chennai_arg_rainfall.csv (non-spatial) vs verified_stations.json (geolocated).
  5. Landlab 2D OverlandFlow terrain engine (8 presets, scenario comparison, Chembarambakkam Adyar wave).
  6. FastAPI REST API endpoints, offline vendor bundles (/static/vendor/*), and live service status API.
"""

from __future__ import annotations

import json
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from digital_twin.terrain_hydrology import (
    PROCESSED_GEO_DIR,
    FOCUS_LOCATIONS,
    PREDEFINED_SCENARIOS,
    HydroScenarioConfig,
    terrain_engine,
)

CHENNAI_LAT_MIN = 12.65
CHENNAI_LAT_MAX = 13.45
CHENNAI_LON_MIN = 79.80
CHENNAI_LON_MAX = 80.40


class TestRealGeospatialLayers:
    def test_dem_utm44n_bundle_and_metadata(self):
        npz_path = PROCESSED_GEO_DIR / "south_chennai_dem_utm44n_150m.npz"
        meta_path = PROCESSED_GEO_DIR / "dem_metadata.json"
        hs_path = PROCESSED_GEO_DIR / "chennai_terrain_hillshade.png"
        assert npz_path.exists() and meta_path.exists() and hs_path.exists()

        meta = json.loads(meta_path.read_text())
        assert meta["crs"] == "EPSG:32644"
        assert meta["grid_shape"] == [111, 175]
        assert meta["dx_m"] == 150.0
        assert meta["valid_land_cells"] > 15000

        z = np.load(npz_path)
        assert z["elevation_m"].shape == (111, 175)
        assert z["channel_mask"].sum() > 900

    def test_ten_focus_locations_grounded_in_domain(self):
        assert len(FOCUS_LOCATIONS) == 10
        ids = {l["id"] for l in FOCUS_LOCATIONS}
        assert {"velachery", "pallikaranai", "adyar", "madipakkam", "perungudi", "saidapet", "porur", "pallavaram", "tambaram", "chembarambakkam"}.issubset(ids)
        for loc in FOCUS_LOCATIONS:
            lon, lat = loc["coordinates"]
            assert CHENNAI_LON_MIN <= lon <= CHENNAI_LON_MAX
            assert CHENNAI_LAT_MIN <= lat <= CHENNAI_LAT_MAX
            pt = terrain_engine.query_point(lon, lat)
            assert pt["in_computational_domain"] is True
            assert pt["copernicus_dsm_elevation_m"] is not None

    def test_verified_wfs_stations_vs_nonspatial_arg_corpus(self):
        st_path = PROCESSED_GEO_DIR / "verified_stations.json"
        stations = json.loads(st_path.read_text())
        assert len(stations) >= 50
        for st in stations:
            lon, lat = st["coordinates"]
            assert CHENNAI_LON_MIN <= lon <= CHENNAI_LON_MAX
            assert CHENNAI_LAT_MIN <= lat <= CHENNAI_LAT_MAX
            assert st["observation_mode"] == "historical_verified_coordinates"

    def test_real_wfs_and_osm_geojson_integrity(self):
        waterways = json.loads((PROCESSED_GEO_DIR / "waterways_official.geojson").read_text())
        waterbodies = json.loads((PROCESSED_GEO_DIR / "waterbodies_official.geojson").read_text())
        watersheds = json.loads((PROCESSED_GEO_DIR / "watersheds_south.geojson").read_text())
        buildings = json.loads((PROCESSED_GEO_DIR / "osm_buildings_south.geojson").read_text())
        roads = json.loads((PROCESSED_GEO_DIR / "osm_roads_major.geojson").read_text())
        bridges = json.loads((PROCESSED_GEO_DIR / "osm_bridges.geojson").read_text())

        assert len(waterways["features"]) >= 400
        assert len(waterbodies["features"]) >= 700
        assert len(watersheds["features"]) >= 30
        assert len(roads["features"]) >= 5000
        assert len(bridges["features"]) >= 500
        assert len(buildings["features"]) >= 10000

        allowed_sources = {"osm_height_tag", "osm_levels_derived", "type_fallback_estimate"}
        for b in buildings["features"][:100]:
            props = b["properties"]
            assert props["height_m"] >= 3.0
            assert props["height_source"] in allowed_sources


class TestTerrainHydrologyIntegration:
    def test_normal_baseline_is_dry(self):
        res = terrain_engine.run_scenario(PREDEFINED_SCENARIOS["normal"])
        assert res["summary"]["stored_water_volume_mcm"] == 0.0
        assert res["summary"]["urban_inundated_area_km2"] == 0.0
        assert res["summary"]["max_urban_depth_m"] == 0.0

    def test_drainage_mitigation_and_obstruction_ordering(self):
        r_imp = terrain_engine.run_scenario(PREDEFINED_SCENARIOS["improved_drainage"])
        r_nom = terrain_engine.run_scenario(PREDEFINED_SCENARIOS["heavy_rainfall"])
        r_red = terrain_engine.run_scenario(PREDEFINED_SCENARIOS["reduced_drainage"])
        assert r_imp["summary"]["stored_water_volume_mcm"] < r_nom["summary"]["stored_water_volume_mcm"]
        assert r_nom["summary"]["stored_water_volume_mcm"] < r_red["summary"]["stored_water_volume_mcm"]

    def test_chembarambakkam_spillway_wave_propagates_down_adyar(self):
        lo = HydroScenarioConfig("test_lo", "Lo", "boundary_discharge", 25.0, 12.0, 4.0, 85.0, chembarambakkam_discharge_cusecs=0.0)
        hi = PREDEFINED_SCENARIOS["reservoir_discharge"]
        r0 = terrain_engine.run_scenario(lo)
        r1 = terrain_engine.run_scenario(hi)
        diff = r1["_max_depth_grid"] - r0["_max_depth_grid"]
        # Channel wave clearly raises depth downstream through central Adyar corridor (cols 50..129 Saidapet)
        assert float(diff[:, 50].max()) > 1.0
        assert float(diff[:, 129].max()) > 0.4
        assert r1["summary"]["mass_balance"]["relative_error"] < 0.01


class TestUrbanRestAndOfflineAssets:
    @pytest.fixture
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_urban_locations_and_stations(self, client):
        r_loc = client.get("/api/urban/locations")
        assert r_loc.status_code == 200 and r_loc.json()["count"] == 10
        r_v = client.get("/api/urban/locations/velachery")
        assert r_v.status_code == 200 and r_v.json()["name"] == "Velachery"
        r_st = client.get("/api/urban/stations")
        assert r_st.status_code == 200 and r_st.json()["count"] >= 50

    def test_nonspatial_arg_analytics_and_reservoirs(self, client):
        r_arg = client.get("/api/urban/historical/arg-analytics")
        assert r_arg.status_code == 200
        d_arg = r_arg.json()
        assert d_arg["has_coordinates"] is False
        assert d_arg["total_records"] == 328

        r_res = client.get("/api/urban/reservoirs")
        assert r_res.status_code == 200
        assert r_res.json()["count"] == 5

    def test_geo_layers_and_search_and_point_query(self, client):
        for layer in ["dem_metadata", "hillshade", "waterways", "waterbodies", "watersheds", "roads_major", "bridges", "buildings", "places"]:
            r = client.get(f"/api/urban/geo/{layer}")
            assert r.status_code == 200, f"Failed geo layer {layer}"
        r_s = client.get("/api/urban/search?q=Velachery")
        assert r_s.status_code == 200 and r_s.json()["count"] >= 1
        r_pt = client.get("/api/urban/point?lon=80.218&lat=12.9815")
        assert r_pt.status_code == 200 and r_pt.json()["in_computational_domain"] is True

    def test_scenario_api_and_compare_and_offline_html(self, client):
        r_sc = client.post("/api/urban/scenario", json={"scenario_id": "heavy_rainfall"})
        assert r_sc.status_code == 200
        assert r_sc.json()["summary"]["stored_water_volume_mcm"] > 10.0

        r_cmp = client.post("/api/urban/scenario/compare", json={"baseline_id": "heavy_rainfall", "alternate_id": "reduced_drainage"})
        assert r_cmp.status_code == 200
        assert r_cmp.json()["delta_inundated_area_km2"] > 0.0

        r_ui = client.get("/urban-twin")
        assert r_ui.status_code == 200
        assert "/static/vendor/maplibre-gl.js" in r_ui.text
        assert "cdn." not in r_ui.text and "unpkg.com" not in r_ui.text

        r_sh = client.get("/showcase")
        assert r_sh.status_code == 200
        assert "/static/vendor/three.min.js" in r_sh.text
        assert "cdn.tailwindcss.com" not in r_sh.text
