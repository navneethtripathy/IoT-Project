# CivicTwin-R: Real-Data Grounded Urban Flood Digital Twin

A resilient cyber-physical digital twin platform for urban water-level monitoring, simulated flood scenario testing, interpretable early-warning forecasting, and missing-data resilience evaluation grounded in real environmental observations from the **Chennai Metropolitan Basin, Tamil Nadu, India** (Adyar, Cooum, and Kosasthalaiyar sub-basins).

## Geographic Grounding: Chennai Metropolitan Basin

CivicTwin-R integrates real-world telemetry and hydrological spatial data:
- **Official Monitoring Portal**: Chennai Flood Monitoring & Spatial Decision Support System ([CFM-DSS](https://www.chennaifloodmonitor.tn.gov.in/)), developed under the World Bank PDGF by TNUIFSL, CRA, GCC, WRD, and IIT Madras.
- **Monitored Sub-Basins**:
  1. `zone_01` (`zone_adyar`): **Adyar River Basin** (Saidapet transit corridor & Chembarambakkam reservoir outflow).
  2. `zone_02` (`zone_cooum`): **Cooum River Basin** (Central Urban Drain, Nungambakkam, and Napier Bridge outflow).
  3. `zone_03` (`zone_kosasthalaiyar`): **Kosasthalaiyar Basin** (North Chennai Industrial Corridor, Poondi upstream, and Ennore Creek).
- **Verified Environmental Observations**:
  - 328 Automatic Rain Gauge (ARG) records across Chennai sub-basins.
  - 5 major reservoir storage capacities (Chembarambakkam, Poondi, RedHills, Cholavaram, Thervoy Kandigai).
  - 144 hourly points of Cyclone Michaung extreme storm rainfall (Dec 1-6, 2023, 369.8 mm total precipitation).
- **Explicit Conceptual Model Disclaimer**: The multi-zone twin models catchment mass-balance (inflow minus drainage with rainfall contribution and upstream transfers); it is explicitly labeled as a conceptual lumped model, not an uncalibrated 2D hydrodynamic finite-element simulation.

## Prerequisites

- Python 3.11 or higher
- pip (Python package installer)
- Git
- Optional for full integration mode:
  - Docker and Docker Compose
  - Node.js (for standalone Node-RED)

## Installation

Clone the repository and install dependencies in editable mode:

```bash
git clone <repository_url>
cd CivicTwin-R

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install package dependencies
pip install -e ".[dev]"

# Or run the setup automation script
./scripts/setup.sh
```

## Data Ingestion & Replay

CivicTwin-R includes reproducible importers for real environmental observations:

```bash
# Ingest official CFM-DSS rain gauges, reservoirs, and Michaung storm series:
python3 scripts/ingest_chennai_data.py
# Or via Makefile:
make ingest

# Replay historical Cyclone Michaung storm observations through the IoT pipeline:
python3 scripts/replay_historical.py
# Or via Makefile:
make replay
```

Raw data is stored in `data/raw/` and cleaned observations in `data/processed/`. Complete provenance metadata is recorded in `data/data_provenance.md`.

## Configuration

Settings are managed via environment variables defined in `.env` (copied from `.env.example` during setup):

| Variable | Default | Purpose |
|---|---|---|
| `STORAGE_BACKEND` | `sqlite` | Storage backend: `sqlite`, `influxdb`, or `memory` |
| `SQLITE_DB_PATH` | `data/civictwin.db` | Local SQLite database file path |
| `API_HOST` | `127.0.0.1` | REST API bind address |
| `API_PORT` | `8000` | REST API port |
| `MQTT_BROKER_HOST` | `localhost` | MQTT broker host |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `MQTT_TOPIC_PREFIX`| `civictwin/v1` | Telemetry topic prefix |
| `INFLUXDB_ENABLED` | `false` | Enable InfluxDB 2.x persistence |
| `INFLUXDB_URL` | `http://localhost:8086` | InfluxDB API URL |
| `INFLUXDB_TOKEN` | `""` | InfluxDB authentication token |
| `TWIN_TIME_STEP_SEC` | `5.0` | Digital twin step interval in seconds |
| `WATER_LEVEL_WARN_PCT` | `70.0` | Warning threshold percentage |
| `WATER_LEVEL_CRIT_PCT` | `85.0` | Critical threshold percentage |
| `WATER_LEVEL_HYSTERESIS_PCT` | `3.0` | Threshold hysteresis band to prevent flutter |
| `RANDOM_SEED` | `42` | Seed for deterministic simulation runs |

## Startup

CivicTwin-R supports two execution modes:

### Standalone Mode (Zero External Infrastructure)

Runs the sensor simulator, digital twin engine, SQLite persistence, and FastAPI REST API within a single Python runtime:

```bash
./scripts/start.sh
# Or using the Makefile:
make run
```

### Full Integration Mode (Docker Stack)

Starts Eclipse Mosquitto (MQTT), InfluxDB 2.x, Node-RED, and the FastAPI backend:

```bash
docker compose up -d
```

## Service Access

When services are running:

- **REST API Root**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive API Documentation (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check Endpoint**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Node-RED Dashboard**: [http://127.0.0.1:1880/ui](http://127.0.0.1:1880/ui) (when Node-RED is running)
- **Node-RED Editor**: [http://127.0.0.1:1880](http://127.0.0.1:1880)

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health, active storage backend, fallback status, ingestion stats |
| `GET` | `/api/config` | Safe configuration summary |
| `GET` | `/api/zones` | List all 3 zones with current water levels, Chennai subbasins, and alert status |
| `GET` | `/api/zones/{zone_id}` | Detailed telemetry and physics state for a zone (supports aliases like `zone_adyar`) |
| `GET` | `/api/forecast/{zone_id}` | Multi-horizon Rate-of-Rise forecast (15m, 60m, 180m) with ±1.96 SE confidence bounds |
| `GET` | `/api/forecast/evaluate` | Time-aware cross-validation comparing forecast model against naive baseline |
| `GET` | `/api/replay/status` | Current status and progress of historical observation replay |
| `POST`| `/api/replay/start` | Start streaming historical Cyclone Michaung storm observations |
| `POST`| `/api/replay/step` | Manually advance historical observation replay by N steps |
| `POST`| `/api/replay/stop` | Stop historical replay |
| `POST`| `/api/replay/reset` | Reset historical replay to beginning |
| `GET` | `/api/telemetry/latest` | Most recent telemetry records |
| `GET` | `/api/telemetry/history` | Historical records over time window |
| `GET` | `/api/alerts` | Active and historical threshold-crossing alerts |
| `GET` | `/api/scenarios` | List 8 available flood and resilience scenarios |
| `GET` | `/api/scenarios/status` | Current scenario step and completion progress |
| `POST`| `/api/scenarios/{id}/start`| Start executing a scenario |
| `POST`| `/api/scenarios/{id}/stop` | Stop running scenario and restore baseline parameters |
| `POST`| `/api/scenarios/step` | Manually advance active scenario by N steps |
| `GET` | `/api/scenarios/results`| Detailed step-by-step history of last scenario run |
| `GET` | `/api/experiments/results`| Precomputed missing-data reconstruction benchmark data |
| `GET` | `/api/stats` | System-wide ingestion, storage, and engine stats |
| `GET` | `/api/data/export` | Export stored telemetry records as JSON or CSV |

## Dashboard Access

The Node-RED flow configuration is stored in `nodered/flows.json`.

1. Launch Node-RED on port 1880.
2. Ensure `node-red-dashboard` nodes are installed (`npm install node-red-dashboard` in `~/.node-red`).
3. Import `nodered/flows.json` through Menu > Import.
4. Deploy the flow and open [http://127.0.0.1:1880/ui](http://127.0.0.1:1880/ui).

The dashboard displays:
- System overview and health status.
- Real-time gauge dials for Adyar Basin, Cooum Basin, and Kosasthalaiyar.
- Real vs Synthetic provenance indicators (`[OBSERVED]`, `[REPLAYED_HISTORICAL]`, `[DIGITAL_TWIN]`).
- Scenario trigger controls (start, stop, step) sending REST commands to the backend.
- Resilience indicators (sensor dropout, network outage, stale observation flags).

## Testing

Execute the automated pytest suite (82 unit, integration, and API tests):

```bash
make test
# Or directly:
python3 -m pytest tests/ -v
```

Run experiments and generate reproducible benchmark plots:

```bash
make experiments
# Or directly:
python3 -m experiments.run_experiments
```

Outputs are written to:
- `results/tables/reconstruction_results.json` & `.csv`
- `results/tables/latency_results.json`
- `results/tables/warning_results.json`
- `results/tables/scenario_summaries.json`
- `results/plots/reconstruction_comparison.png`
- `results/plots/reconstruction_visual.png`
- `results/plots/scenario_water_levels.png`
- `results/plots/sensor_dropout_timeline.png`

Run service connectivity checks:

```bash
make health
# Or directly:
python3 scripts/health_check.py
```

## Shutdown

To stop background processes and containers:

```bash
./scripts/stop.sh
# If Docker was used:
docker compose down
```

Stored SQLite data in `data/civictwin.db` persists across restarts. To reset the database, run `make clean`.

## Troubleshooting

### Connection Refused on http://127.0.0.1:8000
- Ensure the backend is started using `./scripts/start.sh` or `make run`.
- Verify port 8000 is not occupied by another process: `lsof -i :8000`.

### MQTT Broker Not Connected
- Standalone mode handles offline MQTT automatically by routing simulated sensor data directly into the ingestion service.
- For MQTT integration, ensure Mosquitto is active (`mosquitto -c mqtt/mosquitto.conf` or `docker compose up -d mosquitto`).

### Node-RED Dashboard Shows Unknown Nodes
- Install the dashboard UI palette: `cd ~/.node-red && npm install node-red-dashboard`.
- Restart Node-RED and redeploy the flow.

### InfluxDB Connection Errors
- Verify InfluxDB credentials in `.env` (`INFLUXDB_URL`, `INFLUXDB_TOKEN`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`).
- If InfluxDB is unavailable, set `STORAGE_BACKEND=sqlite` and `INFLUXDB_ENABLED=false` to use local SQLite storage.
