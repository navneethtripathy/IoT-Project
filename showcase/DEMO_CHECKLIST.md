# CivicTwin-R — Pre-Presentation Readiness Checklist

**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin  
**Verification Target:** 100% Operational Readiness for Academic Showcase

---

## Phase 1: Environment & Tool Verification (5 Minutes Prior)
- [ ] Operating System is macOS (ARM64 / x86_64) or Linux.
- [ ] Python 3.11+ is installed (`python3 --version`).
- [ ] Homebrew Mosquitto is installed at `/opt/homebrew/sbin/mosquitto` (or in PATH).
- [ ] Node.js and npm are available (`node -v`, `npm -v`).
- [ ] Port 1883 (MQTT), Port 8000 (FastAPI), and Port 1880 (Node-RED) are free.

---

## Phase 2: One-Command Startup
- [ ] Open terminal in project root:
  ```bash
  cd "/Users/navneethtripathy/Desktop/IoT Project/CivicTwin-R"
  ```
- [ ] Launch the complete showcase:
  ```bash
  ./scripts/showcase_start.sh
  ```
- [ ] Verify that all 5 startup steps report `[OK]`:
  1. `[OK] Mosquitto broker running`
  2. `[OK] FastAPI backend healthy`
  3. `[OK] Node-RED engine running`
  4. `[OK] Dual-node simulator active`
  5. `[PASS] All Critical Services Healthy`

---

## Phase 3: Browser Tabs Setup
Open the following URLs in separate browser tabs before examiners arrive:
- [ ] **Tab 1 (Primary Showcase Control Center):** `http://127.0.0.1:8000/showcase`
- [ ] **Tab 2 (Node-RED Flow UI):** `http://127.0.0.1:1880/ui`
- [ ] **Tab 3 (Swagger REST API Docs):** `http://127.0.0.1:8000/docs`
- [ ] **Tab 4 (Health Check Endpoint):** `http://127.0.0.1:8000/health`

---

## Phase 4: Functional Verification Check
- [ ] Telemetry counter on Showcase Control Center is incrementing every 2.5 seconds.
- [ ] Node 01 and Node 02 tank column visualizers show animated water levels.
- [ ] Top bar indicates `MQTT (1883): CONNECTED`.
- [ ] Clicking **"Inject Inflow Surge"** causes Node 1 fill level to rise and trigger WARNING alert.
- [ ] Clicking **"Run Normal Baseline"** restores nominal water level.

---

## Phase 5: Safe Post-Demo Shutdown
- [ ] When demonstration concludes:
  ```bash
  ./scripts/showcase_stop.sh
  ```
- [ ] Confirm all ports released:
  ```bash
  ./scripts/showcase_verify.sh
  ```
