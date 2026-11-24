"""
CivicTwin-R — Chennai Urban Geospatial Digital Twin Automated Test Suite

Validates:
  1. Geographical validity of the 10 Chennai focus locations (WGS84 bounds).
  2. Verified CFM-DSS / IMD Automatic Rain Gauge station locations and metadata.
  3. Official WRD reservoir capacities, storage percentages, and coordinates.
  4. Geospatial GeoJSON integrity for waterways, catchments, and 3D buildings.
  5. Mass-balance hydrological screening engine under various storm profiles.
  6. Monotonic sensitivity: increasing rainfall or reducing drainage increases inundation.
  7. Chembarambakkam reservoir sluice gate discharge propagation to Saidapet and Adyar.
  8. REST API endpoints and HTML template delivery.
"""

from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from digital_twin.chennai_geo_data import (
    CHENNAI_LOCATIONS,
    CHENNAI_RESERVOIRS,
    RAINFALL_STATIONS,
    WATERWAYS_GEOJSON,
    CATCHMENTS_GEOJSON,
    BUILDINGS_GEOJSON,
)
from digital_twin.urban_hydrology import (
    urban_engine,
    PREDEFINED_SCENARIOS,
    UrbanScenarioParams,
)

# Chennai Metropolitan Region Bounding Box
CHENNAI_LAT_MIN = 12.80
CHENNAI_LAT_MAX = 13.45
CHENNAI_LON_MIN = 79.80
CHENNAI_LON_MAX = 80.35


class TestChennaiGeospatialData:
    def test_ten_prioritized_locations_exist(self):
        assert len(CHENNAI_LOCATIONS) == 10
        ids = {loc["id"] for loc in CHENNAI_LOCATIONS}
        required_ids = {
            "velachery",
            "pallikaranai",
            "adyar",
            "madipakkam",
            "perungudi",
            "tambaram",
            "pallavaram",
            "chembarambakkam",
            "porur",
            "saidapet",
        }
        assert required_ids.issubset(ids), f"Missing locations: {required_ids - ids}"

    def test_location_coordinates_within_chennai_bounds(self):
        for loc in CHENNAI_LOCATIONS:
            lon, lat = loc["coordinates"]
            assert CHENNAI_LON_MIN <= lon <= CHENNAI_LON_MAX, f"{loc['name']} lon {lon} out of bounds"
            assert CHENNAI_LAT_MIN <= lat <= CHENNAI_LAT_MAX, f"{loc['name']} lat {lat} out of bounds"
            assert loc["elevation_m"] > 0, f"{loc['name']} elevation must be positive"
            assert loc["area_km2"] > 0, f"{loc['name']} area must be positive"
            assert 0.0 < loc["runoff_coefficient"] <= 1.0, f"{loc['name']} runoff coeff invalid"

    def test_rainfall_stations_coordinates_and_provenance(self):
        assert len(RAINFALL_STATIONS) >= 10
        for st in RAINFALL_STATIONS:
            lon, lat = st["coordinates"]
            assert CHENNAI_LON_MIN <= lon <= CHENNAI_LON_MAX
            assert CHENNAI_LAT_MIN <= lat <= CHENNAI_LAT_MAX
            assert st["provenance"] in ["CFM-DSS_ARG", "IMD_Chennai"]
            assert st["source"] == "observed"
            assert st["rainfall_mm"] >= 0.0

    def test_reservoirs_data_integrity(self):
        assert len(CHENNAI_RESERVOIRS) == 5
        names = {r["reservoir_name"] for r in CHENNAI_RESERVOIRS}
        assert "Chembarambakkam" in names
        assert "Poondi (Sathyamurthy Sagar)" in names
        assert "Red Hills (Puzhal)" in names
        for r in CHENNAI_RESERVOIRS:
            assert r["storage_capacity_gross_mcm"] > r["storage_capacity_live_mcm"] > 0.0
            assert 0.0 <= r["storage_fill_pct"] <= 100.0

    def test_geojson_waterways_and_catchments(self):
        assert WATERWAYS_GEOJSON["type"] == "FeatureCollection"
        assert len(WATERWAYS_GEOJSON["features"]) >= 6

        # Verify key waterways
        feat_names = [f["properties"]["name"] for f in WATERWAYS_GEOJSON["features"]]
        assert any("Adyar River" in n for n in feat_names)
        assert any("Cooum River" in n for n in feat_names)
        assert any("Pallikaranai Marsh" in n for n in feat_names)
        assert any("Chembarambakkam" in n for n in feat_names)

        # Catchments
        assert CATCHMENTS_GEOJSON["type"] == "FeatureCollection"
        assert len(CATCHMENTS_GEOJSON["features"]) >= 4

        # 3D Buildings
        assert BUILDINGS_GEOJSON["type"] == "FeatureCollection"
        assert len(BUILDINGS_GEOJSON["features"]) >= 10
        for b in BUILDINGS_GEOJSON["features"]:
            assert b["properties"]["height_m"] >= 8.0


class TestUrbanHydrologyModel:
    def test_normal_baseline_zero_inundation(self):
        normal_params = PREDEFINED_SCENARIOS["normal"]
        res = urban_engine.run_scenario(normal_params)
        assert res["summary"]["total_accumulated_volume_mcm"] == 0.0
        assert res["summary"]["max_depth_m"] == 0.0
        for loc in res["location_impacts"]:
            assert loc["estimated_depth_m"] == 0.0
            assert loc["risk_level"] == "Low"

    def test_heavy_rainfall_generates_inundation(self):
        heavy_params = PREDEFINED_SCENARIOS["heavy_rain"]
        res = urban_engine.run_scenario(heavy_params)
        assert res["summary"]["total_accumulated_volume_mcm"] > 10.0
        assert res["summary"]["max_depth_m"] > 0.30
        assert len(res["flood_overlay_geojson"]["features"]) > 0

    def test_drainage_obstruction_increases_depth(self):
        base_params = UrbanScenarioParams(
            scenario_id="drain_test_100",
            scenario_name="Normal Drainage",
            rainfall_intensity_mm_hr=50.0,
            duration_hours=4.0,
            runoff_coefficient=0.85,
            drainage_capacity_pct=100.0,
            infiltration_rate_mm_hr=4.0,
            chembarambakkam_discharge_cusecs=1000.0,
            description="100% Drainage",
        )
        obstructed_params = UrbanScenarioParams(
            scenario_id="drain_test_25",
            scenario_name="Obstructed Drainage",
            rainfall_intensity_mm_hr=50.0,
            duration_hours=4.0,
            runoff_coefficient=0.85,
            drainage_capacity_pct=25.0,
            infiltration_rate_mm_hr=4.0,
            chembarambakkam_discharge_cusecs=1000.0,
            description="25% Drainage",
        )
        res_normal = urban_engine.run_scenario(base_params)
        res_choked = urban_engine.run_scenario(obstructed_params)

        assert res_choked["summary"]["total_accumulated_volume_mcm"] > res_normal["summary"]["total_accumulated_volume_mcm"]
        assert res_choked["summary"]["max_depth_m"] > res_normal["summary"]["max_depth_m"]

    def test_chembarambakkam_discharge_propagates_to_adyar_corridor(self):
        low_discharge = UrbanScenarioParams(
            scenario_id="low_q",
            scenario_name="Low Discharge",
            rainfall_intensity_mm_hr=20.0,
            duration_hours=4.0,
            runoff_coefficient=0.75,
            drainage_capacity_pct=90.0,
            infiltration_rate_mm_hr=5.0,
            chembarambakkam_discharge_cusecs=500.0,
            description="500 cfs",
        )
        high_discharge = UrbanScenarioParams(
            scenario_id="high_q",
            scenario_name="Surge Discharge",
            rainfall_intensity_mm_hr=20.0,
            duration_hours=4.0,
            runoff_coefficient=0.75,
            drainage_capacity_pct=90.0,
            infiltration_rate_mm_hr=5.0,
            chembarambakkam_discharge_cusecs=25000.0,
            description="25,000 cfs",
        )
        res_low = urban_engine.run_scenario(low_discharge)
        res_high = urban_engine.run_scenario(high_discharge)

        # Saidapet is on the central Adyar River corridor
        saidapet_low = next(l for l in res_low["location_impacts"] if l["id"] == "saidapet")
        saidapet_high = next(l for l in res_high["location_impacts"] if l["id"] == "saidapet")

        assert saidapet_high["estimated_depth_m"] > saidapet_low["estimated_depth_m"]


class TestUrbanRestApiEndpoints:
    @pytest.fixture
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_get_urban_locations_endpoint(self, client):
        r = client.get("/api/urban/locations")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 10
        assert len(data["locations"]) == 10

    def test_get_single_urban_location(self, client):
        r = client.get("/api/urban/locations/velachery")
        assert r.status_code == 200
        loc = r.json()
        assert loc["name"] == "Velachery"
        assert loc["elevation_m"] == 6.2

    def test_get_urban_stations_endpoint(self, client):
        r = client.get("/api/urban/stations")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 10

    def test_get_urban_reservoirs_endpoint(self, client):
        r = client.get("/api/urban/reservoirs")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 5

    def test_get_urban_geo_layers(self, client):
        for endpoint in ["waterways", "catchments", "buildings"]:
            r = client.get(f"/api/urban/geo/{endpoint}")
            assert r.status_code == 200
            data = r.json()
            assert data["type"] == "FeatureCollection"
            assert len(data["features"]) > 0

    def test_post_urban_scenario_endpoint(self, client):
        payload = {
            "scenario_id": "heavy_rain",
            "rainfall_intensity_mm_hr": 55.0,
            "duration_hours": 3.0,
            "drainage_capacity_pct": 70.0,
            "chembarambakkam_discharge_cusecs": 5000.0,
        }
        r = client.post("/api/urban/scenario", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "summary" in data
        assert "location_impacts" in data
        assert data["summary"]["total_accumulated_volume_mcm"] > 0

    def test_get_urban_twin_html_pages(self, client):
        # 3D Urban Twin dedicated page
        r_urban = client.get("/urban-twin")
        assert r_urban.status_code == 200
        html_urban = r_urban.text
        assert "MapLibre" in html_urban or "maplibre-gl" in html_urban
        assert "Chennai" in html_urban
        assert "Velachery" in html_urban
        assert "Pallikaranai" in html_urban

        # Main Showcase page includes Urban Twin
        r_show = client.get("/showcase")
        assert r_show.status_code == 200
        html_show = r_show.text
        assert "Chennai Urban Geospatial Digital Twin" in html_show
        assert "Experimental IoT Tank Digital Twin" in html_show
