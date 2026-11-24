# CivicTwin-R — Showcase Gap Analysis & Operational Transition Plan

**Date:** 2026-11-23  
**Lead Engineer:** Principal Systems & IoT Integration Engineer  
**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning  
**Target Milestone:** Transition from STATUS B (Disclosed Software Limitations) to **SHOWCASE READY**

---

## 1. Executive Baseline & Mission Definition

The preceding engineering audit established that CivicTwin-R possesses a mathematically verified, fully unit-tested Python backend (119/119 passing tests), calibrated digital twin ODE solver, and comprehensive documentation.

However, to transition from an academic software baseline into a **live, operational, interactive showcase** that can be presented live to professors and reviewers, several operational and integration gaps must be bridged:

```
[Previous State: Status B]                     [Target State: Showcase Ready]
• Software tests pass with mocks                • Live native MQTT broker (Mosquitto)
• Standalone internal simulator                 • Live two-node MQTT telemetry generator
• Disconnected Node-RED flows                   • Running Node-RED dashboard & unified Web UI
• Static test scripts                           • One-command startup/shutdown orchestrator
• Separate disconnected web pages              • Unified interactive Engineering Control Center
• Unverified physical hardware                  • Honest, verified dual-node cyber-physical emulator
```

---

## 2. Component-by-Component Gap Analysis

| Subsystem / Feature | Current State (Baseline) | Gap Identified | Showcase Target Action | Executable Acceptance Criteria |
|---|---|---|---|---|
| **MQTT Broker** | Broker was not installed or running; backend defaulted to standalone internal callback. | Ingestion could not be demonstrated over real TCP sockets on port 1883. | Install and run native Mosquitto broker via Homebrew. | TCP connection to `localhost:1883` succeeds; MQTT pub/sub verified with paho-mqtt. |
| **Two-Node IoT Telemetry** | Python simulator generated data internally via memory callback. | No standalone process publishing continuous dual-node telemetry to actual MQTT topics. | Implement `scripts/mqtt_node_simulator.py` supporting live independent nodes, pause/resume, and sensor dropouts. | `node_01` and `node_02` publish JSON messages to `civictwin/v1/nodes/+/telemetry` over real MQTT. |
| **Node-RED Environment** | `flows.json` existed statically; Node-RED runtime was uninstalled. | Reviewers could not see live gauges without installing and configuring Node-RED. | Install Node-RED via npm; deploy flow; verify polling against FastAPI backend. | Node-RED running on `127.0.0.1:1880/ui` showing active dials and alerts. |
| **Showcase Control Dashboard** | Dashboard was split between Swagger docs (`/docs`) and Node-RED. | Lacked a single unified, modern web control center with one-click showcase scenario triggers. | Build a dedicated, modern, zero-dependency HTML5/JS/Tailwind Showcase Control Center integrated directly into FastAPI (`/showcase`). | Browser loads `/showcase` with 8 required views, real-time telemetry streaming, and scenario triggers. |
| **One-Command Orchestration** | Services had to be started manually across multiple terminal windows. | High risk of port conflicts, orphan processes, or incorrect startup order during a demo. | Develop `./scripts/showcase_start.sh`, `./scripts/showcase_stop.sh`, and `./scripts/showcase_verify.sh`. | Clean execution from any terminal starts broker, backend, simulator, and dashboard in order. |
| **End-to-End Validation** | Verified only through pytest unit tests. | Lack of live browser automation logs and real end-to-end telemetry receipt verification. | Execute automated end-to-end integration tests using live processes and browser automation. | Live database records confirmed; screenshots captured from running interface. |
| **Showcase Documentation** | Standard docs existed, but no presentation-ready demo package. | Missing exact 5–7 min demo script, Q&A defense answers, and backup demo procedures. | Create `showcase/` package (`DEMO_SCRIPT.md`, `DEMO_CHECKLIST.md`, `ARCHITECTURE.md`, `TECHNICAL_QA.md`, etc.). | Complete academic presentation binder in `showcase/`. |

---

## 3. Detailed Operational Transition Plan

### Phase 2: Complete Runtime Environment
- Install Mosquitto (`brew install mosquitto`).
- Install Node-RED (`npm install -g node-red` or local project installation).
- Validate ports: 1883 (MQTT), 8000 (API & Showcase UI), 1880 (Node-RED).
- Ensure safe process management (PID tracking in `.run/`).

### Phase 3: Operational Two-Node System
- Develop `scripts/mqtt_node_simulator.py`:
  - `node_01`: Tank 1 (Saidapet Runoff / Adyar), Area $300\text{ cm}^2$, Height $50\text{ cm}$, $k=4.5$.
  - `node_02`: Tank 2 (Cooum Urban Retention), Area $450\text{ cm}^2$, Height $60\text{ cm}$, $k=6.0$.
  - Features: Real-time MQTT publishing (5s interval), sequence numbering, controllable inflow surge, controllable sensor fault injection, pause/resume.
  - Transparent labeling: Explicitly marked `PYTHON_SIMULATED` to preserve scientific integrity.

### Phase 4: End-to-End Integration Verification
- Verify chain: `mqtt_node_simulator.py` $\rightarrow$ Mosquitto (port 1883) $\rightarrow$ `MQTTIngestionClient` $\rightarrow$ `IngestionService` $\rightarrow$ `SQLiteStorage` (`data/civictwin.db`) $\rightarrow$ FastAPI REST API $\rightarrow$ Dashboard / Node-RED.
- Implement live integration test verifying database records created from real MQTT packets.

### Phase 5 & 6: Digital Twin & Missing-Data Demonstration
- Live API endpoints `/api/tank/predict` and `/api/tank/compare` wired to the showcase interface.
- Scenario controls: Normal, Rising Water, Critical Flood, Sensor Dropout, Network Outage, Return to Normal.
- Visual display of original vs masked vs reconstructed series (LOCF vs Causal vs Linear vs Physics Twin).

### Phase 7 & 8: Freshness, Alerts & Chennai Grounding
- Interactive freshness gauge updating LIVE ($<30\text{s}$ Fresh, $30-90\text{s}$ Stale, $>90\text{s}$ Offline).
- Edge warning optical indicator (1 Hz blink for Warning, Solid ON for Critical).
- Chennai Historical Module: CFM-DSS 117 ARG station selector, Cyclone Michaung hourly storm timeline, reservoir capacity breakdown.

### Phase 9: Unified Showcase Engineering Control Center
- Deliver an executive-grade, responsive Web UI served at `http://127.0.0.1:8000/showcase`.
- 8 distinct panels:
  1. System Health & Topology
  2. Live Dual-Node Telemetry
  3. Digital Twin ODE Prediction
  4. Missing-Data Reconstruction Laboratory
  5. Freshness & Edge Warning State Machine
  6. Chennai Basin Grounding & Historical Replay
  7. Interactive Scenario Laboratory (One-Click Showcase Mode)
  8. Experimental Benchmark Results & Methodology

### Phase 10 & 11: Startup Scripts & Verification
- Implement `scripts/showcase_start.sh`, `scripts/showcase_stop.sh`, `scripts/showcase_verify.sh`.
- Test browser navigation, capture screenshots in `showcase/SCREENSHOTS/`.

### Phase 12 & 13: Presentation Package & Final Acceptance
- Build `showcase/` materials including 30+ technical defense Q&As.
- Produce `reports/FINAL_SHOWCASE_ACCEPTANCE.md`.
