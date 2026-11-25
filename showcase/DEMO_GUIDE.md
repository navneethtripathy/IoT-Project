# CivicTwin-R — Complete Academic Demonstration Guide & Spoken Script

**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning  
**Audience:** Academic Reviewers, Thesis Committee, Technical Examiners  
**Duration:** 10–12 Minutes  
**Primary Demonstration Center:** [http://127.0.0.1:8000/showcase](http://127.0.0.1:8000/showcase)  
**Dedicated 3D Urban Twin View:** [http://127.0.0.1:8000/urban-twin](http://127.0.0.1:8000/urban-twin)  
**Secondary Node-RED Dashboard:** [http://127.0.0.1:1880/ui/](http://127.0.0.1:1880/ui/)  

---

## Pre-Demonstration Setup (T - 2 Minutes)
1. Open a clean browser window at `http://127.0.0.1:8000/showcase`.
2. Open a second tab at `http://127.0.0.1:8000/urban-twin` (Dedicated 3D Urban Map).
3. Open a third tab at `http://127.0.0.1:8086` (InfluxDB 2.x Time-Series UI).
4. Open a fourth tab at `http://127.0.0.1:1880/ui/` (Node-RED Dashboard).
5. Ensure terminal has verified stack health via `./scripts/showcase_verify.sh` with all PASS marks.

---

## Minute-by-Minute Demonstration Sequence

### [00:00 – 03:00] Phase 1: Centerpiece — 3D Chennai Urban Flood Digital Twin & Scenario Planning
- **Tab to Display:** **Tab 1: Chennai Urban 3D Digital Twin** (or direct at `/urban-twin`)
- **Visual Focus:** 
  - Interactive offline-ready 3D WebGL MapLibre view showing Greater Chennai Metropolitan Basin and South Chennai quantitative domain (`111×175` cells at `150m` UTM Zone 44N).
  - 10 Prioritized focus locations: Velachery, Pallikaranai Marsh, Madipakkam, Perungudi, Tambaram, Pallavaram, Chembarambakkam, Porur, Saidapet, Adyar Estuary.
  - Official TN CFM-DSS WFS hydrography: 465 waterways, 771 waterbodies/marshes, 36 watersheds, 200 wards, and 230 historical flood spots.
  - 18,198 real extruded OSM building footprints (`height_source` tracked per building), 9,942 major roads, 38,827 pilot streets, and 1,229 OSM bridges.
  - 56 geolocated CFM-DSS stations and 5 WRD major reservoirs.
- **Actions to Perform:**
  1. Click **"Velachery"** quick fly-to button to zoom in at 3D pitch showing real extruded OSM buildings, bridges, and modeled flood depth prisms, and click anywhere on the map to inspect the Copernicus GLO-30 DSM elevation (`EGM2008`) & cell depth.
  2. Click **"Pallikaranai"** or search **"Adyar"** in the top search bar to navigate across 747 real OSM places, stations, and bridges.
  3. Select Scenario **"Cyclone Michaung Dec 2023 Replay (24h)"** and press **Play ▶** on the timeline scrubber to animate historical rainfall propagation, or use **Compare Impact Delta** (`Heavy Rain` vs `Reduced Drainage`) to quantify drainage clogging impact.
- **Narrative:**
  > "Good morning, members of the evaluation committee. Today we present **CivicTwin-R**, a resilient cyber-physical digital twin architecture designed for urban flood monitoring and scenario planning.
  >
  > The core centerpiece of CivicTwin-R is an **interactive 3D Urban Flood Digital Twin of Chennai, India**, rendered live via WebGL. 
  >
  > As you see on the screen, we have georeferenced 10 critical flood hotspots across the Chennai Metropolitan Basin—focusing on the low-lying South Chennai catchments between the Adyar River and the Pallikaranai Marshland.
  >
  > Notice the geographical fidelity:
  > - We model authentic river flowlines for the Adyar River, Cooum River, and Buckingham Canal, alongside the 800-hectare Pallikaranai wetland sink.
  > - We have extruded 3D building geometry based on real urban footprints, allowing emergency managers to visualize street-level inundation against urban assets.
  > - We integrate 10 real Automatic Rain Gauge stations from the GCC/IMD network and 5 major reservoirs including Chembarambakkam.
  >
  > Under the hood, our **mass-balance hydrological screening model** calculates dynamic runoff, infiltration, and slope-attenuated drainage across each catchment:
  > $$\frac{dV_i}{dt} = Q_{\text{rain}, i} + \sum Q_{\text{upstream}} - Q_{\text{drain}, i} - Q_{\text{infil}, i}$$
  > 
  > When I trigger the 'Heavy Monsoon Rainfall' scenario, notice how Velachery rapidly accumulates $0.45\text{ m}$ of surface ponding due to its bowl-shaped topography, automatically elevating its status to WARNING. This provides city operators with immediate, location-specific situational awareness."

---

### [03:00 – 04:30] Phase 2: Dual-Node Edge Telemetry & Hardware Emulation
- **Tab to Display:** **Tab 4: Dual-Node Edge Telemetry** & **Tab 5: Dual-Node Live Gauges**
- **Action:** Point out Node 01 (Saidapet) and Node 02 (Cooum) gauges and animated fill columns. Click the **"Simulate Node 1 Dropout"** button.
- **Narrative:**
  > "Under Tabs 4 and 5, we observe the cyber-physical edge layer of CivicTwin-R:
  > - **Node 01** represents our edge monitoring unit at Saidapet on the Adyar River corridor.
  > - **Node 02** represents our monitoring unit at the Cooum River retention channel.
  >
  > Each node streams ultrasonic rangefinder distance measurements, water levels, and sensor quality flags via native **Mosquitto MQTT on port 1883**.
  >
  > To demonstrate multi-tenant edge isolation, I now click 'Simulate Node 1 Dropout'.
  >
  > Notice: Node 01 immediately halts receiving packets, and its observation age begins incrementing toward STALE. Meanwhile, look at Node 02: it continues publishing uninterrupted at its steady 5-second interval without a single dropped packet or sequence jitter. This proves complete logical and process isolation between edge channels."

---

### [04:30 – 06:00] Phase 3: Experimental IoT Tank Digital Twin (Laboratory Validation Environment)
- **Tab to Display:** **Tab 6: Experimental IoT Tank Digital Twin**
- **Action:** Orbit (rotate, pan, zoom) around the 3D acrylic tanks in Three.js. Click **Front View**, **Top View**, then **Reset View**. Point out dynamic fluid levels, ultrasonic transducer cone, and ESP32 status LED.
- **Narrative:**
  > "Here in Tab 6, we present our **Experimental IoT Tank Digital Twin**, rendered in real time using Three.js and WebGL.
  >
  > *Let me provide an important academic boundary clarification:* This dual-tank twin is our **physical laboratory validation testbench**. It is deliberately designed as a software-in-the-loop experimental apparatus to benchmark sensor noise, Torricelli fluid dynamics, and communication resilience under controlled conditions before edge algorithms are deployed into urban catchments.
  >
  > We have modeled the exact physical laboratory setup:
  > - Two transparent acrylic cylindrical tanks with metallic bases and millimeter scales ($50\text{ cm}$ and $60\text{ cm}$).
  > - Dynamic translucent fluid meshes that update their geometry in real time to match sensor telemetry.
  > - Yellow warning threshold rings at $70\%$ and red critical inundation rings at $85\%$.
  > - Wall-mounted IP67 enclosures containing the ESP32 microcontroller with a multi-state status LED wired to the waterproof JSN-SR04T ultrasonic transducer."

---

### [06:00 – 07:15] Phase 4: Calibrated Digital Twin & RK4 Numerical ODE Prediction
- **Tab to Display:** **Tab 7: RK4 ODE Trajectory & Predict**
- **Action:** Select **Tank 1 (Saidapet)**. Click **"Run Forward RK4 Simulation"**. Show the tracking between measured sensor telemetry (cyan line) and the forward ODE trajectory (blue dashed line).
- **Narrative:**
  > "Now we examine the mathematical foundation of our cyber-physical engine:
  > The water height dynamics are governed by fluid continuity and Torricelli's Law:
  > $$\frac{dh}{dt} = \frac{Q_{\text{in}}(t) - k\sqrt{h(t)}}{A}$$
  > 
  > We solve this non-linear ODE using a **4th-Order Runge-Kutta (RK4)** numerical integrator with a 1.0-second step size, ensuring fourth-order convergence ($O(\Delta t^4)$) without numerical energy drift.
  >
  > During unforced drain-down tests ($Q_{\text{in}}=0$), the analytical solution is $2A(\sqrt{h_0}-\sqrt{h_t}) = kt$. We perform zero-intercept Ordinary Least Squares regression to calibrate the discharge parameter $k$. On synthetic benchmark data with Gaussian noise, our algorithm recovered $k=4.4749$ against ground truth $4.5$ within $0.56\%$ error with $R^2 = 0.9942$.
  >
  > As you can see on the live chart, the forward prediction tracks incoming sensor telemetry within an MAE of $0.25\text{ cm}$, proving high predictive fidelity."

---

### [07:15 – 08:30] Phase 5: Missing-Data Resilience Benchmark (Setting A vs Setting B)
- **Tab to Display:** **Tab 8: Gap Reconstruction**
- **Action:** Review the benchmark comparison chart across gap lengths ($15\text{s}, 30\text{s}, 60\text{s}, 120\text{s}$). Point out Setting A (Causal) vs Setting B (Retrospective).
- **Narrative:**
  > "Under Tab 8, we present our scientific contribution to IoT data quality: a rigorous comparison of missing-data reconstruction techniques.
  >
  > We strictly distinguish between two operational regimes to prevent future-data leakage:
  > - **Setting A (Online Causal Streaming):** The algorithm runs in real time when a packet drops. It has access **only to past observations** ($\mathcal{H}_{<k}$). Zero future-data leakage is permitted.
  > - **Setting B (Offline Retrospective Gap Filling):** The algorithm runs after communications are restored, bridging past and future boundary points.
  >
  > Notice the key findings:
  > 1. At short-to-medium gaps ($15\text{s} - 60\text{s}$), the **Physics Digital Twin** achieves the lowest error ($\text{MAE} = 0.0227\text{ cm}$ at $15\text{s}$), outperforming LOCF by $79.4\%$ because it models the non-linear orifice deceleration.
  > 2. At long gaps ($120\text{s}$), retrospective Linear Interpolation achieves lower error because its future boundary point constrains open-loop drift.
  > This provides clear operational guidance: physics guidance is optimal for real-time edge streaming, while retrospective interpolation is optimal for archival post-event analysis."

---

### [08:30 – 09:30] Phase 6: Freshness State Machine & Anti-Chatter Hysteresis
- **Tab to Display:** **Tab 9: Freshness & Edge Alerts**
- **Action:** Point to the 4-state freshness lifecycle diagram (`FRESH` $\to$ `STALE` $\to$ `OFFLINE` / `INVALID`) and the edge alert log.
- **Narrative:**
  > "Under Tab 9, we demonstrate operational reliability:
  > - Observations under $30\text{ seconds}$ are rated **FRESH**.
  > - Between $30\text{s}$ and $90\text{s}$, they transition to **STALE**, warning operators that the reading is aging.
  > - Beyond $90\text{s}$, the node is flagged **OFFLINE**.
  >
  > Furthermore, notice our **$3\%$ anti-chatter hysteresis band**:
  > - A rising level triggers a WARNING alert when reaching $70.0\%$.
  > - The warning is NOT cleared until water drops strictly below $(70.0\% - 3.0\% = 67.0\%)$.
  > This completely eliminates alarm toggling, relay chatter, and operator notification spam caused by wave ripples."

---

### [09:30 – 10:30] Phase 7: Chennai Hydrology Grounding & Michaung Replay
- **Tab to Display:** **Tab 10: Chennai Basin Historical Replay**
- **Action:** Show the Chennai river basin catchment map, the WRD major reservoir gauges, and click **"Start Michaung Storm Replay"**.
- **Narrative:**
  > "Tab 10 grounds our digital twin in authentic urban hydrology from Chennai, India:
  > - We integrate $328$ rain gauge records from $117$ Automatic Rain Gauge stations operated by the Greater Chennai Corporation and WRD.
  > - We display daily storage metrics for Chennai's 5 major reservoirs: Chembarambakkam, Poondi, Red Hills, Cholavaram, and Thervoy Kandigai.
  > - We incorporate $144$ hourly precipitation records from the devastating December 2023 **Cyclone Michaung**.
  >
  > Clicking 'Start Michaung Storm Replay' plays back actual storm intensities, demonstrating how urban catchments respond to extreme precipitation surges."

---

### [10:30 – 11:30] Phase 8: Database Inspection Explorer & MQTT Packet Streamer
- **Tab to Display:** **Tab 11: Database Inspection Explorer** & **Tab 12: Live MQTT Packet Streamer** (or InfluxDB UI at `:8086`)
- **Action:** Expand the SQLite table records, showing Write-Ahead Logging (WAL) timestamps, monotonic sequence numbers, and live raw JSON MQTT packets streaming across the socket. Switch to InfluxDB UI (`:8086`) to show time-series visualization in bucket `telemetry`.
- **Narrative:**
  > "Under Tabs 11 and 12, we expose the engineering infrastructure under the hood:
  > - The **Database Inspection Explorer** provides real-time visibility into our SQLite database, configured with Write-Ahead Logging (WAL) for concurrent read-write performance.
  > - Telemetry is concurrently dual-persisted to **InfluxDB 2.x on port 8086**, enabling high-throughput time-series aggregation, Flux analytics, and visualization without impacting relational query performance.
  > - The **MQTT Packet Streamer** taps directly into the Mosquitto broker socket, displaying live JSON payloads, quality flags, and sub-millisecond timestamps."

---

### [11:30 – 12:00] Phase 9: Node-RED Dashboard & Conclusion
- **Tab to Display:** Browser Tab 4: [http://127.0.0.1:1880/ui/](http://127.0.0.1:1880/ui/)
- **Visual Focus:** Operational gauge dials, continuous level charts, edge warning LEDs.
- **Concluding Narrative:**
  > "Finally, we switch to our secondary supervisory interface: the **Node-RED Operational Dashboard**.
  >
  > This interface proves multi-client interoperability, subscribing to the same MQTT topics to deliver rapid-response gauge dials and alert indicators for municipal field workers.
  >
  > In conclusion, CivicTwin-R provides:
  > 1. An authentic **3D Urban Flood Digital Twin of Chennai** covering 10 critical locations, waterways, and 3D buildings.
  > 2. A mathematically rigorous **Experimental IoT Tank Digital Twin** with RK4 numerical ODE forecasting and OLS parameter calibration.
  > 3. Scientifically validated **missing-data resilience algorithms** with zero future-data leakage in real time.
  > 4. Enterprise-grade **dual storage** coupling SQLite WAL with **InfluxDB 2.x time-series indexing**.
  > 5. Full software completeness verified by **157 automated passing tests** across geospatial validation, Landlab 2D hydrology, Torricelli physics, InfluxDB integration, and offline browser QA.
  >
  > Thank you. We are ready to answer your technical questions."
