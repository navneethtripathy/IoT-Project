#!/usr/bin/env python3
"""
CivicTwin-R — Demo Data Generator

Generates a complete sample dataset from the digital twin engine
without requiring MQTT, InfluxDB, or any external service.

Output: data/generated/demo_dataset.csv and demo_dataset.json
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulator import create_demo_dataset
from backend import config


def main():
    print("╔══════════════════════════════════════════╗")
    print("║  CivicTwin-R — Demo Data Generator       ║")
    print("╚══════════════════════════════════════════╝")

    output_dir = config.GENERATED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    data = create_demo_dataset(steps=300, seed=config.RANDOM_SEED)
    print(f"Generated {len(data)} telemetry messages over 300 steps")

    # Save JSON
    json_path = output_dir / "demo_dataset.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved: {json_path}")

    # Save CSV
    csv_path = output_dir / "demo_dataset.csv"
    if data:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"Saved: {csv_path}")

    print("Done.")


if __name__ == "__main__":
    main()
