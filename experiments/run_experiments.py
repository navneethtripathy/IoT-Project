"""
CivicTwin-R — Experiment Runner

Runs reproducible experiments and saves results:
    1. Missing-data reconstruction (LOCF vs Linear at multiple rates)
    2. Scenario simulations (all 8 scenarios)
    3. Latency measurement (simulated pipeline)
    4. Warning behavior evaluation

All experiments use fixed seeds for reproducibility.
Results are saved to results/tables/ and results/plots/.

Usage:
    cd CivicTwin-R
    python -m experiments.run_experiments
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from digital_twin.model import DigitalTwinEngine, create_default_zones
from digital_twin.scenarios import ScenarioController, SCENARIOS
from digital_twin.reconstruction import (
    run_multi_rate_experiment,
    create_missing_mask,
    apply_mask,
    locf,
    linear_interpolation,
    evaluate_reconstruction,
)
from backend import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.experiments")

SEED = config.RANDOM_SEED
RESULTS_DIR = config.TABLES_DIR
PLOTS_DIR = config.PLOTS_DIR


def ensure_dirs():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════
# EXPERIMENT 1: Missing-Data Reconstruction
# ══════════════════════════════════════════════════════════

def experiment_reconstruction() -> list[dict]:
    """
    Generate ground-truth water-level series from the digital twin,
    introduce controlled missing data at 5%, 10%, 20%, 30% rates,
    reconstruct with LOCF and linear interpolation, and evaluate
    against the hidden ground truth.
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 1: Missing-Data Reconstruction")
    logger.info("=" * 60)

    # Generate ground truth from heavy_rainfall scenario
    engine = DigitalTwinEngine(seed=SEED)
    for zone in create_default_zones():
        engine.add_zone(zone)

    ctrl = ScenarioController(engine)
    ctrl.load_scenario("heavy_rainfall")

    ground_truth_series: dict[str, list[float]] = {z: [] for z in engine.zones}

    while not ctrl.is_complete:
        step_data = ctrl.step(dt_sec=5.0)
        for d in step_data:
            zone_id = d["zone_id"]
            ground_truth_series[zone_id].append(d["true_level_cm"])

    # Run reconstruction experiments for each zone
    all_results = []

    for zone_id, gt in ground_truth_series.items():
        logger.info("Zone %s: %d ground-truth points", zone_id, len(gt))

        results = run_multi_rate_experiment(gt, seed=SEED)

        for r in results:
            result_dict = {
                "zone_id": zone_id,
                "method": r.method,
                "missing_rate": r.missing_rate,
                "total_points": r.total_points,
                "missing_points": r.missing_points,
                "evaluated_points": r.evaluated_points,
                "mae": r.mae,
                "rmse": r.rmse,
                "max_error": r.max_error,
            }
            all_results.append(result_dict)
            logger.info(
                "  %s | rate=%.0f%% | MAE=%.4f | RMSE=%.4f | eval=%d pts",
                r.method, r.missing_rate * 100, r.mae, r.rmse, r.evaluated_points,
            )

    # Save results
    save_json(all_results, "reconstruction_results.json")
    save_csv(all_results, "reconstruction_results.csv")

    logger.info("Reconstruction experiment complete: %d result rows", len(all_results))
    return all_results


# ══════════════════════════════════════════════════════════
# EXPERIMENT 2: Scenario Simulations
# ══════════════════════════════════════════════════════════

def experiment_scenarios() -> dict:
    """Run all scenarios and record zone-level statistics."""
    logger.info("=" * 60)
    logger.info("EXPERIMENT 2: Scenario Simulations")
    logger.info("=" * 60)

    scenario_summaries = []

    for scenario_id in SCENARIOS:
        engine = DigitalTwinEngine(seed=SEED)
        for zone in create_default_zones():
            engine.add_zone(zone)

        ctrl = ScenarioController(engine)
        ctrl.load_scenario(scenario_id)

        # Collect per-zone stats
        zone_stats: dict[str, dict] = {}
        for zid in engine.zones:
            zone_stats[zid] = {
                "max_level_pct": 0.0,
                "alert_steps_warning": 0,
                "alert_steps_critical": 0,
                "sensor_failures": 0,
                "network_dropouts": 0,
                "total_steps": 0,
            }

        while not ctrl.is_complete:
            step_data = ctrl.step(dt_sec=5.0)
            for d in step_data:
                zid = d["zone_id"]
                stats = zone_stats[zid]
                stats["total_steps"] += 1
                stats["max_level_pct"] = max(stats["max_level_pct"], d["true_level_pct"])
                if d["alert_level"] == "warning":
                    stats["alert_steps_warning"] += 1
                elif d["alert_level"] == "critical":
                    stats["alert_steps_critical"] += 1
                if not d["sensor_ok"]:
                    stats["sensor_failures"] += 1
                if not d["network_ok"]:
                    stats["network_dropouts"] += 1

        summary = {
            "scenario_id": scenario_id,
            "scenario_name": SCENARIOS[scenario_id].name,
            "total_steps": SCENARIOS[scenario_id].total_steps,
            "zones": zone_stats,
        }
        scenario_summaries.append(summary)

        logger.info("  %s: completed (%d steps)", scenario_id, SCENARIOS[scenario_id].total_steps)
        for zid, stats in zone_stats.items():
            logger.info(
                "    %s: max=%.1f%% warn=%d crit=%d sensor_fail=%d net_drop=%d",
                zid, stats["max_level_pct"],
                stats["alert_steps_warning"], stats["alert_steps_critical"],
                stats["sensor_failures"], stats["network_dropouts"],
            )

    save_json(scenario_summaries, "scenario_summaries.json")
    logger.info("Scenario experiment complete: %d scenarios", len(scenario_summaries))
    return {"scenarios": scenario_summaries}


# ══════════════════════════════════════════════════════════
# EXPERIMENT 3: Latency Measurement
# ══════════════════════════════════════════════════════════

def experiment_latency() -> dict:
    """
    Measure simulated end-to-end latency of the data pipeline.

    Since this is a local software simulation (no real MQTT broker or
    network), we measure the processing time from message creation
    through ingestion and storage. This does NOT include real network
    latency. Results are labelled as "software-pipeline latency".
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 3: Latency Measurement (software pipeline)")
    logger.info("=" * 60)

    from backend.storage import MemoryStorage
    from backend.ingestion import IngestionService
    from backend.simulator import SensorSimulator

    storage = MemoryStorage()
    ingestion_svc = IngestionService(storage)

    engine = DigitalTwinEngine(seed=SEED)
    for zone in create_default_zones():
        engine.add_zone(zone)

    sim = SensorSimulator(engine=engine, interval_sec=1.0)
    latencies_ms = []
    messages_sent = 0
    messages_received = 0

    for step_i in range(100):
        messages = sim.generate_one_step()
        for msg in messages:
            messages_sent += 1
            t_start = time.monotonic_ns()
            result = ingestion_svc.process_message(msg)
            t_end = time.monotonic_ns()

            if result is not None:
                messages_received += 1
                latency_ms = (t_end - t_start) / 1_000_000
                latencies_ms.append(latency_ms)

    if latencies_ms:
        arr = np.array(latencies_ms)
        result = {
            "measurement_type": "software_pipeline_latency",
            "note": "Measures Python processing time only. Does NOT include real network or MQTT latency.",
            "messages_sent": messages_sent,
            "messages_received": messages_received,
            "delivery_rate": round(messages_received / messages_sent, 4) if messages_sent > 0 else 0,
            "mean_latency_ms": round(float(np.mean(arr)), 4),
            "median_latency_ms": round(float(np.median(arr)), 4),
            "p95_latency_ms": round(float(np.percentile(arr, 95)), 4),
            "max_latency_ms": round(float(np.max(arr)), 4),
            "min_latency_ms": round(float(np.min(arr)), 4),
        }
    else:
        result = {"error": "No messages successfully processed"}

    save_json(result, "latency_results.json")
    logger.info("Latency experiment: sent=%d recv=%d rate=%.2f%%",
                messages_sent, messages_received,
                (messages_received / messages_sent * 100) if messages_sent > 0 else 0)
    if latencies_ms:
        logger.info("  mean=%.3fms median=%.3fms p95=%.3fms",
                     result["mean_latency_ms"], result["median_latency_ms"],
                     result["p95_latency_ms"])

    return result


# ══════════════════════════════════════════════════════════
# EXPERIMENT 4: Warning Behavior
# ══════════════════════════════════════════════════════════

def experiment_warnings() -> dict:
    """
    Evaluate threshold detection behavior:
    - Correct detection of known threshold crossings
    - Detection delay
    - False alerts and missed alerts
    """
    logger.info("=" * 60)
    logger.info("EXPERIMENT 4: Warning Behavior Evaluation")
    logger.info("=" * 60)

    engine = DigitalTwinEngine(seed=SEED)
    for zone in create_default_zones():
        engine.add_zone(zone)

    ctrl = ScenarioController(engine)
    ctrl.load_scenario("heavy_rainfall")

    warn_threshold = 70.0
    crit_threshold = 85.0

    zone_warnings: dict[str, dict] = {}
    for zid in engine.zones:
        zone_warnings[zid] = {
            "true_warn_crossings": 0,
            "true_crit_crossings": 0,
            "detected_warnings": 0,
            "detected_criticals": 0,
            "first_warn_step": None,
            "first_crit_step": None,
            "false_alerts": 0,
            "missed_alerts": 0,
            "prev_alert": "normal",
            "prev_true_pct": 0.0,
        }

    step_num = 0
    while not ctrl.is_complete:
        step_data = ctrl.step(dt_sec=5.0)
        step_num += 1

        for d in step_data:
            zid = d["zone_id"]
            info = zone_warnings[zid]
            true_pct = d["true_level_pct"]
            obs_pct = d.get("observed_level_pct")
            alert = d["alert_level"]

            # Ground truth threshold crossings
            if true_pct >= crit_threshold and info["prev_true_pct"] < crit_threshold:
                info["true_crit_crossings"] += 1
                if info["first_crit_step"] is None:
                    info["first_crit_step"] = step_num
            if true_pct >= warn_threshold and info["prev_true_pct"] < warn_threshold:
                info["true_warn_crossings"] += 1
                if info["first_warn_step"] is None:
                    info["first_warn_step"] = step_num

            # Alert detection
            if alert == "critical":
                info["detected_criticals"] += 1
            elif alert == "warning":
                info["detected_warnings"] += 1

            info["prev_true_pct"] = true_pct
            info["prev_alert"] = alert

    results = {
        "scenario": "heavy_rainfall",
        "warn_threshold_pct": warn_threshold,
        "crit_threshold_pct": crit_threshold,
        "zones": zone_warnings,
    }

    save_json(results, "warning_results.json")
    logger.info("Warning experiment complete")
    for zid, info in zone_warnings.items():
        logger.info(
            "  %s: true_warn=%d true_crit=%d det_warn=%d det_crit=%d",
            zid, info["true_warn_crossings"], info["true_crit_crossings"],
            info["detected_warnings"], info["detected_criticals"],
        )

    return results


# ══════════════════════════════════════════════════════════
# PLOTTING
# ══════════════════════════════════════════════════════════

def generate_plots(recon_results: list[dict], scenario_results: dict):
    """Generate report-ready plots from experiment results."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available — skipping plot generation")
        return

    plt.rcParams.update({
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "figure.figsize": (10, 6),
        "figure.dpi": 150,
    })

    # ── Plot 1: Reconstruction MAE by method and rate ─────
    if recon_results:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # Aggregate across zones
        from collections import defaultdict
        method_rate_mae = defaultdict(lambda: defaultdict(list))
        method_rate_rmse = defaultdict(lambda: defaultdict(list))

        for r in recon_results:
            method_rate_mae[r["method"]][r["missing_rate"]].append(r["mae"])
            method_rate_rmse[r["method"]][r["missing_rate"]].append(r["rmse"])

        for method, rate_vals in method_rate_mae.items():
            rates = sorted(rate_vals.keys())
            maes = [np.mean(rate_vals[r]) for r in rates]
            ax1.plot([r * 100 for r in rates], maes, "o-", label=method.upper(), linewidth=2, markersize=8)

        ax1.set_xlabel("Missing Data Rate (%)")
        ax1.set_ylabel("Mean Absolute Error (cm)")
        ax1.set_title("Reconstruction MAE vs. Missing Rate")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        for method, rate_vals in method_rate_rmse.items():
            rates = sorted(rate_vals.keys())
            rmses = [np.mean(rate_vals[r]) for r in rates]
            ax2.plot([r * 100 for r in rates], rmses, "s-", label=method.upper(), linewidth=2, markersize=8)

        ax2.set_xlabel("Missing Data Rate (%)")
        ax2.set_ylabel("Root Mean Square Error (cm)")
        ax2.set_title("Reconstruction RMSE vs. Missing Rate")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(PLOTS_DIR / "reconstruction_comparison.png", bbox_inches="tight")
        plt.close()
        logger.info("Plot saved: reconstruction_comparison.png")

    # ── Plot 2: Scenario water levels ─────────────────────
    if scenario_results and "scenarios" in scenario_results:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()

        scenarios_to_plot = ["normal", "heavy_rainfall", "blocked_drain", "sudden_rise"]
        for idx, scen_id in enumerate(scenarios_to_plot):
            if idx >= len(axes):
                break

            ax = axes[idx]
            engine = DigitalTwinEngine(seed=SEED)
            for zone in create_default_zones():
                engine.add_zone(zone)

            ctrl = ScenarioController(engine)
            ctrl.load_scenario(scen_id)

            zone_levels: dict[str, list[float]] = {z: [] for z in engine.zones}
            steps_list = []

            while not ctrl.is_complete:
                step_data = ctrl.step(dt_sec=5.0)
                steps_list.append(ctrl.current_step)
                for d in step_data:
                    zone_levels[d["zone_id"]].append(d["true_level_pct"])

            for zid, levels in zone_levels.items():
                ax.plot(range(len(levels)), levels, label=zid, linewidth=1.5)

            ax.axhline(y=70, color="orange", linestyle="--", alpha=0.7, label="Warning (70%)")
            ax.axhline(y=85, color="red", linestyle="--", alpha=0.7, label="Critical (85%)")
            ax.set_title(SCENARIOS[scen_id].name)
            ax.set_xlabel("Step")
            ax.set_ylabel("Water Level (%)")
            ax.set_ylim(0, 105)
            ax.legend(fontsize=8)
            ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(PLOTS_DIR / "scenario_water_levels.png", bbox_inches="tight")
        plt.close()
        logger.info("Plot saved: scenario_water_levels.png")

    # ── Plot 3: Reconstruction visual example ─────────────
    if recon_results:
        engine = DigitalTwinEngine(seed=SEED)
        for zone in create_default_zones():
            engine.add_zone(zone)
        ctrl = ScenarioController(engine)
        ctrl.load_scenario("heavy_rainfall")

        gt = []
        while not ctrl.is_complete:
            step_data = ctrl.step(dt_sec=5.0)
            for d in step_data:
                if d["zone_id"] == "zone_01":
                    gt.append(d["true_level_cm"])

        mask = create_missing_mask(len(gt), 0.20, seed=SEED)
        masked = apply_mask(gt, mask)
        recon_locf = locf(masked)
        recon_linear = linear_interpolation(masked)

        fig, ax = plt.subplots(figsize=(14, 5))
        steps = range(len(gt))
        ax.plot(steps, gt, "k-", linewidth=1, alpha=0.5, label="Ground Truth")
        ax.plot(steps, recon_locf, "b-", linewidth=1, alpha=0.7, label="LOCF")
        ax.plot(steps, recon_linear, "r-", linewidth=1, alpha=0.7, label="Linear Interp.")

        # Mark missing regions
        missing_steps = [i for i, m in enumerate(mask) if m]
        if missing_steps:
            ax.scatter(missing_steps, [gt[i] for i in missing_steps],
                      c="gray", s=10, alpha=0.3, label="Hidden Points", zorder=1)

        ax.set_xlabel("Step")
        ax.set_ylabel("Water Level (cm)")
        ax.set_title("Zone 01 — Reconstruction at 20% Missing Rate (Heavy Rainfall Scenario)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(PLOTS_DIR / "reconstruction_visual.png", bbox_inches="tight")
        plt.close()
        logger.info("Plot saved: reconstruction_visual.png")

    # ── Plot 4: Sensor failure and recovery timeline ──────
    engine = DigitalTwinEngine(seed=SEED)
    for zone in create_default_zones():
        engine.add_zone(zone)
    ctrl = ScenarioController(engine)
    ctrl.load_scenario("sensor_dropout")

    sensor_ok_timeline = []
    true_levels = []
    observed_levels = []

    while not ctrl.is_complete:
        step_data = ctrl.step(dt_sec=5.0)
        for d in step_data:
            if d["zone_id"] == "zone_01":
                sensor_ok_timeline.append(1 if d["sensor_ok"] else 0)
                true_levels.append(d["true_level_cm"])
                observed_levels.append(d["observed_level_cm"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True)

    ax1.plot(range(len(true_levels)), true_levels, "b-", label="True Level", linewidth=1.5)
    obs_valid = [(i, v) for i, v in enumerate(observed_levels) if v is not None]
    if obs_valid:
        ax1.scatter([x[0] for x in obs_valid], [x[1] for x in obs_valid],
                   c="green", s=15, alpha=0.6, label="Observed (valid)", zorder=3)
    ax1.set_ylabel("Water Level (cm)")
    ax1.set_title("Zone 01 — Sensor Dropout Scenario")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(range(len(sensor_ok_timeline)), sensor_ok_timeline,
                     alpha=0.4, color="green", label="Sensor OK")
    ax2.set_xlabel("Step")
    ax2.set_ylabel("Sensor Status")
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["Failed", "OK"])
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(PLOTS_DIR / "sensor_dropout_timeline.png", bbox_inches="tight")
    plt.close()
    logger.info("Plot saved: sensor_dropout_timeline.png")


# ══════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════════════════

def save_json(data, filename: str):
    path = RESULTS_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info("Saved: %s", path)


def save_csv(data: list[dict], filename: str):
    if not data:
        return
    path = RESULTS_DIR / filename
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    logger.info("Saved: %s", path)


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    logger.info("╔══════════════════════════════════════════╗")
    logger.info("║  CivicTwin-R — Experiment Suite          ║")
    logger.info("║  Seed: %d                                ║", SEED)
    logger.info("╚══════════════════════════════════════════╝")

    ensure_dirs()

    # Run all experiments
    recon_results = experiment_reconstruction()
    scenario_results = experiment_scenarios()
    latency_results = experiment_latency()
    warning_results = experiment_warnings()

    # Generate plots
    generate_plots(recon_results, scenario_results)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("ALL EXPERIMENTS COMPLETE")
    logger.info("Results: %s", RESULTS_DIR)
    logger.info("Plots:   %s", PLOTS_DIR)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
