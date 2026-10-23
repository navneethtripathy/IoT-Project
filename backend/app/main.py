"""
CivicTwin-R — FastAPI Backend Application

Provides REST API endpoints for:
    - System health and configuration
    - Zone status and telemetry queries
    - Scenario management (list, start, stop)
    - Alert monitoring
    - Experiment results

Integrates the ingestion service, sensor simulator, digital twin engine,
and storage layer into a single process for local development.

Start with:
    cd CivicTwin-R
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend import config
from backend.models import AlertLevel
from backend.storage import create_storage, StorageBackend
from backend.ingestion import IngestionService, MQTTIngestionClient
from backend.simulator import SensorSimulator
from digital_twin.model import DigitalTwinEngine, create_default_zones
from digital_twin.scenarios import ScenarioController, list_scenarios, SCENARIOS

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.api")

# ── Global services (initialized in lifespan) ───────────
storage: Optional[StorageBackend] = None
ingestion: Optional[IngestionService] = None
mqtt_client: Optional[MQTTIngestionClient] = None
simulator: Optional[SensorSimulator] = None
twin_engine: Optional[DigitalTwinEngine] = None
scenario_ctrl: Optional[ScenarioController] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and tear down services."""
    global storage, ingestion, mqtt_client, simulator, twin_engine, scenario_ctrl

    logger.info("Starting CivicTwin-R backend...")
    logger.info("Configuration: %s", json.dumps(config.summary(), indent=2))

    # Storage
    storage = create_storage()
    logger.info("Storage backend: %s", config.STORAGE_BACKEND)

    # Digital Twin Engine
    twin_engine = DigitalTwinEngine(seed=config.RANDOM_SEED)
    for zone in create_default_zones():
        twin_engine.add_zone(zone)

    # Scenario Controller
    scenario_ctrl = ScenarioController(twin_engine)

    # Ingestion Service
    ingestion = IngestionService(storage)

    # MQTT Client (best-effort — may not connect if broker is down)
    mqtt_client = MQTTIngestionClient(ingestion)
    mqtt_connected = mqtt_client.start()
    if not mqtt_connected:
        logger.warning("MQTT broker not available — running in direct/offline mode")

    # Sensor Simulator (feeds directly into ingestion when MQTT is unavailable)
    simulator = SensorSimulator(
        engine=twin_engine,
        direct_callback=ingestion.process_message,
        interval_sec=config.TWIN_TIME_STEP_SEC,
    )
    simulator.start()

    logger.info("CivicTwin-R backend ready")
    yield

    # Shutdown
    logger.info("Shutting down CivicTwin-R backend...")
    if simulator:
        simulator.stop()
    if mqtt_client:
        mqtt_client.stop()
    if storage:
        storage.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="CivicTwin-R API",
    description="Urban Flood Monitoring Digital Twin — REST API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for Node-RED dashboard and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Local demo only — restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════
# HEALTH & STATUS
# ══════════════════════════════════════════════════════════

@app.get("/health")
def health():
    """System health check."""
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
    """Return safe configuration summary (no secrets)."""
    return config.summary()


# ══════════════════════════════════════════════════════════
# ZONES
# ══════════════════════════════════════════════════════════

@app.get("/api/zones")
def get_zones():
    """List all configured zones and their current state."""
    if not twin_engine:
        raise HTTPException(503, "Engine not initialized")

    states = twin_engine.get_all_states()
    zone_statuses = ingestion.zone_status if ingestion else {}

    # Merge engine state with ingestion status
    for state in states:
        zid = state["zone_id"]
        if zid in zone_statuses:
            state.update(zone_statuses[zid])
        state["zone_type"] = "virtual"
        state["data_source"] = "digital_twin"

    return {"zones": states, "count": len(states)}


@app.get("/api/zones/{zone_id}")
def get_zone(zone_id: str):
    """Get detailed state for a specific zone."""
    if not twin_engine:
        raise HTTPException(503, "Engine not initialized")

    state = twin_engine.get_zone_state(zone_id)
    if not state:
        raise HTTPException(404, f"Zone '{zone_id}' not found")

    zone_statuses = ingestion.zone_status if ingestion else {}
    if zone_id in zone_statuses:
        state.update(zone_statuses[zone_id])

    return state


# ══════════════════════════════════════════════════════════
# TELEMETRY
# ══════════════════════════════════════════════════════════

@app.get("/api/telemetry/latest")
def get_latest_telemetry(zone_id: Optional[str] = None, limit: int = Query(5, ge=1, le=100)):
    """Get the most recent telemetry readings."""
    if not storage:
        raise HTTPException(503, "Storage not initialized")

    if zone_id:
        records = storage.query_latest(zone_id, limit)
        return {"zone_id": zone_id, "records": records, "count": len(records)}
    else:
        all_latest = storage.query_all_latest(limit)
        return {"zones": all_latest}


@app.get("/api/telemetry/history")
def get_telemetry_history(
    zone_id: str,
    minutes: int = Query(30, ge=1, le=1440),
    limit: int = Query(500, ge=1, le=5000),
):
    """Get telemetry history for a zone over the past N minutes."""
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


# ══════════════════════════════════════════════════════════
# ALERTS
# ══════════════════════════════════════════════════════════

@app.get("/api/alerts")
def get_alerts(level: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    """Get recent alerts, optionally filtered by level."""
    if not ingestion:
        raise HTTPException(503, "Ingestion not initialized")

    alerts = ingestion.alerts
    if level:
        try:
            level_enum = AlertLevel(level)
            alerts = [a for a in alerts if a.alert_level == level_enum]
        except ValueError:
            raise HTTPException(400, f"Invalid alert level: {level}")

    alerts = alerts[-limit:]
    return {
        "alerts": [a.model_dump(mode="json") for a in alerts],
        "count": len(alerts),
    }


# ══════════════════════════════════════════════════════════
# SCENARIOS
# ══════════════════════════════════════════════════════════

@app.get("/api/scenarios")
def get_scenarios():
    """List all available scenarios."""
    return {"scenarios": list_scenarios()}


@app.get("/api/scenarios/status")
def get_scenario_status():
    """Get current scenario execution status."""
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")
    return scenario_ctrl.get_summary()


@app.post("/api/scenarios/{scenario_id}/start")
def start_scenario(scenario_id: str):
    """Start executing a scenario."""
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    if scenario_id not in SCENARIOS:
        raise HTTPException(404, f"Scenario '{scenario_id}' not found")

    if scenario_ctrl.is_running:
        raise HTTPException(409, "A scenario is already running. Stop it first.")

    success = scenario_ctrl.load_scenario(scenario_id)
    if not success:
        raise HTTPException(500, f"Failed to load scenario '{scenario_id}'")

    return {
        "status": "started",
        "scenario_id": scenario_id,
        "total_steps": SCENARIOS[scenario_id].total_steps,
    }


@app.post("/api/scenarios/{scenario_id}/stop")
def stop_scenario(scenario_id: str):
    """Stop the currently running scenario."""
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    scenario_ctrl.stop()
    return {"status": "stopped", "scenario_id": scenario_id}


@app.post("/api/scenarios/step")
def scenario_step(steps: int = Query(1, ge=1, le=100)):
    """Manually advance the scenario by N steps."""
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    if not scenario_ctrl.is_running:
        raise HTTPException(400, "No scenario is currently running")

    all_data = []
    for _ in range(steps):
        if scenario_ctrl.is_complete:
            break
        step_data = scenario_ctrl.step(dt_sec=config.TWIN_TIME_STEP_SEC)
        all_data.extend(step_data)

        # Feed scenario data into ingestion for storage
        if ingestion:
            for msg in step_data:
                ingestion.process_message(msg)

    return {
        "steps_executed": len(all_data) // max(len(twin_engine.zones), 1) if twin_engine else 0,
        "summary": scenario_ctrl.get_summary(),
        "data_points": len(all_data),
    }


@app.get("/api/scenarios/results")
def get_scenario_results():
    """Get results from the last completed scenario."""
    if not scenario_ctrl:
        raise HTTPException(503, "Scenario controller not initialized")

    results = scenario_ctrl.get_results()
    return {
        "summary": scenario_ctrl.get_summary(),
        "results_count": len(results),
        "results": results[-500:],  # Last 500 data points
    }


# ══════════════════════════════════════════════════════════
# EXPERIMENTS
# ══════════════════════════════════════════════════════════

@app.get("/api/experiments/results")
def get_experiment_results():
    """Get saved experiment results if available."""
    results_file = config.TABLES_DIR / "reconstruction_results.json"
    if not results_file.exists():
        return {
            "status": "no_results",
            "message": "Run experiments first: python -m experiments.run_experiments",
        }

    with open(results_file) as f:
        data = json.load(f)
    return {"status": "available", "results": data}


# ══════════════════════════════════════════════════════════
# STATISTICS
# ══════════════════════════════════════════════════════════

@app.get("/api/stats")
def get_stats():
    """Get system-wide statistics."""
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
    """Export stored telemetry data."""
    if not storage:
        raise HTTPException(503, "Storage not initialized")

    if format == "csv":
        filename = f"export_{zone_id or 'all'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = config.GENERATED_DIR / filename
        count = storage.export_csv(path, zone_id)
        return {"status": "exported", "path": str(path), "records": count}
    else:
        if zone_id:
            records = storage.query_latest(zone_id, limit=1000)
        else:
            all_data = storage.query_all_latest(limit_per_zone=500)
            records = []
            for zone_records in all_data.values():
                records.extend(zone_records)
        return {"records": records, "count": len(records)}
