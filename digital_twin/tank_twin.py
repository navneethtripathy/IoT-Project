"""
CivicTwin-R — Calibrated Physical Tank Digital Twin

Implements the mass-balance ODE for a laboratory water tank with orifice discharge:
    dh/dt = (Q_in - k * sqrt(h)) / A

Where:
    h: water height (cm)
    Q_in: inlet flow rate (cm^3/s)
    k: calibrated orifice discharge coefficient (cm^2.5 / s)
    A: tank cross-sectional area (cm^2)

Provides:
  1. High-precision 4th-order Runge-Kutta (RK4) numerical integration with non-negativity constraints.
  2. Analytical drain-down test calibration for estimating k from empirical (t, h) measurements:
         2 * A * (sqrt(h_0) - sqrt(h_t)) = k * t
  3. Prediction vs. observation comparison (MAE, RMSE, error percentage).
  4. Physics-based missing-data reconstruction via dynamic simulation forward from initial conditions.
  5. Multi-tank support for dual-node laboratory setup (node_01 / tank_01, node_02 / tank_02).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence

logger = logging.getLogger("civictwin.tank_twin")


@dataclass
class TankGeometry:
    """Dimensions and geometric properties of a cylindrical or uniform cross-section tank."""

    tank_id: str
    node_id: str
    name: str
    diameter_cm: float
    max_height_cm: float
    area_cm2: float = field(init=False)
    warn_threshold_cm: float = field(init=False)
    crit_threshold_cm: float = field(init=False)

    def __post_init__(self):
        if self.diameter_cm <= 0:
            raise ValueError(f"Tank diameter must be strictly positive, got {self.diameter_cm}")
        if self.max_height_cm <= 0:
            raise ValueError(f"Tank max height must be strictly positive, got {self.max_height_cm}")
        radius = self.diameter_cm / 2.0
        self.area_cm2 = round(math.pi * (radius ** 2), 2)
        self.warn_threshold_cm = round(self.max_height_cm * 0.70, 2)
        self.crit_threshold_cm = round(self.max_height_cm * 0.85, 2)

    def to_dict(self) -> dict:
        return {
            "tank_id": self.tank_id,
            "node_id": self.node_id,
            "name": self.name,
            "diameter_cm": self.diameter_cm,
            "area_cm2": self.area_cm2,
            "max_height_cm": self.max_height_cm,
            "warn_threshold_cm": self.warn_threshold_cm,
            "crit_threshold_cm": self.crit_threshold_cm,
        }


@dataclass
class TankCalibrationResult:
    """Parameters and goodness-of-fit metrics from a drain-down test calibration."""

    tank_id: str
    calibrated_k: float
    r_squared: float
    h0_cm: float
    num_samples: int
    duration_sec: float
    sample_residuals: list[float] = field(default_factory=list)
    calibrated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "success"
    message: str = "Drain-down test calibration converged successfully."

    def to_dict(self) -> dict:
        return {
            "tank_id": self.tank_id,
            "calibrated_k": round(self.calibrated_k, 4),
            "r_squared": round(self.r_squared, 4),
            "h0_cm": round(self.h0_cm, 2),
            "num_samples": self.num_samples,
            "duration_sec": round(self.duration_sec, 2),
            "status": self.status,
            "message": self.message,
            "calibrated_at": self.calibrated_at,
        }


class PhysicalTankModel:
    """Discrete-time physics simulation of a calibrated laboratory tank."""

    def __init__(
        self,
        geometry: TankGeometry,
        drainage_k: float,
        initial_level_cm: float = 10.0,
        default_q_in_cm3_s: float = 0.0,
    ):
        self.geometry = geometry
        self.drainage_k = max(0.0, drainage_k)
        self.current_level_cm = max(0.0, min(initial_level_cm, geometry.max_height_cm))
        self.default_q_in = max(0.0, default_q_in_cm3_s)
        self.step_count = 0
        self.time_elapsed_sec = 0.0

    @property
    def level_pct(self) -> float:
        if self.geometry.max_height_cm <= 0:
            return 0.0
        return (self.current_level_cm / self.geometry.max_height_cm) * 100.0

    def reset(self, initial_level_cm: Optional[float] = None):
        if initial_level_cm is not None:
            self.current_level_cm = max(0.0, min(initial_level_cm, self.geometry.max_height_cm))
        self.step_count = 0
        self.time_elapsed_sec = 0.0

    def dh_dt(self, h: float, q_in: float) -> float:
        """Instantaneous rate of change of water height dh/dt (cm/s)."""
        if not math.isfinite(h):
            raise ValueError(f"Water height h must be a finite number, got {h}")
        if not math.isfinite(q_in):
            raise ValueError(f"Inflow q_in must be a finite number, got {q_in}")

        if h <= 0.0:
            effective_discharge = 0.0
            net_inflow = max(0.0, q_in)
        else:
            effective_discharge = self.drainage_k * math.sqrt(h)
            net_inflow = q_in - effective_discharge

        return net_inflow / self.geometry.area_cm2

    @staticmethod
    def drain_down_analytical(h0_cm: float, t_sec: float, area_cm2: float, drainage_k: float) -> float:
        """
        Torricelli analytical drainage height at elapsed time t_sec with Q_in = 0:
            sqrt(h(t)) = sqrt(h0) - (k * t) / (2 * A)
        """
        if h0_cm <= 0.0 or area_cm2 <= 0.0:
            return 0.0
        val = math.sqrt(h0_cm) - (drainage_k * t_sec) / (2.0 * area_cm2)
        return max(0.0, val) ** 2

    def step_rk4(
        self,
        dt_sec: float,
        q_in: Optional[float] = None,
        sub_step: bool = False,
        round_digits: Optional[int] = 4,
    ) -> float:
        """
        Integrates the mass-balance ODE across dt_sec using Runge-Kutta 4th Order.
        Clamps solution strictly to [0.0, max_height_cm].

        Args:
            dt_sec: Integration time step (seconds).
            q_in: Instantaneous inflow rate (cm^3/s). Defaults to default_q_in.
            sub_step: If True and dt_sec > 0.5, subdivides into 0.5s sub-steps for stability.
            round_digits: Decimal precision to round output. None preserves full IEEE float.
        """
        if dt_sec <= 0:
            return self.current_level_cm

        inflow = self.default_q_in if q_in is None else max(0.0, q_in)

        if sub_step and dt_sec > 0.5:
            sub_dt = 0.5
            n_sub = max(1, int(math.ceil(dt_sec / sub_dt)))
            actual_sub_dt = dt_sec / n_sub
        else:
            n_sub = 1
            actual_sub_dt = dt_sec

        h = self.current_level_cm
        for _ in range(n_sub):
            k1 = self.dh_dt(h, inflow)
            k2 = self.dh_dt(h + 0.5 * actual_sub_dt * k1, inflow)
            k3 = self.dh_dt(h + 0.5 * actual_sub_dt * k2, inflow)
            k4 = self.dh_dt(h + actual_sub_dt * k3, inflow)

            h += (actual_sub_dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
            h = max(0.0, min(h, self.geometry.max_height_cm))

        self.current_level_cm = round(h, round_digits) if round_digits is not None else h
        self.step_count += 1
        self.time_elapsed_sec += dt_sec
        return self.current_level_cm

    def simulate_trajectory(
        self,
        duration_sec: float,
        dt_sec: float = 1.0,
        q_in: Optional[float] = None,
        h0_cm: Optional[float] = None,
    ) -> list[dict]:
        """Simulates water-level evolution over a specified duration."""
        h_orig = self.current_level_cm
        if h0_cm is not None:
            self.current_level_cm = max(0.0, min(h0_cm, self.geometry.max_height_cm))

        points = []
        t = 0.0
        inflow = self.default_q_in if q_in is None else q_in

        points.append({
            "time_sec": 0.0,
            "level_cm": round(self.current_level_cm, 3),
            "level_pct": round(self.level_pct, 2),
            "q_in_cm3_s": round(inflow, 2),
            "q_out_cm3_s": round(self.drainage_k * math.sqrt(max(0.0, self.current_level_cm)), 2),
        })

        steps = int(duration_sec / dt_sec)
        for _ in range(steps):
            t += dt_sec
            h = self.step_rk4(dt_sec, inflow)
            points.append({
                "time_sec": round(t, 2),
                "level_cm": round(h, 3),
                "level_pct": round(self.level_pct, 2),
                "q_in_cm3_s": round(inflow, 2),
                "q_out_cm3_s": round(self.drainage_k * math.sqrt(max(0.0, h)), 2),
            })

        self.current_level_cm = h_orig
        return points

    def get_state(self) -> dict:
        return {
            "tank_id": self.geometry.tank_id,
            "node_id": self.geometry.node_id,
            "name": self.geometry.name,
            "current_level_cm": round(self.current_level_cm, 2),
            "current_level_pct": round(self.level_pct, 2),
            "max_height_cm": self.geometry.max_height_cm,
            "area_cm2": self.geometry.area_cm2,
            "drainage_k": round(self.drainage_k, 4),
            "warn_threshold_cm": self.geometry.warn_threshold_cm,
            "crit_threshold_cm": self.geometry.crit_threshold_cm,
            "step_count": self.step_count,
            "time_elapsed_sec": round(self.time_elapsed_sec, 2),
        }


def calibrate_drain_down(
    samples: Sequence[tuple[float, float]],
    area_cm2: float,
    tank_id: str = "tank_01",
) -> TankCalibrationResult:
    """
    Calibrates drainage coefficient k from an empirical drain-down test (Q_in = 0).

    Analytical Torricelli relationship:
        2 * A * (sqrt(h_0) - sqrt(h_t)) = k * t

    Fits linear regression through the origin (y = k * t) where:
        y_i = 2 * A * (sqrt(h_0) - sqrt(h_i))
        x_i = t_i
    """
    if area_cm2 <= 0.0:
        return TankCalibrationResult(
            tank_id=tank_id,
            calibrated_k=0.0,
            r_squared=0.0,
            h0_cm=0.0,
            num_samples=len(samples),
            duration_sec=0.0,
            status="error",
            message="Tank cross-sectional area must be strictly positive.",
        )

    # Filter valid finite sample points
    valid_samples = []
    for s in samples:
        if s is not None and len(s) == 2 and s[0] is not None and s[1] is not None:
            t, h = s
            if math.isfinite(t) and math.isfinite(h) and t >= 0.0 and h >= 0.0:
                valid_samples.append((float(t), float(h)))

    if len(valid_samples) < 3:
        return TankCalibrationResult(
            tank_id=tank_id,
            calibrated_k=0.0,
            r_squared=0.0,
            h0_cm=0.0,
            num_samples=len(valid_samples),
            duration_sec=0.0,
            status="error",
            message="At least 3 valid measurement points are required for calibration.",
        )

    # Sort strictly by time
    sorted_samples = sorted(valid_samples, key=lambda s: s[0])
    t0, h0 = sorted_samples[0]
    if h0 <= 0.0:
        return TankCalibrationResult(
            tank_id=tank_id,
            calibrated_k=0.0,
            r_squared=0.0,
            h0_cm=h0,
            num_samples=len(samples),
            duration_sec=0.0,
            status="error",
            message="Initial water level h0 must be greater than zero.",
        )

    t_vals = []
    y_vals = []

    sqrt_h0 = math.sqrt(h0)
    for t_i, h_i in sorted_samples:
        rel_t = t_i - t0
        clamped_h = max(0.0, min(h_i, h0))
        y_i = 2.0 * area_cm2 * (sqrt_h0 - math.sqrt(clamped_h))
        t_vals.append(rel_t)
        y_vals.append(y_i)

    # OLS through origin: k = sum(x * y) / sum(x^2)
    sum_xy = sum(x * y for x, y in zip(t_vals, y_vals))
    sum_xx = sum(x * x for x in t_vals)

    if sum_xx <= 1e-9:
        return TankCalibrationResult(
            tank_id=tank_id,
            calibrated_k=0.0,
            r_squared=0.0,
            h0_cm=h0,
            num_samples=len(samples),
            duration_sec=0.0,
            status="error",
            message="Time duration is zero; cannot compute slope.",
        )

    k = max(0.0, sum_xy / sum_xx)

    # Goodness-of-fit R^2
    y_mean = sum(y_vals) / len(y_vals)
    ss_tot = sum((y - y_mean) ** 2 for y in y_vals)
    ss_res = sum((y - k * x) ** 2 for x, y in zip(t_vals, y_vals))
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-9 else 1.0

    residuals = [round(y - k * x, 4) for x, y in zip(t_vals, y_vals)]
    duration = t_vals[-1] - t_vals[0]

    return TankCalibrationResult(
        tank_id=tank_id,
        calibrated_k=k,
        r_squared=r_squared,
        h0_cm=h0,
        num_samples=len(samples),
        duration_sec=duration,
        sample_residuals=residuals,
        status="success",
        message="Calibration successful.",
    )


def evaluate_tank_prediction(
    measured: Sequence[float],
    predicted: Sequence[float],
) -> dict:
    """Computes MAE, RMSE, Pearson correlation, and max absolute error."""
    if not measured or not predicted:
        return {
            "sample_count": 0,
            "mae_cm": 0.0,
            "rmse_cm": 0.0,
            "max_error_cm": 0.0,
            "mean_error_cm": 0.0,
            "correlation": 0.0,
        }

    n = min(len(measured), len(predicted))
    meas = measured[:n]
    pred = predicted[:n]

    errors = [p - m for p, m in zip(pred, meas)]
    abs_errors = [abs(e) for e in errors]

    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(e ** 2 for e in errors) / n)
    max_err = max(abs_errors)
    mean_err = sum(errors) / n

    # Correlation
    m_mean = sum(meas) / n
    p_mean = sum(pred) / n
    cov = sum((m - m_mean) * (p - p_mean) for m, p in zip(meas, pred))
    m_std = math.sqrt(sum((m - m_mean) ** 2 for m in meas))
    p_std = math.sqrt(sum((p - p_mean) ** 2 for p in pred))
    corr = (cov / (m_std * p_std)) if (m_std * p_std > 1e-9) else 1.0

    return {
        "sample_count": n,
        "mae_cm": round(mae, 4),
        "rmse_cm": round(rmse, 4),
        "max_error_cm": round(max_err, 4),
        "mean_error_cm": round(mean_err, 4),
        "correlation": round(corr, 4),
    }


def reconstruct_physics_based(
    series: list[Optional[float]],
    dt_sec: float,
    area_cm2: float,
    drainage_k: float,
    q_in_cm3_s: float,
    max_height_cm: float,
) -> list[Optional[float]]:
    """
    Reconstructs missing intervals in a water-level time series using forward integration
    of the calibrated mass-balance equation starting from the last valid observed state.

    Integrates:
        dh/dt = (Q_in - k * sqrt(h)) / A
    """
    result = list(series)
    geom = TankGeometry(
        tank_id="temp",
        node_id="temp",
        name="Temp Tank",
        diameter_cm=math.sqrt(4.0 * area_cm2 / math.pi),
        max_height_cm=max_height_cm,
    )
    sim = PhysicalTankModel(geometry=geom, drainage_k=drainage_k, default_q_in_cm3_s=q_in_cm3_s)

    last_valid_idx: Optional[int] = None
    last_valid_level: Optional[float] = None

    for i, val in enumerate(result):
        if val is not None:
            last_valid_idx = i
            last_valid_level = val
        elif last_valid_level is not None:
            # We are inside a missing gap!
            # Initialize simulator to the last valid observed state if this is the start of the gap
            if i - 1 == last_valid_idx:
                sim.current_level_cm = last_valid_level
            sim.step_rk4(dt_sec, q_in_cm3_s)
            result[i] = round(sim.current_level_cm, 3)

    return result


def create_default_tanks() -> dict[str, PhysicalTankModel]:
    """Creates the standard two-tank physical laboratory configuration."""
    # Tank 1 (Node 1) — Medium Cylinder
    geom1 = TankGeometry(
        tank_id="tank_01",
        node_id="node_01",
        name="Tank 1 (Saidapet Drainage Runoff Laboratory Prototype)",
        diameter_cm=19.54,  # -> Area = 300.0 cm^2
        max_height_cm=50.0,
    )
    tank1 = PhysicalTankModel(
        geometry=geom1,
        drainage_k=4.5,  # cm^2.5 / s
        initial_level_cm=12.0,
        default_q_in_cm3_s=25.0,  # 1.5 L/min
    )

    # Tank 2 (Node 2) — Large Cylinder
    geom2 = TankGeometry(
        tank_id="tank_02",
        node_id="node_02",
        name="Tank 2 (Cooum Urban Retention Laboratory Prototype)",
        diameter_cm=23.94,  # -> Area = 450.0 cm^2
        max_height_cm=60.0,
    )
    tank2 = PhysicalTankModel(
        geometry=geom2,
        drainage_k=6.0,  # cm^2.5 / s
        initial_level_cm=15.0,
        default_q_in_cm3_s=35.0,  # 2.1 L/min
    )

    return {"tank_01": tank1, "tank_02": tank2}
