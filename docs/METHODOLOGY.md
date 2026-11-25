# Hydrological & Numerical Methodology

## 1. Urban 2D Overland Flow Routing (Workstream A)

Surface flood screening over the South Chennai pilot domain (`80.045°E–80.285°E`, `12.905°N–13.055°N`) solves the 2D inertial shallow-water approximation via **Landlab `OverlandFlow`** (de Almeida et al. 2012) on an `EPSG:32644` metric grid (`111 × 175` cells, `dx = 150 m`, `18,136` active land cells):

$$\frac{\partial h}{\partial t} + \nabla \cdot \mathbf{q} = i_{\text{rain}}(t) + q_{\text{spillway}}(t) - f_{\text{infil}}(x, y, t) - d_{\text{drain}}(x, y, t)$$

### Implementation Guarantees
- **Channel Hydro-Conditioning (`geoprocessor.py`):** Major river and canal pixels (`Adyar`, `Chembarambakkam surplus`, `Buckingham Canal`, `Pallikaranai`, `Cooum`, `Okkiyam`) undergo 7×7 valid-land minimum filtering plus downstream monotonicity breaching toward coastal ocean cells (`z = 0.0 m`) to prevent artificial DSM bridge decks from blocking river conveyance.
- **Single-Pass Loss Accounting (`terrain_hydrology.py`):** Permeable soil infiltration (`1 - impervious_fraction`) and capped stormwater drainage sinks are deducted without double-counting and strictly bounded by available cell water (`h >= 0`).
- **Spillway Inflow Routing:** Chembarambakkam discharge (`m³/s = cusecs * 0.0283168`) is injected incrementally at each adaptive CFL substep across the 4 headwater channel cells to preserve numerical smoothness (`relative mass-balance error < 0.2%`).

### Implemented Urban Scenarios (`PREDEFINED_SCENARIOS`)

| Scenario ID | Forcing | Purpose |
| :--- | :--- | :--- |
| `normal` | `0 mm/hr`, `2h`, `100%` drainage | Dry-weather baseline (`0.000 MCM` ponding) |
| `heavy_rainfall` | `45 mm/hr`, `4h`, `100%` drainage | Representative convective monsoon event |
| `extreme_rainfall` | `85 mm/hr`, `6h`, `80%` drainage | Hypothetical severe cloudburst stress test |
| `reduced_drainage` | `45 mm/hr`, `4h`, `25%` drainage | Isolates urban stormwater clogging impact |
| `improved_drainage` | `45 mm/hr`, `4h`, `200%` drainage | Counterfactual capacity upgrade assessment |
| `michaung_replay` | Peak `24h` CSV hourly hyetograph | Observed Dec 2023 Cyclone Michaung precipitation forcing |
| `monitoring_dropout` | `55 mm/hr`, `4h`, `75%` drainage | Evaluates uncertainty (`±35%`) under telemetry gaps |
| `reservoir_discharge` | `25 mm/hr`, `12h`, `25,000 cusecs` | Chembarambakkam spillway wave down Adyar valley |

---

## 2. Experimental Tank Physics & Parameter Calibration (Workstream B)

Water depth $h(t)$ inside cylindrical validation tanks (`tank_01`: $H = 50\text{ cm}, A = 299.87\text{ cm}^2, k = 4.5$; `tank_02`: $H = 60\text{ cm}, A = 450.13\text{ cm}^2, k = 6.0$) satisfies Torricelli mass continuity:

$$\frac{dh}{dt} = \frac{Q_{\text{in}}(t) - k\sqrt{h(t)}}{A}$$

Forward trajectories integrate with a fixed-step **4th-Order Runge-Kutta (RK4)** solver ($\Delta t = 1.0\text{ s}$). During unforced drain-down ($Q_{\text{in}} = 0$), exact integration yields $2A(\sqrt{h_0} - \sqrt{h_t}) = k t$, enabling zero-intercept Ordinary Least Squares recovery of $\hat{k}$. On synthetic Gaussian-noise tests ($\sigma = 0.3\text{ cm}$), OLS calibration recovers $\hat{k} = 4.4749$ against true $k = 4.5000$ ($0.56\%$ error, $R^2 = 0.9942$).

---

## 3. Missing-Data Reconstruction Settings (Zero Leakage Design)

`experiments/run_three_method_reconstruction.py` evaluates estimators under strict information boundaries:

- **Setting A (Online Causal Streaming):** Only past observations ($\mathcal{H}_{<k}$) are accessible. Evaluates LOCF, backward Causal Linear Trend, and Physics Digital Twin forward RK4 integration.
- **Setting B (Offline Retrospective Imputation):** Uses both past ($x_{k-1}$) and restored future boundary ($x_{k+m}$). Evaluates Two-Sided Linear Interpolation vs. causal baselines.

| Gap Duration | LOCF MAE (cm) | Causal Trend MAE (cm) | Retrospective Linear MAE (cm) | Physics Twin MAE (cm) | Best Method |
| :---: | :---: | :---: | :---: | :---: | :--- |
| `15 s` | `0.1103` | `0.0637` | `0.0418` | `0.0227` | Physics Twin (Causal) |
| `30 s` | `0.1063` | `0.1691` | `0.1113` | `0.0685` | Physics Twin (Causal) |
| `60 s` | `0.1947` | `0.5086` | `0.2842` | `0.3778` | Retrospective Linear (Settings with future bound) |
| `120 s` | `0.8144` | `1.3161` | `0.2628` | `1.2863` | Retrospective Linear |
