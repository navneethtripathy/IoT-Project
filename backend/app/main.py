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
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

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
    create_default_tanks,
    calibrate_drain_down,
    evaluate_tank_prediction,
    evaluate_telemetry_window,
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

    if config.ENABLE_INTERNAL_SIMULATOR or (not mqtt_connected):
        simulator = SensorSimulator(
            engine=twin_engine,
            direct_callback=ingestion.process_message,
            interval_sec=config.TWIN_TIME_STEP_SEC,
        )
        simulator.start()
        logger.info("Internal sensor simulator started (standalone fallback)")
    else:
        logger.info("Internal sensor simulator disabled; relying on native MQTT simulation / physical hardware")

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

_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/health")
def health():
    active_storage = storage.backend_type if storage else "none"
    is_fallback = storage.is_fallback if storage else False
    influx_active = False
    if storage and hasattr(storage, "secondary_storage") and storage.secondary_storage:
        influx_active = True
    elif storage and storage.backend_type == "influxdb":
        influx_active = True

    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": active_storage,
        "storage_configured": config.STORAGE_BACKEND,
        "storage_fallback_active": is_fallback,
        "influxdb_enabled": config.INFLUXDB_ENABLED,
        "influxdb_active": influx_active,
        "influxdb_url": config.INFLUXDB_URL,
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
        except ValueError as err:
            raise HTTPException(400, f"Invalid alert level: {level}") from err

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
    samples = list(zip(req.times_sec, req.levels_cm, strict=False))

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
    q_in_cm3_s: Optional[float] = Query(None, description="Optional inlet flow override"),
):
    """
    Evaluates digital-twin fidelity against stored telemetry chronologically using causal
    inter-sample timestamps and piecewise past inflow rates, reporting both one-step tracking
    and contiguous multi-step prediction metrics plus historical discrepancy audit context.
    """
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    if tank_id not in tanks:
        raise HTTPException(404, f"Tank '{tank_id}' not found")

    tank = tanks[tank_id]
    node_id = tank.geometry.node_id
    records = storage.query_latest(node_id, limit=min(500, max(limit, 80)))
    if not records:
        fallback_zone = "zone_01" if tank_id == "tank_01" else "zone_02"
        records = storage.query_latest(fallback_zone, limit=limit)

    evaluated = evaluate_telemetry_window(tank=tank, records=records, q_in_override=q_in_cm3_s)
    if not evaluated.get("insufficient_records", True):
        evaluated.pop("insufficient_records", None)
        return evaluated

    # Fallback demonstration trajectory when DB holds fewer than 3 valid contiguous tank records
    trajectory = tank.simulate_trajectory(duration_sec=60.0, dt_sec=2.0, q_in=q_in_cm3_s)
    times = [p["time_sec"] for p in trajectory]
    measured = [p["level_cm"] for p in trajectory]
    import random
    rng = random.Random(42)
    noisy_measured = [round(max(0.0, m + rng.gauss(0, 0.4)), 2) for m in measured]
    eval_metrics = evaluate_tank_prediction(measured=noisy_measured, predicted=measured)
    eval_metrics["data_source"] = "SIMULATED_DEMO"
    eval_metrics["tank_id"] = tank_id
    eval_metrics["node_id"] = node_id
    eval_metrics["measured_levels_cm"] = noisy_measured
    eval_metrics["predicted_levels_cm"] = measured
    eval_metrics["times_sec"] = times
    eval_metrics["q_in_cm3_s"] = round(q_in_cm3_s if q_in_cm3_s is not None else tank.default_q_in, 2)
    eval_metrics["one_step_tracking"] = evaluate_tank_prediction(measured=noisy_measured[1:], predicted=measured[1:])
    eval_metrics["multi_step_prediction"] = dict(eval_metrics)
    eval_metrics["physical_validation"] = "unavailable (virtual simulator stream only — no physical sensor hardware deployed)"
    return eval_metrics


# -------------------------------------------------------------------------
# Showcase Control Center Endpoints & Web UI
# -------------------------------------------------------------------------

SHOWCASE_HTML_PATH = Path(__file__).resolve().parent / "templates" / "showcase.html"
URBAN_TWIN_HTML_PATH = Path(__file__).resolve().parent / "templates" / "urban_twin.html"
SIMULATOR_CONTROL_FILE = config._PROJECT_ROOT / ".run" / "simulator_control.json"


@app.get("/api/mqtt/recent-messages")
def get_recent_mqtt_messages(limit: int = Query(50, ge=1, le=100)):
    """Returns most recent incoming MQTT messages received by IngestionService."""
    if not ingestion:
        raise HTTPException(503, "Ingestion service not initialized")
    return ingestion.get_recent_mqtt_messages(limit=limit)


@app.get("/api/database/tables")
def get_database_tables():
    """Returns list of tables in active storage backend."""
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    tables = storage.get_table_names()
    table_info = []
    for t in tables:
        schema = storage.get_table_schema(t)
        count = storage.count() if t == "telemetry" else 0
        table_info.append({"name": t, "columns": len(schema), "rows": count, "schema": schema})
    return {"tables": table_info, "backend": storage.backend_type}


@app.get("/api/database/records")
def get_database_records(
    table: str = Query("telemetry", description="Table name"),
    zone_id: Optional[str] = Query(None, description="Optional zone filter"),
    device_id: Optional[str] = Query(None, description="Optional device filter"),
    limit: int = Query(50, ge=1, le=200, description="Records limit"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Returns paginated database records for local inspection."""
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    return storage.query_records_paginated(
        table_name=table,
        zone_id=zone_id,
        device_id=device_id,
        limit=limit,
        offset=offset,
    )


@app.get("/api/database/stats")
def get_database_stats():
    """Returns storage statistics and database metadata."""
    if not storage:
        raise HTTPException(503, "Storage not initialized")
    return storage.get_database_stats()


@app.get("/api/storage/influx/status")
def get_influx_status():
    """Returns InfluxDB connectivity and bucket status."""
    secondary = getattr(storage, "secondary_storage", None)
    target = secondary if secondary else (storage if storage and storage.backend_type == "influxdb" else None)
    if not target or not hasattr(target, "is_healthy"):
        return {
            "status": "disabled" if not config.INFLUXDB_ENABLED else "not_configured",
            "connected": False,
            "url": config.INFLUXDB_URL,
            "org": config.INFLUXDB_ORG,
            "bucket": config.INFLUXDB_BUCKET,
        }
    healthy = target.is_healthy()
    record_count = target.count() if healthy else 0
    return {
        "status": "connected" if healthy else "unhealthy",
        "connected": healthy,
        "url": config.INFLUXDB_URL,
        "org": config.INFLUXDB_ORG,
        "bucket": config.INFLUXDB_BUCKET,
        "records_count": record_count,
    }


@app.get("/api/storage/influx/latest")
def get_influx_latest(
    zone_id: Optional[str] = Query(None, description="Optional zone or device ID"),
    limit: int = Query(10, ge=1, le=100)
):
    """Queries telemetry directly from InfluxDB 2.x."""
    secondary = getattr(storage, "secondary_storage", None)
    target = secondary if secondary else (storage if storage and storage.backend_type == "influxdb" else None)
    if not target or not hasattr(target, "query_latest"):
        raise HTTPException(503, "InfluxDB storage backend not active")
    if zone_id:
        records = target.query_latest(zone_id, limit=limit)
    else:
        grouped = target.query_all_latest(limit_per_zone=limit)
        records = []
        for r_list in grouped.values():
            records.extend(r_list)
    return {"backend": "influxdb", "count": len(records), "records": records}


@app.get("/api/services/status")
def get_services_status():
    """Live runtime status checks for every service (no hardcoded placeholder greens)."""
    import socket

    # 1. MQTT TCP & client check
    mqtt_tcp_up = False
    try:
        with socket.create_connection((config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT), timeout=0.4):
            mqtt_tcp_up = True
    except OSError:
        mqtt_tcp_up = False

    # 2. InfluxDB live check
    sec = getattr(storage, "secondary_storage", None) if storage else None
    influx_target = sec if sec else (storage if storage and storage.backend_type == "influxdb" else None)
    influx_ok = bool(influx_target and hasattr(influx_target, "is_healthy") and influx_target.is_healthy())
    influx_count = influx_target.count() if influx_ok else 0

    # 3. Node-RED HTTP UI check
    import httpx
    nodered_ok = False
    nodered_editor_ok = False
    nr_base = f"http://127.0.0.1:{config.NODERED_PORT}"
    for path_probe, flag in [("/ui/", "ui"), ("/", "ed")]:
        try:
            resp = httpx.get(f"{nr_base}{path_probe}", timeout=0.5, follow_redirects=False)
            if resp.status_code < 400:
                if flag == "ui":
                    nodered_ok = True
                else:
                    nodered_editor_ok = True
        except (OSError, httpx.HTTPError) as e:
            logger.debug("Node-RED probe %s skipped: %s", path_probe, e)

    # 4. Simulator health via ingestion stats & node freshness
    ing_health = ingestion.get_health() if ingestion else {}
    msg_count = ing_health.get("stats", {}).get("messages_valid", 0)
    db_stats = storage.get_database_stats() if storage else {}

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "fastapi": {
                "status": "online",
                "url": f"http://{config.API_HOST}:{config.API_PORT}",
                "docs_url": f"http://{config.API_HOST}:{config.API_PORT}/docs",
            },
            "mqtt_broker": {
                "status": "connected" if (mqtt_client and mqtt_client.is_connected and mqtt_tcp_up) else ("reachable" if mqtt_tcp_up else "offline"),
                "host": config.MQTT_BROKER_HOST,
                "port": config.MQTT_BROKER_PORT,
                "client_connected": bool(mqtt_client and mqtt_client.is_connected),
                "tcp_reachable": mqtt_tcp_up,
            },
            "sqlite": {
                "status": "online" if storage else "offline",
                "records_stored": storage.count() if storage else 0,
                "db_size_kb": db_stats.get("size_kb", db_stats.get("file_size_kb", 0)),
            },
            "influxdb": {
                "status": "connected" if influx_ok else ("disabled" if not config.INFLUXDB_ENABLED else "offline"),
                "connected": influx_ok,
                "url": config.INFLUXDB_URL,
                "bucket": config.INFLUXDB_BUCKET,
                "records_count": influx_count,
            },
            "nodered": {
                "status": "online" if (nodered_ok or nodered_editor_ok) else "offline",
                "dashboard_reachable": nodered_ok,
                "editor_reachable": nodered_editor_ok,
                "ui_url": f"http://127.0.0.1:{config.NODERED_PORT}/ui/",
                "editor_url": f"http://127.0.0.1:{config.NODERED_PORT}/",
            },
            "simulator": {
                "status": "active" if (simulator is not None or msg_count > 0) else "idle",
                "internal_fallback_running": simulator is not None,
                "valid_messages_ingested": msg_count,
            },
        },
    }


@app.get("/urban-twin", response_class=HTMLResponse)
def get_urban_twin_page():
    """Serves the offline-first Chennai Urban 3D Digital Twin Command Center."""
    if not URBAN_TWIN_HTML_PATH.exists():
        raise HTTPException(404, "Chennai urban twin template not found")
    return FileResponse(URBAN_TWIN_HTML_PATH)


_GEO_PROCESSED_DIR = config.GEO_PROCESSED_DIR
_ACTIVE_SCENARIO_RESULT: dict = {}
_SEARCH_INDEX_CACHE: Optional[list] = None


def _get_default_urban_result():
    from digital_twin.terrain_hydrology import terrain_engine, PREDEFINED_SCENARIOS
    if "last" not in _ACTIVE_SCENARIO_RESULT:
        _ACTIVE_SCENARIO_RESULT["last"] = terrain_engine.run_scenario(PREDEFINED_SCENARIOS["heavy_rainfall"])
    return _ACTIVE_SCENARIO_RESULT["last"]


def _get_search_index() -> list:
    global _SEARCH_INDEX_CACHE
    if _SEARCH_INDEX_CACHE is not None:
        return _SEARCH_INDEX_CACHE
    items = []
    from digital_twin.terrain_hydrology import FOCUS_LOCATIONS
    for loc in FOCUS_LOCATIONS:
        items.append({
            "name": loc["name"],
            "tamil_name": loc.get("tamil_name", ""),
            "category": "Focus Basin",
            "id": loc["id"],
            "coordinates": loc["coordinates"],
            "zoom": 13.8,
        })
    places_p = _GEO_PROCESSED_DIR / "osm_places_index.json"
    if places_p.exists():
        for pl in json.loads(places_p.read_text()):
            items.append({
                "name": pl["name"],
                "category": f"OSM {pl.get('place_type', 'place').title()}",
                "coordinates": pl["coordinates"],
                "zoom": 14.2,
            })
    st_p = _GEO_PROCESSED_DIR / "verified_stations.json"
    if st_p.exists():
        for st in json.loads(st_p.read_text()):
            items.append({
                "name": st["station_name"],
                "category": f"CFM-DSS {st['station_kind']}",
                "coordinates": st["coordinates"],
                "zoom": 14.5,
            })
    br_p = _GEO_PROCESSED_DIR / "osm_bridges.geojson"
    if br_p.exists():
        gj = json.loads(br_p.read_text())
        seen_br = set()
        for f in gj.get("features", []):
            nm = (f.get("properties") or {}).get("name")
            if nm and nm.lower() not in seen_br:
                seen_br.add(nm.lower())
                coords = (f.get("geometry") or {}).get("coordinates", [])
                if coords and isinstance(coords[0], list):
                    mid = coords[len(coords) // 2]
                    items.append({"name": nm, "category": "Bridge", "coordinates": mid, "zoom": 15.2})
    bldg_p = _GEO_PROCESSED_DIR / "osm_buildings_south.geojson"
    if bldg_p.exists():
        gj = json.loads(bldg_p.read_text())
        seen_b = set()
        for f in gj.get("features", []):
            nm = (f.get("properties") or {}).get("name")
            if nm and nm.lower() not in seen_b and len(seen_b) < 2500:
                seen_b.add(nm.lower())
                g = f.get("geometry") or {}
                c = g.get("coordinates", [])
                ring = c[0] if g.get("type") == "Polygon" and c else (c[0][0] if g.get("type") == "MultiPolygon" and c else None)
                if ring:
                    items.append({"name": nm, "category": "OSM Building", "coordinates": ring[0], "zoom": 16.0})
    _SEARCH_INDEX_CACHE = items
    return items


# ── Chennai Urban Geospatial Digital Twin REST APIs ───────────────────────
@app.get("/api/urban/locations")
def get_urban_locations():
    """Returns prioritized South Chennai focus locations grounded with Copernicus DEM elevation."""
    from digital_twin.terrain_hydrology import FOCUS_LOCATIONS, terrain_engine
    locs = []
    for loc in FOCUS_LOCATIONS:
        entry = dict(loc)
        pt_info = terrain_engine.query_point(loc["coordinates"][0], loc["coordinates"][1])
        entry["elevation_m"] = pt_info.get("copernicus_dsm_elevation_m")
        locs.append(entry)
    return {"count": len(locs), "locations": locs}


@app.get("/api/urban/locations/{location_id}")
def get_urban_location(location_id: str):
    """Returns individual location details for a Chennai focus locality."""
    from digital_twin.terrain_hydrology import FOCUS_LOCATIONS, terrain_engine
    for loc in FOCUS_LOCATIONS:
        if loc["id"] == location_id:
            entry = dict(loc)
            pt_info = terrain_engine.query_point(loc["coordinates"][0], loc["coordinates"][1])
            entry["elevation_m"] = pt_info.get("copernicus_dsm_elevation_m")
            entry["terrain_info"] = pt_info
            return entry
    raise HTTPException(404, f"Location '{location_id}' not found")


@app.get("/api/urban/stations")
def get_urban_stations():
    """Returns strictly geolocated official CFM-DSS meteorological & flood stations."""
    st_path = _GEO_PROCESSED_DIR / "verified_stations.json"
    if not st_path.exists():
        raise HTTPException(404, "Processed verified_stations.json not found")
    stations = json.loads(st_path.read_text())
    return {
        "count": len(stations),
        "observation_mode": "historical_verified_coordinates",
        "note": "CFM-DSS WFS geolocated stations only; non-geolocated CSV ARG series are surfaced via /api/urban/historical/arg-analytics.",
        "stations": stations,
    }


@app.get("/api/urban/reservoirs")
def get_urban_reservoirs():
    """Returns real preserved WRD reservoir capacities merged with geospatial coordinates."""
    import csv
    csv_path = config.PROCESSED_DIR / "chennai_reservoirs.csv"
    if not csv_path.exists():
        raise HTTPException(404, "Preserved chennai_reservoirs.csv not found")

    coords_lookup = {
        "RedHills": [80.1850, 13.1980],
        "Cholavaram": [80.1460, 13.2250],
        "Thervoy Kandigai": [79.9690, 13.3470],
        "Chembarambakkam": [80.0680, 13.0120],
        "Poondi": [79.8630, 13.1950],
    }
    reservoirs = []
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            nm = row["reservoir_name"].strip()
            live = float(row["storage_capacity_live_mcm"])
            gross = float(row["storage_capacity_gross_mcm"])
            dead = float(row["storage_capacity_dead_mcm"])
            fill_pct = float(row["storage_fill_pct"])
            reservoirs.append({
                "tank_id": row["tank_id"],
                "reservoir_name": nm,
                "storage_capacity_live_mcm": live,
                "storage_capacity_gross_mcm": gross,
                "storage_capacity_dead_mcm": dead,
                "storage_fill_pct": fill_pct,
                "coordinates": coords_lookup.get(nm, [80.068, 13.012]),
                "in_south_pilot_domain": nm == "Chembarambakkam",
                "source": row["source"],
                "provenance": row["provenance"],
            })
    return {"count": len(reservoirs), "reservoirs": reservoirs}


@app.get("/api/urban/historical/michaung")
def get_urban_historical_michaung():
    """Returns complete 144 hourly Cyclone Michaung rainfall observations from preserved CSV."""
    import csv
    michaung_path = config.PROCESSED_DIR / "chennai_michaung_hourly.csv"
    if not michaung_path.exists():
        raise HTTPException(404, "Preserved chennai_michaung_hourly.csv not found")
    with open(michaung_path) as f:
        rows = list(csv.DictReader(f))
    records = [
        {
            "timestamp_local": r["timestamp_local"],
            "hourly_precipitation_mm": float(r["hourly_precipitation_mm"]),
            "cumulative_rainfall_mm": float(r["cumulative_rainfall_mm"]),
        }
        for r in rows
    ]
    peak = max((r["hourly_precipitation_mm"] for r in records), default=0.0)
    cum = records[-1]["cumulative_rainfall_mm"] if records else 0.0
    return {
        "event_id": "cyclone_michaung_2023",
        "event_name": "Cyclone Michaung (Dec 1–6, 2023)",
        "records_count": len(records),
        "peak_hourly_mm_hr": round(peak, 2),
        "cumulative_mm": round(cum, 2),
        "station_coordinates": [80.2707, 13.0827],
        "provenance": "ERA5_IMD_Calibrated (observed historical rainfall)",
        "records": records,
    }


@app.get("/api/urban/historical/arg-analytics")
def get_urban_arg_analytics():
    """Aggregates preserved chennai_arg_rainfall.csv by subbasin (explicitly non-spatial; no coordinates)."""
    import csv
    csv_path = config.PROCESSED_DIR / "chennai_arg_rainfall.csv"
    if not csv_path.exists():
        raise HTTPException(404, "Preserved chennai_arg_rainfall.csv not found")
    subbasins: dict = {}
    stations_seen = set()
    total_rows = 0
    with open(csv_path) as f:
        for r in csv.DictReader(f):
            total_rows += 1
            sb = r["subbasin"].strip()
            st_id = r["station_id"].strip()
            stations_seen.add(st_id)
            rain = float(r["rainfall_mm"])
            prev = float(r["previous_rainfall_mm"])
            entry = subbasins.setdefault(sb, {"subbasin": sb, "records": 0, "stations": set(), "max_rain_mm": 0.0, "sum_rain_mm": 0.0, "max_prev_mm": 0.0})
            entry["records"] += 1
            entry["stations"].add(st_id)
            entry["max_rain_mm"] = max(entry["max_rain_mm"], rain)
            entry["max_prev_mm"] = max(entry["max_prev_mm"], prev)
            entry["sum_rain_mm"] += rain
    summary = []
    for sb, d in sorted(subbasins.items(), key=lambda x: x[1]["max_rain_mm"], reverse=True):
        summary.append({
            "subbasin": sb,
            "station_count": len(d["stations"]),
            "record_count": d["records"],
            "mean_rainfall_mm": round(d["sum_rain_mm"] / max(1, d["records"]), 2),
            "max_rainfall_mm": round(d["max_rain_mm"], 2),
            "max_previous_rainfall_mm": round(d["max_prev_mm"], 2),
        })
    return {
        "has_coordinates": False,
        "provenance": "CFM-DSS_ARG",
        "note": "Preserved chennai_arg_rainfall.csv contains 328 rows across 13 subbasins without lat/lon coordinates; displayed as non-spatial analytics rather than fabricated map pins.",
        "total_records": total_rows,
        "unique_stations": len(stations_seen),
        "subbasins_count": len(summary),
        "subbasins": summary,
    }


@app.get("/api/urban/historical-events")
def get_urban_historical_events():
    """Summary endpoint returning Cyclone Michaung overview metrics."""
    m = get_urban_historical_michaung()
    return {
        "event_id": m["event_id"],
        "event_name": m["event_name"],
        "peak_hourly_intensity_mm_hr": m["peak_hourly_mm_hr"],
        "cumulative_precipitation_mm": m["cumulative_mm"],
        "records_count": m["records_count"],
        "sample_records": m["records"][:12],
        "provenance": m["provenance"],
    }


_GEO_LAYER_FILES = {
    "hillshade": ("chennai_terrain_hillshade.png", "image/png"),
    "terrain_hillshade.png": ("chennai_terrain_hillshade.png", "image/png"),
    "dem_metadata": ("dem_metadata.json", "application/json"),
    "gcc_boundary": ("gcc_boundary.geojson", "application/json"),
    "watersheds": ("watersheds_south.geojson", "application/json"),
    "catchments": ("watersheds_south.geojson", "application/json"),
    "wards": ("wards_chennai.geojson", "application/json"),
    "waterways": ("waterways_official.geojson", "application/json"),
    "waterbodies": ("waterbodies_official.geojson", "application/json"),
    "flood_spots": ("historical_flood_spots.geojson", "application/json"),
    "roads_major": ("osm_roads_major.geojson", "application/json"),
    "streets_pilot": ("osm_streets_pilot.geojson", "application/json"),
    "bridges": ("osm_bridges.geojson", "application/json"),
    "parks": ("osm_parks_landuse.geojson", "application/json"),
    "buildings": ("osm_buildings_south.geojson", "application/json"),
    "places": ("osm_places_index.json", "application/json"),
    "manifest": ("acquisition_manifest.json", "application/json"),
}


def _safe_filename_slug(value: str) -> str:
    import re
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "scenario")).strip("._")
    return clean[:64] or "scenario"


def _resolve_urban_scenario_result(scenario_id: str) -> dict:
    from digital_twin.terrain_hydrology import (
        HydroScenarioConfig,
        PREDEFINED_SCENARIOS,
        normalize_scenario_id,
        terrain_engine,
    )

    nid = normalize_scenario_id(scenario_id)
    if nid in _ACTIVE_SCENARIO_RESULT:
        return _ACTIVE_SCENARIO_RESULT[nid]
    if nid in PREDEFINED_SCENARIOS:
        res = terrain_engine.run_scenario(PREDEFINED_SCENARIOS[nid])
        _ACTIVE_SCENARIO_RESULT[nid] = res
        return res
    for saved in terrain_engine.list_saved_scenarios():
        if saved.get("id") == nid or saved.get("saved_name") == scenario_id:
            cfg = HydroScenarioConfig(**saved["config"])
            res = terrain_engine.run_scenario(cfg)
            _ACTIVE_SCENARIO_RESULT[nid] = res
            return res
    raise HTTPException(404, f"Scenario '{scenario_id}' not found")


@app.get("/api/urban/geo/terrain_tiles/{z}/{x}/{y}.png")
def get_urban_terrain_tile(z: int, x: int, y: int):
    """Serves offline Terrarium RGB elevation tiles derived from local Copernicus GLO-30 DEM."""
    from digital_twin.terrain_hydrology import terrain_engine

    if z < 0 or z > 17 or x < 0 or y < 0 or x >= (1 << z) or y >= (1 << z):
        raise HTTPException(400, "Invalid XYZ terrain tile coordinates")
    png_bytes = terrain_engine.render_terrarium_tile_png(z, x, y)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/urban/geo/{layer}")
def get_urban_geo_layer(layer: str):
    """Serves processed offline geospatial assets (Copernicus DEM relief, WFS polygons, OSM features)."""
    if layer not in _GEO_LAYER_FILES:
        raise HTTPException(404, f"Geospatial layer '{layer}' not found")
    fname, media_type = _GEO_LAYER_FILES[layer]
    fpath = _GEO_PROCESSED_DIR / fname
    if not fpath.exists():
        raise HTTPException(404, f"Processed file missing: {fname}")
    return FileResponse(fpath, media_type=media_type)


@app.get("/api/urban/search")
def search_urban_features(q: str = Query(..., min_length=1, max_length=80), limit: int = Query(12, ge=1, le=30)):
    """Fast prefix/substring search across South Chennai basins, OSM neighborhoods, WFS stations, bridges & buildings."""
    ql = q.strip().lower()
    idx = _get_search_index()
    prefix_hits = [x for x in idx if x["name"].lower().startswith(ql)]
    sub_hits = [x for x in idx if ql in x["name"].lower() and not x["name"].lower().startswith(ql)]
    results = (prefix_hits + sub_hits)[:limit]
    return {"query": q, "count": len(results), "results": results}


@app.get("/api/urban/point")
def inspect_urban_point(lon: float = Query(...), lat: float = Query(...), scenario_id: Optional[str] = Query(None)):
    """Inspect Copernicus DSM elevation, UTM coordinates, surface mask, and modeled depth at (lon, lat)."""
    from digital_twin.terrain_hydrology import terrain_engine
    active = _get_default_urban_result()
    if scenario_id:
        try:
            active = _resolve_urban_scenario_result(scenario_id)
        except HTTPException:
            pass
    return terrain_engine.query_point(lon, lat, active_result=active)


@app.get("/api/urban/scenarios/list")
def list_urban_scenarios():
    """Returns all 8 scientific predefined scenarios for the Landlab 2D OverlandFlow twin."""
    from digital_twin.terrain_hydrology import PREDEFINED_SCENARIOS
    return [
        {
            "id": p.scenario_id,
            "name": p.scenario_name,
            "mode": p.mode,
            "description": p.description,
            "rainfall_intensity_mm_hr": p.rainfall_intensity_mm_hr,
            "duration_hours": p.duration_hours,
            "infiltration_rate_mm_hr": p.infiltration_rate_mm_hr,
            "drainage_efficiency_pct": p.drainage_efficiency_pct,
            "chembarambakkam_discharge_cusecs": p.chembarambakkam_discharge_cusecs,
            "mannings_n": p.mannings_n,
        }
        for p in PREDEFINED_SCENARIOS.values()
    ]


@app.post("/api/urban/scenario")
def execute_urban_scenario(payload: Optional[dict] = None):
    """Executes the Landlab 2D OverlandFlow terrain simulation over South Chennai UTM 44N DEM."""
    from digital_twin.terrain_hydrology import (
        terrain_engine,
        PREDEFINED_SCENARIOS,
        HydroScenarioConfig,
        normalize_scenario_id,
        strip_internal_grids,
    )
    payload = payload or {}
    raw_id = payload.get("scenario_id", "heavy_rainfall")
    scenario_id = normalize_scenario_id(raw_id)

    custom_keys = {
        "rainfall_intensity_mm_hr",
        "duration_hours",
        "infiltration_rate_mm_hr",
        "drainage_efficiency_pct",
        "drainage_capacity_pct",
        "chembarambakkam_discharge_cusecs",
        "mannings_n",
        "initial_depth_m",
    }
    if scenario_id in PREDEFINED_SCENARIOS and not any(k in payload for k in custom_keys):
        cfg = PREDEFINED_SCENARIOS[scenario_id]
    else:
        drain_pct = float(payload.get("drainage_efficiency_pct", payload.get("drainage_capacity_pct", 100.0)))
        cfg = HydroScenarioConfig(
            scenario_id=scenario_id,
            scenario_name=payload.get("scenario_name", f"Custom Scenario ({scenario_id})"),
            mode=payload.get("mode", "historical_replay" if scenario_id == "michaung_replay" else "scenario_simulation"),
            rainfall_intensity_mm_hr=float(payload.get("rainfall_intensity_mm_hr", 45.0)),
            duration_hours=float(payload.get("duration_hours", 4.0)),
            infiltration_rate_mm_hr=float(payload.get("infiltration_rate_mm_hr", 5.0)),
            drainage_efficiency_pct=drain_pct,
            nominal_drain_cap_mm_hr=float(payload.get("nominal_drain_cap_mm_hr", 12.0)),
            chembarambakkam_discharge_cusecs=float(payload.get("chembarambakkam_discharge_cusecs", 0.0)),
            mannings_n=float(payload.get("mannings_n", 0.045)),
            initial_depth_m=float(payload.get("initial_depth_m", 0.0)),
            description=payload.get("description", "Custom interactive urban flood simulation scenario."),
            provenance_tags=["user_defined_scenario", "terrain_routed_landlab"],
        )

    try:
        res = terrain_engine.run_scenario(cfg)
    except ValueError as ve:
        raise HTTPException(422, str(ve)) from ve

    _ACTIVE_SCENARIO_RESULT["last"] = res
    _ACTIVE_SCENARIO_RESULT[scenario_id] = res
    return strip_internal_grids(res)


@app.post("/api/urban/scenario/compare")
def compare_urban_scenarios(payload: dict):
    """Computes explicit cell-by-cell numerical, spatial delta raster, and exposure comparison."""
    from digital_twin.terrain_hydrology import terrain_engine

    b_raw = str(payload.get("baseline_id", "heavy_rainfall"))
    a_raw = str(payload.get("alternate_id", "reduced_drainage"))
    threshold_m = float(payload.get("threshold_m", 0.15))
    if not (0.01 <= threshold_m <= 2.0):
        raise HTTPException(422, "threshold_m must be between 0.01 and 2.0 m")
    include_exposure = bool(payload.get("include_exposure", True))

    r_base = _resolve_urban_scenario_result(b_raw)
    r_alt = _resolve_urban_scenario_result(a_raw)
    return terrain_engine.compare_scenarios(
        r_base,
        r_alt,
        include_exposure=include_exposure,
        threshold_m=threshold_m,
    )


@app.post("/api/urban/scenario/save")
def save_urban_scenario(payload: dict):
    """Persists a scenario configuration to data/geo/processed/saved_scenarios.json."""
    from digital_twin.terrain_hydrology import terrain_engine, HydroScenarioConfig
    saved_name = str(payload.get("saved_name", "")).strip()
    if not saved_name:
        raise HTTPException(422, "saved_name is required")
    cfg = HydroScenarioConfig(
        scenario_id=payload.get("scenario_id", f"saved_{int(datetime.now().timestamp())}"),
        scenario_name=payload.get("scenario_name", saved_name),
        mode=payload.get("mode", "scenario_simulation"),
        rainfall_intensity_mm_hr=float(payload.get("rainfall_intensity_mm_hr", 45.0)),
        duration_hours=float(payload.get("duration_hours", 4.0)),
        infiltration_rate_mm_hr=float(payload.get("infiltration_rate_mm_hr", 5.0)),
        drainage_efficiency_pct=float(payload.get("drainage_efficiency_pct", 100.0)),
        chembarambakkam_discharge_cusecs=float(payload.get("chembarambakkam_discharge_cusecs", 0.0)),
        mannings_n=float(payload.get("mannings_n", 0.045)),
        initial_depth_m=float(payload.get("initial_depth_m", 0.0)),
        description=payload.get("description", f"Saved scenario: {saved_name}"),
    )
    try:
        cfg.validate()
    except ValueError as ve:
        raise HTTPException(422, str(ve)) from ve
    return terrain_engine.save_scenario_config(saved_name, cfg)


@app.get("/api/urban/scenarios/saved")
def get_saved_urban_scenarios():
    from digital_twin.terrain_hydrology import terrain_engine
    saved = terrain_engine.list_saved_scenarios()
    return {"count": len(saved), "scenarios": saved}


@app.patch("/api/urban/scenarios/saved/{scenario_key}")
def rename_saved_urban_scenario(scenario_key: str, payload: dict):
    from digital_twin.terrain_hydrology import terrain_engine
    new_name = str(payload.get("new_name", "")).strip()
    if not new_name:
        raise HTTPException(422, "new_name is required")
    updated = terrain_engine.rename_saved_scenario(scenario_key, new_name)
    if not updated:
        raise HTTPException(404, f"Saved scenario '{scenario_key}' not found")
    return updated


@app.post("/api/urban/scenarios/saved/{scenario_key}/duplicate")
def duplicate_saved_urban_scenario(scenario_key: str, payload: Optional[dict] = None):
    from digital_twin.terrain_hydrology import terrain_engine
    new_name = str((payload or {}).get("new_name", "")).strip() or None
    dup = terrain_engine.duplicate_saved_scenario(scenario_key, new_name=new_name)
    if not dup:
        raise HTTPException(404, f"Saved scenario '{scenario_key}' not found")
    return dup


@app.delete("/api/urban/scenarios/saved/{scenario_key}")
def delete_saved_urban_scenario(scenario_key: str):
    from digital_twin.terrain_hydrology import terrain_engine
    ok = terrain_engine.delete_saved_scenario(scenario_key)
    if not ok:
        raise HTTPException(404, f"Saved scenario '{scenario_key}' not found")
    return {"status": "deleted", "key": scenario_key}


@app.get("/api/urban/exposure")
def get_urban_exposure(
    scenario_id: str = Query("heavy_rainfall"),
    threshold_m: float = Query(0.15, ge=0.01, le=2.0),
    include_geojson: bool = Query(True),
):
    """Computes EPSG:32644 potential exposure of buildings, roads, bridges, and OSM civic facilities."""
    from digital_twin.exposure_engine import get_exposure_engine

    res = _resolve_urban_scenario_result(scenario_id)
    return get_exposure_engine().evaluate_scenario_exposure(
        res["_final_depth_grid"],
        scenario_id=res["scenario"]["id"],
        scenario_name=res["scenario"]["name"],
        threshold_m=threshold_m,
        include_highlight_geojson=include_geojson,
    )


@app.get("/api/urban/neighbourhoods")
def get_urban_neighbourhoods(
    scenario_id: str = Query("heavy_rainfall"),
    boundary_type: str = Query("watersheds", pattern="^(watersheds|wards)$"),
    threshold_m: float = Query(0.15, ge=0.01, le=2.0),
):
    """Aggregates hydrological depth and projected exposure across official Watersheds or GCC Wards."""
    from digital_twin.exposure_engine import get_exposure_engine

    res = _resolve_urban_scenario_result(scenario_id)
    return get_exposure_engine().evaluate_neighbourhoods(
        res["_final_depth_grid"],
        scenario_id=res["scenario"]["id"],
        scenario_name=res["scenario"]["name"],
        boundary_type=boundary_type,
        threshold_m=threshold_m,
    )


@app.post("/api/urban/sensitivity")
def run_urban_sensitivity(payload: dict):
    """Executes bounded parameter sensitivity sweeps over real Landlab 2D OverlandFlow grids."""
    from digital_twin.terrain_hydrology import (
        HydroScenarioConfig,
        PREDEFINED_SCENARIOS,
        normalize_scenario_id,
        terrain_engine,
    )

    param = str(payload.get("parameter", "rainfall_intensity_mm_hr")).strip()
    min_val = float(payload.get("min_val", 10.0))
    max_val = float(payload.get("max_val", 110.0))
    steps = int(payload.get("steps", 5))
    base_id = normalize_scenario_id(str(payload.get("base_scenario_id", "heavy_rainfall")))
    threshold_m = float(payload.get("threshold_m", 0.15))
    include_exposure = bool(payload.get("include_exposure", True))

    if not (0.01 <= threshold_m <= 2.0):
        raise HTTPException(422, "threshold_m must be between 0.01 and 2.0 m")

    base_cfg = PREDEFINED_SCENARIOS.get(base_id)
    if base_cfg is None:
        base_res = _resolve_urban_scenario_result(base_id)
        sc = base_res["scenario"]
        base_cfg = HydroScenarioConfig(
            scenario_id=sc["id"],
            scenario_name=sc["name"],
            mode=sc["mode"],
            rainfall_intensity_mm_hr=sc["rainfall_intensity_mm_hr"],
            duration_hours=sc["duration_hours"],
            infiltration_rate_mm_hr=sc["infiltration_rate_mm_hr"],
            drainage_efficiency_pct=sc["drainage_efficiency_pct"],
            chembarambakkam_discharge_cusecs=sc["chembarambakkam_discharge_cusecs"],
            mannings_n=sc["mannings_n"],
            initial_depth_m=sc.get("initial_depth_m", 0.0),
        )

    try:
        return terrain_engine.run_sensitivity_sweep(
            parameter=param,
            min_val=min_val,
            max_val=max_val,
            steps=steps,
            base_cfg=base_cfg,
            include_exposure=include_exposure,
            threshold_m=threshold_m,
        )
    except ValueError as ve:
        raise HTTPException(422, str(ve)) from ve


@app.get("/api/urban/report/pdf")
def download_urban_pdf_report(
    scenario_id: str = Query("heavy_rainfall"),
    compare_id: Optional[str] = Query(None),
    boundary_type: str = Query("watersheds", pattern="^(watersheds|wards)$"),
    threshold_m: float = Query(0.15, ge=0.01, le=2.0),
    objective: str = Query(
        "South Chennai terrain-aware flood screening & projected infrastructure exposure assessment.",
        max_length=260,
    ),
):
    """Generates and downloads an offline A4 PDF engineering report from actual solver & exposure results."""
    from digital_twin.exposure_engine import get_exposure_engine
    from digital_twin.report_generator import generate_engineering_pdf_bytes
    from digital_twin.terrain_hydrology import terrain_engine

    res = _resolve_urban_scenario_result(scenario_id)
    exp_eng = get_exposure_engine()
    exposure = exp_eng.evaluate_scenario_exposure(
        res["_final_depth_grid"],
        scenario_id=res["scenario"]["id"],
        scenario_name=res["scenario"]["name"],
        threshold_m=threshold_m,
        include_highlight_geojson=False,
    )
    neighbourhoods = exp_eng.evaluate_neighbourhoods(
        res["_final_depth_grid"],
        scenario_id=res["scenario"]["id"],
        scenario_name=res["scenario"]["name"],
        boundary_type=boundary_type,
        threshold_m=threshold_m,
    )
    compare_rep = None
    if compare_id and compare_id.strip():
        alt_res = _resolve_urban_scenario_result(compare_id.strip())
        compare_rep = terrain_engine.compare_scenarios(
            res,
            alt_res,
            include_exposure=True,
            threshold_m=threshold_m,
        )

    pdf_bundle = generate_engineering_pdf_bytes(
        terrain_engine_obj=terrain_engine,
        scenario_result=res,
        exposure_report=exposure,
        neighbourhood_report=neighbourhoods,
        compare_report=compare_rep,
        analysis_objective=objective,
    )
    safe_fn = _safe_filename_slug(pdf_bundle["filename"])
    return Response(
        content=pdf_bundle["pdf_bytes"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_fn}"',
            "X-CivicTwin-Report-Id": pdf_bundle["report_id"],
        },
    )


@app.get("/api/urban/report/csv")
def download_urban_csv_report(
    scenario_id: str = Query("heavy_rainfall"),
    boundary_type: str = Query("watersheds", pattern="^(watersheds|wards)$"),
    threshold_m: float = Query(0.15, ge=0.01, le=2.0),
):
    """Exports scenario summary, infrastructure exposure, and neighbourhood analysis as CSV."""
    from digital_twin.exposure_engine import get_exposure_engine
    from digital_twin.report_generator import generate_scenario_csv_text

    res = _resolve_urban_scenario_result(scenario_id)
    exp_eng = get_exposure_engine()
    exposure = exp_eng.evaluate_scenario_exposure(
        res["_final_depth_grid"],
        scenario_id=res["scenario"]["id"],
        scenario_name=res["scenario"]["name"],
        threshold_m=threshold_m,
        include_highlight_geojson=False,
    )
    neighbourhoods = exp_eng.evaluate_neighbourhoods(
        res["_final_depth_grid"],
        scenario_id=res["scenario"]["id"],
        scenario_name=res["scenario"]["name"],
        boundary_type=boundary_type,
        threshold_m=threshold_m,
    )
    csv_txt = generate_scenario_csv_text(res, exposure, neighbourhoods)
    safe_slug = _safe_filename_slug(res["scenario"]["id"])
    return Response(
        content=csv_txt,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="civictwin_{safe_slug}_analysis.csv"'},
    )


@app.get("/api/urban/scenario/{scenario_id}/export")
def export_urban_scenario(scenario_id: str, fmt: str = Query("geojson", pattern="^(geojson|summary)$")):
    """Downloads active/cached scenario flood polygons GeoJSON or summary JSON."""
    from fastapi.responses import JSONResponse
    from digital_twin.terrain_hydrology import normalize_scenario_id, strip_internal_grids

    res = _resolve_urban_scenario_result(scenario_id)
    safe_slug = _safe_filename_slug(normalize_scenario_id(scenario_id))
    if fmt == "geojson":
        return JSONResponse(
            content=res["flood_overlay_geojson"],
            headers={"Content-Disposition": f'attachment; filename="civictwin_{safe_slug}_flood.geojson"'},
        )
    return JSONResponse(
        content=strip_internal_grids(res),
        headers={"Content-Disposition": f'attachment; filename="civictwin_{safe_slug}_summary.json"'},
    )


@app.get("/api/urban/scenario/{scenario_id}")
def get_urban_scenario_result(scenario_id: str):
    """Retrieves computed Landlab 2D flood results for a predefined, cached, or saved scenario ID."""
    from digital_twin.terrain_hydrology import strip_internal_grids

    res = _resolve_urban_scenario_result(scenario_id)
    return strip_internal_grids(res)


@app.get("/", response_class=HTMLResponse)
@app.get("/showcase", response_class=HTMLResponse)
def get_showcase_dashboard():
    """Serves the Unified Showcase Engineering Control Center."""
    if not SHOWCASE_HTML_PATH.exists():
        raise HTTPException(404, "Showcase dashboard template not found")
    return FileResponse(SHOWCASE_HTML_PATH)


@app.post("/api/showcase/scenario/{name}")
def trigger_showcase_scenario(name: str):
    """Activates controlled showcase scenarios for live demonstration across all 10 operational profiles."""
    SIMULATOR_CONTROL_FILE.parent.mkdir(parents=True, exist_ok=True)
    control_data = {"scenario": name, "timestamp": datetime.now(timezone.utc).isoformat(), "nodes": {}}

    if name in ("normal", "normal_dry"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 25.0, "reset_level": 15.0, "drainage_k_override": 4.5},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 35.0, "reset_level": 18.0, "drainage_k_override": 6.0},
        }
        if scenario_ctrl and scenario_ctrl.is_running:
            scenario_ctrl.stop()
    elif name in ("heavy_surge", "rising_water"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 55.0, "drainage_k_override": 4.5},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 65.0, "drainage_k_override": 6.0},
        }
        if twin_engine:
            twin_engine.apply_scenario_params("zone_01", inflow_rate=0.55)
            twin_engine.apply_scenario_params("zone_02", inflow_rate=0.50)
    elif name in ("drainage_obstruction", "drainage_blocked"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 30.0, "drainage_k_override": 1.5},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 40.0, "drainage_k_override": 2.0},
        }
    elif name in ("warning_breach", "warning_water"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 65.0, "reset_level": 36.0, "drainage_k_override": 4.5},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 75.0, "reset_level": 43.5, "drainage_k_override": 6.0},
        }
    elif name in ("critical_inundation", "critical_water"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 80.0, "reset_level": 43.5, "drainage_k_override": 4.5},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 90.0, "reset_level": 52.0, "drainage_k_override": 6.0},
        }
        if twin_engine:
            twin_engine.apply_scenario_params("zone_01", inflow_rate=0.85)
            twin_engine.apply_scenario_params("zone_02", inflow_rate=0.80)
    elif name in ("node1_dropout", "sensor_dropout"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": True},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False},
        }
    elif name in ("node2_stale", "telemetry_stale"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False},
            "node_02": {"paused": True, "disconnected": False, "sensor_fault": False},
        }
    elif name == "missing_data_recovery":
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 25.0, "drainage_k_override": 4.5},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 35.0, "drainage_k_override": 6.0},
        }
    elif name in ("rapid_reconnect", "reconnect"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False},
        }
    elif name in ("return_to_normal", "reset"):
        control_data["nodes"] = {
            "node_01": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 25.0, "drainage_k_override": 4.5},
            "node_02": {"paused": False, "disconnected": False, "sensor_fault": False, "inflow_override": 35.0, "drainage_k_override": 6.0},
        }
    else:
        raise HTTPException(400, f"Unknown showcase scenario: {name}. Available: normal, heavy_surge, drainage_obstruction, warning_breach, critical_inundation, node1_dropout, node2_stale, missing_data_recovery, rapid_reconnect, return_to_normal")

    with open(SIMULATOR_CONTROL_FILE, "w") as f:
        json.dump(control_data, f, indent=2)

    logger.info("Activated showcase scenario '%s'", name)
    return {"status": "activated", "scenario": name, "control": control_data}


@app.post("/api/showcase/node/{node_id}/{action}")
def control_showcase_node(node_id: str, action: str):
    """Controls simulated node behavior (disconnect, reconnect, fault, pause)."""
    SIMULATOR_CONTROL_FILE.parent.mkdir(parents=True, exist_ok=True)
    control_data = {"timestamp": datetime.now(timezone.utc).isoformat(), "nodes": {}}

    if SIMULATOR_CONTROL_FILE.exists():
        try:
            with open(SIMULATOR_CONTROL_FILE, "r") as f:
                control_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("Ignoring stale simulator control file: %s", e)

    if "nodes" not in control_data:
        control_data["nodes"] = {}

    targets = ["node_01", "node_02"] if node_id in ("both", "all") else [node_id]

    for nid in targets:
        if nid not in control_data["nodes"]:
            control_data["nodes"][nid] = {}

        if action == "disconnect":
            control_data["nodes"][nid]["disconnected"] = True
        elif action == "reconnect":
            control_data["nodes"][nid]["disconnected"] = False
            control_data["nodes"][nid]["sensor_fault"] = False
            control_data["nodes"][nid]["paused"] = False
        elif action == "sensor_fault":
            control_data["nodes"][nid]["sensor_fault"] = True
        elif action == "pause":
            control_data["nodes"][nid]["paused"] = True
        elif action == "resume":
            control_data["nodes"][nid]["paused"] = False
        else:
            raise HTTPException(400, f"Unknown node action: {action}")

    with open(SIMULATOR_CONTROL_FILE, "w") as f:
        json.dump(control_data, f, indent=2)

    logger.info("Showcase node control applied: %s -> %s", node_id, action)
    return {"status": "applied", "node_id": node_id, "action": action, "control": control_data}


