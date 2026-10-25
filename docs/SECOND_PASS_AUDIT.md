# CivicTwin-R: Second-Pass Master Engineering Audit & Resolution Record

**Audit Date:** 25 October 2026  
**Auditor:** Independent Principal Systems Architect & QA Lead  
**Audit Scope:** Full codebase, numerical models, physical digital twin, firmware, telemetry freshness, missing-data experiment, deployment configs, and technical documentation.  
**Target Deadline:** **15 November 2026** *(Revised per Professor's Directive)*  
**Verification Baseline:** **119 Automated Tests Passing (100% Pass Rate)**  

---

## 1. Phase 0: Baseline & Repository Health Check

### 1.1 Git Status & Data Protection
- **Repository Path:** `/Users/navneethtripathy/Desktop/IoT Project/CivicTwin-R`
- **Branch:** `main` (synchronized with `origin/main`)
- **Uncommitted User Data Protection:**
  - `data/processed/chennai_arg_rainfall.csv` — **PRESERVED & UNTOUCHED**
  - `data/processed/chennai_reservoirs.csv` — **PRESERVED & UNTOUCHED**
  - `data/raw/cfm_dashboard_raw.json` — **PRESERVED & UNTOUCHED**
  - `data/raw/chennai_michaung_hourly_raw.json` — **PRESERVED & UNTOUCHED**
  - Zero reset, checkout, or destructive clean operations executed.

### 1.2 Baseline Automated Test Verification
- **Baseline Test Run:** `python3 -m pytest tests -q`
- **Baseline Result:** 109 passed, 1 warning in 30.39s (Python 3.14.5, macOS).
- **Final Test Run After Hardening:** **119 passed, 1 warning in 30.42s** (10 new rigorous tests added, 0 failures).

---

## 2. Phase 1: Reconciliation of the 10 Handover Discrepancies

| # | Handover Claim / Area | Audit Reality Check | Finding Classification | Engineering Action Taken |
|---|---|---|---|---|
| **1** | "Zero future-data leakage in linear interpolation" | Standard two-sided linear interpolation $x_t = x_i + \frac{x_j - x_i}{j - i}(t - i)$ requires the future recovery point $x_j$. In real-time streaming, $x_j$ has not yet occurred. | **Confirmed Scientific Defect** | Formally defined **Setting A (Online Causal Streaming)** using backward-looking velocity trend (`linear_trend_causal`) and **Setting B (Offline Retrospective)** using two-sided `linear_interpolation`. |
| **2** | "Two node identities prove concurrent dual-node operation" | Code defined `node_01` and `node_02`, but existing tests only queried them sequentially or via static config. No integration test proved concurrent dual-node streams. | **Verification Gap** | Implemented `TestDualNodeConcurrentIsolation::test_concurrent_dual_node_isolation`, proving concurrent interleaved streams, independent histories, independent freshness states, and selective failure. |
| **3** | "Node-RED dashboard verified via JSON parse" | Static JSON parsing proves syntax validity, but does not prove live widget binding without a running Node-RED instance. | **Limitation Disclosed** | Validated JSON schema and parameterized URLs using `${BACKEND_URL:-http://127.0.0.1:8000}`; documented live verification steps. |
| **4** | "Mock MQTT proves broker integration" | Unit tests mock the Paho client or use in-memory dispatch. Real TCP broker connectivity requires Mosquitto. | **Clarification Required** | Clearly distinguished mock unit tests from live broker requirements in documentation. |
| **5** | "127.0.0.1 in Node-RED flows breaks Docker containers" | Hardcoding `http://127.0.0.1:8000` enabled host macOS execution, but inside Docker containers `127.0.0.1` targets the Node-RED container itself, breaking container networking. | **Architecture Defect** | Parameterized all 7 HTTP request nodes in `nodered/flows.json` with `${BACKEND_URL:-http://127.0.0.1:8000}`. |
| **6** | "Calibrated tank twin" | The analytical OLS Torricelli calibration was evaluated on synthetic data ($k=4.5, R^2 > 0.99$), not physical tank measurements. | **Integrity Statement** | Explicitly labeled all results as **`SIMULATED VALIDATION`**; emphasized calibration workflow is ready for physical bench data. |
| **7** | "Wokwi simulation verified" | `diagram.json` and firmware exist and compile, but browser-based interactive simulation cannot be run autonomously via CLI. | **Limitation Disclosed** | Disclosed that Wokwi is an interactive manual verification tool. |
| **8** | "DOCX report generated" | The initial DOCX generator converted markdown table rows to plain pipe-delimited text (` | `), lacking true Word tables, borders, and embedded plot figures. | **Quality Defect** | Re-engineered `scripts/generate_docx_report.py` to create native Word `Table` objects with XML borders, cell padding, background shading, and embedded PNG figures. |
| **9** | "109 passing tests reproducible" | Independently rerun and verified: 109 passed in 30.39s. | **VERIFIED PASS** | Retained and expanded to **119 passing tests** with 0 failures. |
| **10**| "Physical sensor deployment" | No physical hardware has been submerged or deployed in Chennai rivers or laboratory bench tanks. | **Integrity Statement** | Retained unambiguous disclaimers across all reports and code headers. |

---

## 3. Phase 2: Numerical and Physical Model Audit

### 3.1 Governing Equation & Dimensional Balance
The tank mass-balance ODE is governed by Torricelli orifice discharge:

$$\frac{dh}{dt} = \frac{Q_{\text{in}} - k\sqrt{h}}{A}$$

- $h$: Water depth $(\text{cm})$
- $t$: Time $(\text{s})$
- $Q_{\text{in}}$: Volumetric inflow rate $(\text{cm}^3/\text{s})$
- $A$: Tank cross-sectional area $(\text{cm}^2)$
- $k$: Lumped orifice discharge coefficient $(\text{cm}^{2.5}/\text{s})$
- Dimensional homogeneity confirmed: $[dh/dt] = \text{cm}/\text{s}$; $[Q_{\text{in}}/A] = \text{cm}/\text{s}$; $[k\sqrt{h}/A] = \text{cm}/\text{s}$.

### 3.2 Numerical Convergence Verification
- **Defect Found:** `step_rk4()` originally enforced an internal 0.5s sub-stepping limit and rounded to 4 decimals unconditionally, which masked the truncation error behavior during convergence analysis.
- **Correction:** Added configurable `sub_step: bool = False` and `round_digits: Optional[int] = 4`.
- **Convergence Test:** In `test_rk4_convergence_rate`, evaluated single-step RK4 error vs the exact analytical Torricelli solution $h_{\text{exact}}(t) = (\sqrt{h_0} - \frac{k}{2A}t)^2$ at $t=20\text{s}$ for step sizes $\Delta t \in [10.0\text{s}, 5.0\text{s}, 2.0\text{s}]$. Truncation error decreased monotonically from $1.1 \times 10^{-2}$ to $2.4 \times 10^{-4}\text{ cm}$.

### 3.3 Calibration Recovery & Sensitivity Analysis
- **Noise Recovery Test (`test_calibration_noise_recovery`):** Tested OLS regression $2A(\sqrt{h_0}-\sqrt{h_t}) = k \cdot t$ on synthetic drain-down data corrupted with Gaussian measurement noise ($\sigma = 1.5\text{ mm}$). Recovered $k = 4.47\text{ cm}^{2.5}/\text{s}$ (within $0.7\%$ of true $4.5$, $R^2 > 0.98$).
- **Parameter Sensitivity Test (`test_calibration_parameter_sensitivity`):** Perturbed $k$ by $\pm 15\%$. Proved that under-estimating $k$ ($3.825$) results in positive water level bias, while over-estimating $k$ ($5.175$) results in negative bias.

---

## 4. Phase 3: Two-Node Telemetry & Freshness Audit

### 4.1 Concurrent Isolation Verification
In `TestDualNodeConcurrentIsolation::test_concurrent_dual_node_isolation`:
- Interleaved 5 telemetry packets each for `node_01` (Zone 1) and `node_02` (Zone 2).
- Storage query confirmed exactly 5 records for `zone_01` and 5 records for `zone_02`.
- Zero cross-contamination or parameter overwriting between nodes.

### 4.2 Selective Node Failure & Freshness State Transitions
- Telemetry for `node_01` was stopped while `node_02` continued receiving fresh packets.
- At $t=130\text{s}$, `node_01` transitioned to `STALE` / `OFFLINE` ($>90\text{s}$ timeout), while `node_02` remained strictly `FRESH`.
- Out-of-order rejection: sending `seq=2` after `seq=5` was rejected with `messages_duplicate` incremented and zero corruption of latest valid water level.

---

## 5. Phase 4: Firmware & Edge Warning Audit

### 5.1 Firmware Defect Resolutions in `firmware/esp32/src/main.ino`
1. **Duplicate Constants Removed:** `CONTAINER_HEIGHT_CM = 30.0` and `SENSOR_MIN_CM = 2.0` were redeclared at lines 104-105, conflicting with the per-node `#if NODE_SELECT` blocks. Removed the redundant declarations.
2. **Hysteresis Logic Ordering Fixed:** Originally, `waterPct >= WARN_THRESHOLD_PCT` was checked before checking critical hysteresis retention (`currentAlert == "critical" && waterPct >= 82.0`). As a result, any level between 82% and 85% immediately demoted to Warning instead of staying Critical. Corrected the branching order so critical hysteresis retention takes precedence.
3. **LED State Differentiation Added:** Implemented `updateLedIndicator(now)` providing 1 Hz blinking (500ms ON / 500ms OFF) for Warning vs solid steady illumination for Critical, allowing field personnel to distinguish caution from emergency.
4. **Electrical Safety Voltage Divider:** Documented 2.2kΩ/3.3kΩ passive resistor divider on GPIO 18 to step 5V Echo pulse down to 3.0V logic, preventing ESP32 gate degradation.
5. **Pure-Python Testable Component:** Created `digital_twin/edge_warning.py` (`EdgeWarningEvaluator`) allowing automated unit testing of boundary conditions, hysteresis retention, ripple oscillation suppression, and sensor fault tolerance (holding state up to 4 faults, transitioning to FAULT on 5th).

---

## 6. Phase 5: Scientific Audit of Missing-Data Reconstruction

### 6.1 Formalization of Setting A vs Setting B
- **Setting A — Online Causal Streaming (Zero Future Information):**
  - LOCF (Last Observation Carried Forward)
  - Causal Linear Trend (`linear_trend_causal`: backward slope with decay damping)
  - Physics Digital Twin (forward RK4 ODE integration)
- **Setting B — Offline Retrospective Gap Reconstruction:**
  - Two-Sided Linear Interpolation (bridges past and future boundary points)
  - LOCF & Physics Twin (baseline comparisons)

### 6.2 Multi-Seed Benchmark Results
Evaluated across seeds 42, 101, 2024 and gap durations 15s, 30s, 60s, 120s:
- **15s Gaps:** Causal Linear Trend achieves $\text{MAE} = 0.0052\text{ cm}$; Linear Interpolation achieves $\text{MAE} = 0.0207\text{ cm}$; Physics Twin achieves $\text{MAE} = 0.3683\text{ cm}$.
- **120s Gaps:** Linear extrapolation drifts to $\text{RMSE} = 1.2324\text{ cm}$; retrospective linear interpolation degrades to $\text{RMSE} = 1.0824\text{ cm}$; **Physics Digital Twin outperforms both in RMSE ($0.8029\text{ cm}$)** because the mass-balance ODE physically bounds the trajectory toward hydraulic equilibrium ($Q_{\text{in}} = k\sqrt{h}$).
- Generated 3 publication-quality plots:
  - `results/plots/three_method_gap_length_mae.png`
  - `results/plots/three_method_gap_length_rmse.png`
  - `results/plots/three_method_reconstruction_trajectories.png`

---

## 7. Phase 6 & 7: Backend, Storage & Node-RED Audit

### 7.1 Backend API & Storage
- Provenance categories enforced canonically (`OBSERVED`, `SYNTHETIC`, `REPLAYED`, `TWIN_ESTIMATED`, `IMPUTED`).
- Telemetry deduplication verified on `(device_id, sequence)`.
- SQLite storage migrations and query interfaces verified.

### 7.2 Node-RED Dynamic Deployment Compatibility
- Parameterized all HTTP request URLs in `nodered/flows.json` using `${BACKEND_URL:-http://127.0.0.1:8000}`.
- Enables native standalone host execution on macOS and container networking inside Docker without code changes.

---

## 8. Phase 8 & 9: Technical Documentation & Final Verification

### 8.1 High-Fidelity DOCX Generation
- Re-engineered `scripts/generate_docx_report.py` to create native Word `Table` objects with XML borders, header shading (`#1F4E79`), and cell padding.
- Automatically embeds high-resolution PNG plots with centered figure captions.
- Generates `docs/CivicTwin-R_Technical_Report.docx` (1,243.5 KB, 5 true Word tables, 231 paragraphs).

### 8.2 Final Test Suite Summary
- **Total Tests:** **119**
- **Passed:** **119 (100%)**
- **Failed:** **0**
- **Execution Time:** ~30.5 seconds on macOS Python 3.14.5.
- **Authoritative Breakdown by File:**
  - `tests/test_all.py` (73 tests): Core digital twin, scenarios, reconstruction, ingestion, hysteresis, storage, APIs, provenance.
  - `tests/test_chennai_twin.py` (19 tests): Chennai basin hydrology, historical replay, fallback storage, and forecasting baseline.
  - `tests/test_tank_twin.py` (27 tests): Physics, calibration, freshness, APIs, RK4 convergence, noise recovery, dual-node concurrent isolation, edge warning, and Setting A/B causal tests.
