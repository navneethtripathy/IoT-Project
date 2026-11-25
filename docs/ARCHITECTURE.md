# System Architecture

CivicTwin-R implements two cleanly separated cyber-physical workstreams within a unified offline-capable web platform:

1. **Chennai 3D Urban Flood Digital Twin (Primary Workstream A)** — Geospatial MapLibre GL JS WebGL interface (`EPSG:4326`) coupled with `Landlab OverlandFlow` 2D shallow-water routing on a metric `EPSG:32644` (UTM Zone 44N, `150 m`) grid derived from Copernicus GLO-30 topography, official Tamil Nadu CFM-DSS WFS layers, and OpenStreetMap extracts.
2. **Experimental IoT Bench Twin & Telemetry Resilience Pipeline (Workstream B)** — Simulated two-node cyber-physical testbench (`node_01`, `node_02`) streaming ultrasonic level telemetry over Mosquitto MQTT (`1883`) into FastAPI (`8000`), dual-persisted to `SQLite` (WAL mode) and `InfluxDB 2.x` (`8086`), and visualized on both Three.js WebGL and Node-RED (`1880/ui/`).

---

## Multi-Tier Data Flow

```text
Workstream A — Urban Flood Terrain Twin
  Copernicus GLO-30 DEM + CFM-DSS WFS + OSM PBF
        |
        v (EPSG:32644 UTM 44N, dx=150m, 111x175 cells)
  digital_twin/terrain_hydrology.py (Landlab OverlandFlow)
        |
        v (GeoJSON + RGBA depth PNG + mass-balance summary)
  FastAPI REST (/api/urban/*) -> Offline MapLibre 3D UI (/urban-twin)

Workstream B — Experimental IoT Bench Pipeline
  Node 01 (50 cm tank) & Node 02 (60 cm tank) [MQTT QoS 1]
        |
        +--> Mosquitto Broker (127.0.0.1:1883)
                |
                +--> Node-RED (127.0.0.1:1880/ui/) [Gauges, Charts, Debug]
                +--> FastAPI IngestionService (Pydantic v2 + Dedup + Freshness + Hysteresis)
                        |
                        +--> SQLite WAL (data/civictwin.db)
                        +--> InfluxDB 2.x (http://127.0.0.1:8086, bucket telemetry)
                        +--> Torricelli RK4 Twin + Three.js WebGL (/showcase)
```

---

## MQTT Topic & Payload Contract

Prefix: `civictwin/v1/` (QoS `1`).

| Topic Pattern | Retain | Cadence | Purpose |
| :--- | :--- | :--- | :--- |
| `civictwin/v1/nodes/{device_id}/telemetry` | `false` | `5 s` | Depth, distance, fill %, quality flags, `source` tag |
| `civictwin/v1/nodes/{device_id}/status` | `true` | `30 s` | Heap, uptime, Wi-Fi/MQTT flags, alert state |
| `civictwin/v1/nodes/{device_id}/alerts` | `false` | Event | Hysteresis-filtered warning/critical transitions |
| `civictwin/v1/zones/{zone_id}/telemetry` | `false` | `5 s` | Zone-mapped telemetry stream |
| `civictwin/v1/zones/{zone_id}/status` | `true` | `30 s` | Zone heartbeat summary |
| `civictwin/v1/zones/{zone_id}/alerts` | `false` | Event | Zone threshold transition alerts |

### Telemetry Schema Highlights (`v1.0`)
- Required fields: `schema_version`, `device_id`, `zone_id`, `sequence` (`>= 0`), `timestamp` (UTC ISO-8601), `sensor_status` (`valid | invalid | stale | offline | simulated`), `source`.
- Optional analog rain fields: `rain_sensor_raw`, `rain_indicator_pct` (Wokwi potentiometer stand-in; uncalibrated relative indicator, never interpreted as `mm` or `mm/hr`, tagged with `rain_indicator_uncalibrated`).
- Freshness state thresholds (configurable in `backend/config.py`): `FRESH` (`<= 30 s`), `STALE` (`30–90 s`), `OFFLINE` (`> 90 s`).
- Edge alarm thresholds: `70.0%` warning, `85.0%` critical, with a `3.0%` hysteresis clearance band.

---

## Persistence Schema & Storage Roles

1. **SQLite (Primary Store, WAL Mode):** Stores validated telemetry rows (`telemetry` table with `(device_id, sequence)` deduplication), zone states, and threshold alerts at `config.SQLITE_DB_PATH`. Inspectable read-only at `/api/database/tables` and `/api/database/records`.
2. **InfluxDB 2.x (Parallel Time-Series Store):** Receives dual-written measurement `telemetry` with tags (`device_id`, `zone_id`, `sensor_status`, `source`) and float fields (`distance_cm`, `water_level_cm`, `water_level_pct`, `rain_indicator_pct`) in bucket `telemetry`. Falls back gracefully to SQLite if offline.

---

## Core Service Endpoints

| Component | URL / Address | Function |
| :--- | :--- | :--- |
| Primary 3D Urban Twin | `http://127.0.0.1:8000/urban-twin` | Interactive MapLibre 3D flood terrain & scenario studio |
| Control Center | `http://127.0.0.1:8000/showcase` | Unified multi-tab interface (Urban + IoT Lab + Explorer) |
| Live Service Probes | `http://127.0.0.1:8000/api/services/status` | Real TCP/HTTP/DB health JSON for UI & verification |
| OpenAPI / Swagger UI | `http://127.0.0.1:8000/docs` | Full interactive REST documentation |
| InfluxDB 2.x UI | `http://127.0.0.1:8086` | Flux Data Explorer & time-series visualization |
| Node-RED Dashboard | `http://127.0.0.1:1880/ui/` | Secondary MQTT operational dashboard (` flows editor at /`) |
| Mosquitto MQTT | `tcp://127.0.0.1:1883` | Local MQTT message broker |
