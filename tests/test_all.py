"""
CivicTwin-R — Comprehensive Automated Test Suite

Tests digital twin physics, scenario controller, reconstruction algorithms,
data models, storage backends, ingestion pipeline, threshold hysteresis,
failure recovery, and FastAPI REST endpoints.
"""

from __future__ import annotations

import json
import math
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from digital_twin.model import ZoneModel, DigitalTwinEngine, ZoneReading, create_default_zones
from digital_twin.scenarios import ScenarioController, SCENARIOS, list_scenarios
from digital_twin.reconstruction import (
    locf,
    linear_interpolation,
    create_missing_mask,
    apply_mask,
    evaluate_reconstruction,
    run_reconstruction_experiment,
    run_multi_rate_experiment,
)
from backend.models import (
    TelemetryMessage, IngestedTelemetry, SensorStatus,
    DataSource, AlertLevel, ZoneConfig, ZoneState,
)
from backend.storage import MemoryStorage, SQLiteStorage, create_storage
from backend.ingestion import IngestionService
from backend.app.main import app
from backend import config


# Zone Model Tests

class TestZoneModel:
    def test_initial_conditions(self):
        zone = ZoneModel(zone_id="test", zone_name="Test Zone", baseline_level_cm=10.0)
        assert zone.current_level_cm == 10.0
        assert zone.step_count == 0

    def test_step_produces_reading(self):
        zone = ZoneModel(zone_id="test", zone_name="Test Zone")
        reading = zone.step(dt_sec=5.0)
        assert isinstance(reading, ZoneReading)
        assert reading.zone_id == "test"
        assert reading.step == 1
        assert reading.true_level_cm >= 0

    def test_drainage_reduces_level(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            baseline_level_cm=20.0,
            inflow_rate=0.0,
            drainage_capacity=1.0,
        )
        zone.step(dt_sec=5.0)
        assert zone.current_level_cm < 20.0

    def test_inflow_increases_level(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            baseline_level_cm=5.0,
            inflow_rate=2.0,
            drainage_capacity=0.0,
        )
        zone.step(dt_sec=5.0)
        assert zone.current_level_cm > 5.0

    def test_level_clamped_at_zero(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            baseline_level_cm=0.5,
            inflow_rate=0.0,
            drainage_capacity=10.0,
        )
        zone.step(dt_sec=5.0)
        assert zone.current_level_cm >= 0.0

    def test_level_clamped_at_max(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            container_height_cm=30.0,
            baseline_level_cm=29.0,
            inflow_rate=5.0,
            drainage_capacity=0.0,
        )
        zone.step(dt_sec=5.0)
        assert zone.current_level_cm <= 30.0

    def test_sensor_failure_simulation(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            sensor_reliability=0.0,
        )
        reading = zone.step()
        assert not reading.sensor_ok
        assert reading.observed_level_cm is None
        assert reading.sensor_status == "invalid"

    def test_network_failure_simulation(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            network_availability=0.0,
        )
        reading = zone.step()
        assert not reading.network_ok
        assert reading.sensor_status == "offline"

    def test_reset(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            baseline_level_cm=10.0,
            inflow_rate=5.0,
            drainage_capacity=0.0,
        )
        zone.step()
        assert zone.current_level_cm > 10.0
        zone.reset()
        assert zone.current_level_cm == 10.0
        assert zone.step_count == 0

    def test_alert_levels(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            container_height_cm=100.0,
            baseline_level_cm=10.0,
            warn_threshold_pct=70.0,
            crit_threshold_pct=85.0,
        )
        r1 = zone.step()
        assert r1.alert_level == "normal"

        zone.current_level_cm = 75.0
        r2 = zone.step(dt_sec=0.0)
        assert r2.alert_level == "warning"

        zone.current_level_cm = 90.0
        r3 = zone.step(dt_sec=0.0)
        assert r3.alert_level == "critical"


# Digital Twin Engine Tests

class TestDigitalTwinEngine:
    def test_add_zones(self):
        engine = DigitalTwinEngine(seed=42)
        zones = create_default_zones()
        for z in zones:
            engine.add_zone(z)
        assert len(engine.zones) == 3

    def test_step_all(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        readings = engine.step_all(dt_sec=5.0)
        assert len(readings) == 3
        assert engine.global_step == 1

    def test_deterministic(self):
        e1 = DigitalTwinEngine(seed=123)
        e2 = DigitalTwinEngine(seed=123)
        for z in create_default_zones():
            e1.add_zone(z)
        for z in create_default_zones():
            e2.add_zone(z)

        r1 = e1.step_all()
        r2 = e2.step_all()

        for a, b in zip(r1, r2):
            assert a.true_level_cm == b.true_level_cm
            assert a.observed_level_cm == b.observed_level_cm

    def test_get_zone_state(self):
        engine = DigitalTwinEngine(seed=42)
        engine.add_zone(ZoneModel(zone_id="z1", zone_name="Zone 1", baseline_level_cm=10.0))
        state = engine.get_zone_state("z1")
        assert state is not None
        assert state["zone_id"] == "z1"
        assert state["current_level_cm"] == 10.0

    def test_apply_scenario_params(self):
        engine = DigitalTwinEngine(seed=42)
        zone = ZoneModel(zone_id="z1", zone_name="Zone 1", inflow_rate=0.1)
        engine.add_zone(zone)
        engine.apply_scenario_params("z1", inflow_rate=2.5)
        assert engine.zones["z1"].inflow_rate == 2.5


# Scenario Tests

class TestScenarios:
    def test_all_scenarios_defined(self):
        expected = [
            "normal", "heavy_rainfall", "blocked_drain", "sudden_rise",
            "sensor_dropout", "noisy_sensor", "network_outage", "multi_zone_stress",
        ]
        for name in expected:
            assert name in SCENARIOS, f"Missing scenario: {name}"

    def test_list_scenarios(self):
        scenarios = list_scenarios()
        assert len(scenarios) == 8
        for s in scenarios:
            assert "scenario_id" in s
            assert "name" in s
            assert "total_steps" in s

    def test_scenario_controller_load(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        ctrl = ScenarioController(engine)
        assert ctrl.load_scenario("heavy_rainfall")
        assert ctrl.is_running
        assert not ctrl.is_complete
        assert ctrl.current_step == 0

    def test_scenario_runs_to_completion(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        ctrl = ScenarioController(engine)
        ctrl.load_scenario("normal")
        steps = 0
        while not ctrl.is_complete:
            data = ctrl.step()
            steps += 1
            assert len(data) == 3
        assert steps == 200
        assert not ctrl.is_running
        assert ctrl.is_complete

    def test_scenario_stop(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        ctrl = ScenarioController(engine)
        ctrl.load_scenario("heavy_rainfall")
        ctrl.step()
        ctrl.step()
        ctrl.stop()
        assert not ctrl.is_running

    def test_invalid_scenario(self):
        engine = DigitalTwinEngine(seed=42)
        ctrl = ScenarioController(engine)
        assert not ctrl.load_scenario("nonexistent_scenario")


# Reconstruction Tests

class TestReconstruction:
    def test_locf_basic(self):
        series = [1.0, None, None, 4.0, None]
        result = locf(series)
        assert result == [1.0, 1.0, 1.0, 4.0, 4.0]

    def test_locf_leading_none(self):
        series = [None, None, 3.0, None]
        result = locf(series)
        assert result == [None, None, 3.0, 3.0]

    def test_linear_interpolation_basic(self):
        series = [10.0, None, None, 40.0]
        result = linear_interpolation(series)
        assert result[0] == 10.0
        assert abs(result[1] - 20.0) < 1e-6
        assert abs(result[2] - 30.0) < 1e-6
        assert result[3] == 40.0

    def test_linear_interpolation_no_gaps(self):
        series = [1.0, 2.0, 3.0]
        result = linear_interpolation(series)
        assert result == [1.0, 2.0, 3.0]

    def test_mask_creation(self):
        mask = create_missing_mask(100, missing_rate=0.2, seed=42)
        assert len(mask) == 100
        assert any(mask)
        assert not all(mask)
        assert abs(sum(mask) - 20) <= 5

    def test_mask_deterministic(self):
        m1 = create_missing_mask(100, 0.2, seed=99)
        m2 = create_missing_mask(100, 0.2, seed=99)
        assert m1 == m2

    def test_apply_mask(self):
        gt = [1.0, 2.0, 3.0, 4.0, 5.0]
        mask = [False, True, False, True, False]
        masked = apply_mask(gt, mask)
        assert masked == [1.0, None, 3.0, None, 5.0]

    def test_evaluate_reconstruction_metrics(self):
        gt = [10.0, 20.0, 30.0, 40.0, 50.0]
        recon = [10.0, 22.0, 30.0, 38.0, 50.0]
        mask = [False, True, False, True, False]
        metrics = evaluate_reconstruction(gt, recon, mask)
        assert metrics["evaluated_points"] == 2
        assert abs(metrics["mae"] - 2.0) < 1e-4
        assert abs(metrics["rmse"] - 2.0) < 1e-4
        assert abs(metrics["max_error"] - 2.0) < 1e-4

    def test_no_data_leakage(self):
        gt = [10.0, 15.0, 20.0, 25.0, 30.0]
        mask = [False, True, True, True, False]
        masked = apply_mask(gt, mask)
        recon_locf = locf(masked)
        assert recon_locf[1] == 10.0
        assert recon_locf[2] == 10.0
        assert recon_locf[3] == 10.0

    def test_run_experiment(self):
        gt = [math.sin(i * 0.1) * 10 + 20 for i in range(100)]
        results = run_reconstruction_experiment(gt, missing_rate=0.1, seed=42)
        assert len(results) == 2
        methods = {r.method for r in results}
        assert "locf" in methods
        assert "linear" in methods
        for r in results:
            assert r.mae >= 0
            assert r.rmse >= 0

    def test_multi_rate_experiment(self):
        gt = [10.0 + i * 0.5 for i in range(100)]
        results = run_multi_rate_experiment(gt, rates=[0.1, 0.2], seed=42)
        assert len(results) == 4


# Data Model Tests

class TestModels:
    def test_telemetry_valid(self):
        msg = TelemetryMessage(
            device_id="dev1",
            zone_id="zone_01",
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            water_level_cm=15.0,
            water_level_pct=50.0,
        )
        assert msg.device_id == "dev1"
        assert msg.water_level_pct == 50.0

    def test_telemetry_pct_clamped(self):
        msg = TelemetryMessage(
            device_id="dev1",
            zone_id="zone_01",
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            water_level_pct=150.0,
        )
        assert msg.water_level_pct == 100.0

    def test_telemetry_iso_timestamp(self):
        msg = TelemetryMessage(
            device_id="dev1",
            zone_id="zone_01",
            sequence=1,
            timestamp="2026-10-23T12:00:00Z",
            water_level_pct=50.0,
        )
        assert isinstance(msg.timestamp, datetime)

    def test_telemetry_invalid_device_id(self):
        with pytest.raises(Exception):
            TelemetryMessage(
                device_id="",
                zone_id="zone_01",
                sequence=1,
                timestamp=datetime.now(timezone.utc),
            )


# Storage Tests

class TestStorage:
    def _make_record(self, zone_id="z1", seq=1, level=10.0, pct=33.3):
        return IngestedTelemetry(
            device_id=f"dev_{zone_id}",
            zone_id=zone_id,
            sequence=seq,
            timestamp=datetime.now(timezone.utc),
            water_level_cm=level,
            water_level_pct=pct,
            sensor_status=SensorStatus.VALID,
            source=DataSource.SIMULATOR,
        )

    def test_memory_store_and_query(self):
        store = MemoryStorage()
        rec = self._make_record("z1", 1)
        assert store.store(rec)
        assert store.count() == 1
        latest = store.query_latest("z1")
        assert len(latest) == 1
        assert latest[0]["sequence"] == 1

    def test_memory_duplicate_rejection(self):
        store = MemoryStorage()
        rec = self._make_record("z1", 1)
        assert store.store(rec)
        assert not store.store(rec)
        assert store.count() == 1

    def test_sqlite_store_and_query(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStorage(tmp.name)
            rec = self._make_record("z1", 1)
            assert store.store(rec)
            assert store.count() == 1
            latest = store.query_latest("z1")
            assert len(latest) == 1
            assert latest[0]["sequence"] == 1
            store.close()

    def test_sqlite_duplicate_rejection(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStorage(tmp.name)
            rec = self._make_record("z1", 1)
            assert store.store(rec)
            store.store(rec)
            assert store.count() == 1
            store.close()

    def test_query_all_latest(self):
        store = MemoryStorage()
        store.store(self._make_record("z1", 1))
        store.store(self._make_record("z2", 2))
        all_latest = store.query_all_latest()
        assert "z1" in all_latest
        assert "z2" in all_latest

    def test_storage_fallback_on_unconfigured_influx(self, monkeypatch):
        monkeypatch.setattr(config, "INFLUXDB_ENABLED", False)
        store = create_storage("influxdb")
        assert isinstance(store, SQLiteStorage)
        store.close()


# Ingestion Pipeline Tests

class TestIngestion:
    def test_process_valid_message(self):
        store = MemoryStorage()
        svc = IngestionService(store)
        msg = {
            "device_id": "dev1",
            "zone_id": "zone_01",
            "sequence": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "water_level_cm": 15.0,
            "water_level_pct": 50.0,
            "sensor_status": "valid",
            "source": "simulator",
        }
        result = svc.process_message(msg)
        assert result is not None
        assert svc.stats["messages_valid"] == 1

    def test_reject_invalid_message(self):
        store = MemoryStorage()
        svc = IngestionService(store)
        result = svc.process_message({"bad": "data"})
        assert result is None
        assert svc.stats["messages_invalid"] == 1

    def test_duplicate_detection(self):
        store = MemoryStorage()
        svc = IngestionService(store)
        msg = {
            "device_id": "dev1",
            "zone_id": "zone_01",
            "sequence": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "water_level_pct": 50.0,
        }
        svc.process_message(msg)
        result = svc.process_message(msg)
        assert result is None
        assert svc.stats["messages_duplicate"] == 1

    def test_threshold_alert_generation(self):
        store = MemoryStorage()
        svc = IngestionService(store)
        msg = {
            "device_id": "dev1",
            "zone_id": "zone_01",
            "sequence": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "water_level_pct": 90.0,
            "sensor_status": "valid",
        }
        svc.process_message(msg)
        alerts = svc.alerts
        assert len(alerts) >= 1
        assert alerts[-1].alert_level == AlertLevel.CRITICAL

    def test_health_endpoint(self):
        store = MemoryStorage()
        svc = IngestionService(store)
        health = svc.get_health()
        assert health["status"] == "running"
        assert "stats" in health

    def test_raw_mqtt_processing(self):
        store = MemoryStorage()
        svc = IngestionService(store)
        payload = json.dumps({
            "device_id": "mqtt_dev",
            "zone_id": "zone_01",
            "sequence": 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "water_level_pct": 40.0,
        }).encode("utf-8")
        rec = svc.process_raw("civictwin/v1/zones/zone_01/telemetry", payload)
        assert rec is not None
        assert rec.device_id == "mqtt_dev"


# Threshold Hysteresis Tests

class TestHysteresisAndAlerts:
    def test_hysteresis_prevents_chatter(self):
        store = MemoryStorage()
        svc = IngestionService(store)
        base_time = datetime.now(timezone.utc)

        # Baseline reading: normal
        svc.process_message({
            "device_id": "d1",
            "zone_id": "zone_01",
            "sequence": 1,
            "timestamp": base_time.isoformat(),
            "water_level_pct": 60.0,
        })
        assert len(svc.alerts) == 0

        # Rises to 71.0% (crosses warning threshold of 70%)
        svc.process_message({
            "device_id": "d1",
            "zone_id": "zone_01",
            "sequence": 2,
            "timestamp": (base_time + timedelta(seconds=5)).isoformat(),
            "water_level_pct": 71.0,
        })
        assert len(svc.alerts) == 1
        assert svc.alerts[-1].alert_level == AlertLevel.WARNING

        # Dips slightly to 69.0% (inside hysteresis band: 70 - 3 = 67%)
        svc.process_message({
            "device_id": "d1",
            "zone_id": "zone_01",
            "sequence": 3,
            "timestamp": (base_time + timedelta(seconds=10)).isoformat(),
            "water_level_pct": 69.0,
        })
        # Should stay in warning; no clearing event yet
        assert len(svc.alerts) == 1

        # Rises back to 71.0% - should not create duplicate warning
        svc.process_message({
            "device_id": "d1",
            "zone_id": "zone_01",
            "sequence": 4,
            "timestamp": (base_time + timedelta(seconds=15)).isoformat(),
            "water_level_pct": 71.0,
        })
        assert len(svc.alerts) == 1

        # Drops below clearing threshold (65% < 67%)
        svc.process_message({
            "device_id": "d1",
            "zone_id": "zone_01",
            "sequence": 5,
            "timestamp": (base_time + timedelta(seconds=20)).isoformat(),
            "water_level_pct": 65.0,
        })
        # Alert clears to normal
        assert len(svc.alerts) == 2
        assert svc.alerts[-1].alert_level == AlertLevel.NORMAL


# Failure and Recovery Tests

class TestFailureAndRecovery:
    def test_sensor_dropout_and_recovery(self):
        zone = ZoneModel(zone_id="dropout_zone", zone_name="Dropout Test", baseline_level_cm=10.0)

        r1 = zone.step()
        assert r1.sensor_ok
        assert r1.sensor_status == "valid"

        # Inject failure
        zone.sensor_reliability = 0.0
        r2 = zone.step()
        assert not r2.sensor_ok
        assert r2.sensor_status == "invalid"
        assert r2.observed_level_cm is None

        # Recovery
        zone.sensor_reliability = 1.0
        r3 = zone.step()
        assert r3.sensor_ok
        assert r3.sensor_status == "valid"
        assert r3.observed_level_cm is not None

    def test_network_outage_and_recovery(self):
        zone = ZoneModel(zone_id="net_zone", zone_name="Network Test", baseline_level_cm=10.0)

        # Normal transmission
        r1 = zone.step()
        assert r1.network_ok
        assert r1.sensor_status == "valid"

        # Outage
        zone.network_availability = 0.0
        r2 = zone.step()
        assert not r2.network_ok
        assert r2.sensor_status == "offline"

        # Restoration
        zone.network_availability = 1.0
        r3 = zone.step()
        assert r3.network_ok
        assert r3.sensor_status == "valid"


# Integration Tests

class TestIntegration:
    def test_simulator_to_ingestion_pipeline(self):
        from backend.simulator import SensorSimulator

        store = MemoryStorage()
        svc = IngestionService(store)
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)

        sim = SensorSimulator(
            engine=engine,
            direct_callback=svc.process_message,
        )

        for _ in range(10):
            messages = sim.generate_one_step()
            for msg in messages:
                if msg.get("sensor_status") != "offline":
                    svc.process_message(msg)

        assert store.count() > 0
        assert svc.stats["messages_valid"] > 0

    def test_scenario_produces_data(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)

        ctrl = ScenarioController(engine)
        ctrl.load_scenario("heavy_rainfall")

        max_level = 0
        steps = 0
        while not ctrl.is_complete:
            data = ctrl.step(dt_sec=5.0)
            steps += 1
            for d in data:
                if d["zone_id"] == "zone_01":
                    max_level = max(max_level, d["true_level_pct"])

        assert max_level > 50.0
        assert steps == SCENARIOS["heavy_rainfall"].total_steps


# REST API Endpoints Tests

@pytest.fixture(scope="module")
def api_client():
    with TestClient(app) as test_client:
        yield test_client


class TestApiEndpoints:
    def test_health_endpoint(self, api_client):
        res = api_client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "healthy"
        assert "storage" in data

    def test_config_endpoint(self, api_client):
        res = api_client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert "mqtt_broker" in data
        assert "sensor_warn_pct" in data

    def test_get_zones(self, api_client):
        res = api_client.get("/api/zones")
        assert res.status_code == 200
        data = res.json()
        assert "zones" in data
        assert len(data["zones"]) == 3
        z1 = data["zones"][0]
        assert "water_level_cm" in z1
        assert "water_level_pct" in z1
        assert "alert_level" in z1

    def test_get_single_zone(self, api_client):
        res = api_client.get("/api/zones/zone_01")
        assert res.status_code == 200
        assert res.json()["zone_id"] == "zone_01"

        res_404 = api_client.get("/api/zones/zone_nonexistent")
        assert res_404.status_code == 404

    def test_scenarios_listing(self, api_client):
        res = api_client.get("/api/scenarios")
        assert res.status_code == 200
        scenarios = res.json()["scenarios"]
        assert len(scenarios) == 8

    def test_scenario_execution_lifecycle(self, api_client):
        res_stat = api_client.get("/api/scenarios/status")
        assert res_stat.status_code == 200

        res_start = api_client.post("/api/scenarios/blocked_drain/start")
        assert res_start.status_code == 200
        assert res_start.json()["status"] == "started"

        res_step = api_client.post("/api/scenarios/step?steps=5")
        assert res_step.status_code == 200
        assert res_step.json()["data_points"] > 0

        res_stop = api_client.post("/api/scenarios/blocked_drain/stop")
        assert res_stop.status_code == 200
        assert res_stop.json()["status"] == "stopped"

    def test_telemetry_latest_and_history(self, api_client):
        res_latest = api_client.get("/api/telemetry/latest")
        assert res_latest.status_code == 200

        res_hist = api_client.get("/api/telemetry/history?zone_id=zone_01&minutes=10")
        assert res_hist.status_code == 200
        assert "records" in res_hist.json()

    def test_alerts_endpoint(self, api_client):
        res = api_client.get("/api/alerts")
        assert res.status_code == 200
        assert "alerts" in res.json()

    def test_stats_endpoint(self, api_client):
        res = api_client.get("/api/stats")
        assert res.status_code == 200
        data = res.json()
        assert "storage" in data
        assert "ingestion" in data

    def test_data_export(self, api_client):
        res_json = api_client.get("/api/data/export?format=json")
        assert res_json.status_code == 200
        assert "records" in res_json.json()

        res_csv = api_client.get("/api/data/export?format=csv")
        assert res_csv.status_code == 200
        assert res_csv.json()["status"] == "exported"
