"""
CivicTwin-R — Chennai Grounding & Forecasting Test Suite

Validates:
  1. Chennai real dataset processing and provenance schemas.
  2. Multi-zone digital twin alignment to Chennai sub-basins & alias resolution.
  3. Rainfall-driven mass-balance hydrology.
  4. Interpretable forecasting baseline with time-aware zero-leakage evaluation.
  5. Historical replay pipeline with strict 'replayed_historical' provenance.
  6. Explicit storage fallback status reporting.
  7. REST API endpoints for forecasting and historical replay.
"""

from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.models import TelemetryMessage, DataSource, SensorStatus
from backend.storage import MemoryStorage, SQLiteStorage, create_storage
from backend.ingestion import IngestionService
from backend.app.main import app
from digital_twin.model import ZoneModel, DigitalTwinEngine, create_default_zones
from digital_twin.forecast import BaselineForecaster, evaluate_forecaster_time_aware
from scripts.replay_historical import HistoricalReplayController


class TestChennaiDataGrounding:
    def test_arg_data_processed_exists_and_valid(self):
        arg_path = config.PROCESSED_DIR / "chennai_arg_rainfall.csv"
        assert arg_path.exists(), "Processed ARG rainfall file must exist"
        with open(arg_path) as f:
            reader = list(csv.DictReader(f))
            assert len(reader) >= 100, f"Expected at least 100 ARG records, found {len(reader)}"
            first = reader[0]
            assert "station_id" in first
            assert "subbasin" in first
            assert "rainfall_mm" in first
            assert first["source"] == "observed"

    def test_reservoir_data_exists_and_valid(self):
        res_path = config.PROCESSED_DIR / "chennai_reservoirs.csv"
        assert res_path.exists(), "Processed reservoirs file must exist"
        with open(res_path) as f:
            reader = list(csv.DictReader(f))
            assert len(reader) >= 4, "Expected at least 4 major Chennai reservoirs"
            names = [r["reservoir_name"] for r in reader]
            assert "Chembarambakkam" in names
            assert "Poondi" in names
            assert "RedHills" in names
            for r in reader:
                assert float(r["storage_capacity_gross_mcm"]) > 0

    def test_michaung_hourly_exists_and_valid(self):
        mich_path = config.PROCESSED_DIR / "chennai_michaung_hourly.csv"
        assert mich_path.exists(), "Cyclone Michaung hourly file must exist"
        with open(mich_path) as f:
            reader = list(csv.DictReader(f))
            assert len(reader) == 144, "Expected 144 hourly storm points (6 days)"
            total_rain = sum(float(r["hourly_precipitation_mm"]) for r in reader)
            assert total_rain > 300.0, f"Michaung cumulative rainfall should exceed 300mm, got {total_rain}"


class TestChennaiDigitalTwin:
    def test_default_zones_reflect_chennai_basins(self):
        zones = create_default_zones()
        assert len(zones) == 3
        subbasins = [z.subbasin for z in zones]
        assert "Adyar" in subbasins
        assert "Cooum" in subbasins
        assert "Kosasthalaiyar" in subbasins

    def test_zone_alias_resolution(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)

        state_01 = engine.get_zone_state("zone_01")
        state_adyar = engine.get_zone_state("zone_adyar")
        assert state_01 is not None
        assert state_adyar is not None
        assert state_01["zone_id"] == state_adyar["zone_id"] == "zone_01"

    def test_rainfall_input_affects_water_level(self):
        zone_dry = ZoneModel(
            zone_id="test_dry",
            zone_name="Test Dry",
            baseline_level_cm=5.0,
            rainfall_input_mm=0.0,
            drainage_capacity=0.2,
        )
        zone_wet = ZoneModel(
            zone_id="test_wet",
            zone_name="Test Wet",
            baseline_level_cm=5.0,
            rainfall_input_mm=25.0,  # 25mm rain
            drainage_capacity=0.2,
        )
        r_dry = zone_dry.step(dt_sec=5.0)
        r_wet = zone_wet.step(dt_sec=5.0)
        assert r_wet.true_level_cm > r_dry.true_level_cm

    def test_conceptual_topology_disclaimer_present(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        state = engine.get_zone_state("zone_01")
        assert "conceptual_topology" in state
        assert "not an uncalibrated 2d hydrodynamic simulation" in state["conceptual_topology"].lower()


class TestForecastingBaseline:
    def test_forecast_predict_horizons(self):
        forecaster = BaselineForecaster()
        levels = [5.0, 5.2, 5.5, 6.0, 6.7, 7.5]  # rising water level
        fc = forecaster.forecast_zone("zone_01", levels, container_height_cm=30.0)

        assert fc.zone_id == "zone_01"
        assert fc.provenance == "forecast"
        assert len(fc.horizons) == 3
        h15 = fc.horizons[0]
        assert h15.horizon_minutes == 15
        assert h15.trend == "rising"
        assert h15.forecast_level_cm >= levels[-1]

    def test_forecast_uncertainty_bounds(self):
        forecaster = BaselineForecaster()
        levels = [5.0, 5.1, 5.0, 5.2, 5.1]
        fc = forecaster.forecast_zone("zone_01", levels, container_height_cm=30.0)
        for h in fc.horizons:
            assert h.lower_bound_cm <= h.forecast_level_cm <= h.upper_bound_cm

    def test_forecast_eval_time_aware_zero_leakage(self):
        # 100 step synthetic series
        series = [5.0 + 0.1 * i + 0.05 * math.sin(i) for i in range(100)]
        res = evaluate_forecaster_time_aware(
            series, container_height_cm=30.0, horizon_steps=3, train_ratio=0.7
        )
        assert res.evaluated_points > 0
        assert not math.isnan(res.model_mae)
        assert not math.isnan(res.model_rmse)
        assert res.model_mae >= 0.0
        assert res.data_classification == "observed"


class TestHistoricalReplay:
    def test_replay_step_sets_replayed_historical_source(self):
        controller = HistoricalReplayController()
        reading = controller.step()
        assert reading is not None
        assert reading["source"] == DataSource.REPLAYED_HISTORICAL.value
        assert "historical_replay" in reading["quality_flags"]

    def test_replay_preserves_original_timestamp(self):
        controller = HistoricalReplayController()
        reading = controller.step()
        assert reading is not None
        assert reading["timestamp"].startswith("2023-12-01")

    def test_replay_ingestion_no_false_stale_flag(self):
        storage = MemoryStorage()
        ingestion = IngestionService(storage)

        # Ingest a replayed historical message
        controller = HistoricalReplayController()
        msg = controller.step()
        record = ingestion.process_message(msg)

        assert record is not None
        assert record.is_stale is False
        assert "stale" not in record.quality_flags
        assert record.source == DataSource.REPLAYED_HISTORICAL


class TestStorageFallbackReporting:
    def test_sqlite_fallback_property(self):
        storage_direct = SQLiteStorage(":memory:", is_fallback=False)
        assert storage_direct.backend_type == "sqlite"
        assert storage_direct.is_fallback is False

        storage_fallback = SQLiteStorage(":memory:", is_fallback=True)
        assert storage_fallback.backend_type == "sqlite"
        assert storage_fallback.is_fallback is True

    def test_create_storage_fallback_on_disabled_influx(self):
        from backend import config
        prev_backend = config.STORAGE_BACKEND
        prev_influx = config.INFLUXDB_ENABLED
        try:
            config.STORAGE_BACKEND = "influxdb"
            config.INFLUXDB_ENABLED = False
            s = create_storage("influxdb")
            assert s.backend_type == "sqlite"
            assert s.is_fallback is True
        finally:
            config.STORAGE_BACKEND = prev_backend
            config.INFLUXDB_ENABLED = prev_influx


class TestNewApiEndpoints:
    def test_api_forecast_endpoint(self):
        with TestClient(app) as client:
            resp = client.get("/api/forecast/zone_01")
            assert resp.status_code == 200
            data = resp.json()
            assert data["zone_id"] == "zone_01"
            assert data["provenance"] == "forecast"
            assert len(data["horizons"]) >= 2
            assert "subbasin" in data

    def test_api_forecast_alias_endpoint(self):
        with TestClient(app) as client:
            resp = client.get("/api/forecast/zone_adyar")
            assert resp.status_code == 200
            data = resp.json()
            assert data["zone_id"] == "zone_01"

    def test_api_forecast_evaluate_endpoint(self):
        with TestClient(app) as client:
            resp = client.get("/api/forecast/evaluate?zone_id=zone_01")
            assert resp.status_code == 200
            data = resp.json()
            assert "evaluation_horizons" in data
            assert len(data["evaluation_horizons"]) >= 2

    def test_api_replay_endpoints(self):
        with TestClient(app) as client:
            # Check status
            resp = client.get("/api/replay/status")
            assert resp.status_code == 200
            data = resp.json()
            assert "total_records" in data

            # Step replay
            resp = client.post("/api/replay/step?steps=2")
            assert resp.status_code == 200
            step_data = resp.json()
            assert step_data["steps_executed"] == 2
            assert step_data["sample"]["source"] == "replayed_historical"

            # Stop replay
            resp = client.post("/api/replay/stop")
            assert resp.status_code == 200
