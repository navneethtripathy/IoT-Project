"""
CivicTwin-R — Test Suite

Comprehensive tests for the digital twin engine, reconstruction module,
storage layer, ingestion service, and data models.

Run with:
    cd CivicTwin-R
    python -m pytest tests/ -v
"""

import json
import math
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

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
    DataSource, AlertLevel, ZoneConfig,
)
from backend.storage import MemoryStorage, SQLiteStorage
from backend.ingestion import IngestionService


# ══════════════════════════════════════════════════════════
# DIGITAL TWIN MODEL TESTS
# ══════════════════════════════════════════════════════════

class TestZoneModel:
    """Tests for the ZoneModel discrete-time simulation."""

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
        reading = zone.step(dt_sec=5.0)
        assert zone.current_level_cm < 20.0

    def test_inflow_increases_level(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            baseline_level_cm=5.0,
            inflow_rate=2.0,
            drainage_capacity=0.0,
        )
        reading = zone.step(dt_sec=5.0)
        assert zone.current_level_cm > 5.0

    def test_level_clamped_at_zero(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            baseline_level_cm=0.5,
            inflow_rate=0.0,
            drainage_capacity=10.0,  # Much higher than level
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
            sensor_reliability=0.0,  # Always fails
        )
        reading = zone.step()
        assert not reading.sensor_ok
        assert reading.observed_level_cm is None
        assert reading.sensor_status == "invalid"

    def test_network_failure_simulation(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            network_availability=0.0,  # Always fails
        )
        reading = zone.step()
        assert not reading.network_ok
        assert reading.sensor_status == "offline"

    def test_reset(self):
        zone = ZoneModel(zone_id="test", zone_name="Test", baseline_level_cm=10.0)
        zone.step()
        zone.step()
        zone.reset(seed=42)
        assert zone.current_level_cm == 10.0
        assert zone.step_count == 0

    def test_alert_levels(self):
        zone = ZoneModel(
            zone_id="test", zone_name="Test",
            container_height_cm=100.0,
            baseline_level_cm=90.0,  # 90% fill
            inflow_rate=0.0,
            drainage_capacity=0.0,
            warn_threshold_pct=70.0,
            crit_threshold_pct=85.0,
        )
        reading = zone.step()
        assert reading.alert_level == "critical"


class TestDigitalTwinEngine:
    """Tests for the multi-zone engine."""

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
        """Same seed produces same results."""
        def run(seed):
            engine = DigitalTwinEngine(seed=seed)
            for z in create_default_zones():
                engine.add_zone(z)
            results = []
            for _ in range(50):
                readings = engine.step_all(dt_sec=5.0)
                for r in readings:
                    results.append(r.true_level_cm)
            return results

        r1 = run(42)
        r2 = run(42)
        assert r1 == r2

    def test_get_zone_state(self):
        engine = DigitalTwinEngine(seed=42)
        engine.add_zone(ZoneModel(zone_id="z1", zone_name="Zone 1"))
        engine.step_all()
        state = engine.get_zone_state("z1")
        assert state is not None
        assert "current_level_cm" in state

    def test_apply_scenario_params(self):
        engine = DigitalTwinEngine(seed=42)
        zone = ZoneModel(zone_id="z1", zone_name="Zone 1", inflow_rate=0.1)
        engine.add_zone(zone)
        engine.apply_scenario_params("z1", inflow_rate=5.0)
        assert engine.zones["z1"].inflow_rate == 5.0


# ══════════════════════════════════════════════════════════
# SCENARIO TESTS
# ══════════════════════════════════════════════════════════

class TestScenarios:
    """Tests for scenario definitions and controller."""

    def test_all_scenarios_defined(self):
        expected = {
            "normal", "heavy_rainfall", "blocked_drain", "sudden_rise",
            "sensor_dropout", "noisy_sensor", "network_outage", "multi_zone_stress",
        }
        assert set(SCENARIOS.keys()) == expected

    def test_list_scenarios(self):
        result = list_scenarios()
        assert len(result) == 8
        for s in result:
            assert "scenario_id" in s
            assert "name" in s

    def test_scenario_controller_load(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        ctrl = ScenarioController(engine)
        assert ctrl.load_scenario("normal")
        assert ctrl.is_running
        assert not ctrl.is_complete

    def test_scenario_runs_to_completion(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        ctrl = ScenarioController(engine)
        ctrl.load_scenario("normal")

        while not ctrl.is_complete:
            data = ctrl.step(dt_sec=5.0)
            assert len(data) > 0

        assert ctrl.is_complete
        assert not ctrl.is_running
        results = ctrl.get_results()
        assert len(results) > 0

    def test_scenario_stop(self):
        engine = DigitalTwinEngine(seed=42)
        for z in create_default_zones():
            engine.add_zone(z)
        ctrl = ScenarioController(engine)
        ctrl.load_scenario("heavy_rainfall")
        ctrl.step()
        ctrl.stop()
        assert not ctrl.is_running

    def test_invalid_scenario(self):
        engine = DigitalTwinEngine(seed=42)
        ctrl = ScenarioController(engine)
        assert not ctrl.load_scenario("nonexistent")


# ══════════════════════════════════════════════════════════
# RECONSTRUCTION TESTS
# ══════════════════════════════════════════════════════════

class TestReconstruction:
    """Tests for missing-data reconstruction methods."""

    def test_locf_basic(self):
        series = [1.0, None, None, 4.0, None, 6.0]
        result = locf(series)
        assert result == [1.0, 1.0, 1.0, 4.0, 4.0, 6.0]

    def test_locf_leading_none(self):
        series = [None, None, 3.0, None]
        result = locf(series)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == 3.0
        assert result[3] == 3.0

    def test_linear_interpolation_basic(self):
        series = [0.0, None, None, 6.0]
        result = linear_interpolation(series)
        assert result[0] == 0.0
        assert abs(result[1] - 2.0) < 0.01
        assert abs(result[2] - 4.0) < 0.01
        assert result[3] == 6.0

    def test_linear_interpolation_no_gaps(self):
        series = [1.0, 2.0, 3.0, 4.0]
        result = linear_interpolation(series)
        assert result == series

    def test_mask_creation(self):
        mask = create_missing_mask(100, 0.20, seed=42)
        assert len(mask) == 100
        assert sum(mask) > 0
        assert sum(mask) <= 25  # Allow some variance

    def test_mask_deterministic(self):
        m1 = create_missing_mask(100, 0.10, seed=42)
        m2 = create_missing_mask(100, 0.10, seed=42)
        assert m1 == m2

    def test_apply_mask(self):
        gt = [1.0, 2.0, 3.0, 4.0, 5.0]
        mask = [False, True, False, True, False]
        result = apply_mask(gt, mask)
        assert result == [1.0, None, 3.0, None, 5.0]

    def test_evaluate_reconstruction_metrics(self):
        gt = [1.0, 2.0, 3.0, 4.0, 5.0]
        recon = [1.0, 1.5, 3.0, 3.5, 5.0]  # Errors at masked positions
        mask = [False, True, False, True, False]
        result = evaluate_reconstruction(gt, recon, mask)
        assert result["evaluated_points"] == 2
        assert result["mae"] == 0.5  # (0.5 + 0.5) / 2
        assert result["rmse"] == 0.5

    def test_no_data_leakage(self):
        """Ensure reconstruction doesn't see hidden values."""
        gt = [10.0, 20.0, 30.0, 40.0, 50.0]
        mask = [False, True, True, True, False]
        masked = apply_mask(gt, mask)

        # LOCF should carry 10.0 forward, not use 20/30/40
        result = locf(masked)
        assert result[1] == 10.0  # Carried from index 0
        assert result[2] == 10.0
        assert result[3] == 10.0

    def test_run_experiment(self):
        gt = list(range(100))  # Simple linearly increasing
        results = run_reconstruction_experiment(gt, missing_rate=0.10, seed=42)
        assert len(results) == 2  # LOCF and Linear
        for r in results:
            assert r.evaluated_points > 0
            assert r.mae >= 0
            assert r.rmse >= 0

    def test_multi_rate_experiment(self):
        gt = [float(i) for i in range(200)]
        results = run_multi_rate_experiment(gt, seed=42)
        assert len(results) == 8  # 4 rates × 2 methods


# ══════════════════════════════════════════════════════════
# DATA MODEL TESTS
# ══════════════════════════════════════════════════════════

class TestModels:
    """Tests for Pydantic data models."""

    def test_telemetry_valid(self):
        msg = TelemetryMessage(
            device_id="node_01",
            zone_id="zone_01",
            sequence=1,
            timestamp=datetime.now(timezone.utc),
            distance_cm=12.5,
            water_level_cm=17.5,
            water_level_pct=58.3,
        )
        assert msg.schema_version == "1.0"
        assert msg.sensor_status == SensorStatus.VALID

    def test_telemetry_pct_clamped(self):
        msg = TelemetryMessage(
            device_id="n1", zone_id="z1", sequence=1,
            timestamp=datetime.now(timezone.utc),
            water_level_pct=150.0,
        )
        assert msg.water_level_pct == 100.0

    def test_telemetry_iso_timestamp(self):
        msg = TelemetryMessage(
            device_id="n1", zone_id="z1", sequence=1,
            timestamp="2026-01-15T10:30:00Z",
        )
        assert msg.timestamp.year == 2026

    def test_telemetry_invalid_device_id(self):
        with pytest.raises(Exception):
            TelemetryMessage(
                device_id="", zone_id="z1", sequence=1,
                timestamp=datetime.now(timezone.utc),
            )


# ══════════════════════════════════════════════════════════
# STORAGE TESTS
# ══════════════════════════════════════════════════════════

class TestStorage:
    """Tests for storage backends."""

    def _make_record(self, zone_id="z1", seq=1) -> IngestedTelemetry:
        return IngestedTelemetry(
            device_id="dev1",
            zone_id=zone_id,
            sequence=seq,
            timestamp=datetime.now(timezone.utc),
            distance_cm=10.0,
            water_level_cm=20.0,
            water_level_pct=66.7,
            source=DataSource.SIMULATOR,
        )

    def test_memory_store_and_query(self):
        store = MemoryStorage()
        r = self._make_record()
        assert store.store(r)
        assert store.count() == 1
        latest = store.query_latest("z1")
        assert len(latest) == 1

    def test_memory_duplicate_rejection(self):
        store = MemoryStorage()
        r1 = self._make_record(seq=1)
        r2 = self._make_record(seq=1)  # Same device + sequence
        assert store.store(r1)
        assert not store.store(r2)  # Duplicate
        assert store.count() == 1

    def test_sqlite_store_and_query(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SQLiteStorage(db_path)
            r = self._make_record()
            assert store.store(r)
            assert store.count() == 1
            latest = store.query_latest("z1")
            assert len(latest) == 1
            store.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_sqlite_duplicate_rejection(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store = SQLiteStorage(db_path)
            r1 = self._make_record(seq=1)
            r2 = self._make_record(seq=1)
            assert store.store(r1)
            assert store.store(r2)  # INSERT OR IGNORE returns True but ignores
            assert store.count() == 1  # Only one record
            store.close()
        finally:
            Path(db_path).unlink(missing_ok=True)

    def test_query_all_latest(self):
        store = MemoryStorage()
        store.store(self._make_record("z1", 1))
        store.store(self._make_record("z2", 2))
        all_latest = store.query_all_latest()
        assert "z1" in all_latest
        assert "z2" in all_latest


# ══════════════════════════════════════════════════════════
# INGESTION TESTS
# ══════════════════════════════════════════════════════════

class TestIngestion:
    """Tests for the ingestion service."""

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
        result = svc.process_message(msg)  # Duplicate
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
            "water_level_pct": 90.0,  # Above critical threshold
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


# ══════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ══════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end tests combining multiple components."""

    def test_simulator_to_ingestion_pipeline(self):
        """Verify data flows from simulator through ingestion to storage."""
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

        # Generate 10 steps and feed messages through ingestion
        for _ in range(10):
            messages = sim.generate_one_step()
            for msg in messages:
                # Simulate what _publish does for direct callback
                if msg.get("sensor_status") != "offline":
                    svc.process_message(msg)

        assert store.count() > 0
        assert svc.stats["messages_valid"] > 0

    def test_scenario_produces_data(self):
        """Verify scenarios produce expected data patterns."""
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

        # Heavy rainfall should cause significant water rise
        assert max_level > 50.0  # Should rise above 50%
        assert steps == SCENARIOS["heavy_rainfall"].total_steps
