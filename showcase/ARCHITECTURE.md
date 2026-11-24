# CivicTwin-R — Final System Architecture & Technical Specifications

---

## 1. Multi-Tier Cyber-Physical Architecture

CivicTwin-R implements a five-tier decoupled architecture:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER 1: EDGE SENSING & CYBER-PHYSICAL EMULATION                             │
│ • Node 01: Tank 1 (Saidapet / Adyar Basin Prototype, Area 300cm², H 50cm)    │
│ • Node 02: Tank 2 (Cooum Urban Retention Prototype, Area 450cm², H 60cm)   │
│ • JSN-SR04T Waterproof Ultrasonic Interface (2.2kΩ/3.3kΩ Voltage Divider)  │
│ • Local Edge Warning State Machine (Hysteresis, 1 Hz LED Blink vs Solid ON) │
│ • Python MultiNodeMqttSimulator: Deterministic RK4 steps, noise injection   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ JSON Telemetry over TCP (QoS 1)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER 2: TRANSPORT & MESSAGE BROKER (MQTT)                                  │
│ • Eclipse Mosquitto 2.1.4 running on localhost:1883 TCP & 9001 WebSockets  │
│ • Topic Hierarchy:                                                          │
│     civictwin/v1/nodes/{node_id}/telemetry  (Per-device raw readings)       │
│     civictwin/v1/nodes/{node_id}/status     (Node diagnostics & heartbeat)  │
│     civictwin/v1/nodes/{node_id}/alerts     (Edge threshold crossings)      │
│     civictwin/v1/zones/{zone_id}/telemetry  (Aggregated catchment channel)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Paho MQTT Async Client Subscription
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER 3: INGESTION, VALIDATION & FRESHNESS ENGINE                            │
│ • Pydantic v2 Schema Enforcement (TelemetryMessage, IngestedTelemetry)      │
│ • Per-device Sequence Tracking: Drops duplicate & out-of-order packets      │
│ • 4-State Freshness Machine: FRESH (<30s), STALE (30-90s), OFFLINE (>90s)   │
│ • Sensor Fault Guard: Emits null depth for echo timeouts (no false zeroes)  │
│ • Hysteresis Evaluator: Warn (70%), Crit (85%), Anti-Chatter Band (3%)      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Thread-Safe Persistence & Query
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER 4: STORAGE & DIGITAL TWIN ODE SOLVER                                   │
│ • SQLite (WAL Mode) in data/civictwin.db (compound unique device_id + seq)  │
│ • InfluxDB 2.7 Fallback Engine: Gracefully switches to SQLite if disabled   │
│ • Physical Tank ODE: dh/dt = (Q_in - k√h) / A (Runge-Kutta 4th Order)       │
│ • Analytical OLS Torricelli Calibration: 2A(√h0 - √ht) = k·t (R² > 0.99)    │
│ • Missing-Data Imputation: LOCF, Causal Trend (Setting A), Linear (Setting B│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ JSON REST APIs & WebSockets
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIER 5: CONTROL CENTER & PRESENTATION INTERFACES                            │
│ • Showcase Engineering Control Center: Single-Page App at /showcase         │
│ • Node-RED Dashboard: Flow-based operational dials at :1880/ui              │
│ • FastAPI Interactive Swagger Documentation at /docs                        │
│ • Historical Storm Replay: 144 hourly steps of Cyclone Michaung (Dec 2023)  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

| Component | Technology | Version | Purpose |
|---|---|---|---|
| **Programming Language** | Python | 3.14.5 | Core backend, physics solvers, simulator, test suite |
| **Web Framework** | FastAPI / Starlette | 0.115+ | High-performance async REST API and HTML serving |
| **ASGI Web Server** | Uvicorn | 0.32+ | Production-grade async HTTP server |
| **Data Validation** | Pydantic | v2.10+ | Schema validation, type enforcement, model serialization |
| **MQTT Broker** | Eclipse Mosquitto | 2.1.4 | Native lightweight publish/subscribe message broker |
| **MQTT Client** | Paho MQTT | 2.1+ | Async Python MQTT subscriber and publisher |
| **Embedded Firmware** | C++ / Arduino | 2.0+ | ESP32 dual-node firmware with edge warning logic |
| **Primary Database** | SQLite 3 | 3.43+ | Thread-safe embedded relational storage with WAL |
| **Time-Series Database** | InfluxDB | 2.7 | Optional multi-tenant time-series storage (Docker mode) |
| **Dashboard Runtime** | Node-RED | 5.0.10 | Flow-based operational dashboard engine |
| **Dashboard UI Nodes** | node-red-dashboard | 3.6.6 | Gauge dials, status indicators, and scenario buttons |
| **Showcase Front-End** | HTML5 / Tailwind / Chart.js | Modern | Unified dark-theme Engineering Showcase Control Center |
| **Testing Framework** | pytest / pytest-asyncio | 9.1+ | 126 automated unit and end-to-end integration tests |

---

## 3. Mathematical & Physical Models

### 3.1 Tank Orifice Mass Balance ODE
$$\frac{dh}{dt} = \frac{Q_{\text{in}}(t) - k\sqrt{h(t)}}{A}$$

- $h$: Water height ($\text{cm}$)
- $A$: Tank cross-sectional area ($\text{cm}^2$)
- $Q_{\text{in}}$: Inflow volumetric rate ($\text{cm}^3/\text{s}$)
- $k$: Torricelli orifice discharge coefficient ($\text{cm}^{2.5}/\text{s}$)

### 3.2 Torricelli Drain-Down Calibration (OLS)
$$2A\left(\sqrt{h_0} - \sqrt{h_t}\right) = k \cdot t$$
$$\hat{k} = \frac{\sum_i t_i \cdot y_i}{\sum_i t_i^2} \quad \text{where} \quad y_i = 2A\left(\sqrt{h_0} - \sqrt{h_i}\right)$$

### 3.3 Catchment Lumped Water Balance
$$h_{t+1} = h_t + \left[Q_{\text{base}} + Q_{\text{upstream}} + (P_{\text{rain}} \cdot C_{\text{runoff}})\right]\Delta t - \min\left(D_{\text{cap}}\Delta t, \, h_t\right)$$
