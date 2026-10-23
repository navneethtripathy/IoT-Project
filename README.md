# CivicTwin-R: Real-Data Grounded Urban Flood Digital Twin

A resilient cyber-physical digital twin platform for urban water-level monitoring, simulated flood scenario testing, interpretable early-warning forecasting, and missing-data resilience evaluation grounded in real environmental observations from the **Chennai Metropolitan Basin, Tamil Nadu, India** (Adyar, Cooum, and Kosasthalaiyar sub-basins).

---

## 1. End-to-End Cyber-Physical Architecture & Data Pipeline

The project implements a verifiable end-to-end data pipeline connecting edge sensing, transport, storage, digital-twin physics, and visualization:

```
[Wokwi ESP32 / Physical ESP32 / Python Simulator]
                         │
                         ▼ (JSON Telemetry via Wi-Fi)
                  [MQTT Broker: Mosquitto]
                         │ (Topic: civictwin/v1/zones/{zone}/telemetry)
                         ▼
             [Ingestion & Validation Service]
              • Schema validation & sequence check
              • Duplicate rejection & stale-data flagging
                         │
                         ▼
             [Dual Storage Engine]
              • InfluxDB 2.x (Mode A: Docker Stack)
              • SQLite local DB (Mode B: Standalone Fallback)
                         │
                         ▼
         [Digital Twin Model & Scenario Engine]
          • Discrete-time catchment mass balance
          • Rate-of-Rise multi-horizon forecasting
          • 8 hypothetical flood & failure scenarios
          • Missing-data reconstruction (LOCF & Linear)
                         │
                         ▼
        [FastAPI REST API] & [Node-RED Dashboard]
          • Interactive Swagger Docs (/docs)
          • Real-time gauge dials, alerts, and provenance badges
```

---

## 2. Geographic Grounding: Chennai Study Zones

CivicTwin-R models three distinct hydrological sub-basins within the Chennai Metropolitan Basin:
1. `zone_01` (`zone_adyar`): **Adyar River Basin** (Saidapet transit corridor & Chembarambakkam reservoir outflow).
2. `zone_02` (`zone_cooum`): **Cooum River Basin** (Central Urban Drain, Nungambakkam, and Napier Bridge outflow).
3. `zone_03` (`zone_kosasthalaiyar`): **Kosasthalaiyar Basin** (North Chennai Industrial Corridor, Poondi upstream, and Ennore Creek).

> **Important Study Area Disclaimer:**  
> These three zones represent **virtual study catchments in the software digital twin**. They demonstrate cyber-physical modeling and resilience analysis; they do **not** imply that physical hardware sensor nodes have been deployed across Chennai's rivers.

---

## 3. Strict Data Provenance Standards

To ensure transparency, every telemetry record, API response, and dashboard badge strictly maintains its origin provenance tag. **Simulated, predicted, replayed, or imputed values are never labeled as live observations:**

| Provenance Tag | Source Description | Role in CivicTwin-R |
|---|---|---|
| `WOKWI_SIMULATED` | Virtual ESP32 DevKit and simulated HC-SR04 ultrasonic distance sensor in Wokwi. | Edge simulation mapped specifically to `zone_adyar` (`zone_01`). |
| `PYTHON_SIMULATED` | Python multi-zone sensor simulator (`backend/simulator.py`). | Synthetic multi-zone sensor generation for testing and CI. |
| `OBSERVED` | Verified historical records from official monitoring portals. | CFM-DSS rain gauge records and reservoir storage metrics. |
| `REPLAYED_HISTORICAL` | Historical storm observations replayed through the IoT ingestion pipeline. | Cyclone Michaung Dec 2023 hourly storm series. |
| `DIGITAL_TWIN` | Physics model states, hypothetical scenario runs, and rate-of-rise forecasts. | Catchment mass-balance calculations and multi-horizon predictions. |
| `IMPUTED` | Missing readings reconstructed using imputation algorithms. | Evaluated data recovery (LOCF / Linear interpolation) during sensor dropouts. |

---

## 4. Edge Sensor Behavior & Wokwi Simulation

The edge firmware (`firmware/esp32/src/main.ino`) targets an ESP32 microcontroller with an HC-SR04 ultrasonic distance sensor:

- **Wokwi Association:** The Wokwi virtual node (`node_01`) is explicitly associated with a single designated study zone: **Adyar Basin (`zone_01`)**. It does not measure all three basins simultaneously.
- **Distance Control:** Adjusting the HC-SR04 slider in Wokwi changes the acoustic echo time, directly altering the simulated distance.
- **Sampling Interval:** Configured to **5 seconds** (`READ_INTERVAL_MS = 5000`).
- **Container Geometry & Conversion Formula:**
  The sensor assumes a fixed downward mount above a channel/container with a known reference height:
  $$\text{Water Depth (cm)} = \text{Container Reference Height (cm)} - \text{Measured Distance (cm)}$$
  $$\text{Water Level (\%)} = 100 \times \frac{\text{Water Depth (cm)}}{\text{Container Reference Height (cm)}}$$
  - Default prototype reference height: **30.0 cm** (`CONTAINER_HEIGHT_CM`).
  - Values are clamped to $[0.0, 30.0]\text{ cm}$ and $[0.0\%, 100.0\%]$.
- **Safe Invalid Handling:** Echo timeouts or distances outside $[2.0, 400.0]\text{ cm}$ trigger `sensor_status: "invalid"`. Null values are emitted rather than fabricating a false zero-depth reading.
- **Circuit Pinouts in `diagram.json`:**
  - `TRIG` $\rightarrow$ GPIO 5
  - `ECHO` $\rightarrow$ GPIO 18
  - `Status Alert LED` $\rightarrow$ GPIO 2 (with 220Ω resistor)
  - Voltage divider note: Physical deployment requires a $2.2\text{k}\Omega / 3.3\text{k}\Omega$ voltage divider on GPIO 18 (steps 5V ECHO down to 3.0V). Not required in Wokwi simulation.

---

## 5. Warning Thresholds & Alert Logic

- **Warning Threshold:** `70.0%`
- **Critical Threshold:** `85.0%`
- **Hysteresis Band:** `3.0%` (prevents alert oscillation when levels hover near threshold)
- **Local LED Alert:** GPIO 2 LED turns ON during warning and critical states, operating independently even if network connectivity drops.

> **Prototype Threshold Disclaimer:**  
> The 70% and 85% thresholds are software test parameters for evaluating alert mechanics. They are **not** officially validated, certified, or legal flood alert levels for Chennai.

---

## 6. Official Environmental Data & Hydrological Claims

- **CFM-DSS Monitoring Network:** Developed under the World Bank PDGF by TNUIFSL, CRA, GCC, WRD, and IIT Madras ([https://www.chennaifloodmonitor.tn.gov.in/](https://www.chennaifloodmonitor.tn.gov.in/)).
- **Station Count vs. Record Count:** The CFM-DSS raw dataset contains **328 historical observation records** collected across **117 Automatic Rain Gauge (ARG) stations**.
- **Rainfall vs. River Level Distinction:** ARG stations measure **precipitation (mm)**, not direct river water depth. In CivicTwin-R, rainfall drives catchment inflow in the mass-balance equations; it is not treated as river water level.
- **Reservoirs Storage Metrics:** Capacities from Chembarambakkam, Poondi, RedHills, Cholavaram, and Thervoy Kandigai reflect official WRD daily stage-storage reports in Million Cubic Meters (MCM), not automated continuous depth gauges.
- **Unverified Data Limitations:** No open real-time river stage ultrasonic sensor API is published for Chennai waterways. River levels are simulated via the lumped mass-balance model.

---

## 7. Prerequisites & Installation

### Prerequisites
- Python 3.11 or higher
- pip (Python package installer)
- Git
- Optional for full Docker stack: Docker & Docker Compose; Node-RED for dashboard.

### Installation
```bash
git clone <repository_url>
cd CivicTwin-R

# Install dependencies in editable mode
pip install -e ".[dev]"
```

---

## 8. Startup & Execution Modes

### Mode B: Standalone Mode (Zero External Infrastructure)
Runs the sensor simulator, digital twin engine, SQLite persistence, and FastAPI REST API locally within Python:
```bash
./scripts/start.sh
# Or via Makefile:
make run
```

### Mode A: Full Integration Mode (Docker Stack)
Starts Mosquitto MQTT broker, InfluxDB 2.x, Node-RED, and the FastAPI backend:
```bash
docker compose up -d
```

---

## 9. Service Access & Endpoints

- **REST API Root**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive Swagger Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- **Node-RED Dashboard**: [http://127.0.0.1:1880/ui](http://127.0.0.1:1880/ui)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health, storage backend, fallback status, ingestion metrics |
| `GET` | `/api/config` | Safe configuration summary |
| `GET` | `/api/zones` | List all 3 zones with water level, sub-basin info, and provenance |
| `GET` | `/api/zones/{zone_id}` | Detailed telemetry and physics state for a zone |
| `GET` | `/api/forecast/{zone_id}` | Multi-horizon Rate-of-Rise forecast (15m, 60m, 180m) with ±1.96 SE bounds |
| `GET` | `/api/forecast/evaluate` | Time-aware cross-validation comparing forecast model against naive baseline |
| `GET` | `/api/replay/status` | Current status and progress of historical observation replay |
| `POST`| `/api/replay/start` | Start streaming historical Cyclone Michaung storm observations |
| `POST`| `/api/replay/step` | Manually advance historical observation replay by N steps |
| `POST`| `/api/replay/stop` | Stop historical replay |
| `GET` | `/api/telemetry/latest` | Most recent telemetry records with explicit provenance |
| `GET` | `/api/alerts` | Active and historical threshold-crossing alerts |
| `GET` | `/api/scenarios` | List 8 available flood and resilience scenarios (with simulation disclaimer) |
| `POST`| `/api/scenarios/{id}/start`| Start executing a hypothetical scenario |
| `POST`| `/api/scenarios/{id}/stop` | Stop running scenario and restore baseline parameters |
| `GET` | `/api/experiments/results`| Precomputed missing-data reconstruction benchmark data |

---

## 10. Node-RED Dashboard

The dashboard flow configuration is stored in `nodered/flows.json`.
Import `nodered/flows.json` in Node-RED and navigate to [http://127.0.0.1:1880/ui](http://127.0.0.1:1880/ui).

- **Real-Time Dials:** Gauge dials for Adyar Basin, Cooum Basin, and Kosasthalaiyar.
- **Status & Provenance Badges:** Every reading shows its source tag (`[WOKWI_SIMULATED]`, `[PYTHON_SIMULATED]`, `[OBSERVED]`, `[REPLAYED_HISTORICAL]`, `[DIGITAL_TWIN]`, `[IMPUTED]`), status (`[ONLINE]`, `[STALE]`, `[INVALID]`, `[OFFLINE]`), and timestamp.
- **Scenario Laboratory:** Clearly labeled as **Hypothetical Model Simulations** for resilience testing, not actual future measurements.

---

## 11. Testing & Experiments

Run the automated test suite (82+ unit, integration, and API tests):
```bash
python3 -m pytest tests/ -v
# Or via Makefile:
make test
```

Execute the reproducible missing-data reconstruction experiments and generate benchmark plots:
```bash
python3 -m experiments.run_experiments
# Or via Makefile:
make experiments
```

Outputs generated in `results/`:
- `results/tables/reconstruction_results.json` & `.csv` (LOCF vs. Linear interpolation across 5%, 10%, 20%, 30% dropout rates)
- `results/plots/reconstruction_comparison.png`
- `results/plots/reconstruction_visual.png`
- `results/plots/scenario_water_levels.png`
- `results/plots/sensor_dropout_timeline.png`
