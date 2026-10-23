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

from backend import config
from backend.models import AlertLevel
from backend.storage import create_storage, StorageBackend
from backend.ingestion import IngestionService, MQTTIngestionClient
from backend.simulator import SensorSimulator
from digital_twin.model import DigitalTwinEngine, create_default_zones
from digital_twin.scenarios import ScenarioController, list_scenarios, SCENARIOS

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global storage, ingestion, mqtt_client, simulator, twin_engine, scenario_ctrl

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

    logger.info("CivicTwin-R backend initialized and ready")
    yield

    logger.info("Stopping CivicTwin-R backend services")
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
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": config.STORAGE_BACKEND,
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
        state["sensor_status"] = status.get("sensor_status", "valid")
        state["alert_level"] = status.get("alert_level", "normal")
        state["zone_type"] = "virtual"
        state["data_source"] = status.get("source", "digital_twin")
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
    state["sensor_status"] = status.get("sensor_status", "valid")
    state["alert_level"] = status.get("alert_level", "normal")
    state["zone_type"] = "virtual"
    state["data_source"] = status.get("source", "digital_twin")

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
    return {"scenarios": list_scenarios()}


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
            "backend": config.STORAGE_BACKEND,
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
