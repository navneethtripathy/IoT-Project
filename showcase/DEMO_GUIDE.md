# CivicTwin-R — Complete Academic Demonstration Guide & Spoken Script

**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning  
**Audience:** Academic Reviewers, Thesis Committee, Technical Examiners  
**Duration:** 10–12 Minutes  
**Demonstration Center:** [http://127.0.0.1:8000/showcase](http://127.0.0.1:8000/showcase)  
**Secondary Dashboard:** [http://127.0.0.1:1880/ui/](http://127.0.0.1:1880/ui/)  

---

## Pre-Demonstration Setup (T - 2 Minutes)
1. Open a clean browser window at `http://127.0.0.1:8000/showcase`.
2. Open a second tab at `http://127.0.0.1:1880/ui/` (Node-RED Dashboard).
3. Ensure terminal has executed `./scripts/showcase_verify.sh` with all PASS marks.

---

## Minute-by-Minute Demonstration Sequence

### [00:00 – 01:30] Phase 1: Problem Formulation & System Architecture
- **Tab to Display:** **Tab 1: Overview**
- **Visual Focus:** System Architecture diagram, live service badges (FastAPI, MQTT, SQLite), active zone KPIs.
- **Narrative:**
  > "Good morning, members of the evaluation committee. Today we present **CivicTwin-R**, a resilient cyber-physical digital twin architecture designed for urban flood monitoring and scenario planning.
  >
  > In real-world urban flood monitoring, edge IoT systems face severe real-world challenges: ultrasonic sensor noise, acoustic blind zones, intermittent wireless connectivity, and catastrophic packet loss during storms. CivicTwin-R solves these challenges by coupling physical differential equations with real-time IoT telemetry, grounded in official hydrological data from the Chennai river basins.
  >
  > As you see on the top status bar, our complete software stack is running natively on local host infrastructure:
  > - Two concurrent sensor nodes are streaming telemetry via native **Mosquitto MQTT on port 1883**.
  > - Our **FastAPI backend** validates schemas with Pydantic v2, enforces monotonic sequence deduplication, evaluates alert hysteresis, and stores records in SQLite with Write-Ahead Logging.
  > - Notice that the system status reports healthy with over 100 persisted telemetry records."

---

### [01:30 – 03:00] Phase 2: Dual-Node Real-Time Telemetry & Cross-Talk Isolation
- **Tab to Display:** **Tab 2: Dual-Node Gauges**
- **Action:** Point out Node 01 (Saidapet) and Node 02 (Cooum) gauges and animated fill columns. Click the **"Simulate Node 1 Dropout"** button.
- **Narrative:**
  > "Under Tab 2, we observe our dual-node architecture operating concurrently.
  > - **Node 01** monitors a $50\text{ cm}$ cylindrical tank prototype representing Saidapet on the Adyar River.
  > - **Node 02** monitors a $60\text{ cm}$ retention tank prototype representing the Cooum River.
  >
  > Notice the independent progression of timestamps, distances, and water levels. To demonstrate multi-tenant isolation, I now click 'Simulate Node 1 Dropout'.
  >
  > Observe: Node 01 immediately halts receiving packets, and its observation age counter begins incrementing. Meanwhile, look at Node 02: it continues publishing at its steady 5-second interval without a single dropped packet or sequence jitter. This verifies absolute logical isolation between edge nodes."

---

### [03:00 – 04:30] Phase 3: Interactive 3D WebGL Digital Twin (Three.js)
- **Tab to Display:** **Tab 3: Interactive 3D Digital Twin**
- **Action:** Use mouse to orbit (rotate, pan, zoom) around the 3D acrylic tanks. Click **Front View**, **Top View**, then **Reset View**. Point out dynamic fluid levels and the ESP32 status LED.
- **Narrative:**
  > "Here in Tab 3, we present our **Interactive 3D Cyber-Physical Digital Twin**, rendered in real time using Three.js and WebGL.
  >
  > We have modeled the exact physical laboratory setup on an anti-static workbench:
  > - Two transparent acrylic cylindrical tanks with metallic bases and calibrated millimeter scales.
  > - Dynamic translucent blue fluid meshes that scale their vertical geometry in real time to match incoming sensor readings.
  > - Yellow warning threshold rings at $70\%$ ($35\text{ cm}$ and $42\text{ cm}$) and red critical inundation rings at $85\%$ ($42.5\text{ cm}$ and $51\text{ cm}$).
  > - Top inlet manifold pipes and bottom orifice drainage valves.
  > - Wall-mounted IP67 enclosures containing the **ESP32 microcontroller** with a multi-state status LED, wired to the waterproof JSN-SR04T ultrasonic transducer.
  >
  > Notice that we can smoothly rotate, pan, and inspect the tanks from any angle using OrbitControls, giving city operators immediate spatial awareness."

---

### [04:30 – 06:00] Phase 4: Calibrated Digital Twin & RK4 Numerical ODE Prediction
- **Tab to Display:** **Tab 4: Digital Twin ODE Prediction**
- **Action:** Select **Tank 1 (Saidapet)**. Click **"Run Forward RK4 Simulation"**. Show the tracking between measured sensor telemetry (cyan line) and the forward ODE trajectory (blue dashed line).
- **Narrative:**
  > "Now we examine the mathematical core of CivicTwin-R: our **Calibrated Tank Digital Twin**.
  >
  > The rate of change of water height is governed by the mass-balance ODE:
  > $$\frac{dh}{dt} = \frac{Q_{\text{in}}(t) - k\sqrt{h(t)}}{A}$$
  > where Torricelli's Law defines orifice outflow under gravity.
  >
  > We solve this non-linear ODE using a **4th-Order Runge-Kutta (RK4)** numerical integrator with a 1.0-second step size, ensuring $O(\Delta t^4)$ convergence.
  >
  > During unforced drain-down tests ($Q_{\text{in}}=0$), the analytical solution is $2A(\sqrt{h_0}-\sqrt{h_t}) = kt$. We perform zero-intercept OLS regression to calibrate the discharge parameter $k$. On synthetic benchmark data with Gaussian noise, our algorithm recovered $k=4.4749$ against ground truth $4.5$ within $0.56\%$ error with $R^2 = 0.9942$.
  >
  > On this chart, notice how the digital twin's forward prediction closely tracks the live sensor telemetry. Our live Mean Absolute Error is just $0.25\text{ cm}$ with an RMSE of $0.30\text{ cm}$, proving high predictive fidelity."

---

### [06:00 – 07:30] Phase 5: Missing-Data Reconstruction Benchmark (Setting A vs Setting B)
- **Tab to Display:** **Tab 5: Gap Reconstruction**
- **Action:** Review the benchmark comparison chart across gap lengths ($15\text{s}, 30\text{s}, 60\text{s}, 120\text{s}$). Point out Setting A (Causal) vs Setting B (Retrospective).
- **Narrative:**
  > "Under Tab 5, we present our scientific contribution to IoT data quality: a rigorous comparison of missing-data reconstruction techniques.
  >
  > We strictly distinguish between two operational regimes:
  > - **Setting A (Online Causal Streaming):** The algorithm runs in real time when a packet drops. It has access **only to past observations** ($\mathcal{H}_{<k}$). Zero future-data leakage is permitted.
  > - **Setting B (Offline Retrospective Gap Filling):** The algorithm runs after communications are restored, bridging past and future boundary points.
  >
  > Notice the key findings:
  > 1. At short gaps ($15\text{s} - 30\text{s}$), the **Physics Digital Twin** achieves the lowest error ($\text{MAE} = 0.0227\text{ cm}$ at $15\text{s}$), outperforming LOCF by $79.4\%$ because it models the non-linear orifice deceleration.
  > 2. At long gaps ($120\text{s}$), retrospective Linear Interpolation achieves lower error because its future boundary point constrains open-loop drift.
  > This provides clear guidance: physics guidance is optimal for real-time edge streaming, while retrospective interpolation is optimal for archival analysis."

---

### [07:30 – 08:30] Phase 6: Freshness State Machine & Anti-Chatter Hysteresis
- **Tab to Display:** **Tab 6: Freshness & Alerts**
- **Action:** Point to the 4-state freshness lifecycle diagram (`FRESH` $\to$ `STALE` $\to$ `OFFLINE` / `INVALID`) and the edge alert log.
- **Narrative:**
  > "Under Tab 6, we demonstrate operational reliability:
  > - Observations under $30\text{ seconds}$ are rated **FRESH**.
  > - Between $30\text{s}$ and $90\text{s}$, they transition to **STALE**, warning operators that the reading is aging.
  > - Beyond $90\text{s}$, the node is flagged **OFFLINE**.
  >
  > Furthermore, notice our **$3\%$ anti-chatter hysteresis band**:
  > - A rising level triggers a WARNING alert when reaching $70.0\%$.
  > - The warning is NOT cleared until water drops strictly below $(70.0\% - 3.0\% = 67.0\%)$.
  > This completely eliminates alarm toggling, relay wear, and notification spam caused by wave ripples."

---

### [08:30 – 09:30] Phase 7: Chennai Hydrology Grounding & Michaung Replay
- **Tab to Display:** **Tab 7: Chennai Basin**
- **Action:** Show the Chennai river basin catchment map, the WRD major reservoir gauges, and click **"Start Michaung Storm Replay"**.
- **Narrative:**
  > "Tab 7 grounds our digital twin in authentic urban hydrology from Chennai, India:
  > - We integrate $328$ rain gauge records from $117$ Automatic Rain Gauge stations operated by the Greater Chennai Corporation and WRD.
  > - We display daily storage metrics for Chennai's 5 major reservoirs: Chembarambakkam, Poondi, Red Hills, Cholavaram, and Thervoy Kandigai.
  > - We incorporate $144$ hourly precipitation records from the devastating December 2023 **Cyclone Michaung**.
  >
  > By clicking 'Start Michaung Storm Replay', the system plays back actual storm intensities, demonstrating how urban catchments respond to extreme rainfall surges."

---

### [09:30 – 10:30] Phase 8: Scenario Planning Laboratory
- **Tab to Display:** **Tab 8: Showcase Laboratory Scenarios**
- **Action:** Click **Scenario 2: Heavy Inflow Surge**, then **Scenario 3: Drainage Obstruction**, and finally **Scenario 10: Return to Normal Baseline**.
- **Narrative:**
  > "Tab 8 is our Scenario Planning Laboratory, featuring 10 one-click cyber-physical operating profiles:
  > 1. Normal dry weather equilibrium.
  > 2. Heavy inflow storm surge ($Q_{\text{in}}$ doubles to $55\text{ cm}^3/\text{s}$).
  > 3. Drainage obstruction ($k$ drops by $67\%$ due to debris blockage).
  > 4. Warning breach ($70\%$ threshold crossing with $1\text{ Hz}$ blinking LED).
  > 5. Critical inundation ($85\%$ breach with solid red alarm).
  > 6. Node 1 ultrasonic dropout fault injection.
  > 7. Node 2 silence aging to stale and offline.
  > 8. Digital twin forward missing-data recovery.
  > 9. Rapid node reconnection and sequence resync.
  > 10. Return to nominal steady-state baseline.
  >
  > This allows municipal planners to safely test emergency mitigation policies before implementing them in the field."

---

### [10:30 – 11:30] Phase 9: Database Inspection Explorer & MQTT Packet Streamer
- **Tab to Display:** **Tab 9: Database Explorer**, then **Tab 10: MQTT Streamer**
- **Action:** On Tab 9, show SQLite table metadata, record count, and click pagination. On Tab 10, demonstrate the real-time MQTT packet ring buffer.
- **Narrative:**
  > "In Tab 9, our **Database Inspection Explorer** provides transparent read-only access to our SQLite storage engine. Notice the metadata badge: database size, WAL journal mode, and total persisted records. Operators can paginate through raw records or export them to CSV.
  >
  > In Tab 10, our **MQTT Live Streamer** captures real-time packets directly from Mosquitto on port 1883. We can inspect individual JSON payloads, schema versions, quality flags, and byte sizes without leaving the browser."

---

### [11:30 – 12:00] Phase 10: Node-RED Operational Dashboard & Conclusion
- **Action:** Switch browser tab to `http://127.0.0.1:1880/ui/` to show the secondary Node-RED dashboard.
- **Narrative:**
  > "Finally, we switch to our secondary operational viewer: **Node-RED on port 1880**.
  >
  > Here, industrial gauges, water level bar charts, and real-time alert badges receive telemetry concurrently from the MQTT broker, demonstrating multi-client interoperability.
  >
  > In conclusion, CivicTwin-R delivers a fully verified, resilient cyber-physical digital twin that bridges physical fluid dynamics, edge reliability, missing-data recovery, and urban flood scenario planning with $100\%$ automated test verification. Thank you, and we welcome your questions."
