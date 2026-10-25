"""
CivicTwin-R — Missing-Data Reconstruction Scientific Benchmark
Comparative evaluation of missing-data estimation for cyber-physical water level monitoring.

Evaluates four estimators across two rigorous evaluation settings:
    Setting A: Online Causal Streaming (Zero Future Information)
        - LOCF (Last Observation Carried Forward)
        - Causal Linear Trend (backward-looking velocity with exponential decay)
        - Physics Digital Twin (calibrated Runge-Kutta 4th Order mass-balance ODE)
    Setting B: Offline Retrospective Gap Reconstruction
        - LOCF
        - Two-Sided Linear Interpolation (bridges past and future boundary points)
        - Physics Digital Twin

Also conducts parameter sensitivity analysis comparing calibrated twin (k=4.5)
against miscalibrated twin models (+/-15% parameter drift).

Generates:
    - results/tables/three_method_reconstruction.json
    - results/tables/three_method_reconstruction.csv
    - results/plots/three_method_gap_length_mae.png
    - results/plots/three_method_gap_length_rmse.png
    - results/plots/three_method_reconstruction_trajectories.png

Usage:
    python3 -m experiments.run_three_method_reconstruction
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import random
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from backend import config
from digital_twin.tank_twin import create_default_tanks, reconstruct_physics_based, PhysicalTankModel, TankGeometry
from digital_twin.reconstruction import (
    apply_mask,
    create_missing_mask,
    evaluate_reconstruction,
    linear_interpolation,
    linear_trend_causal,
    locf,
    run_gap_length_experiment,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.three_method_exp")

SEEDS = [42, 101, 2024]
TABLES_DIR = config.TABLES_DIR
PLOTS_DIR = config.PLOTS_DIR
DATA_SOURCE = "SIMULATED VALIDATION"


def generate_tank_ground_truth(
    duration_sec: float = 600.0,
    dt_sec: float = 5.0,
    regime: str = "dynamic_surge",
) -> tuple[list[float], list[float], dict]:
    """
    Generates an uncorrupted ground-truth water-level trajectory using calibrated tank physics.
    Supports regimes: 'dynamic_surge', 'drainage_drydown', 'steady_state'.
    """
    tanks = create_default_tanks()
    tank1 = tanks["tank_01"]
    n_steps = int(duration_sec / dt_sec)
    times = []
    levels = []

    if regime == "dynamic_surge":
        tank1.current_level_cm = 20.0
        for step in range(n_steps):
            t = step * dt_sec
            dynamic_q_in = max(5.0, 25.0 + 12.0 * math.sin(0.025 * t))
            tank1.step_rk4(dt_sec=dt_sec, q_in=dynamic_q_in)
            times.append(round(t, 1))
            levels.append(round(tank1.current_level_cm, 3))
    elif regime == "drainage_drydown":
        tank1.current_level_cm = 45.0
        for step in range(n_steps):
            t = step * dt_sec
            tank1.step_rk4(dt_sec=dt_sec, q_in=2.0)  # Low base inflow -> strong drainage
            times.append(round(t, 1))
            levels.append(round(tank1.current_level_cm, 3))
    else:  # steady_state
        tank1.current_level_cm = 30.0
        for step in range(n_steps):
            t = step * dt_sec
            tank1.step_rk4(dt_sec=dt_sec, q_in=24.65)  # Matches k*sqrt(30) equilibrium
            times.append(round(t, 1))
            levels.append(round(tank1.current_level_cm, 3))

    tank_params = {
        "area_cm2": tank1.geometry.area_cm2,
        "drainage_k": tank1.drainage_k,
        "q_in_cm3_s": 25.0,
        "max_height_cm": tank1.geometry.max_height_cm,
    }
    return times, levels, tank_params


def run_experiment() -> list[dict]:
    logger.info("Starting Multi-Method Missing-Data Reconstruction Benchmark")
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    dt_sec = 5.0
    times, ground_truth, tank_params = generate_tank_ground_truth(duration_sec=600.0, dt_sec=dt_sec, regime="dynamic_surge")
    logger.info("Generated primary ground truth: %d samples, dt=%.1fs", len(ground_truth), dt_sec)

    # 1. Gap Length Experiment: 3 (15s), 6 (30s), 12 (60s), 24 (120s) steps across multiple seeds
    gap_lengths = [3, 6, 12, 24]
    gap_records: list[dict] = []

    for seed in SEEDS:
        records = run_gap_length_experiment(
            ground_truth=ground_truth,
            gap_lengths=gap_lengths,
            seed=seed,
            dt_sec=dt_sec,
            tank_params=tank_params,
            data_source=DATA_SOURCE,
        )
        for r in records:
            r["seed"] = seed
            r["regime"] = "dynamic_surge"
            gap_records.append(r)

    # 2. Random Missing Rate Experiment: 5%, 10%, 20%, 30%
    rate_records: list[dict] = []
    rates = [0.05, 0.10, 0.20, 0.30]

    for rate in rates:
        mask = create_missing_mask(len(ground_truth), missing_rate=rate, seed=42)
        masked = apply_mask(ground_truth, mask)

        reconstructions = {
            ("LOCF", "Setting A & B (Past Only)"): locf(masked),
            ("Causal Linear Trend", "Setting A (Online Causal)"): linear_trend_causal(masked),
            ("Linear Interpolation", "Setting B (Offline Retrospective)"): linear_interpolation(masked),
            ("Physics Digital Twin", "Setting A & B (Model Guided)"): reconstruct_physics_based(
                masked, dt_sec, tank_params["area_cm2"], tank_params["drainage_k"],
                tank_params["q_in_cm3_s"], tank_params["max_height_cm"]
            ),
        }

        for (method_name, setting), recon_series in reconstructions.items():
            metrics = evaluate_reconstruction(ground_truth, recon_series, mask)
            rate_records.append({
                "method": method_name,
                "setting": setting,
                "missing_rate": rate,
                "missing_percentage": round(rate * 100.0, 1),
                "gap_length_steps": "distributed",
                "gap_duration_sec": "distributed",
                "sample_count": metrics["evaluated_points"],
                "MAE": metrics["mae"],
                "RMSE": metrics["rmse"],
                "max_error": metrics["max_error"],
                "seed": 42,
                "regime": "dynamic_surge",
                "data_source": DATA_SOURCE,
            })

    # 3. Model Parameter Mismatch Investigation (Physics Robustness)
    mismatch_records: list[dict] = []
    gap_len = 12  # 60-second gap
    mask_60s = [False] * len(ground_truth)
    for i in range(35, 35 + gap_len):
        mask_60s[i] = True
    masked_60s = apply_mask(ground_truth, mask_60s)

    k_calibrated = tank_params["drainage_k"]  # 4.5
    k_variations = {
        "Physics Twin (Calibrated k=4.5)": k_calibrated,
        "Physics Twin (Under-estimated k=3.82, -15%)": k_calibrated * 0.85,
        "Physics Twin (Over-estimated k=5.18, +15%)": k_calibrated * 1.15,
    }

    for label, k_val in k_variations.items():
        recon = reconstruct_physics_based(
            masked_60s, dt_sec, tank_params["area_cm2"], k_val,
            tank_params["q_in_cm3_s"], tank_params["max_height_cm"]
        )
        metrics = evaluate_reconstruction(ground_truth, recon, mask_60s)
        mismatch_records.append({
            "method": label,
            "setting": "Setting A & B (Model Guided)",
            "missing_rate": round(gap_len / len(ground_truth), 3),
            "missing_percentage": round(gap_len / len(ground_truth) * 100.0, 1),
            "gap_length_steps": gap_len,
            "gap_duration_sec": gap_len * dt_sec,
            "sample_count": metrics["evaluated_points"],
            "MAE": metrics["mae"],
            "RMSE": metrics["rmse"],
            "max_error": metrics["max_error"],
            "seed": 42,
            "regime": "dynamic_surge",
            "data_source": DATA_SOURCE,
        })

    all_records = gap_records + rate_records + mismatch_records

    # Save JSON table
    json_path = TABLES_DIR / "three_method_reconstruction.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": "CivicTwin-R Multi-Method Missing-Data Reconstruction Benchmark",
            "evaluated_at": "2026-10-25T12:00:00Z",
            "seeds_evaluated": SEEDS,
            "data_source": DATA_SOURCE,
            "tank_parameters": tank_params,
            "evaluation_settings": {
                "Setting A": "Online Causal Streaming (LOCF, Causal Linear Trend, Physics Twin) - zero future data leakage",
                "Setting B": "Offline Retrospective Gap Reconstruction (LOCF, Two-Sided Linear Interpolation, Physics Twin)"
            },
            "results": all_records,
        }, f, indent=2)
    logger.info("Saved JSON results to %s (%d records)", json_path, len(all_records))

    # Save CSV table
    csv_path = TABLES_DIR / "three_method_reconstruction.csv"
    fieldnames = [
        "method", "setting", "gap_length_steps", "gap_duration_sec", "missing_percentage",
        "sample_count", "MAE", "RMSE", "max_error", "seed", "regime", "data_source"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in all_records:
            writer.writerow(r)
    logger.info("Saved CSV results to %s", csv_path)

    # 4. Generate Publication Plots
    plot_mae_vs_gap_length(gap_records)
    plot_rmse_vs_gap_length(gap_records)
    plot_trajectory_overlay(times, ground_truth, dt_sec, tank_params)

    logger.info("Reconstruction benchmark completed successfully.")
    return all_records


def plot_mae_vs_gap_length(gap_records: list[dict]):
    """Plots reconstruction MAE (cm) vs Gap Length Duration across Setting A and Setting B."""
    methods = ["LOCF", "Causal Linear Trend", "Linear Interpolation", "Physics Digital Twin"]
    durations = [15.0, 30.0, 60.0, 120.0]

    # Aggregate across seeds
    mae_means = {m: [] for m in methods}
    for d in durations:
        for m in methods:
            matches = [r["MAE"] for r in gap_records if r["method"] == m and r.get("gap_duration_sec") == d]
            mae_means[m].append(float(np.mean(matches)) if matches else 0.0)

    plt.figure(figsize=(9.5, 5.5))
    colors = {
        "LOCF": "#d9534f",
        "Causal Linear Trend": "#9c27b0",
        "Linear Interpolation": "#f0ad4e",
        "Physics Digital Twin": "#0275d8",
    }
    markers = {
        "LOCF": "s",
        "Causal Linear Trend": "d",
        "Linear Interpolation": "^",
        "Physics Digital Twin": "o",
    }
    linestyles = {
        "LOCF": "--",
        "Causal Linear Trend": "-.",
        "Linear Interpolation": ":",
        "Physics Digital Twin": "-",
    }

    labels = {
        "LOCF": "LOCF [Setting A & B baseline]",
        "Causal Linear Trend": "Causal Linear Trend [Setting A: Online]",
        "Linear Interpolation": "Linear Interpolation [Setting B: Retrospective]",
        "Physics Digital Twin": "Physics Digital Twin [Setting A & B: Model Guided]",
    }

    for m in methods:
        plt.plot(
            durations,
            mae_means[m],
            label=labels[m],
            color=colors[m],
            marker=markers[m],
            linestyle=linestyles[m],
            linewidth=2.2,
            markersize=7.5,
        )

    plt.title(
        "CivicTwin-R — Missing-Data Reconstruction MAE vs. Gap Duration\n"
        "[SIMULATED VALIDATION: Multi-Seed Average, Tank Prototype]",
        fontsize=12,
        pad=12,
    )
    plt.xlabel("Missing Gap Duration (seconds)", fontsize=11)
    plt.ylabel("Mean Absolute Error (cm)", fontsize=11)
    plt.xticks(durations, ["15s (3 steps)", "30s (6 steps)", "60s (12 steps)", "120s (24 steps)"])
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend(frameon=True, facecolor="#f8f9fa", edgecolor="#cccccc", fontsize=9.5)
    plt.tight_layout()

    out_file = PLOTS_DIR / "three_method_gap_length_mae.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    logger.info("Saved MAE vs Gap Length plot to %s", out_file)


def plot_rmse_vs_gap_length(gap_records: list[dict]):
    """Plots reconstruction RMSE (cm) vs Gap Length Duration across Setting A and Setting B."""
    methods = ["LOCF", "Causal Linear Trend", "Linear Interpolation", "Physics Digital Twin"]
    durations = [15.0, 30.0, 60.0, 120.0]

    rmse_means = {m: [] for m in methods}
    for d in durations:
        for m in methods:
            matches = [r["RMSE"] for r in gap_records if r["method"] == m and r.get("gap_duration_sec") == d]
            rmse_means[m].append(float(np.mean(matches)) if matches else 0.0)

    plt.figure(figsize=(9.5, 5.5))
    colors = {
        "LOCF": "#d9534f",
        "Causal Linear Trend": "#9c27b0",
        "Linear Interpolation": "#f0ad4e",
        "Physics Digital Twin": "#0275d8",
    }
    markers = {
        "LOCF": "s",
        "Causal Linear Trend": "d",
        "Linear Interpolation": "^",
        "Physics Digital Twin": "o",
    }
    labels = {
        "LOCF": "LOCF [Setting A & B]",
        "Causal Linear Trend": "Causal Linear Trend [Setting A: Online]",
        "Linear Interpolation": "Linear Interpolation [Setting B: Retrospective]",
        "Physics Digital Twin": "Physics Digital Twin [Setting A & B: Model Guided]",
    }

    for m in methods:
        plt.plot(
            durations,
            rmse_means[m],
            label=labels[m],
            color=colors[m],
            marker=markers[m],
            linewidth=2.2,
            markersize=7.5,
        )

    plt.title(
        "CivicTwin-R — Missing-Data Reconstruction RMSE vs. Gap Duration\n"
        "[SIMULATED VALIDATION: Multi-Seed Average, Tank Prototype]",
        fontsize=12,
        pad=12,
    )
    plt.xlabel("Missing Gap Duration (seconds)", fontsize=11)
    plt.ylabel("Root Mean Square Error (cm)", fontsize=11)
    plt.xticks(durations, ["15s (3 steps)", "30s (6 steps)", "60s (12 steps)", "120s (24 steps)"])
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend(frameon=True, facecolor="#f8f9fa", edgecolor="#cccccc", fontsize=9.5)
    plt.tight_layout()

    out_file = PLOTS_DIR / "three_method_gap_length_rmse.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    logger.info("Saved RMSE vs Gap Length plot to %s", out_file)


def plot_trajectory_overlay(
    times: list[float],
    ground_truth: list[float],
    dt_sec: float,
    tank_params: dict,
):
    """Plots visual comparison of Ground Truth vs LOCF vs Causal vs Linear vs Physics Twin on a 60s gap."""
    length = len(ground_truth)
    mask = [False] * length
    start = 35
    gap_len = 12  # 60 seconds
    end = start + gap_len
    for i in range(start, end):
        mask[i] = True

    masked = apply_mask(ground_truth, mask)
    recon_locf = locf(masked)
    recon_causal = linear_trend_causal(masked)
    recon_linear = linear_interpolation(masked)
    recon_physics = reconstruct_physics_based(
        masked, dt_sec, tank_params["area_cm2"], tank_params["drainage_k"],
        tank_params["q_in_cm3_s"], tank_params["max_height_cm"]
    )

    w_start = max(0, start - 15)
    w_end = min(length, end + 15)
    t_win = times[w_start:w_end]
    gt_win = ground_truth[w_start:w_end]
    locf_win = recon_locf[w_start:w_end]
    causal_win = recon_causal[w_start:w_end]
    lin_win = recon_linear[w_start:w_end]
    phys_win = recon_physics[w_start:w_end]

    plt.figure(figsize=(10.5, 5.8))
    plt.plot(t_win, gt_win, label="Ground Truth (Uncorrupted)", color="#222222", linewidth=2.6, linestyle="-")
    plt.plot(t_win, locf_win, label="LOCF [Setting A & B]", color="#d9534f", linewidth=1.8, linestyle="--")
    plt.plot(t_win, causal_win, label="Causal Trend [Setting A: Online]", color="#9c27b0", linewidth=1.8, linestyle="-.")
    plt.plot(t_win, lin_win, label="Linear Interpolation [Setting B: Retrospective]", color="#f0ad4e", linewidth=1.8, linestyle=":")
    plt.plot(t_win, phys_win, label="Physics Digital Twin [Model Guided]", color="#0275d8", linewidth=2.2, linestyle="-")

    plt.axvspan(times[start], times[end - 1], color="#ffebee", alpha=0.55, label="Simulated Missing Gap (60s)")

    plt.title(
        "CivicTwin-R — Missing Interval Reconstruction Comparison (60s Gap)\n"
        "[SIMULATED VALIDATION: Setting A Online vs Setting B Retrospective]",
        fontsize=12,
        pad=12,
    )
    plt.xlabel("Simulation Elapsed Time (seconds)", fontsize=11)
    plt.ylabel("Water Level (cm)", fontsize=11)
    plt.grid(True, linestyle="--", alpha=0.6)
    plt.legend(loc="lower left", frameon=True, facecolor="#ffffff", edgecolor="#cccccc", fontsize=9.2)
    plt.tight_layout()

    out_file = PLOTS_DIR / "three_method_reconstruction_trajectories.png"
    plt.savefig(out_file, dpi=300)
    plt.close()
    logger.info("Saved Trajectory Overlay plot to %s", out_file)


if __name__ == "__main__":
    records = run_experiment()
    print("\n=== THREE-METHOD RECONSTRUCTION RESULTS SUMMARY ===")
    print(f"{'Method':<24} | {'Setting':<25} | {'Gap Dur':<9} | {'MAE (cm)':<8} | {'RMSE (cm)':<9}")
    print("-" * 85)
    for r in records[:16]:  # Print first 16 primary gap records
        dur = f"{r['gap_duration_sec']}s" if isinstance(r.get('gap_duration_sec'), (int, float)) else str(r.get('gap_duration_sec'))
        set_str = r.get('setting', 'N/A')[:25]
        print(f"{r['method']:<24} | {set_str:<25} | {dur:<9} | {r['MAE']:<8.4f} | {r['RMSE']:<9.4f}")
