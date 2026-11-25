# Setup, Configuration, and Testing Guide

## 1. Prerequisites
- **Python:** 3.11+ (verified on 3.14.5 Apple Silicon macOS and CI Ubuntu 3.12).
- **System Services (Native macOS Full Stack):**
  - **Mosquitto MQTT Broker** (`brew install mosquitto`)
  - **InfluxDB 2.x** (`brew install influxdb@2`) — optional; SQLite WAL stores all records when InfluxDB is disabled.
  - **Node.js 20+** and local `nodered_runtime/` (`npm install node-red node-red-dashboard` inside `nodered_runtime` if Node-RED UI is desired).
- **Optional Browser QA:** Google Chrome or Chromium + `playwright`.

---

## 2. Clean Installation & Environment Initialization

```bash
git clone https://github.com/navneethtripathy/IoT-Project.git
cd CivicTwin-R

# Automated setup: generates local .env credentials, installs editable package + GIS libs,
# initializes InfluxDB if present, and checks pre-processed Chennai geospatial bundles
./scripts/setup.sh
```

> **Security Note:** `.env` is gitignored. Never commit credentials or tokens. `setup.sh` populates `.env` from `.env.example` with randomized local InfluxDB credentials (`ct2_...`).

---

## 3. Configuration (`backend/config.py` & `.env`)

All runtime settings are centralized in `backend/config.py`:

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `API_HOST`, `API_PORT` | `127.0.0.1`, `8000` | FastAPI listen address |
| `MQTT_BROKER_HOST`, `MQTT_BROKER_PORT` | `localhost`, `1883` | Mosquitto broker endpoint |
| `STORAGE_BACKEND` | `sqlite` | `sqlite`, `influxdb`, or `memory` |
| `SQLITE_DB_PATH` | `data/civictwin.db` | Local WAL database location |
| `INFLUXDB_ENABLED`, `INFLUXDB_URL`, `INFLUXDB_ORG`, `INFLUXDB_BUCKET`, `INFLUXDB_TOKEN` | `false`, `http://localhost:8086`, `civictwin`, `telemetry`, `""` | Dual time-series storage connection |
| `NODERED_PORT` | `1880` | Local Node-RED HTTP port |
| `STALE_READING_TIMEOUT_SEC`, `OFFLINE_TIMEOUT_SEC` | `30.0`, `90.0` | Freshness transition thresholds |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG` prints packet-level telemetry) |

---

## 4. Lifecycle Commands

```bash
# Start full operational stack (Mosquitto, InfluxDB, FastAPI, Node-RED, Two-Node Simulator)
./scripts/showcase_start.sh

# Run live endpoint, broker, database, geospatial, and telemetry health checks
./scripts/showcase_verify.sh

# Cleanly terminate only project-owned services tracked under .run/
./scripts/showcase_stop.sh
```

To re-acquire raw Copernicus/WFS/OSM assets from public upstream mirrors (requires ~560 MB download for Geofabrik PBF):
```bash
python3 scripts/acquire_chennai_geodata.py
python3 scripts/process_chennai_geodata.py
```

---

## 5. Automated Testing & Scientific Benchmarks

```bash
# Offline unit, physics calibration, geospatial DEM/WFS/OSM, and Landlab 2D tests (CI suite)
PYTHONPATH=. pytest tests/test_all.py tests/test_tank_twin.py tests/test_chennai_twin.py tests/test_terrain_hydrology.py tests/test_urban_twin.py -v

# Full local test suite (includes live Mosquitto, Node-RED & InfluxDB integration suites)
PYTHONPATH=. pytest tests/ -v

# Headless Chrome strict-offline browser QA & screenshot capture
python3 scripts/verify_browser_qa.py

# Reproduce reconstruction & scenario benchmark plots
python3 -m experiments.run_experiments
python3 -m experiments.run_three_method_reconstruction
```
