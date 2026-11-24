# CivicTwin-R — Phase 1 Architecture & Requirements Review

**Date:** 2026-11-23  
**Auditor:** Principal IoT Systems & Software Architect  
**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning  
**Status:** **AUDIT COMPLETE — PASSED WITH DISCLOSED SIMULATION SCOPE**

---

## 1. Executive Summary

This architecture review verifies that the implemented software and simulation architecture strictly aligns with the declared project requirements for both **Workstream A (Chennai Urban Flood Monitoring)** and **Workstream B (Tank-Level Digital Twin)**. Every requirement has been mapped to concrete code modules and test cases. Architectural boundaries between physical ground truth, simulated laboratory dynamics, and historical municipal datasets are rigorously maintained.

---

## 2. Requirements Traceability Matrix (RTM)

The table below establishes full bidirectional traceability between requirements, code implementations, automated verification tests, and status.

| Req ID | Requirement Statement | Implementing Component | Verification Test Case | Verified Status | Evidence Summary |
|---|---|---|---|---|---|
| **FR-01** | Support concurrent ingestion for dual distinct nodes (`node_01`, `node_02`) without cross-contamination. | `backend/ingestion.py`<br>`backend/models.py` | `tests/test_tank_twin.py::TestDualNodeConcurrentIsolation` | **PASS** | Interleaved message streams are logically separated in memory and SQLite; per-node sequence tracking prevents cross-talk. |
| **FR-02** | Telemetry payload schema validation and explicit `null` handling for invalid sensor echo timeouts. | `backend/models.py`<br>`backend/ingestion.py` | `tests/test_tank_twin.py::TestFreshnessEngine::test_freshness_lifecycle` | **PASS** | Pydantic v2 schemas reject malformed JSON; invalid echoes emit `null` depth rather than zero depth. |
| **FR-03** | Telemetry deduplication and out-of-order rejection based on `(device_id, sequence)` tracking. | `backend/ingestion.py` | `tests/test_tank_twin.py::TestDualNodeConcurrentIsolation` | **PASS** | Sequence numbers strictly tracked per `device_id`; older/duplicate sequences increment duplicate counter and are dropped. |
| **FR-04** | Timestamp-driven freshness classification (`FRESH`, `STALE`, `OFFLINE`, `INVALID`) based on event timestamps. | `backend/ingestion.py`<br>`backend/models.py` | `tests/test_tank_twin.py::TestFreshnessEngine` | **PASS** | State transitions: $<30\text{s} \rightarrow \text{FRESH}$; $30\text{s}-90\text{s} \rightarrow \text{STALE}$; $>90\text{s} \rightarrow \text{OFFLINE}$. |
| **FR-05** | Autonomous edge warning with anti-chatter hysteresis ($70\%$ warn, $85\%$ crit, $3\%$ hysteresis band). | `firmware/esp32/src/main.ino`<br>`digital_twin/edge_warning.py` | `tests/test_tank_twin.py::TestEdgeWarningEvaluator` | **PASS** | Evaluated locally; 1 Hz LED blink for Warning; Solid ON for Critical; clearing requires falling below $(T - 3\%)$. |
| **FR-06** | Calibrated mass-balance ODE solver ($\frac{dh}{dt} = \frac{Q_{\text{in}} - k\sqrt{h}}{A}$) using Runge-Kutta 4th Order. | `digital_twin/tank_twin.py`<br>`PhysicalTankModel.step_rk4()` | `tests/test_tank_twin.py::TestNumericalConvergenceAndCalibration` | **PASS** | Convergence verified against analytical solution; step truncation errors decrease $O(\Delta t^4)$. |
| **FR-07** | Analytical Torricelli drain-down calibration ($2A(\sqrt{h_0}-\sqrt{h_t}) = k \cdot t$) recovering $k$ via OLS regression. | `digital_twin/tank_twin.py`<br>`calibrate_drain_down()` | `tests/test_tank_twin.py::TestNumericalConvergenceAndCalibration` | **PASS** | Recovers synthetic $k=4.5$ within $0.56\%$ error under Gaussian sensor measurement noise ($R^2 > 0.99$). |
| **FR-08** | Digital twin prediction vs measurement error evaluation (MAE, RMSE, Pearson correlation). | `digital_twin/tank_twin.py`<br>`evaluate_tank_prediction()` | `tests/test_tank_twin.py::TestRestApiExtensions::test_tank_compare_endpoint` | **PASS** | Computed via `/api/tank/compare` against stored telemetry window. |
| **FR-09** | Missing-data reconstruction benchmarking LOCF, Causal Linear Trend, Linear Interpolation, and Physics Twin. | `digital_twin/reconstruction.py`<br>`experiments/run_three_method_reconstruction.py` | `tests/test_tank_twin.py::TestThreeMethodReconstruction` | **PASS** | Strict separation of Setting A (Online Causal) and Setting B (Offline Retrospective) across 4 gap durations and 3 seeds. |
| **FR-10** | Strict provenance tagging across all storage records (`OBSERVED`, `PYTHON_SIMULATED`, `REPLAYED_HISTORICAL`, `DIGITAL_TWIN`, `IMPUTED`). | `backend/models.py`<br>`DataSource` enum | `tests/test_all.py::TestProvenanceAndSensorVerification` | **PASS** | Canonical uppercase tags enforced across Pydantic models, SQLite persistence, and API schemas. |
| **FR-11** | Dual persistence backend (SQLite default + optional InfluxDB 2.x) with automatic fallback. | `backend/storage.py`<br>`SQLiteStorage` | `tests/test_all.py::TestStorage` | **PASS** | Automatic fallback to SQLite when InfluxDB is disabled or unreachable; schema migrations survive restarts. |
| **FR-12** | REST API endpoints for tank config, prediction, calibration, freshness, and node status. | `backend/app/main.py` | `tests/test_tank_twin.py::TestRestApiExtensions` | **PASS** | All 25+ endpoints operational with valid schemas, error handling, and CORS middleware. |
| **FR-13** | Node-RED dashboard interface with dynamic environment-variable backend URL resolution. | `nodered/flows.json`<br>`nodered/README.md` | Static JSON inspect & URL template audit | **PASS** | Uses `${BACKEND_URL:-http://127.0.0.1:8000}`, supporting both standalone host and Docker networking. |
| **FR-14** | Historical Chennai rainfall and reservoir dataset ingestion and replay. | `scripts/replay_historical.py`<br>`scripts/ingest_chennai_data.py` | `tests/test_chennai_twin.py::TestNewApiEndpoints` | **PASS** | Historical rainfall (CFM-DSS) and reservoir capacity (WRD) ingested; replayed deterministically. |
| **FR-15** | Physical sensor hardware deployment with JSN-SR04T and physical tank drain test. | Physical Laboratory Hardware | Hardware bench inspection | **BLOCKED** | No physical hardware attached; firmware and electrical schematics verified in software. |

---

## 3. Subsystem Architecture Audits

### 3.1 Workstream A: Chennai Urban Flood Monitoring
- **Hydrological Grounding:** Real observations from the Chennai Flood Monitoring & Decision Support System (CFM-DSS, World Bank PDGF) covering 117 Automatic Rain Gauge (ARG) stations (328 records) and daily storage from 5 major reservoirs (Chembarambakkam, Poondi, Red Hills, Cholavaram, Thervoy Kandigai).
- **Distinction of Concepts:** Rainfall measurements are in millimeters ($\text{mm}$) and drive catchment runoff calculations; reservoir capacities are in Million Cubic Meters ($\text{MCM}$) and provide boundary conditions. Neither is conflated with river stage water level ($\text{cm}$).
- **Lumped Catchment Model:** The discrete-time mass balance model simulates 3 sub-basins:
  1. `zone_01`: Adyar Basin (Saidapet / Chembarambakkam corridor)
  2. `zone_02`: Cooum Basin (Central urban drainage corridor)
  3. `zone_03`: Kosasthalaiyar Basin (North Chennai / Ennore corridor)
- **Scientific Honesty:** Model outputs are explicitly identified as lumped hydrological simulations for scenario exploration, not certified 2D hydrodynamic flood forecasts.

### 3.2 Workstream B: Tank-Level Digital Twin
- **Dual Node Identity:**
  - `node_01` / `tank_01`: Diameter $19.54\text{ cm}$, Area $299.87\text{ cm}^2$, Max Height $50.0\text{ cm}$, Nominal $k=4.5\text{ cm}^{2.5}/\text{s}$, Inflow $25.0\text{ cm}^3/\text{s}$.
  - `node_02` / `tank_02`: Diameter $23.94\text{ cm}$, Area $450.13\text{ cm}^2$, Max Height $60.0\text{ cm}$, Nominal $k=6.0\text{ cm}^{2.5}/\text{s}$, Inflow $35.0\text{ cm}^3/\text{s}$.
- **Electrical Safety & Sensor Interfacing:**
  - Designed for JSN-SR04T waterproof ultrasonic sensor with $20\text{ cm}$ minimum blind distance (or HC-SR04 with $2\text{ cm}$ minimum).
  - Explicit $2.2\text{k}\Omega / 3.3\text{k}\Omega$ passive resistor divider protects the ESP32 GPIO 18 from 5V echo logic, dropping voltage to $3.0\text{V}$.
- **Edge Warning State Machine:**
  - Autonomous edge evaluation running on ESP32 without backend dependency.
  - Hysteresis band of $3.0\%$ prevents relay/LED chatter near warning ($70\%$) and critical ($85\%$) thresholds.
  - Distinct LED signalling: 1 Hz blink for Warning, Solid ON for Critical, Rapid strobe (5 Hz) for Sensor Fault.

---

## 4. Architectural Deficiencies & Resolutions

1. **Hardcoded URLs in Health Check:**
   - *Deficiency:* `scripts/health_check.py` previously had hardcoded `127.0.0.1` addresses.
   - *Resolution:* Updated to import `config.API_HOST`, `config.API_PORT`, `config.NODERED_PORT`, and `config.INFLUXDB_URL`.
2. **Polluted `nodered/README.md`:**
   - *Deficiency:* File contained 1158 lines of duplicated audit prompts before actual content.
   - *Resolution:* Cleaned to contain strictly the valid 60-line Node-RED dashboard operational instructions.

---

## 5. Phase 1 Acceptance Decision

**Verdict: ACCEPTED (PASS)**  
All software and simulated architectural requirements are fully satisfied, verifiable in code, and confirmed by passing regression tests. Hardware deployment remains explicitly classified as BLOCKED.
