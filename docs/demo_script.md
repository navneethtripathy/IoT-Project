# CivicTwin-R — Live Demo Script

## Duration: 8–10 minutes

## Prerequisites
- Python 3.11+ installed
- CivicTwin-R dependencies installed (`python3 -m pip install -e ".[dev]"`)
- Terminal open in the `CivicTwin-R/` directory

---

## Part 1: System Overview (1 min)

**Narration:** "CivicTwin-R is a cyber-physical digital twin for urban
flood monitoring. It demonstrates how an IoT sensor network can monitor
water levels, detect floods, and maintain useful warnings even when
sensors fail or networks go down."

**Action:** Show the project README and architecture diagram.

---

## Part 2: Run Tests (1 min)

**Narration:** "Let's verify the system is working. We have 48 automated
tests covering the digital twin, data pipeline, and reconstruction algorithms."

```bash
python3 -m pytest tests/ -v --tb=short
```

**Show:** All 48 tests passing.

---

## Part 3: Start the Backend (1 min)

```bash
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

**Narration:** "The backend starts a sensor simulator with three virtual
monitoring zones. It generates real telemetry data using our digital twin
engine."

**Open browser:** http://127.0.0.1:8000/docs

**Show:** The interactive API documentation (Swagger UI).

---

## Part 4: Explore Live Data (2 min)

**In a new terminal:**

```bash
# Check system health
curl http://127.0.0.1:8000/health | python3 -m json.tool

# View the three monitoring zones
curl http://127.0.0.1:8000/api/zones | python3 -m json.tool

# View latest telemetry
curl http://127.0.0.1:8000/api/telemetry/latest | python3 -m json.tool
```

**Narration:** "Each zone reports real-time water level data. Notice the
source field says 'simulator' — we clearly distinguish simulated data
from physical sensor data."

---

## Part 5: Run a Flood Scenario (2 min)

```bash
# Start the heavy rainfall scenario
curl -X POST http://127.0.0.1:8000/api/scenarios/heavy_rainfall/start

# Advance 100 steps
curl -X POST "http://127.0.0.1:8000/api/scenarios/step?steps=100"

# Check alerts
curl http://127.0.0.1:8000/api/alerts | python3 -m json.tool

# Check scenario status
curl http://127.0.0.1:8000/api/scenarios/status | python3 -m json.tool
```

**Narration:** "The heavy rainfall scenario increases water inflow across
all zones. Watch the alert levels change from normal to warning to critical
as thresholds are crossed."

---

## Part 6: Experiment Results (2 min)

**Stop the backend (Ctrl+C). Run experiments:**

```bash
python3 -m experiments.run_experiments
```

**Narration:** "Our experiment suite tests data reconstruction accuracy,
scenario simulations, pipeline latency, and warning behavior."

**Show the generated plots:**
- `results/plots/reconstruction_comparison.png` — MAE/RMSE comparison
- `results/plots/scenario_water_levels.png` — Water levels across scenarios
- `results/plots/reconstruction_visual.png` — Visual reconstruction example
- `results/plots/sensor_dropout_timeline.png` — Sensor failure and recovery

**Key finding:** "Linear interpolation consistently outperforms LOCF,
especially during rapid water level changes."

---

## Part 7: ESP32 Firmware (1 min)

**Show:** `firmware/esp32/src/main.ino`

**Narration:** "The ESP32 firmware reads an HC-SR04 ultrasonic sensor,
applies median filtering, evaluates local thresholds with hysteresis,
and publishes JSON telemetry over MQTT. It continues threshold checking
even when MQTT is disconnected."

**Show:** `firmware/wokwi/diagram.json` — The Wokwi wiring diagram.

---

## Part 8: Summary (1 min)

**Narration:** "CivicTwin-R demonstrates a complete IoT pipeline from
sensor to dashboard to evaluation. It handles sensor failures, network
outages, and missing data — key requirements for real-world resilient
monitoring systems."

**Key metrics to highlight:**
- 48/48 automated tests passing
- 8 configurable scenarios
- 2 reconstruction methods evaluated at 4 missing-data rates
- 3 virtual monitoring zones
- Sub-millisecond software pipeline latency
