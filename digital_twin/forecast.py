"""
CivicTwin-R — Interpretable Water-Level Forecasting Baseline

Provides transparent, interpretable baseline forecasting for urban flood catchments.
Implements:
  1. Naive Persistence Baseline: Assumes water level remains at last observed state.
  2. Rate-of-Rise (AR-RoR) Baseline: Projects level using momentum, recent velocity,
     and catchment recession with zero future-data leakage.
  3. Prediction Uncertainty Intervals: Defensible ±1.96 SE confidence bounds.
  4. Time-Aware Cross-Validation: Evaluates MAE/RMSE on chronological splits.

Decision-Support Notice:
  Forecasts are intended as early-warning decision indicators and must not
  substitute for official meteorological bulletins or government flood directives.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("civictwin.twin.forecast")

DISCLAIMER = (
    "Decision-support indicator; not an official flood warning substitute. "
    "Do not use for emergency evacuation decisions."
)


@dataclass
class HorizonForecast:
    """Projected water level for a specific time horizon."""

    horizon_minutes: int
    forecast_level_cm: float
    forecast_level_pct: float
    lower_bound_cm: float
    upper_bound_cm: float
    trend: str  # "rising", "falling", "steady"
    projected_alert: str  # "normal", "warning", "critical"

    def to_dict(self) -> dict:
        return {
            "horizon_minutes": self.horizon_minutes,
            "forecast_level_cm": round(self.forecast_level_cm, 2),
            "forecast_level_pct": round(self.forecast_level_pct, 2),
            "lower_bound_cm": round(self.lower_bound_cm, 2),
            "upper_bound_cm": round(self.upper_bound_cm, 2),
            "trend": self.trend,
            "projected_alert": self.projected_alert,
        }


@dataclass
class ZoneForecast:
    """Consolidated multi-horizon forecast for a catchment zone."""

    zone_id: str
    base_timestamp: datetime
    current_level_cm: float
    current_level_pct: float
    horizons: list[HorizonForecast]
    model_name: str = "rate_of_rise_baseline"
    provenance: str = "forecast"
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "base_timestamp": self.base_timestamp.isoformat(),
            "current_level_cm": round(self.current_level_cm, 2),
            "current_level_pct": round(self.current_level_pct, 2),
            "horizons": [h.to_dict() for h in self.horizons],
            "model_name": self.model_name,
            "provenance": self.provenance,
            "disclaimer": self.disclaimer,
        }


@dataclass
class ForecastEvaluationResult:
    """Chronological evaluation metrics comparing model against naive baseline."""

    zone_id: str
    horizon_minutes: int
    evaluated_points: int
    model_mae: float
    model_rmse: float
    baseline_mae: float
    baseline_rmse: float
    skill_score: float  # 1 - (model_mse / baseline_mse)
    data_classification: str  # "observed" or "synthetic"

    def to_dict(self) -> dict:
        return {
            "zone_id": self.zone_id,
            "horizon_minutes": self.horizon_minutes,
            "evaluated_points": self.evaluated_points,
            "model_mae": round(self.model_mae, 4),
            "model_rmse": round(self.model_rmse, 4),
            "baseline_mae": round(self.baseline_mae, 4),
            "baseline_rmse": round(self.baseline_rmse, 4),
            "skill_score": round(self.skill_score, 4),
            "data_classification": self.data_classification,
        }


class BaselineForecaster:
    """Interpretable Rate-of-Rise (RoR) forecaster."""

    def __init__(
        self,
        lookback_window: int = 6,
        recession_factor: float = 0.95,
        warn_pct: float = 70.0,
        crit_pct: float = 85.0,
    ):
        self.lookback_window = lookback_window
        self.recession_factor = recession_factor
        self.warn_pct = warn_pct
        self.crit_pct = crit_pct

    def predict(
        self,
        recent_levels_cm: list[float],
        container_height_cm: float,
        horizon_minutes: int,
        step_duration_minutes: float = 5.0 / 60.0,
    ) -> HorizonForecast:
        """
        Generate projection for a given horizon in minutes.
        Uses Rate-of-Rise autoregression over recent observations.
        """
        if not recent_levels_cm:
            return HorizonForecast(
                horizon_minutes=horizon_minutes,
                forecast_level_cm=0.0,
                forecast_level_pct=0.0,
                lower_bound_cm=0.0,
                upper_bound_cm=0.0,
                trend="steady",
                projected_alert="normal",
            )

        current_level = recent_levels_cm[-1]
        n_points = min(len(recent_levels_cm), self.lookback_window)
        active_window = recent_levels_cm[-n_points:]

        # Calculate rate of rise (cm per minute)
        if len(active_window) >= 2:
            dt_total_min = (len(active_window) - 1) * step_duration_minutes
            velocity_cm_per_min = (active_window[-1] - active_window[0]) / max(dt_total_min, 1e-4)
        else:
            velocity_cm_per_min = 0.0

        # Project level with recession damping
        # velocity decays slightly with longer horizons to avoid unphysical linear explosion
        steps_ahead = horizon_minutes / max(step_duration_minutes, 1e-4)
        effective_horizon_min = horizon_minutes * (self.recession_factor ** (steps_ahead / 10.0))

        forecast_level = current_level + (velocity_cm_per_min * effective_horizon_min)
        forecast_level = max(0.0, min(forecast_level, container_height_cm))

        forecast_pct = (forecast_level / container_height_cm * 100.0) if container_height_cm > 0 else 0.0

        # Uncertainty: estimated from local variance in recent slope
        if len(active_window) >= 3:
            diffs = [active_window[i+1] - active_window[i] for i in range(len(active_window)-1)]
            mean_diff = sum(diffs) / len(diffs)
            var_diff = sum((d - mean_diff)**2 for d in diffs) / len(diffs)
            std_diff = math.sqrt(var_diff)
        else:
            std_diff = 0.2

        uncertainty_cm = 1.96 * std_diff * math.sqrt(max(1.0, horizon_minutes))
        lower_bound = max(0.0, forecast_level - uncertainty_cm)
        upper_bound = min(container_height_cm, forecast_level + uncertainty_cm)

        # Trend and projected alert
        if velocity_cm_per_min > 0.05:
            trend = "rising"
        elif velocity_cm_per_min < -0.05:
            trend = "falling"
        else:
            trend = "steady"

        if forecast_pct >= self.crit_pct:
            projected_alert = "critical"
        elif forecast_pct >= self.warn_pct:
            projected_alert = "warning"
        else:
            projected_alert = "normal"

        return HorizonForecast(
            horizon_minutes=horizon_minutes,
            forecast_level_cm=forecast_level,
            forecast_level_pct=forecast_pct,
            lower_bound_cm=lower_bound,
            upper_bound_cm=upper_bound,
            trend=trend,
            projected_alert=projected_alert,
        )

    def forecast_zone(
        self,
        zone_id: str,
        recent_levels_cm: list[float],
        container_height_cm: float,
        horizons_minutes: tuple[int, ...] = (15, 60, 180),
        base_timestamp: Optional[datetime] = None,
    ) -> ZoneForecast:
        """Produce multi-horizon forecast for a zone."""
        current_cm = recent_levels_cm[-1] if recent_levels_cm else 0.0
        current_pct = (current_cm / container_height_cm * 100.0) if container_height_cm > 0 else 0.0
        ts = base_timestamp or datetime.now(timezone.utc)

        horizons = [
            self.predict(recent_levels_cm, container_height_cm, h)
            for h in horizons_minutes
        ]

        return ZoneForecast(
            zone_id=zone_id,
            base_timestamp=ts,
            current_level_cm=current_cm,
            current_level_pct=current_pct,
            horizons=horizons,
        )


def evaluate_forecaster_time_aware(
    series: list[float],
    container_height_cm: float,
    horizon_steps: int = 3,
    train_ratio: float = 0.7,
    zone_id: str = "zone_eval",
    data_classification: str = "observed",
) -> ForecastEvaluationResult:
    """
    Evaluates forecaster strictly forward-in-time without future-data leakage.
    Splits series into [0 : split_idx] for initial context and evaluates predictions
    on the remaining test segment.
    """
    n = len(series)
    if n < horizon_steps + 10:
        return ForecastEvaluationResult(
            zone_id=zone_id,
            horizon_minutes=int(horizon_steps * 5),
            evaluated_points=0,
            model_mae=0.0,
            model_rmse=0.0,
            baseline_mae=0.0,
            baseline_rmse=0.0,
            skill_score=0.0,
            data_classification=data_classification,
        )

    split_idx = int(n * train_ratio)
    model = BaselineForecaster()

    model_errors = []
    baseline_errors = []

    # Step forward through evaluation slice
    for t in range(split_idx, n - horizon_steps):
        history = series[:t+1]  # strictly up to t, zero future information
        true_future = series[t + horizon_steps]

        # Rate-of-rise prediction
        pred = model.predict(
            history,
            container_height_cm=container_height_cm,
            horizon_minutes=int(horizon_steps * 5),
        )
        model_errors.append(pred.forecast_level_cm - true_future)

        # Naive persistence baseline: assumes level stays at series[t]
        baseline_pred = series[t]
        baseline_errors.append(baseline_pred - true_future)

    count = len(model_errors)
    model_mae = sum(abs(e) for e in model_errors) / count
    model_rmse = math.sqrt(sum(e**2 for e in model_errors) / count)

    baseline_mae = sum(abs(e) for e in baseline_errors) / count
    baseline_rmse = math.sqrt(sum(e**2 for e in baseline_errors) / count)

    base_mse = baseline_rmse ** 2
    model_mse = model_rmse ** 2
    skill_score = 1.0 - (model_mse / base_mse) if base_mse > 0 else 0.0

    return ForecastEvaluationResult(
        zone_id=zone_id,
        horizon_minutes=int(horizon_steps * 5),
        evaluated_points=count,
        model_mae=model_mae,
        model_rmse=model_rmse,
        baseline_mae=baseline_mae,
        baseline_rmse=baseline_rmse,
        skill_score=skill_score,
        data_classification=data_classification,
    )
