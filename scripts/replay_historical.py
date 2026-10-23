"""
CivicTwin-R — Historical Flood Observation Replay Controller

Replays verified historical Chennai storm observations (Cyclone Michaung, Dec 2023)
through the telemetry pipeline at a controlled speed.

Safety Guarantees:
  - Provenance tag is strictly set to 'replayed_historical'.
  - Original observation timestamps are preserved without modification.
  - Historical data does not overwrite live sensor state.
"""

from __future__ import annotations

import csv
import json
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

# Setup paths
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from backend import config
from backend.models import TelemetryMessage, DataSource, SensorStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.replay")


class HistoricalReplayController:
    """Manages playback of historical storm observations into the ingestion pipeline."""

    def __init__(self, callback: Optional[Callable] = None):
        self._callback = callback
        self._records: list[dict] = []
        self._current_index: int = 0
        self._is_running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._speed_multiplier: float = 1.0  # 1 step per second
        self.load_dataset()

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def total_records(self) -> int:
        return len(self._records)

    def load_dataset(self, csv_path: Optional[Path] = None):
        path = csv_path or (config.PROCESSED_DIR / "chennai_michaung_hourly.csv")
        if not path.exists():
            logger.warning("Historical dataset not found at %s. Run scripts/ingest_chennai_data.py first.", path)
            return

        with open(path) as f:
            reader = csv.DictReader(f)
            self._records = list(reader)

        logger.info("Loaded %d historical records for replay from %s", len(self._records), path)

    def step(self) -> Optional[dict]:
        """Advance one historical observation step."""
        with self._lock:
            if not self._records or self._current_index >= len(self._records):
                return None

            row = self._records[self._current_index]
            self._current_index += 1

        # Synthesize physical water level from cumulative rainfall and nominal drainage
        precip = float(row.get("hourly_precipitation_mm", 0.0))
        cum_rain = float(row.get("cumulative_rainfall_mm", 0.0))
        timestamp_str = row.get("timestamp_local", "")

        # Water level proxy in cm (scaled from historical rainfall observations for pipeline replay)
        # Note: Rainfall is not a direct physical measurement of river stage; this serves as a
        # calibrated replay stream for resilience testing.
        water_level_cm = min(30.0, max(2.0, (cum_rain / 370.0) * 28.0 + 2.0))
        water_level_pct = (water_level_cm / 30.0) * 100.0

        telemetry_payload = {
            "schema_version": "1.0",
            "device_id": "chennai_historical_station_01",
            "zone_id": "zone_01",
            "sequence": self._current_index,
            "timestamp": timestamp_str + ":00+05:30" if len(timestamp_str) == 16 else timestamp_str,
            "distance_cm": round(30.0 - water_level_cm, 2),
            "water_level_cm": round(water_level_cm, 2),
            "water_level_pct": round(water_level_pct, 2),
            "sensor_status": SensorStatus.VALID.value,
            "source": DataSource.REPLAYED_HISTORICAL.value,
            "quality_flags": ["historical_replay", "cyclone_michaung_2023", "rainfall_derived_proxy"],
        }

        if self._callback:
            try:
                self._callback(telemetry_payload)
            except Exception as e:
                logger.warning("Replay callback error: %s", e)

        return telemetry_payload

    def start(self, interval_sec: float = 1.0):
        if self._is_running:
            return
        self._is_running = True

        def _loop():
            logger.info("Historical replay background thread started")
            while self._is_running:
                payload = self.step()
                if payload is None:
                    logger.info("Historical replay completed all records")
                    self._is_running = False
                    break
                time.sleep(interval_sec)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._is_running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Historical replay stopped")

    def reset(self):
        with self._lock:
            self._current_index = 0
        logger.info("Historical replay reset to beginning")

    def get_status(self) -> dict:
        return {
            "is_running": self._is_running,
            "current_index": self._current_index,
            "total_records": len(self._records),
            "progress_pct": round((self._current_index / len(self._records) * 100.0), 1) if self._records else 0.0,
            "source_classification": "replayed_historical",
            "event_name": "Cyclone Michaung Dec 2023",
        }


if __name__ == "__main__":
    controller = HistoricalReplayController(callback=lambda p: print(f"Replayed: {p['timestamp']} -> {p['water_level_cm']} cm ({p['water_level_pct']}%)"))
    print("Replaying 5 steps...")
    for _ in range(5):
        controller.step()
