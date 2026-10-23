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
    """Linear interpolation between available observations without extrapolation."""
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
) -> list[ReconstructionEvaluation]:
    if methods is None:
        methods = ["locf", "linear"]

    mask = create_missing_mask(len(ground_truth), missing_rate, seed=seed)
    masked_series = apply_mask(ground_truth, mask)
    missing_count = sum(mask)

    results = []
    method_funcs = {
        "locf": locf,
        "linear": linear_interpolation,
    }

    for method_name in methods:
        func = method_funcs.get(method_name)
        if not func:
            logger.warning("Unknown reconstruction method: %s", method_name)
            continue

        reconstructed = func(masked_series)
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
        ))

    return results


def run_multi_rate_experiment(
    ground_truth: list[float],
    rates: Optional[list[float]] = None,
    seed: int = 42,
) -> list[ReconstructionEvaluation]:
    if rates is None:
        rates = [0.05, 0.10, 0.20, 0.30]

    all_results = []
    for rate in rates:
        results = run_reconstruction_experiment(
            ground_truth, missing_rate=rate, seed=seed
        )
        all_results.extend(results)

    return all_results
