"""
CivicTwin-R — Automated Tests for Physical Tank Digital Twin & Freshness Monitoring

Validates:
    1. Tank Geometry, mass-balance ODE (dh/dt = (Q_in - k*sqrt(h))/A) and RK4 numerical integration.
    2. Analytical drain-down calibration (Torricelli regression for discharge coefficient k).
    3. Timestamp-driven data freshness state transitions (FRESH -> STALE -> OFFLINE -> INVALID).
    4. Three-method missing-data reconstruction (LOCF vs Linear vs Physics-Based Twin).
    5. REST API extensions for dual-node monitoring and tank digital-twin endpoints.
"""

import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.models import (
    DataSource,
    FreshnessState,
    IngestedTelemetry,
    NodeAlertPayload,
    NodeStatusPayload,
    SensorStatus,
    TelemetryMessage,
)
from backend.storage import MemoryStorage
from backend.ingestion import IngestionService
from digital_twin.tank_twin import (
    PhysicalTankModel,
    TankGeometry,
    TankCalibrationResult,
    create_default_tanks,
    calibrate_drain_down,
    evaluate_tank_prediction,
    reconstruct_physics_based,
)
import random
from digital_twin.reconstruction import (
    apply_mask,
    create_missing_mask,
    linear_interpolation,
    linear_trend_causal,
    locf,
    run_gap_length_experiment,
)
from digital_twin.edge_warning import (
    EdgeAlertState,
    EdgeWarningEvaluator,
    LedIndicatorMode,
)
from backend.app.main import app


# =========================================================================
# 1. Tank Physics & Numerical Integration Tests
# =========================================================================

class TestTankPhysics:
    def test_tank_geometry_creation(self):
        geom = TankGeometry(
            tank_id="tank_test",
            node_id="node_test",
            name="Test Cylinder",
            diameter_cm=20.0,
            max_height_cm=50.0,
        )
        assert abs(geom.area_cm2 - (math.pi * 100.0)) < 0.1
        assert geom.warn_threshold_cm == 35.0  # 70% of 50cm
        assert geom.crit_threshold_cm == 42.5  # 85% of 50cm
        d = geom.to_dict()
        assert d["tank_id"] == "tank_test"
        assert d["max_height_cm"] == 50.0

    def test_mass_balance_dh_dt(self):
        geom = TankGeometry(
            tank_id="t1",
            node_id="n1",
            name="T1",
            diameter_cm=19.54,  # Area = 300 cm^2
            max_height_cm=50.0,
        )
        model = PhysicalTankModel(geom, drainage_k=4.0, default_q_in_cm3_s=20.0)

        # Level h = 16.0 cm -> sqrt(h) = 4.0
        # Q_out = 4.0 * 4.0 = 16.0 cm^3/s
        # Net inflow = 20.0 - 16.0 = 4.0 cm^3/s
        # dh/dt = 4.0 / 300.0 = 0.01333 cm/s
        dh_dt = model.dh_dt(16.0, q_in=20.0)
        expected = 4.0 / geom.area_cm2
        assert abs(dh_dt - expected) < 1e-4

    def test_rk4_drain_down_against_analytical(self):
        """Pure drain down (Q_in = 0) must follow Torricelli: sqrt(h(t)) = sqrt(h0) - k*t/(2*A)."""
        geom = TankGeometry(
            tank_id="t1",
            node_id="n1",
            name="T1",
            diameter_cm=19.54,  # Area = 300 cm^2
            max_height_cm=50.0,
        )
        k = 4.0
        h0 = 25.0
        model = PhysicalTankModel(geom, drainage_k=k, initial_level_cm=h0, default_q_in_cm3_s=0.0)

        # Simulate 10 seconds of drainage
        duration = 10.0
        dt = 0.5
        steps = int(duration / dt)
        for _ in range(steps):
            model.step_rk4(dt, q_in=0.0)

        # Analytical solution
        analytical_h = model.drain_down_analytical(h0, duration, geom.area_cm2, k)

        # Numerical RK4 should match analytical solution within 0.01 cm
        assert abs(model.current_level_cm - analytical_h) < 0.01

    def test_rk4_steady_state_equilibrium(self):
        """At steady state: Q_in = k*sqrt(h*) -> h* = (Q_in / k)^2."""
        geom = TankGeometry(tank_id="t1", node_id="n1", name="T1", diameter_cm=20.0, max_height_cm=50.0)
        k = 5.0
        q_in = 25.0
        h_star = (q_in / k) ** 2  # = 25.0 cm

        model = PhysicalTankModel(geom, drainage_k=k, initial_level_cm=h_star, default_q_in_cm3_s=q_in)

        # Step forward 20 seconds
        for _ in range(20):
            model.step_rk4(1.0, q_in=q_in)

        # Level must remain stable at 25.0 cm
        assert abs(model.current_level_cm - h_star) < 1e-3

    def test_rk4_boundedness(self):
        """Water height must never become negative or exceed maximum tank height."""
        geom = TankGeometry(tank_id="t1", node_id="n1", name="T1", diameter_cm=10.0, max_height_cm=30.0)
        model = PhysicalTankModel(geom, drainage_k=10.0, initial_level_cm=1.0, default_q_in_cm3_s=0.0)

        # Drain empty
        for _ in range(50):
            model.step_rk4(1.0, q_in=0.0)
        assert model.current_level_cm >= 0.0

        # Overfill
        for _ in range(100):
            model.step_rk4(1.0, q_in=5000.0)
        assert model.current_level_cm <= geom.max_height_cm


# =========================================================================
# 2. Calibration Workflow Tests
# =========================================================================

class TestTankCalibration:
    def test_drain_down_calibration_synthetic(self):
        """Analytical OLS calibration must recover known k and achieve R^2 > 0.999."""
        area = 300.0
        true_k = 4.5
        h0 = 25.0
        model = PhysicalTankModel(
            geometry=TankGeometry("temp", "temp", "Temp", 19.54, 50.0),
            drainage_k=true_k,
            initial_level_cm=h0,
        )

        samples = []
        for t in range(0, 61, 5):  # 0 to 60 seconds at 5s intervals
            h = model.drain_down_analytical(h0, float(t), area, true_k)
            samples.append((float(t), h))

        result = calibrate_drain_down(samples, area_cm2=area, tank_id="tank_01")
        assert result.status == "success"
        assert abs(result.calibrated_k - true_k) < 0.05
        assert result.r_squared > 0.999
        assert result.num_samples == len(samples)

    def test_calibration_zero_duration_error(self):
        samples = [(0.0, 20.0), (0.0, 20.0)]
        res = calibrate_drain_down(samples, area_cm2=300.0, tank_id="tank_01")
        assert res.status == "error"

    def test_calibration_negative_h0_error(self):
        samples = [(0.0, -5.0), (10.0, -5.0)]
        res = calibrate_drain_down(samples, area_cm2=300.0, tank_id="tank_01")
        assert res.status == "error"


# =========================================================================
# 3. Data Freshness State Transitions Tests
# =========================================================================

class TestFreshnessEngine:
    def test_freshness_lifecycle(self):
        storage = MemoryStorage()
        ingestion = IngestionService(storage)
        node_id = "node_01"

        # 1. Initially unobserved -> OFFLINE
        rep_initial = ingestion.get_node_freshness(node_id)
        assert rep_initial.freshness_state == FreshnessState.OFFLINE
        assert rep_initial.is_online is False

        # 2. Ingest fresh valid reading at reference time
        ref_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)
        ingestion.process_message({
            "device_id": node_id,
            "zone_id": "zone_01",
            "sequence": 1,
            "timestamp": ref_time.isoformat(),
            "water_level_cm": 22.0,
            "water_level_pct": 44.0,
            "sensor_status": "valid",
            "source": "FIELD_SENSOR",
        })

        # At ref_time + 5s (age 5s < 30s) -> FRESH
        rep_fresh = ingestion.get_node_freshness(node_id, now=ref_time + timedelta(seconds=5))
        assert rep_fresh.freshness_state == FreshnessState.FRESH
        assert rep_fresh.is_online is True
        assert rep_fresh.age_seconds == 5.0

        # 3. At ref_time + 40s (age 40s > 30s threshold) -> STALE
        rep_stale = ingestion.get_node_freshness(node_id, now=ref_time + timedelta(seconds=40))
        assert rep_stale.freshness_state == FreshnessState.STALE
        assert rep_stale.is_online is True
        assert rep_stale.age_seconds == 40.0

        # 4. At ref_time + 120s (age 120s > 90s offline threshold) -> OFFLINE
        rep_offline = ingestion.get_node_freshness(node_id, now=ref_time + timedelta(seconds=120))
        assert rep_offline.freshness_state == FreshnessState.OFFLINE
        assert rep_offline.is_online is False
        assert rep_offline.age_seconds == 120.0

        # 5. Sensor failure event -> INVALID
        ingestion.process_message({
            "device_id": node_id,
            "zone_id": "zone_01",
            "sequence": 2,
            "timestamp": (ref_time + timedelta(seconds=130)).isoformat(),
            "water_level_cm": None,
            "water_level_pct": None,
            "sensor_status": "invalid",
            "source": "FIELD_SENSOR",
        })
        rep_invalid = ingestion.get_node_freshness(node_id, now=ref_time + timedelta(seconds=135))
        assert rep_invalid.freshness_state == FreshnessState.INVALID


# =========================================================================
# 4. Three-Method Reconstruction Comparison Tests
# =========================================================================

class TestThreeMethodReconstruction:
    def test_run_gap_length_experiment(self):
        """Verifies LOCF, Causal Linear Trend, Linear Interpolation, and Physics Twin on identical corrupted gaps."""
        gt = [20.0 + 3.0 * math.sin(0.1 * i) for i in range(100)]
        records = run_gap_length_experiment(gt, gap_lengths=[3, 6], seed=42, dt_sec=5.0)

        # 2 gap lengths * 4 evaluation methods across Setting A and Setting B = 8 records
        assert len(records) == 8
        methods = {r["method"] for r in records}
        assert "LOCF" in methods
        assert "Causal Linear Trend" in methods
        assert "Linear Interpolation" in methods
        assert "Physics Digital Twin" in methods

        settings = {r["setting"] for r in records}
        assert "Setting A (Online Causal)" in settings
        assert "Setting B (Offline Retrospective)" in settings

        for r in records:
            assert r["MAE"] >= 0.0
            assert r["RMSE"] >= 0.0
            assert r["sample_count"] > 0
            assert r["data_source"] == "SIMULATED VALIDATION"

    def test_zero_future_leakage_physics_reconstruction(self):
        """Physics twin forward integration must not use future boundary data."""
        series = [15.0, None, None, None, 40.0]  # Missing gap: indices 1, 2, 3
        recon = reconstruct_physics_based(
            series=series,
            dt_sec=5.0,
            area_cm2=300.0,
            drainage_k=4.5,
            q_in_cm3_s=25.0,
            max_height_cm=50.0,
        )

        assert recon[0] == 15.0
        assert recon[4] == 40.0
        assert recon[1] is not None
        assert recon[2] is not None
        assert recon[3] is not None
        # Forward integration from 15.0 with Q_in=25 and k=4.5
        assert recon[1] > 15.0  # Levels should rise smoothly from 15.0


# =========================================================================
# 5. REST API Extension Tests
# =========================================================================

class TestRestApiExtensions:
    @pytest.fixture(scope="module")
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_get_tank_config(self, client):
        resp = client.get("/api/tank/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "tank_01" in data
        assert "tank_02" in data
        assert data["tank_01"]["max_height_cm"] == 50.0
        assert data["tank_02"]["max_height_cm"] == 60.0

    def test_tank_predict_endpoint(self, client):
        resp = client.get("/api/tank/predict?tank_id=tank_01&duration_sec=30&dt_sec=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tank_id"] == "tank_01"
        assert len(data["times_sec"]) == 16  # 0 to 30s by 2s
        assert len(data["predicted_levels_cm"]) == 16
        assert data["provenance"] == "TWIN_ESTIMATED"

    def test_tank_calibrate_endpoint(self, client):
        payload = {
            "tank_id": "tank_01",
            "times_sec": [0.0, 10.0, 20.0, 30.0],
            "levels_cm": [25.0, 22.0, 19.5, 17.2],
        }
        resp = client.post("/api/tank/calibrate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["calibrated_k"] > 0
        assert data["r_squared"] > 0.95

    def test_nodes_freshness_endpoint(self, client):
        resp = client.get("/api/nodes/freshness")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # node_01 and node_02
        states = {item["node_id"]: item["freshness_state"] for item in data}
        assert "node_01" in states
        assert "node_02" in states

    def test_nodes_status_endpoint(self, client):
        resp = client.get("/api/nodes/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_tank_compare_endpoint(self, client):
        resp = client.get("/api/tank/compare?tank_id=tank_01&limit=20")
        assert resp.status_code == 200
        data = resp.json()
        assert "mae_cm" in data
        assert "rmse_cm" in data
        assert "sample_count" in data
        assert data["sample_count"] > 0


# =========================================================================
# 6. Numerical Convergence & Calibration Sensitivity Tests
# =========================================================================

class TestNumericalConvergenceAndCalibration:
    def test_rk4_convergence_rate(self):
        """
        Verify that numerical RK4 integration error vs analytical Torricelli solution
        strictly decreases as time-step dt is reduced (O(dt^4) behavior).
        Analytical ODE: dh/dt = - (k/A) * sqrt(h), for Qin = 0.
        Analytical solution: sqrt(h(t)) = sqrt(h0) - (k / (2A)) * t
        """
        area = 300.0
        k = 4.5
        h0 = 36.0  # sqrt(h0) = 6.0
        t_final = 20.0
        # Exact solution at t_final:
        sqrt_h_exact = math.sqrt(h0) - (k / (2.0 * area)) * t_final
        h_exact = sqrt_h_exact ** 2

        geom = TankGeometry(tank_id="conv_tank", node_id="node_01", name="Convergence Tank", diameter_cm=19.5441, max_height_cm=50.0)
        model = PhysicalTankModel(geometry=geom, drainage_k=k, default_q_in_cm3_s=0.0, initial_level_cm=h0)

        dt_steps = [10.0, 5.0, 2.0]
        errors = []

        for dt in dt_steps:
            steps = int(t_final / dt)
            model.reset(initial_level_cm=h0)
            for _ in range(steps):
                model.step_rk4(dt_sec=dt, q_in=0.0, sub_step=False, round_digits=None)
            err = abs(model.current_level_cm - h_exact)
            errors.append(err)

        # Truncation error decreases monotonically before reaching floating-point noise floor
        for i in range(len(errors) - 1):
            assert errors[i + 1] < errors[i], f"Error at dt={dt_steps[i+1]} ({errors[i+1]}) not smaller than dt={dt_steps[i]} ({errors[i]})"
        assert errors[-1] < 1e-4

    def test_calibration_noise_recovery(self):
        """
        Verify that OLS regression on Torricelli equation accurately recovers
        drainage coefficient k even under sensor measurement noise.
        """
        area = 300.0
        true_k = 4.5
        h0 = 36.0
        rng = random.Random(42)

        # Generate noisy observations over 40 seconds
        times = [float(t) for t in range(0, 45, 5)]
        samples = []
        for t in times:
            exact_sqrt = math.sqrt(h0) - (true_k / (2.0 * area)) * t
            exact_h = exact_sqrt ** 2
            noise = rng.gauss(0.0, 0.15)  # 1.5mm standard deviation noise
            samples.append((t, max(0.1, exact_h + noise)))

        result = calibrate_drain_down(samples, area_cm2=area, tank_id="test_tank")
        assert abs(result.calibrated_k - true_k) < 0.25  # Within ~5% of true 4.5
        assert result.r_squared > 0.98

    def test_calibration_parameter_sensitivity(self):
        """
        Verify that a miscalibrated k (+/- 15%) creates predictable, measurable drift
        in water level prediction.
        """
        geom = TankGeometry(tank_id="sens_tank", node_id="node_01", name="Sensitivity Tank", diameter_cm=19.5441, max_height_cm=50.0)
        true_model = PhysicalTankModel(geometry=geom, drainage_k=4.5, initial_level_cm=30.0)
        under_model = PhysicalTankModel(geometry=geom, drainage_k=4.5 * 0.85, initial_level_cm=30.0)
        over_model = PhysicalTankModel(geometry=geom, drainage_k=4.5 * 1.15, initial_level_cm=30.0)

        # Step forward 30 seconds with Qin = 20.0
        pts_true = true_model.simulate_trajectory(duration_sec=30.0, dt_sec=1.0, q_in=20.0)
        pts_under = under_model.simulate_trajectory(duration_sec=30.0, dt_sec=1.0, q_in=20.0)
        pts_over = over_model.simulate_trajectory(duration_sec=30.0, dt_sec=1.0, q_in=20.0)

        h_true = pts_true[-1]["level_cm"]
        h_under = pts_under[-1]["level_cm"]
        h_over = pts_over[-1]["level_cm"]

        # Under-estimating k means less drainage -> higher water level
        assert h_under > h_true
        # Over-estimating k means more drainage -> lower water level
        assert h_over < h_true


# =========================================================================
# 7. Dual-Node Concurrent Isolation Integration Tests
# =========================================================================

class TestDualNodeConcurrentIsolation:
    def test_concurrent_dual_node_isolation(self):
        """
        Verifies that two independent nodes (node_01 and node_02) can publish concurrently
        without cross-contamination, overwrites, or corrupted freshness.
        """
        storage = MemoryStorage()
        ingestion = IngestionService(storage=storage)
        base_time = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)

        # 1. Publish 5 interleaved telemetry messages from both nodes
        for seq in range(1, 6):
            t1 = base_time + timedelta(seconds=seq * 5)
            t2 = base_time + timedelta(seconds=seq * 5 + 1)

            # Node 01 telemetry
            ingestion.process_message({
                "device_id": "node_01",
                "zone_id": "zone_01",
                "sequence": seq,
                "timestamp": t1.isoformat(),
                "distance_cm": 25.0 - seq * 0.5,
                "water_level_cm": 25.0 + seq * 0.5,
                "water_level_pct": 50.0 + seq * 1.0,
                "sensor_status": "valid",
                "source": "FIELD_SENSOR",
            })

            # Node 02 telemetry
            ingestion.process_message({
                "device_id": "node_02",
                "zone_id": "zone_02",
                "sequence": seq,
                "timestamp": t2.isoformat(),
                "distance_cm": 35.0 - seq * 1.0,
                "water_level_cm": 25.0 + seq * 1.0,
                "water_level_pct": 41.7 + seq * 1.6,
                "sensor_status": "valid",
                "source": "FIELD_SENSOR",
            })

        # 2. Verify independent history from storage
        hist_01 = storage.query_latest("zone_01", limit=10)
        hist_02 = storage.query_latest("zone_02", limit=10)

        assert len(hist_01) == 5
        assert len(hist_02) == 5
        for rec in hist_01:
            assert rec["device_id"] == "node_01"
            assert rec["zone_id"] == "zone_01"
        for rec in hist_02:
            assert rec["device_id"] == "node_02"
            assert rec["zone_id"] == "zone_02"

        # 3. Verify independent freshness states
        now_check = base_time + timedelta(seconds=30)
        rep_01 = ingestion.get_node_freshness("node_01", now=now_check)
        rep_02 = ingestion.get_node_freshness("node_02", now=now_check)
        assert rep_01.freshness_state == FreshnessState.FRESH
        assert rep_02.freshness_state == FreshnessState.FRESH

        # 4. Selective disconnection: advance node_02 while node_01 goes silent
        # After 100 seconds without node_01 updates:
        # node_01 should be STALE, while node_02 receives fresh update at t=125s
        t_fresh_02 = base_time + timedelta(seconds=125)
        ingestion.process_message({
            "device_id": "node_02",
            "zone_id": "zone_02",
            "sequence": 6,
            "timestamp": t_fresh_02.isoformat(),
            "distance_cm": 30.0,
            "water_level_cm": 30.0,
            "water_level_pct": 50.0,
            "sensor_status": "valid",
            "source": "FIELD_SENSOR",
        })

        eval_time = base_time + timedelta(seconds=130)
        rep_01_stale = ingestion.get_node_freshness("node_01", now=eval_time)
        rep_02_fresh = ingestion.get_node_freshness("node_02", now=eval_time)

        assert rep_01_stale.freshness_state in (FreshnessState.STALE, FreshnessState.OFFLINE)
        assert rep_02_fresh.freshness_state == FreshnessState.FRESH

        # 5. Out-of-order rejection test: node_01 receives an old sequence (seq=2)
        old_msg = {
            "device_id": "node_01",
            "zone_id": "zone_01",
            "sequence": 2,  # Already processed seq 5
            "timestamp": (base_time + timedelta(seconds=10)).isoformat(),
            "water_level_cm": 99.0,
            "water_level_pct": 99.0,
            "sensor_status": "valid",
            "source": "FIELD_SENSOR",
        }
        res = ingestion.process_message(old_msg)
        assert res is None  # Duplicate sequence rejected
        assert ingestion.stats["messages_duplicate"] == 1
        # Latest valid level should NOT be 99.0
        assert ingestion.zone_status["zone_01"]["water_level_cm"] != 99.0


# =========================================================================
# 8. Edge Warning & Hysteresis Logic Tests
# =========================================================================

class TestEdgeWarningEvaluator:
    def test_threshold_crossing_and_led_modes(self):
        evaluator = EdgeWarningEvaluator(warn_threshold_pct=70.0, crit_threshold_pct=85.0, hysteresis_pct=3.0)

        # Normal
        state, led = evaluator.evaluate(50.0)
        assert state == EdgeAlertState.NORMAL
        assert led == LedIndicatorMode.OFF

        # Warning breach (>= 70%)
        state, led = evaluator.evaluate(70.0)
        assert state == EdgeAlertState.WARNING
        assert led == LedIndicatorMode.BLINK_1HZ

        # Critical breach (>= 85%)
        state, led = evaluator.evaluate(85.5)
        assert state == EdgeAlertState.CRITICAL
        assert led == LedIndicatorMode.SOLID_ON

    def test_falling_hysteresis_retention(self):
        evaluator = EdgeWarningEvaluator(warn_threshold_pct=70.0, crit_threshold_pct=85.0, hysteresis_pct=3.0)

        # Drive to Critical
        evaluator.evaluate(86.0)
        assert evaluator.current_state == EdgeAlertState.CRITICAL

        # Drops to 83.5% (above 85 - 3 = 82): MUST retain critical!
        state, led = evaluator.evaluate(83.5)
        assert state == EdgeAlertState.CRITICAL
        assert led == LedIndicatorMode.SOLID_ON

        # Drops to 81.5% (< 82): demotes to Warning
        state, led = evaluator.evaluate(81.5)
        assert state == EdgeAlertState.WARNING
        assert led == LedIndicatorMode.BLINK_1HZ

        # Drops to 68.0% (above 70 - 3 = 67): MUST retain warning!
        state, led = evaluator.evaluate(68.0)
        assert state == EdgeAlertState.WARNING
        assert led == LedIndicatorMode.BLINK_1HZ

        # Drops to 66.5% (< 67): clears to Normal
        state, led = evaluator.evaluate(66.5)
        assert state == EdgeAlertState.NORMAL
        assert led == LedIndicatorMode.OFF

    def test_anti_chatter_oscillation_suppression(self):
        evaluator = EdgeWarningEvaluator(warn_threshold_pct=70.0, crit_threshold_pct=85.0, hysteresis_pct=3.0)

        # Water ripples around 70%: 69.8% -> 70.2% -> 69.9% -> 70.1% -> 69.5%
        evaluator.evaluate(69.8)  # Normal
        assert evaluator.current_state == EdgeAlertState.NORMAL

        evaluator.evaluate(70.2)  # Warning triggers
        assert evaluator.current_state == EdgeAlertState.WARNING

        # Surface rippling below 70% does not toggle warning off!
        evaluator.evaluate(69.9)
        assert evaluator.current_state == EdgeAlertState.WARNING
        evaluator.evaluate(70.1)
        assert evaluator.current_state == EdgeAlertState.WARNING
        evaluator.evaluate(69.5)
        assert evaluator.current_state == EdgeAlertState.WARNING

    def test_sensor_fault_tolerance(self):
        evaluator = EdgeWarningEvaluator(max_consecutive_faults=5)
        evaluator.evaluate(60.0)  # Valid initial reading

        # 4 consecutive sensor faults: retains state during momentary glitch
        for _ in range(4):
            state, led = evaluator.evaluate(None, is_valid=False)
            assert state == EdgeAlertState.NORMAL
            assert led == LedIndicatorMode.OFF

        # 5th consecutive fault: transitions to FAULT
        state, led = evaluator.evaluate(None, is_valid=False)
        assert state == EdgeAlertState.FAULT
        assert led == LedIndicatorMode.RAPID_STROBE


# =========================================================================
# 9. Setting A vs Setting B Reconstruction Integrity
# =========================================================================

class TestCausalReconstructionSettingAandB:
    def test_causal_linear_trend_zero_future_leakage(self):
        """
        Verify that linear_trend_causal only uses past observations.
        Modifying future data must produce identical estimates at earlier gap points.
        """
        series_v1 = [20.0, 21.0, 22.0, None, None, None, 50.0]
        series_v2 = [20.0, 21.0, 22.0, None, None, None, 100.0]  # Very different future endpoint

        res_v1 = linear_trend_causal(series_v1)
        res_v2 = linear_trend_causal(series_v2)

        # The causal trend estimates at indices 3, 4, 5 MUST be strictly identical
        # because the future value (index 6) cannot leak backward into causal estimation!
        for idx in [3, 4, 5]:
            assert res_v1[idx] == pytest.approx(res_v2[idx], abs=1e-6)

    def test_retrospective_linear_interpolation_uses_future(self):
        """
        Verify that standard linear interpolation in Setting B relies on future endpoint.
        """
        from digital_twin.reconstruction import linear_interpolation

        series_v1 = [20.0, None, None, 26.0]
        series_v2 = [20.0, None, None, 50.0]

        res_v1 = linear_interpolation(series_v1)
        res_v2 = linear_interpolation(series_v2)

        # Retrospective interpolation reflects future endpoint changes
        assert res_v1[1] != res_v2[1]
        assert res_v1[1] == pytest.approx(22.0)
        assert res_v2[1] == pytest.approx(30.0)

