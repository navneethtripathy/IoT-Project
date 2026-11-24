# CivicTwin-R — Master Academic Showcase Demonstration Checklist

**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning  
**Verification Target:** 100% Operational Readiness, Zero Defects, Live Integration  

---

## Phase 1: Environment Pre-Flight (T - 15 Minutes)

- [ ] **Operating System:** macOS Darwin (Apple Silicon ARM64 / Intel) or Linux.
- [ ] **Python Runtime:** Python 3.11+ available (`python3 --version`).
- [ ] **Node.js Runtime:** Node.js v18+ available (`node -v`).
- [ ] **Mosquitto MQTT:** Installed at `/opt/homebrew/sbin/mosquitto` or in system `$PATH`.
- [ ] **Protected Datasets Intact:**
  - `data/processed/chennai_arg_rainfall.csv` (329 lines, 29 KB)
  - `data/processed/chennai_reservoirs.csv` (6 lines, 678 B)
  - `data/raw/cfm_dashboard_raw.json` (76 KB)
  - `data/raw/chennai_michaung_hourly_raw.json` (7.2 KB)
- [ ] **Port Availability Check:** Ports `8000`, `1883`, `1880` are unallocated (`lsof -i :8000 -i :1883 -i :1880`).

---

## Phase 2: One-Command System Launch (T - 10 Minutes)

1. Open a clean terminal in the repository root:
   ```bash
   cd "/Users/navneethtripathy/Desktop/IoT Project/CivicTwin-R"
   ```
2. Launch the full showcase stack:
   ```bash
   ./scripts/showcase_start.sh
   ```
3. Confirm all startup stages output `[OK]`:
   - [ ] `[OK] Mosquitto broker running (PID: ...)`
   - [ ] `[OK] FastAPI backend healthy (PID: ...)`
   - [ ] `[OK] Node-RED engine running (PID: ...)`
   - [ ] `[OK] Dual-node simulator active (PID: ...)`
   - [ ] `[PASS] All Critical Services Healthy (Result: PASS)`

---

## Phase 3: Browser Setup (T - 5 Minutes)

Open the following tabs in a single browser window:
- [ ] **Tab 1 (Primary Showcase Control Center):** `http://127.0.0.1:8000/showcase`
- [ ] **Tab 2 (Node-RED Flow UI):** `http://127.0.0.1:1880/ui/`
- [ ] **Tab 3 (Swagger REST API Docs):** `http://127.0.0.1:8000/docs`
- [ ] **Tab 4 (Health Check Endpoint):** `http://127.0.0.1:8000/health`

---

## Phase 4: In-Flight Demonstration Sequence (10–12 Minutes)

Follow `showcase/DEMO_GUIDE.md` through each tab:
- [ ] **Tab 1 (Overview):** Present topology, active services, storage mode (SQLite WAL), and record counter.
- [ ] **Tab 2 (Dual-Node Gauges):** Demonstrate independent telemetry streaming for Saidapet and Cooum; click **"Simulate Node 1 Dropout"** to show per-node isolation.
- [ ] **Tab 3 (3D Digital Twin):** Orbit around Three.js acrylic tanks; show real-time fluid scaling, warning/critical rings, and ESP32 LED status.
- [ ] **Tab 4 (Digital Twin ODE):** Run forward RK4 simulation; show close tracking against sensor readings (MAE < 0.25 cm).
- [ ] **Tab 5 (Gap Reconstruction):** Explain Setting A (Online Causal) vs Setting B (Offline Retrospective); highlight Physics Twin superiority at short gaps.
- [ ] **Tab 6 (Freshness & Alerts):** Show 4-state lifecycle (`FRESH` $\to$ `STALE` $\to$ `OFFLINE`) and demonstrate $3\%$ anti-chatter hysteresis.
- [ ] **Tab 7 (Chennai Basin):** Present Chennai catchment map, WRD reservoir storage gauges, and trigger **Michaung Storm Replay**.
- [ ] **Tab 8 (Scenario Laboratory):** Execute scenarios:
  - [ ] Scenario 2: Heavy Inflow Surge
  - [ ] Scenario 3: Drainage Obstruction
  - [ ] Scenario 4: Warning Breach (70%)
  - [ ] Scenario 10: Return to Normal Baseline
- [ ] **Tab 9 (Database Explorer):** Demonstrate live SQLite table schema, record pagination, and CSV export.
- [ ] **Tab 10 (MQTT Streamer):** Demonstrate live packet ring buffer and inspect JSON payloads.
- [ ] **Node-RED Tab:** Show secondary operational dashboard on port 1880/ui receiving MQTT streams concurrently.

---

## Phase 5: Automated Verification & Testing Reassurance

If examiners request proof of test coverage or mathematical correctness:
- [ ] Run full automated test suite:
  ```bash
  python3 -m pytest tests/ -v
  ```
  Confirm all **126 automated tests pass with 100% success rate**.

---

## Phase 6: Post-Demonstration Clean Shutdown

When the evaluation concludes:
```bash
./scripts/showcase_stop.sh
```
Confirm all processes terminated and ports released cleanly.
