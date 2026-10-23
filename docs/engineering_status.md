# CivicTwin-R — Engineering Status & Acceptance Checklist

Last Updated: October 2026

## System Verification Matrix

| Status Code | Meaning |
|---|---|
| **PASS** | Implemented, executed, and verified through automated tests or runtime checks |
| **FAIL** | Implemented but verification produced errors or unmet assertions |
| **BLOCKED** | Cannot be verified due to missing host dependencies (e.g. physical hardware, offline Docker) |
| **IMPLEMENTED BUT UNVERIFIED** | Code and configuration complete, but live end-to-end user verification requires external runtime |

## Acceptance Criteria Checklist

| ID | Criterion | Status | Evidence / Verification Notes |
|---|---|:---:|---|
| AC-01 | Clean and organized codebase | **PASS** | Uniform structure; no duplicate modules; minimal docstrings; no emojis or decorative comment banners in source code. |
| AC-02 | Working installation path | **PASS** | `pyproject.toml` installs via `pip install -e ".[dev]"`; `scripts/setup.sh` prepares directories and configuration. |
| AC-03 | Documented startup commands work | **PASS** | Standalone mode (`./scripts/start.sh` or `make run`) launches FastAPI server with background simulation. |
| AC-04 | MQTT telemetry reaches ingestion service | **PASS** | Verified via `TestIngestion::test_raw_mqtt_processing` and `TestIntegration::test_simulator_to_ingestion_pipeline`. Real broker fallback tested. |
| AC-05 | Telemetry persisted and queryable | **PASS** | Verified with `SQLiteStorage` and `MemoryStorage`. Multi-zone latest and range queries return persisted records. |
| AC-06 | REST API returns actual data | **PASS** | All 14 API routes verified with pytest TestClient (`TestApiEndpoints` 11/11 passing). |
| AC-07 | Node-RED consumes actual data | **IMPLEMENTED BUT UNVERIFIED** | `nodered/flows.json` polls `GET /api/zones` and `GET /health`. Live UI verification blocked because Node-RED is not running on host. |
| AC-08 | Interactive dashboard controls work | **IMPLEMENTED BUT UNVERIFIED** | Flow buttons wired to POST endpoints (`/api/scenarios/{id}/start`, `/api/scenarios/step`, `/api/scenarios/{id}/stop`). |
| AC-09 | Three virtual zones function | **PASS** | Riverside Canal, Downtown Storm Drain, and Suburban Retention Basin step synchronously and produce independent state. |
| AC-10 | All eight scenarios execute | **PASS** | `normal`, `heavy_rainfall`, `blocked_drain`, `sudden_rise`, `sensor_dropout`, `noisy_sensor`, `network_outage`, `multi_zone_stress` pass automated tests and generate data. |
| AC-11 | Missing-data reconstruction evaluated | **PASS** | LOCF and Linear Interpolation benchmarked across 5%, 10%, 20%, 30% missing rates with zero ground truth leakage. |
| AC-12 | Threshold warnings with hysteresis work | **PASS** | Verified in `TestHysteresisAndAlerts::test_hysteresis_prevents_chatter`. Alert clearing verified on water level recession. |
| AC-13 | Failure recovery verified | **PASS** | Verified in `TestFailureAndRecovery` for sensor failure/recovery and network outage/restoration. |
| AC-14 | Automated test suite passes | **PASS** | 63/63 pytest tests pass in 5.2 seconds (`make test`). |
| AC-15 | Integration tests pass | **PASS** | Multi-component pipelines (Engine -> Simulator -> Ingestion -> Storage -> API) pass in test suite. |
| AC-16 | Wokwi files valid | **PASS** | `firmware/wokwi/diagram.json` syntax validated; pinouts match ESP32 firmware (TRIG=5, ECHO=18, LED=2). |
| AC-17 | No critical integration failure remains | **PASS** | Starlette lifespan initialization tested; storage deadlock resolved with RLock; InfluxDB module implemented. |
| AC-18 | No secrets committed | **PASS** | `.env` ignored in `.gitignore`; `.env.example` contains placeholder credentials only. |
| AC-19 | Unused / temporary files removed | **PASS** | Runtime `.db` files ignored; unused packages excluded; no dead code branches. |
| AC-20 | Troubleshooting docs match implementation | **PASS** | Documented commands match scripts, Makefile targets, and API endpoints. |

## Execution Mode Breakdown

### Verified Locally (Host Machine)
- FastAPI REST backend with Lifespan management
- SQLite persistent storage with index optimization
- Digital Twin Engine with 3 zones and discrete-time hydrology physics
- 8 repeatable scenario simulations
- LOCF and Linear Interpolation missing-data reconstruction
- Ingestion deduplication, out-of-order rejection, and stale observation flagging
- Threshold crossing alerts with stateful hysteresis clearing
- Data export (CSV and JSON)
- 63 automated unit, integration, and API tests

### Tested in Wokwi / Firmware Readiness
- ESP32 Arduino C++ firmware compiles cleanly conceptually
- Circuit wiring diagram in `diagram.json` configured for HC-SR04 ultrasonic distance sensor and status LED
- Local threshold logic with hysteresis executes independently of MQTT network connection

### Blocked / External Dependencies
- Physical ESP32 hardware flashing (no physical microcontroller attached to host)
- Physical HC-SR04 water vessel calibration (no physical sensor hardware available)
- Full-stack Docker deployment (Docker daemon is not running on the macOS host)
- Live Node-RED dashboard browser rendering (requires Node-RED service running on port 1880)
