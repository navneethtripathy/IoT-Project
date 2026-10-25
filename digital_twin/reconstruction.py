"""
CivicTwin-R — Missing-Data Reconstruction Module

Implements and evaluates baseline methods for reconstructing missing sensor observations.
Methods:
    - LOCF (Last Observation Carried Forward)
    - Linear Interpolation
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("civictwin.twin.reconstruction")


@dataclass
class ReconstructionEvaluation:
    """Evaluation result for a reconstruction method on a dataset."""

    method: str
    missing_rate: float
    total_points: int
    missing_points: int
    evaluated_points: int
    mae: float
    rmse: float
    max_error: float
    reconstructed_values: list[Optional[float]]
    ground_truth: list[float]
    mask: list[bool]
    provenance: str = "IMPUTED"


def locf(series: list[Optional[float]]) -> list[Optional[float]]:
    """Last Observation Carried Forward. Leading Nones remain None."""
    result = list(series)
    last_valid: Optional[float] = None
    for i, v in enumerate(result):
        if v is not None:
            last_valid = v
        elif last_valid is not None:
            result[i] = last_valid
    return result


def linear_interpolation(series: list[Optional[float]]) -> list[Optional[float]]:
    """
    Setting B — Offline Retrospective Linear Interpolation.
    Requires both past observation x_i and future observation x_j to bridge the gap.
    Not usable in real-time streaming where x_j has not yet arrived.
    """
    result = list(series)
    valid_indices = [i for i, v in enumerate(result) if v is not None]

    if len(valid_indices) < 2:
        return locf(series)

    for idx in range(len(valid_indices) - 1):
        start_i = valid_indices[idx]
        end_i = valid_indices[idx + 1]

        if end_i - start_i <= 1:
            continue

        start_val = result[start_i]
        end_val = result[end_i]
        gap = end_i - start_i

        for j in range(start_i + 1, end_i):
            t = (j - start_i) / gap
            result[j] = start_val + t * (end_val - start_val)

    return result


def linear_trend_causal(
    series: list[Optional[float]],
    max_extrapolate_steps: int = 24,
    decay: float = 0.95,
) -> list[Optional[float]]:
    """
    Setting A — Online Causal Linear Trend Estimator (Zero Future-Data Leakage).
    Extrapolates missing values forward using only past observations prior to the gap.
    Uses slope between the last two valid observations:
        m = (x_k - x_{k-1})
        x_{k+j} = max(0.0, x_k + m * j * (decay ** j))
    """
    result = list(series)
    valid_history: list[tuple[int, float]] = []

    for i, v in enumerate(result):
        if v is not None:
            valid_history.append((i, v))
        elif valid_history:
            last_idx, last_val = valid_history[-1]
            gap_step = i - last_idx

            if len(valid_history) >= 2:
                prev_idx, prev_val = valid_history[-2]
                dt_indices = max(1, last_idx - prev_idx)
                slope = (last_val - prev_val) / dt_indices
            else:
                slope = 0.0

            damping = decay ** gap_step
            extrapolated = last_val + slope * gap_step * damping
            result[i] = round(max(0.0, extrapolated), 4)

    return result


def create_missing_mask(
    length: int,
    missing_rate: float,
    seed: int = 42,
    min_gap: int = 1,
    max_gap: int = 5,
) -> list[bool]:
    """Generates a reproducible contiguous-dropout mask."""
    rng = random.Random(seed)
    mask = [False] * length
    target_missing = int(length * missing_rate)
    missing_count = 0

    start_safe = max(2, int(length * 0.02))
    end_safe = length - start_safe

    attempts = 0
    max_attempts = length * 10

    while missing_count < target_missing and attempts < max_attempts:
        attempts += 1
        gap_len = rng.randint(min_gap, max_gap)
        start = rng.randint(start_safe, end_safe)
        end = min(start + gap_len, end_safe)

        for i in range(start, end):
            if not mask[i]:
                mask[i] = True
                missing_count += 1
                if missing_count >= target_missing:
                    break

    return mask


def apply_mask(
    ground_truth: list[float],
    mask: list[bool],
) -> list[Optional[float]]:
    return [None if m else v for v, m in zip(ground_truth, mask)]


def evaluate_reconstruction(
    ground_truth: list[float],
    reconstructed: list[Optional[float]],
    mask: list[bool],
) -> dict:
    """Computes MAE and RMSE strictly on held-out positions."""
    errors = []
    for gt, recon, is_missing in zip(ground_truth, reconstructed, mask):
        if is_missing and recon is not None:
            errors.append(abs(gt - recon))

    if not errors:
        return {
            "evaluated_points": 0,
            "mae": float("nan"),
            "rmse": float("nan"),
            "max_error": float("nan"),
        }

    mae = sum(errors) / len(errors)
    rmse = math.sqrt(sum(e ** 2 for e in errors) / len(errors))
    max_error = max(errors)

    return {
        "evaluated_points": len(errors),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "max_error": round(max_error, 4),
    }


def run_reconstruction_experiment(
    ground_truth: list[float],
    missing_rate: float,
    seed: int = 42,
    methods: Optional[list[str]] = None,
    tank_params: Optional[dict] = None,
    dt_sec: float = 5.0,
    data_source: str = "SIMULATED VALIDATION",
) -> list[ReconstructionEvaluation]:
    if methods is None:
        methods = ["locf", "linear"]

    mask = create_missing_mask(len(ground_truth), missing_rate, seed=seed)
    masked_series = apply_mask(ground_truth, mask)
    missing_count = sum(mask)

    results = []

    # Default physics parameters if not specified
    t_params = tank_params or {
        "area_cm2": 300.0,
        "drainage_k": 4.5,
        "q_in_cm3_s": 25.0,
        "max_height_cm": 50.0,
    }

    for method_name in methods:
        if method_name == "locf":
            reconstructed = locf(masked_series)
        elif method_name == "linear":
            reconstructed = linear_interpolation(masked_series)
        elif method_name in ("physics_twin", "physics", "digital_twin"):
            from digital_twin.tank_twin import reconstruct_physics_based
            reconstructed = reconstruct_physics_based(
                series=masked_series,
                dt_sec=dt_sec,
                area_cm2=t_params["area_cm2"],
                drainage_k=t_params["drainage_k"],
                q_in_cm3_s=t_params["q_in_cm3_s"],
                max_height_cm=t_params["max_height_cm"],
            )
        else:
            logger.warning("Unknown reconstruction method: %s", method_name)
            continue

        metrics = evaluate_reconstruction(ground_truth, reconstructed, mask)

        results.append(ReconstructionEvaluation(
            method=method_name,
            missing_rate=missing_rate,
            total_points=len(ground_truth),
            missing_points=missing_count,
            evaluated_points=metrics["evaluated_points"],
            mae=metrics["mae"],
            rmse=metrics["rmse"],
            max_error=metrics["max_error"],
            reconstructed_values=reconstructed,
            ground_truth=ground_truth,
            mask=mask,
            provenance="IMPUTED" if data_source == "OBSERVED" else "SIMULATED VALIDATION",
        ))

    return results


def run_multi_rate_experiment(
    ground_truth: list[float],
    rates: Optional[list[float]] = None,
    seed: int = 42,
    methods: Optional[list[str]] = None,
    tank_params: Optional[dict] = None,
    dt_sec: float = 5.0,
) -> list[ReconstructionEvaluation]:
    if rates is None:
        rates = [0.05, 0.10, 0.20, 0.30]

    all_results = []
    for rate in rates:
        results = run_reconstruction_experiment(
            ground_truth,
            missing_rate=rate,
            seed=seed,
            methods=methods or ["locf", "linear"],
            tank_params=tank_params,
            dt_sec=dt_sec,
        )
        all_results.extend(results)

    return all_results


def run_gap_length_experiment(
    ground_truth: list[float],
    gap_lengths: Optional[list[int]] = None,
    seed: int = 42,
    dt_sec: float = 5.0,
    tank_params: Optional[dict] = None,
    data_source: str = "SIMULATED VALIDATION",
) -> list[dict]:
    """
    Evaluates LOCF, Linear, and Physics-Based Twin Reconstruction across specific gap durations.
    Returns structured records suitable for tabular reporting.
    """
    if gap_lengths is None:
        gap_lengths = [3, 6, 12, 24]  # e.g. 15s, 30s, 60s, 120s at dt=5s

    from digital_twin.tank_twin import reconstruct_physics_based

    t_params = tank_params or {
        "area_cm2": 300.0,
        "drainage_k": 4.5,
        "q_in_cm3_s": 25.0,
        "max_height_cm": 50.0,
    }

    records = []
    rng = random.Random(seed)
    length = len(ground_truth)
    max_gap = max(gap_lengths) if gap_lengths else 24
    start_min = 10
    start_max = max(start_min + 1, length - max_gap - 10)
    seed_start = rng.randint(start_min, start_max)

    for gap_len in gap_lengths:
        # Create a single missing gap starting at the seed-controlled position
        mask = [False] * length
        start = seed_start
        end = min(start + gap_len, length)
        for idx in range(start, end):
            mask[idx] = True

        missing_count = sum(mask)
        missing_pct = round((missing_count / length) * 100.0, 1)
        masked = apply_mask(ground_truth, mask)

        reconstructions = {
            "LOCF": (locf(masked), "Setting A & B (Past Only)"),
            "Causal Linear Trend": (linear_trend_causal(masked), "Setting A (Online Causal)"),
            "Linear Interpolation": (linear_interpolation(masked), "Setting B (Offline Retrospective)"),
            "Physics Digital Twin": (
                reconstruct_physics_based(
                    masked, dt_sec, t_params["area_cm2"], t_params["drainage_k"],
                    t_params["q_in_cm3_s"], t_params["max_height_cm"]
                ),
                "Setting A & B (Model Guided)",
            ),
        }

        for method_name, (recon_series, setting_name) in reconstructions.items():
            metrics = evaluate_reconstruction(ground_truth, recon_series, mask)
            records.append({
                "method": method_name,
                "setting": setting_name,
                "gap_length_steps": gap_len,
                "gap_duration_sec": round(gap_len * dt_sec, 1),
                "missing_percentage": missing_pct,
                "sample_count": metrics["evaluated_points"],
                "MAE": metrics["mae"],
                "RMSE": metrics["rmse"],
                "max_error": metrics["max_error"],
                "data_source": data_source,
            })

    return records

