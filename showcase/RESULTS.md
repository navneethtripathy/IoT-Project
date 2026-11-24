# CivicTwin-R — Measured Results & Verification Evidence

**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin  
**Verification Date:** 2026-11-23  
**Pass Rate:** 100% (126 / 126 Automated Tests Passing)

---

## 1. Missing-Data Reconstruction Benchmark Evidence

Evaluated on uncorrupted ground-truth water-level trajectories across 4 gap durations and 3 random seeds (42, 101, 2024).

### Tabular Performance Metrics

| Gap Duration | Steps ($dt=5\text{s}$) | Method | Setting | MAE (cm) | RMSE (cm) | Max Error (cm) | Relative Error vs LOCF |
|---|---|---|---|---|---|---|---|
| **15 seconds** | 3 steps | LOCF | Setting A & B | 0.1103 | 0.1139 | 0.1180 | Baseline (0.0%) |
| | | Causal Linear Trend | Setting A (Online) | 0.0637 | 0.0739 | 0.0890 | 42.2% reduction |
| | | Linear Interpolation | Setting B (Retrospective) | 0.0418 | 0.0423 | 0.0450 | 62.1% reduction |
| | | **Physics Digital Twin** | **Setting A & B (Model Guided)** | **0.0227** | **0.0247** | **0.0270** | **79.4% reduction** |
| **30 seconds** | 6 steps | LOCF | Setting A & B | 0.1063 | 0.1106 | 0.1240 | Baseline (0.0%) |
| | | Causal Linear Trend | Setting A (Online) | 0.1691 | 0.2084 | 0.2540 | Diverges (-59.1%) |
| | | Linear Interpolation | Setting B (Retrospective) | 0.1113 | 0.1154 | 0.1210 | -4.7% |
| | | **Physics Digital Twin** | **Setting A & B (Model Guided)** | **0.0685** | **0.0951** | **0.1120** | **35.6% reduction** |
| **60 seconds** | 12 steps | LOCF | Setting A & B | 0.1947 | 0.2583 | 0.3200 | Baseline (0.0%) |
| | | Causal Linear Trend | Setting A (Online) | 0.5086 | 0.6434 | 0.8120 | Diverges |
| | | **Linear Interpolation** | **Setting B (Retrospective)** | **0.2842** | **0.3027** | **0.3250** | **Best Retrospective** |
| | | Physics Digital Twin | Setting A & B (Model Guided) | 0.3778 | 0.5270 | 0.6410 | Inflow drift accumulates |
| **120 seconds**| 24 steps | LOCF | Setting A & B | 0.8144 | 1.0643 | 1.4500 | High error |
| | | Causal Linear Trend | Setting A (Online) | 1.3161 | 1.5929 | 1.9800 | High error |
| | | **Linear Interpolation** | **Setting B (Retrospective)** | **0.2628** | **0.3095** | **0.3400** | **Best Overall (Pinned by Future)** |
| | | Physics Digital Twin | Setting A & B (Model Guided) | 1.2863 | 1.6360 | 2.1200 | Open-loop drift |

---

## 2. Digital Twin Calibration Evidence

- **Synthetic Truth:** Tank 1, $A = 299.87\text{ cm}^2$, true $k = 4.5000\text{ cm}^{2.5}/\text{s}$, initial level $h_0 = 40.0\text{ cm}$.
- **Noise Model:** Additive Gaussian noise $\mathcal{N}(0, 0.3\text{ cm})$.
- **Recovered Parameter:** $\hat{k} = 4.4749\text{ cm}^{2.5}/\text{s}$.
- **Parameter Estimation Error:** $0.56\%$.
- **Goodness-of-Fit:** $R^2 = 0.9942$.
- **Verification Evidence:** `tests/test_tank_twin.py::TestTankCalibration::test_drain_down_calibration_synthetic` (PASSED).

---

## 3. Runge-Kutta 4th Order Convergence Evidence

Evaluated against exact analytical Torricelli drain-down solution:

| Step Size $\Delta t$ | Error at $t=60\text{s}$ ($\text{cm}$) | Truncation Behavior |
|---|---|---|
| $\Delta t = 10.0\text{ s}$ | $2.41 \times 10^{-4}$ | Stable |
| $\Delta t = 5.0\text{ s}$ | $1.48 \times 10^{-5}$ | Monotonic reduction |
| $\Delta t = 2.0\text{ s}$ | $3.76 \times 10^{-7}$ | Fourth-order $O(\Delta t^4)$ verified |

---

## 4. Live System Operational Metrics

- **Average Telemetry Ingestion Latency:** $2.4\text{ ms}$ (including Pydantic validation and SQLite write).
- **RK4 Single Step Execution Time:** $< 0.05\text{ ms}$.
- **Duplicate Message Drop Rate:** $100\%$ on repeated `(device_id, sequence)`.
- **Anti-Chatter Hysteresis Suppression:** $0$ false alert oscillations across 20 cycles alternating across $70.0\%$ threshold.
- **Node-RED UI Response Time:** $< 15\text{ ms}$ on local loopback.
- **FastAPI Endpoint Availability:** $100\%$ across all 25+ routes.
