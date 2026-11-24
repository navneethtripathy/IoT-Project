# CivicTwin-R — 5–7 Minute Master Showcase Walkthrough Script

**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring & Scenario Planning  
**Target Audience:** Professor, External Examiners, Review Panel  
**Estimated Time:** 6 Minutes  
**Demonstration URL:** `http://127.0.0.1:8000/showcase`  
**Secondary URL (Node-RED):** `http://127.0.0.1:1880/ui`

---

## Minute 0:00 – 1:00 — Introduction, Cyber-Physical Problem & System Topology

### Action:
1. Open browser to `http://127.0.0.1:8000/showcase`.
2. Keep view on **Tab 1: Overview & System Health**.

### Spoken Explanation:
> "Good morning, Professor and committee members. Today we present **CivicTwin-R**, a cyber-physical digital twin platform for urban flood monitoring and scenario planning.
>
> Urban water-level monitoring faces critical cyber-physical challenges: sensor noise, communication dropouts, and sudden flood surges. In CivicTwin-R, we combine real hydrological data from Chennai's river basins with physical laboratory tank twins governed by non-linear Torricelli mass-balance equations.
>
> As shown on this screen, our live pipeline is currently running on native host infrastructure:
> - Dual simulated sensor nodes (`node_01` and `node_02`) publish telemetry over our native **Mosquitto MQTT broker on port 1883**.
> - Our FastAPI ingestion engine validates schemas via Pydantic v2, enforces sequence deduplication, evaluates threshold hysteresis, and persists data to SQLite.
> - Notice the top status bar: FastAPI is 200 OK, MQTT is CONNECTED on port 1883, and over 200 telemetry records have been persisted."

---

## Minute 1:00 – 2:00 — Live Two-Node Telemetry & Dual-Node Isolation

### Action:
1. Click **Tab 2: Dual-Node Telemetry**.
2. Point out the animated column visualizers for **Node 01 (Tank 1 / Adyar)** and **Node 02 (Tank 2 / Cooum)**.
3. Click the button: **"Simulate Node 1 Dropout"**.

### Spoken Explanation:
> "Under Tab 2, we see our two independent nodes operating concurrently.
> - **Node 01** represents our Saidapet prototype (height 50 cm, area 300 cm², discharge coefficient $k=4.5$).
> - **Node 02** represents our Cooum retention prototype (height 60 cm, area 450 cm², $k=6.0$).
>
> Notice that sequence numbers and timestamps advance independently. There is zero data cross-contamination between nodes.
>
> Now, I will inject a sensor communication dropout on Node 01 by clicking 'Simulate Node 1 Dropout'.
> Observe: Node 01 stops receiving updates, and its freshness counter immediately begins incrementing. Meanwhile, Node 02 continues streaming uninterrupted at its 5-second cadence. This proves our dual-node architectural isolation."

---

## Minute 2:00 – 3:00 — Data Freshness State Machine & Anti-Chatter Hysteresis

### Action:
1. Click **Tab 5: Freshness & Edge Warnings**.
2. Explain the 4-state diagram while pointing at the status badges.
3. Click **"Reconnect Both Nodes"** from the top bar.

### Spoken Explanation:
> "Under Tab 5, we demonstrate our real-time data freshness state machine:
> - Telemetry under 30 seconds is classified as **FRESH**.
> - Between 30 and 90 seconds, it transitions to **STALE**, warning operators that the reading may be outdated.
> - Beyond 90 seconds, it is flagged as **OFFLINE**.
>
> If a sensor reports physical echo failure—such as distances below 2 cm or above 400 cm—it transitions to **INVALID** and emits null rather than fabricating a false zero-depth measurement.
>
> Furthermore, look at our edge warning hysteresis:
> - Water level rising to $70\%$ triggers a **Warning** alert and flashes the ESP32 GPIO 2 LED at 1 Hz.
> - A breach of $85\%$ triggers a **Critical** alert with solid LED illumination.
> - To prevent relay chatter and alert oscillation from water surface waves, the level must drop strictly below $(70\% - 3\% = 67\%)$ to clear the warning."

---

## Minute 3:00 – 4:00 — Calibrated Digital Twin & RK4 Forward Prediction

### Action:
1. Click **Tab 3: Digital Twin ODE Prediction**.
2. Select **Tank 1**, then click **"Refresh Forward RK4 Simulation"**.
3. Point out the solid cyan line (Measured) and dashed blue line (RK4 Prediction).

### Spoken Explanation:
> "Now we examine the mathematical heart of CivicTwin-R: our **Calibrated Tank Digital Twin**.
>
> The water height follows the continuous mass-balance ODE:
> $$\frac{dh}{dt} = \frac{Q_{\text{in}} - k\sqrt{h}}{A}$$
> where $k\sqrt{h}$ represents Torricelli orifice discharge.
>
> We solve this non-linear ODE forward in time using a 4th-order Runge-Kutta numerical integrator with a 1.0-second time step.
>
> In an unforced drain-down test ($Q_{\text{in}} = 0$), the analytical solution is $2A(\sqrt{h_0} - \sqrt{h_t}) = kt$. We perform zero-intercept OLS regression to calibrate $k$. On our synthetic benchmark, our algorithm recovered the true $k=4.5$ within $0.56\%$ error with $R^2 = 0.9942$.
>
> On this chart, the cyan curve shows simulated telemetry with Gaussian sensor noise, while the blue dashed curve is the digital twin's forward prediction. Notice the close tracking: our Mean Absolute Error is under 0.05 cm and Pearson correlation exceeds 0.99."

---

## Minute 4:00 – 5:00 — Missing-Data Reconstruction Benchmark (Setting A vs Setting B)

### Action:
1. Click **Tab 4: Missing-Data Reconstruction**.
2. Point out the bar chart comparing LOCF, Causal Linear Trend, Linear Interpolation, and Physics Digital Twin across 15s, 30s, 60s, and 120s gaps.

### Spoken Explanation:
> "In Tab 4, we address sensor dropouts through rigorous scientific benchmarking.
>
> Crucially, we enforce a strict academic distinction between:
> - **Setting A (Online Causal Streaming):** The algorithm operates in real-time. It has access **only to past observations** prior to the gap. The future point is unknown. Zero future-data leakage is permitted.
> - **Setting B (Offline Retrospective Reconstruction):** The algorithm runs after communication restores, bridging past and future boundary points.
>
> Our results across multiple seeds show:
> - For short gaps of 15 seconds, our **Physics Digital Twin** achieves a Mean Absolute Error of **0.0227 cm**—a **79.4% error reduction** compared to LOCF (0.1103 cm).
> - For longer gaps beyond 60 seconds, offline Linear Interpolation performs best because the future observation pins the end of the trajectory, whereas online methods face accumulating unmeasured inflow variance."

---

## Minute 5:00 – 6:00 — Chennai Environmental Data Grounding & Interactive Scenarios

### Action:
1. Click **Tab 6: Chennai Basin Grounding**.
2. Click **Tab 7: Showcase Laboratory Scenarios**, and click **"Activate Scenario 2: Monsoon Inflow Surge"**.
3. Watch the live water level rise in the top gauges and trigger a WARNING alert.

### Spoken Explanation:
> "Finally, under Tab 6, CivicTwin-R is hydrologically grounded in real environmental observations from the Chennai Metropolitan Basin:
> - We ingest **328 historical records across 117 Automatic Rain Gauge (ARG) stations** from the official CFM-DSS monitoring portal.
> - We track daily stage-storage for **5 major reservoirs** (Chembarambakkam, Poondi, Red Hills, Cholavaram, Thervoy Kandigai).
> - We distinguish precipitation in millimeters from modeled river stage in centimeters.
>
> To conclude, under Tab 7, we provide one-click showcase scenarios that alter the real physics and telemetry. I have just triggered 'Monsoon Inflow Surge'. Inflow jumped to 45 cm³/s, water height breached 70%, and a live WARNING alert was generated in the system log.
>
> In summary, CivicTwin-R represents a complete, rigorously verified, and operational cyber-physical digital twin. Thank you, and we welcome your questions."
