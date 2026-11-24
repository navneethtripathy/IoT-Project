# CivicTwin-R — Comprehensive Service Directory & Access Matrix

**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning  
**Environment:** Local Host Deployment (macOS Darwin ARM64 / Linux)  
**Host Binding:** `127.0.0.1` / `localhost`

---

## 1. Primary Service Endpoints

| Service Name | Protocol / Port | Primary Access URL | Function & Capability | Authentication | Process Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Engineering Showcase Web Center** | HTTP / `8000` | [http://127.0.0.1:8000/showcase](http://127.0.0.1:8000/showcase) | Primary academic demonstration UI: Dual-node gauges, 3D WebGL twin, RK4 ODE prediction, reconstruction benchmark, scenario lab, SQLite database explorer, and MQTT packet streamer. | Anonymous (Read/Write) | Uvicorn / FastAPI (`backend.app.main:app`) |
| **Interactive OpenAPI Documentation** | HTTP / `8000` | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Swagger UI for interactive execution and validation of all REST API endpoints. | Anonymous | FastAPI (`/docs`) |
| **ReDoc API Specifications** | HTTP / `8000` | [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc) | Alternative structured technical reference documentation for the REST API. | Anonymous | FastAPI (`/redoc`) |
| **Node-RED Operational Dashboard** | HTTP / `1880` | [http://127.0.0.1:1880/ui/](http://127.0.0.1:1880/ui/) | Secondary real-time operations dashboard featuring gauges, water level bar charts, alert badges, and historical trend curves. | Anonymous | Node.js (`node-red/red.js`) |
| **Node-RED Flow Editor** | HTTP / `1880` | [http://127.0.0.1:1880/](http://127.0.0.1:1880/) | Visual drag-and-drop IoT flow programming canvas displaying MQTT subscriptions, JSON parsing, and dashboard node connections. | Anonymous | Node.js (`node-red/red.js`) |
| **Mosquitto MQTT Message Broker** | TCP / `1883` | `mqtt://127.0.0.1:1883` | Central message broker handling real-time publish/subscribe message distribution for all edge nodes, simulators, backend, and Node-RED. | Anonymous (local binding) | Eclipse Mosquitto binary |

---

## 2. Core REST API Endpoints Index

### System Health & Status
- **`GET /health`**: Returns system operational status, database storage mode, MQTT connection state, message ingestion counters, and tracked zone counts.
- **`GET /api/scenarios/status`**: Returns active cyber-physical scenario status and remaining duration.

### Telemetry & Zones
- **`GET /api/zones`**: Returns state for all active zones (`zone_01` Adyar, `zone_02` Cooum, `zone_03` Kosasthalaiyar), including water level, distance, battery, RSSI, and alert state.
- **`GET /api/telemetry/latest?zone_id={id}&limit={n}`**: Returns latest ingested telemetry records filtered by zone or device ID.
- **`GET /api/telemetry/history?zone_id={id}&start={iso}&end={iso}`**: Returns historical time-series telemetry records within a bounded timestamp window.
- **`GET /api/alerts?limit={n}`**: Returns active and historical edge alert events with severity classifications.

### Calibrated Tank Digital Twin
- **`GET /api/tank/config?tank_id={id}`**: Returns physical geometry specifications ($H_{\max}, R, A, k_{\text{nominal}}, V_{\max}$) for the specified tank twin.
- **`GET /api/tank/predict?tank_id={id}&duration_sec={s}&dt_sec={s}&q_in={v}`**: Computes forward RK4 numerical ODE trajectory under specified or calibrated inflow.
- **`GET /api/tank/compare?tank_id={id}&duration_sec={s}&dt_sec={s}`**: Compares recent live sensor telemetry against simulated RK4 trajectory, computing real-time MAE, RMSE, and Pearson correlation metrics.
- **`POST /api/tank/calibrate`**: Executes Ordinary Least Squares regression on unforced drain-down observations to calculate the experimental orifice discharge coefficient $\hat{k}$ and $R^2$.

### Reliability & Freshness
- **`GET /api/nodes/freshness`**: Returns real-time freshness state (`FRESH`, `STALE`, `OFFLINE`) and observation age for all registered nodes.
- **`GET /api/nodes/status`**: Returns diagnostic heartbeat status (battery voltage, WiFi RSSI, sensor hardware status, quality flags).

### Database Explorer
- **`GET /api/database/tables`**: Returns list of all SQLite tables and row counts.
- **`GET /api/database/records?table={name}&limit={n}&offset={m}&device_id={id}`**: Returns paginated database records with column schema metadata.
- **`GET /api/database/stats`**: Returns database file size, journal mode, total records, min/max timestamps, and storage health.
- **`GET /api/database/export?format=csv`**: Downloads complete telemetry archive as CSV.

### Live MQTT Streamer
- **`GET /api/mqtt/recent-messages?limit={n}`**: Returns in-memory ring buffer of recent incoming MQTT packets with topic, payload, QoS, timestamp, and size.

### Scenario Planning Laboratory
- **`POST /api/showcase/scenario/{name}`**: Triggers one of 10 cyber-physical operational profiles (`normal`, `rising_water`, `drainage_obstruction`, `warning_breach`, `critical_inundation`, `node1_dropout`, `node2_stale`, `missing_data_recovery`, `rapid_reconnect`, `return_to_normal`).
- **`POST /api/replay/michaung/start`**: Initiates historical playback of the December 2023 Cyclone Michaung storm series.
- **`POST /api/replay/michaung/stop`**: Halts historical storm replay and returns to live telemetry.

---

## 3. MQTT Topic Hierarchy Reference

| Topic Pattern | QoS | Direction | Description |
| :--- | :--- | :--- | :--- |
| `civictwin/v1/nodes/{device_id}/telemetry` | 1 | Edge $\to$ Broker | Primary sensor packet: `distance_cm`, `water_level_cm`, `water_level_pct`, `sequence`, `source`. |
| `civictwin/v1/nodes/{device_id}/status` | 1 | Edge $\to$ Broker | Node heartbeat: `battery_v`, `wifi_rssi_dbm`, `sensor_status`, `uptime_s`. |
| `civictwin/v1/nodes/{device_id}/alerts` | 1 | Edge $\to$ Broker | Edge-triggered alert: `alert_level`, `threshold_pct`, `optical_pattern`. |
| `civictwin/v1/zones/{zone_id}/telemetry` | 1 | Edge $\to$ Broker | Catchment-level telemetry stream for zone-aggregated monitoring. |
| `civictwin/v1/zones/{zone_id}/status` | 1 | Edge $\to$ Broker | Zone diagnostic summary stream. |
| `civictwin/v1/zones/{zone_id}/alerts` | 1 | Edge $\to$ Broker | Zone threshold alert notification stream. |

---

## 4. Local File & Storage Paths

| Resource | Path on Disk | Format | Description |
| :--- | :--- | :--- | :--- |
| **SQLite Database** | `data/civictwin.db` | SQLite 3 (WAL mode) | Primary time-series and state persistence store. |
| **Runtime Logs Directory** | `.run/logs/` | Text (`.log`) | Contains `mosquitto.log`, `backend.log`, `nodered.log`, `simulator.log`. |
| **Process ID Files** | `.run/*.pid` | Text (PID) | Contains `mosquitto.pid`, `backend.pid`, `nodered.pid`, `simulator.pid`. |
| **Node-RED Flows** | `nodered/flows.json` | JSON | Complete Node-RED visual dashboard flow definition. |
| **Simulator Control File** | `data/simulator_control.json` | JSON | IPC parameter override file used by the scenario controller. |
| **Protected Chennai Datasets** | `data/processed/*.csv`, `data/raw/*.json` | CSV / JSON | Historical rainfall, reservoir storage, and Cyclone Michaung datasets. |
