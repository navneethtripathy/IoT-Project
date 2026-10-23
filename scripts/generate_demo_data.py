#!/usr/bin/env python3
"""
CivicTwin-R — Demo Data Generator

Generates a deterministically seeded sample dataset from the digital twin engine.
Saves outputs to data/generated/demo_dataset.csv and demo_dataset.json.
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.simulator import create_demo_dataset
from backend import config


def main():
    print("Generating CivicTwin-R demo dataset...")

    output_dir = config.GENERATED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    data = create_demo_dataset(steps=300, seed=config.RANDOM_SEED)
    print(f"Generated {len(data)} telemetry records over 300 simulation steps.")

    json_path = output_dir / "demo_dataset.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"JSON export: {json_path}")

    csv_path = output_dir / "demo_dataset.csv"
    if data:
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        print(f"CSV export:  {csv_path}")

    print("Generation complete.")


if __name__ == "__main__":
    main()
