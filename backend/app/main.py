"""
CivicTwin-R — FastAPI Backend Application

Integrates telemetry ingestion, simulation, digital twin physics, and persistence
into a unified REST API for dashboard clients and operational control.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from backend import config
from backend.models import AlertLevel
from backend.storage import create_storage, StorageBackend
from backend.ingestion import IngestionService, MQTTIngestionClient
from backend.simulator import SensorSimulator
from digital_twin.model import DigitalTwinEngine, create_default_zones
from digital_twin.scenarios import ScenarioController, list_scenarios, SCENARIOS
from digital_twin.forecast import BaselineForecaster, evaluate_forecaster_time_aware
from digital_twin.tank_twin import (
    PhysicalTankModel,
    TankGeometry,
    TankCalibrationResult,
    create_default_tanks,
    calibrate_drain_down,
    evaluate_tank_prediction,
)
from scripts.replay_historical import HistoricalReplayController

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.api")

storage: Optional[StorageBackend] = None
ingestion: Optional[IngestionService] = None
mqtt_client: Optional[MQTTIngestionClient] = None
simulator: Optional[SensorSimulator] = None
twin_engine: Optional[DigitalTwinEngine] = None
scenario_ctrl: Optional[ScenarioController] = None
replay_ctrl: Optional[HistoricalReplayController] = None
forecaster = BaselineForecaster()
tanks: dict[str, PhysicalTankModel] = create_default_tanks()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, ingestion, mqtt_client, simulator, twin_engine, scenario_ctrl, replay_ctrl

    logger.info("Initializing CivicTwin-R backend services")

    storage = create_storage()

    twin_engine = DigitalTwinEngine(seed=config.RANDOM_SEED)
    for zone in create_default_zones():
        twin_engine.add_zone(zone)

    scenario_ctrl = ScenarioController(twin_engine)
    ingestion = IngestionService(storage)

    mqtt_client = MQTTIngestionClient(ingestion)
    mqtt_connected = mqtt_client.start()
    if not mqtt_connected:
        logger.info("MQTT broker not reached; continuing in standalone simulation mode")

    simulator = SensorSimulator(
        engine=twin_engine,
        direct_callback=ingestion.process_message,
        interval_sec=config.TWIN_TIME_STEP_SEC,
    )
    simulator.start()

    replay_ctrl = HistoricalReplayController(callback=ingestion.process_message)

    logger.info("CivicTwin-R backend initialized and ready")
    yield

    logger.info("Stopping CivicTwin-R backend services")
    if replay_ctrl:
        replay_ctrl.stop()
    if simulator:
        simulator.stop()
    if mqtt_client:
        mqtt_client.stop()
    if storage:
        storage.close()
    logger.info("CivicTwin-R backend shutdown complete")


app = FastAPI(
    title="CivicTwin-R API",
    description="Cyber-Physical Digital Twin for Flood Monitoring",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    active_storage = storage.backend_type if storage else "none"
    is_fallback = storage.is_fallback if storage else False
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": active_storage,
        "storage_configured": config.STORAGE_BACKEND,
        "storage_fallback_active": is_fallback,
        "mqtt_connected": mqtt_client.is_connected if mqtt_client else False,
        "simulator_running": simulator is not None,
        "records_stored": storage.count() if storage else 0,
        "ingestion": ingestion.get_health() if ingestion else {},
    }


@app.get("/api/config")
def get_config():
    return config.summary()


@app.get("/api/zones")
def get_zones():
    if not twin_engine:
        raise HTTPException(503, "Digital twin engine not initialized")

    states = twin_engine.get_all_states()
    zone_statuses = ingestion.zone_status if ingestion else {}

    for state in states:
        zid = state["zone_id"]
        status = zone_statuses.get(zid, {})
        state["water_level_cm"] = status.get("water_level_cm", state.get("current_level_cm", 0.0))
        state["water_level_pct"] = status.get("water_level_pct", state.get("current_level_pct", 0.0))
        state["current_level_cm"] = state["water_level_cm"]
        state["current_level_pct"] = state["water_level_pct"]
        state["rain_sensor_raw"] = status.get("rain_sensor_raw")
        state["rain_indicator_pct"] = status.get("rain_indicator_pct")
        state["rainfall_measurement_type"] = status.get("rainfall_measurement_type")
        state["sensor_status"] = status.get("sensor_status", "valid")
        state["alert_level"] = status.get("alert_level", "normal")
        state["zone_type"] = "virtual"
        state["data_source"] = status.get("source", "DIGITAL_TWIN")
        state["is_stale"] = status.get("is_stale", False)

    return {"zones": states, "count": len(states)}


@app.get("/api/zones/{zone_id}")
def get_zone(zone_id: str):
    if not twin_engine:
        raise HTTPException(503, "Digital twin engine not initialized")

    state = twin_engine.get_zone_state(zone_id)
    if not state:
        raise HTTPException(404, f"Zone '{zone_id}' not found")

    zone_statuses = ingestion.zone_status if ingestion else {}
    status = zone_statuses.get(zone_id, {})
    state["water_level_cm"] = status.get("water_level_cm", state.get("current_level_cm", 0.0))
    state["water_level_pct"] = status.get("water_level_pct", state.get("current_level_pct", 0.0))
    state["current_level_cm"] = state["water_level_cm"]
    state["current_level_pct"] = state["water_level_pct"]
    state["rain_sensor_raw"] = status.get("rain_sensor_raw")
    state["rain_indicator_pct"] = status.get("rain_indicator_pct")
    state["rainfall_measurement_type"] = status.get("rainfall_measurement_type")
    state["sensor_status"] = status.get("sensor_status", "valid")
    state["alert_level"] = status.get("alert_level", "normal")
    state["zone_type"] = "virtual"
    state["data_source"] = status.get("source", "DIGITAL_TWIN")
    state["is_stale"] = status.get("is_stale", False)

    return state


@app.get("/api/telemetry/latest")
def get_latest_telemetry(zone_id: Optional[str] = None, limit: int = Query(5, ge=1, le=100)):
    if not storage:
        raise HTTPException(503, "Storage not initialized")

    if zone_id:
        records = storage.query_latest(zone_id, limit)
        return {"zone_id": zone_id, "records": records, "count": len(records)}

    all_latest = storage.query_all_latest(limit)
    return {"zones": all_latest}


@app.get("/api/telemetry/history")
def get_telemetry_history(
    zone_id: str,
    minutes: int = Query(30, ge=1, le=1440),
    limit: int = Query(500, ge=1, le=5000),
):
    if not storage:
        raise HTTPException(503, "Storage not initialized")

    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    records = storage.query_range(zone_id, start, end, limit)
    return {
        "zone_id": zone_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "records": records,
        "count": len(records),
    }


@app.get("/api/alerts")
def get_alerts(level: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    if not ingestion:
        raise HTTPException(503, "Ingestion not initialized")

    alerts = ingestion.alerts
    if level:
        try:
            level_enum = AlertLevel(level.lower())
            alerts = [a for a in alerts if a.alert_level == level_enum]
        except ValueError:
            raise HTTPException(400, f"Invalid alert level: {level}")

    alerts = alerts[-limit:]
    return {
        "alerts": [a.model_dump(mode="json") for a in alerts],
        "count": len(alerts),
    }


@app.get("/api/scenarios")
def get_scenarios():
    return {
        "scenarios": list_scenarios(),
        "disclaimer": (
            "Scenario outputs are hypothetical digital-twin model simulations for resilience testing, "
            "not actual future observations or official flood predictions."
        ),
    }


@app.get("/api/scenarios/status")
def get_scenario_status():
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")
    return scenario_ctrl.get_summary()


@app.post("/api/scenarios/{scenario_id}/start")
def start_scenario(scenario_id: str):
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    if scenario_id not in SCENARIOS:
        raise HTTPException(404, f"Scenario '{scenario_id}' not found")

    if scenario_ctrl.is_running:
        raise HTTPException(409, "A scenario is currently active; stop it before starting another")

    success = scenario_ctrl.load_scenario(scenario_id)
    if not success:
        raise HTTPException(500, f"Failed to initialize scenario '{scenario_id}'")

    return {
        "status": "started",
        "scenario_id": scenario_id,
        "total_steps": SCENARIOS[scenario_id].total_steps,
    }


@app.post("/api/scenarios/{scenario_id}/stop")
def stop_scenario(scenario_id: str):
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    scenario_ctrl.stop()
    return {"status": "stopped", "scenario_id": scenario_id}


@app.post("/api/scenarios/step")
def scenario_step(steps: int = Query(1, ge=1, le=100)):
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    if not scenario_ctrl.is_running:
        raise HTTPException(400, "No scenario is currently active")

    all_data = []
    for _ in range(steps):
        if scenario_ctrl.is_complete:
            break
        step_data = scenario_ctrl.step(dt_sec=config.TWIN_TIME_STEP_SEC)
        all_data.extend(step_data)

        if ingestion:
            for msg in step_data:
                ingestion.process_message(msg)

    zones_count = len(twin_engine.zones) if twin_engine and twin_engine.zones else 1
    return {
        "steps_executed": len(all_data) // zones_count,
        "summary": scenario_ctrl.get_summary(),
        "data_points": len(all_data),
    }


@app.get("/api/scenarios/results")
def get_scenario_results():
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    results = scenario_ctrl.get_results()
    return {
        "summary": scenario_ctrl.get_summary(),
        "results_count": len(results),
        "results": results[-500:],
    }


@app.get("/api/experiments/results")
def get_experiment_results():
    results_file = config.TABLES_DIR / "reconstruction_results.json"
    if not results_file.exists():
        return {
            "status": "no_results",
            "message": "Run experiments script first: python3 experiments/run_experiments.py",
        }

    with open(results_file) as f:
        data = json.load(f)
    return {"status": "available", "results": data}


@app.get("/api/stats")
def get_stats():
    return {
        "storage": {
            "backend": storage.backend_type if storage else "none",
            "configured": config.STORAGE_BACKEND,
            "fallback_active": storage.is_fallback if storage else False,
            "total_records": storage.count() if storage else 0,
        },
        "ingestion": ingestion.get_health() if ingestion else {},
        "simulator": simulator.stats if simulator else {},
        "mqtt_connected": mqtt_client.is_connected if mqtt_client else False,
        "scenario": scenario_ctrl.get_summary() if scenario_ctrl else {},
    }


@app.get("/api/data/export")
def export_data(zone_id: Optional[str] = None, format: str = "json"):
    if not storage:
        raise HTTPException(503, "Storage not initialized")

    if format.lower() == "csv":
        filename = f"export_{zone_id or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = config.GENERATED_DIR / filename
        count = storage.export_csv(path, zone_id)
        return {"status": "exported", "path": str(path), "records": count}

    if zone_id:
        records = storage.query_latest(zone_id, limit=1000)
    else:
        all_data = storage.query_all_latest(limit_per_zone=500)
        records = []
        for zone_records in all_data.values():
            records.extend(zone_records)
    return {"records": records, "count": len(records)}


@app.get("/api/forecast/evaluate")
def evaluate_forecast(zone_id: Optional[str] = "zone_01"):
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    if not twin_engine:
        raise HTTPException(503, "Digital twin engine not initialized")

    target_id = twin_engine._resolve_id(zone_id or "zone_01")
    state = twin_engine.get_zone_state(target_id)
    height = state.get("container_height_cm", 30.0) if state else 30.0

    history = storage.query_latest(target_id, limit=200)
    series = [r.get("water_level_cm", 0.0) for r in reversed(history) if r.get("water_level_cm") is not None]
    sources = {r.get("source") for r in history if r.get("source")}

    if len(series) < 20:
        eval_engine = DigitalTwinEngine(seed=config.RANDOM_SEED)
        for z in create_default_zones():
            eval_engine.add_zone(z)
        ctrl = ScenarioController(eval_engine)
        ctrl.load_scenario("heavy_rainfall")
        series = []
        while not ctrl.is_complete:
            data = ctrl.step(dt_sec=5.0)
            for d in data:
                if d["zone_id"] == target_id:
                    series.append(d["true_level_cm"])
        classification = "synthetic"
    else:
        # Determine classification accurately from stored telemetry metadata
        if sources and all(s in ("OBSERVED", "FIELD_SENSOR") for s in sources):
            classification = "observed"
        elif "REPLAYED" in sources:
            classification = "replayed"
        else:
            classification = "synthetic"

    eval_15m = evaluate_forecaster_time_aware(series, height, horizon_steps=3, zone_id=target_id, data_classification=classification)
    eval_60m = evaluate_forecaster_time_aware(series, height, horizon_steps=12, zone_id=target_id, data_classification=classification)

    return {
        "zone_id": target_id,
        "evaluation_horizons": [eval_15m.to_dict(), eval_60m.to_dict()],
        "baseline_comparison": "Naive Persistence (Constant Water Level)",
        "methodology": "Time-aware split; strictly zero future-data leakage.",
        "disclaimer": "Decision-support indicator; not an official flood warning substitute.",
    }


@app.get("/api/forecast/{zone_id}")
def get_forecast(zone_id: str):
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    if not twin_engine:
        raise HTTPException(503, "Digital twin engine not initialized")

    state = twin_engine.get_zone_state(zone_id)
    if not state:
        raise HTTPException(404, f"Zone '{zone_id}' not found")

    target_id = twin_engine._resolve_id(zone_id)
    history = storage.query_latest(target_id, limit=20)
    levels = [r.get("water_level_cm", 0.0) for r in reversed(history) if r.get("water_level_cm") is not None]
    if not levels and state:
        levels = [state.get("current_level_cm", 0.0)]

    height = state.get("container_height_cm", 30.0)
    forecast = forecaster.forecast_zone(
        zone_id=target_id,
        recent_levels_cm=levels,
        container_height_cm=height,
    )
    res = forecast.to_dict()
    res["zone_name"] = state.get("zone_name", "")
    res["subbasin"] = state.get("subbasin", "")
    res["provenance"] = "DIGITAL_TWIN"
    return res


@app.get("/api/replay/status")
def get_replay_status():
    if not replay_ctrl:
        raise HTTPException(503, "Replay controller not initialized")
    return replay_ctrl.get_status()


@app.post("/api/replay/start")
def start_replay(interval_sec: float = Query(1.0, ge=0.1, le=10.0)):
    if not replay_ctrl:
        raise HTTPException(503, "Replay controller not initialized")
    replay_ctrl.start(interval_sec=interval_sec)
    return {"status": "started", "replay": replay_ctrl.get_status()}


@app.post("/api/replay/step")
def step_replay(steps: int = Query(1, ge=1, le=50)):
    if not replay_ctrl:
        raise HTTPException(503, "Replay controller not initialized")
    replayed = []
    for _ in range(steps):
        p = replay_ctrl.step()
        if p is None:
            break
        replayed.append(p)
    return {
        "steps_executed": len(replayed),
        "replay": replay_ctrl.get_status(),
        "sample": replayed[-1] if replayed else None,
    }


@app.post("/api/replay/stop")
def stop_replay():
    if not replay_ctrl:
        raise HTTPException(503, "Replay controller not initialized")
    replay_ctrl.stop()
    return {"status": "stopped", "replay": replay_ctrl.get_status()}


@app.post("/api/replay/reset")
def reset_replay():
    if not replay_ctrl:
        raise HTTPException(503, "Replay controller not initialized")
    replay_ctrl.reset()
    return {"status": "reset", "replay": replay_ctrl.get_status()}


# -------------------------------------------------------------------------
# Node Freshness & Hardware Diagnostics Endpoints
# -------------------------------------------------------------------------


@app.get("/api/nodes/freshness")
def get_all_nodes_freshness():
    """Returns freshness state, last valid timestamp, and age for all monitored nodes."""
    if not ingestion:
        raise HTTPException(503, "Ingestion service not initialized")
    return [report.model_dump() for report in ingestion.get_all_node_freshness()]


@app.get("/api/nodes/{node_id}/freshness")
def get_node_freshness(node_id: str):
    """Returns real-time freshness state for a specific node."""
    if not ingestion:
        raise HTTPException(503, "Ingestion service not initialized")
    return ingestion.get_node_freshness(node_id).model_dump()


@app.get("/api/nodes/status")
def get_all_nodes_status():
    """Returns edge diagnostics, battery levels, RSSI, and boot counts."""
    if not ingestion:
        raise HTTPException(503, "Ingestion service not initialized")
    return ingestion.get_all_node_diagnostics()


# -------------------------------------------------------------------------
# Calibrated Physical Tank Digital Twin Endpoints
# -------------------------------------------------------------------------


class DrainDownCalibrationRequest(BaseModel):
    tank_id: str = Field("tank_01", description="Identifier of the tank to calibrate")
    times_sec: list[float] = Field(..., description="Timestamp offsets in seconds from drain start")
    levels_cm: list[float] = Field(..., description="Water height measurements in cm")
    area_cm2: Optional[float] = Field(None, description="Optional override for cross-sectional area")


@app.get("/api/tank/config")
def get_tank_config():
    """Returns physical specifications and operational parameters for all laboratory tanks."""
    return {tank_id: tank.get_state() for tank_id, tank in tanks.items()}


@app.get("/api/tank/{tank_id}/state")
def get_tank_state(tank_id: str):
    """Returns current state and geometry for a specific laboratory tank."""
    if tank_id not in tanks:
        raise HTTPException(404, f"Tank '{tank_id}' not found. Available: {list(tanks.keys())}")
    return tanks[tank_id].get_state()


@app.post("/api/tank/calibrate")
def calibrate_tank(req: DrainDownCalibrationRequest):
    """
    Performs analytical OLS calibration of the discharge coefficient k using Torricelli's Law:
        2 * A * (sqrt(h0) - sqrt(ht)) = k * t
    """
    if req.tank_id not in tanks:
        raise HTTPException(404, f"Tank '{req.tank_id}' not found")

    tank = tanks[req.tank_id]
    area = req.area_cm2 if req.area_cm2 is not None else tank.geometry.area_cm2
    samples = list(zip(req.times_sec, req.levels_cm))

    result = calibrate_drain_down(samples=samples, area_cm2=area, tank_id=req.tank_id)
    if result.status == "success" and result.calibrated_k > 0:
        tank.drainage_k = result.calibrated_k
        logger.info(
            "Updated tank '%s' drainage_k to %.4f (R^2=%.4f)",
            req.tank_id,
            result.calibrated_k,
            result.r_squared,
        )

    return result.to_dict()


@app.get("/api/tank/predict")
def predict_tank_trajectory(
    tank_id: str = Query("tank_01", description="Tank identifier"),
    duration_sec: float = Query(60.0, ge=1.0, le=3600.0, description="Prediction duration in seconds"),
    dt_sec: float = Query(1.0, ge=0.01, le=10.0, description="Simulation step in seconds"),
    q_in_cm3_s: Optional[float] = Query(None, description="Inlet flow rate (cm^3/s). Defaults to tank default."),
    initial_level_cm: Optional[float] = Query(None, description="Initial level (cm). Defaults to current tank level."),
):
    """Simulates physical water height trajectory forward in time using RK4 numerical integration."""
    if tank_id not in tanks:
        raise HTTPException(404, f"Tank '{tank_id}' not found")
    tank = tanks[tank_id]
    h0 = initial_level_cm if initial_level_cm is not None else tank.current_level_cm
    trajectory = tank.simulate_trajectory(
        duration_sec=duration_sec,
        dt_sec=dt_sec,
        q_in=q_in_cm3_s,
        h0_cm=h0,
    )
    times = [p["time_sec"] for p in trajectory]
    levels = [p["level_cm"] for p in trajectory]
    return {
        "tank_id": tank_id,
        "node_id": tank.geometry.node_id,
        "times_sec": times,
        "predicted_levels_cm": levels,
        "initial_level_cm": h0,
        "q_in_cm3_s": q_in_cm3_s if q_in_cm3_s is not None else tank.default_q_in,
        "drainage_k": tank.drainage_k,
        "area_cm2": tank.geometry.area_cm2,
        "provenance": "TWIN_ESTIMATED",
    }


@app.get("/api/tank/compare")
def compare_tank_prediction_vs_measured(
    tank_id: str = Query("tank_01", description="Tank identifier"),
    limit: int = Query(50, ge=5, le=500, description="Telemetry sample window limit"),
):
    """
    Evaluates digital-twin fidelity by simulating forward from the earliest measurement
    in the window and computing MAE and RMSE against actual stored telemetry.
    """
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    if tank_id not in tanks:
        raise HTTPException(404, f"Tank '{tank_id}' not found")

    tank = tanks[tank_id]
    node_id = tank.geometry.node_id
    records = storage.query_latest(node_id, limit=limit)
    if not records:
        # Fall back to zone_01 / zone_02 if node-specific telemetry is not yet populated
        fallback_zone = "zone_01" if tank_id == "tank_01" else "zone_02"
        records = storage.query_latest(fallback_zone, limit=limit)

    if len(records) < 5:
        # Generate demonstration comparison using calibrated ODE simulation
        trajectory = tank.simulate_trajectory(duration_sec=60.0, dt_sec=2.0)
        times = [p["time_sec"] for p in trajectory]
        measured = [p["level_cm"] for p in trajectory]
        import random
        rng = random.Random(42)
        noisy_measured = [round(max(0.0, m + rng.gauss(0, 0.4)), 2) for m in measured]
        eval_metrics = evaluate_tank_prediction(measured=noisy_measured, predicted=measured)
        eval_metrics["data_source"] = "SIMULATED_DEMO"
        eval_metrics["tank_id"] = tank_id
        eval_metrics["measured_levels_cm"] = noisy_measured
        eval_metrics["predicted_levels_cm"] = measured
        eval_metrics["times_sec"] = times
        return eval_metrics

    chronological = list(reversed(records))
    measured_levels = [r.get("water_level_cm", 0.0) for r in chronological if r.get("water_level_cm") is not None]

    h0 = measured_levels[0]
    dt = 5.0
    duration = dt * (len(measured_levels) - 1)
    trajectory = tank.simulate_trajectory(duration_sec=duration, dt_sec=dt, h0_cm=h0)
    times = [p["time_sec"] for p in trajectory]
    predicted_levels = [p["level_cm"] for p in trajectory]

    eval_metrics = evaluate_tank_prediction(measured=measured_levels, predicted=predicted_levels)
    eval_metrics["data_source"] = chronological[0].get("source", "SIMULATED")
    eval_metrics["tank_id"] = tank_id
    eval_metrics["node_id"] = node_id
    eval_metrics["measured_levels_cm"] = measured_levels
    eval_metrics["predicted_levels_cm"] = predicted_levels[:len(measured_levels)]
    eval_metrics["times_sec"] = times[:len(measured_levels)]
    return eval_metrics

