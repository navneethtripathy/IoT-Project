"""
CivicTwin-R — Storage Abstraction Layer

Provides a unified interface for persisting and querying telemetry data.
Supports three backends:
  - SQLite  (default, zero-dependency local fallback)
  - InfluxDB 2.x (preferred for time-series at scale)
  - In-memory (for unit tests and quick demos)

The active backend is selected via STORAGE_BACKEND env var.
"""

from __future__ import annotations

import abc
import csv
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.models import IngestedTelemetry, DataSource, SensorStatus

logger = logging.getLogger("civictwin.storage")


# ── Abstract Interface ───────────────────────────────────

class StorageBackend(abc.ABC):
    """Abstract base for all storage backends."""

    @abc.abstractmethod
    def store(self, record: IngestedTelemetry) -> bool:
        """Store a single telemetry record. Returns True on success."""

    @abc.abstractmethod
    def query_latest(self, zone_id: str, limit: int = 1) -> list[dict]:
        """Return the most recent records for a zone."""

    @abc.abstractmethod
    def query_range(
        self,
        zone_id: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[dict]:
        """Return records within a time range for a zone."""

    @abc.abstractmethod
    def query_all_latest(self, limit_per_zone: int = 1) -> dict[str, list[dict]]:
        """Return latest records for every zone."""

    @abc.abstractmethod
    def export_csv(self, path: Path, zone_id: Optional[str] = None) -> int:
        """Export records to CSV. Returns row count."""

    @abc.abstractmethod
    def count(self, zone_id: Optional[str] = None) -> int:
        """Count stored records."""

    def close(self):
        """Clean up resources."""
        pass


# ── SQLite Backend ───────────────────────────────────────

class SQLiteStorage(StorageBackend):
    """SQLite-based storage — reliable local fallback requiring no external service."""

    _CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        zone_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        event_timestamp TEXT NOT NULL,
        ingestion_timestamp TEXT NOT NULL,
        distance_cm REAL,
        water_level_cm REAL,
        water_level_pct REAL,
        sensor_status TEXT NOT NULL,
        source TEXT NOT NULL,
        is_reconstructed INTEGER DEFAULT 0,
        reconstruction_method TEXT,
        scenario_id TEXT,
        quality_flags TEXT DEFAULT '[]',
        UNIQUE(device_id, sequence)
    );
    """

    _CREATE_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_telemetry_zone_time
        ON telemetry(zone_id, event_timestamp);
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(self._CREATE_TABLE)
        self._conn.execute(self._CREATE_INDEX)
        self._conn.commit()
        logger.info("SQLite storage initialized: %s", db_path)

    def store(self, record: IngestedTelemetry) -> bool:
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT OR IGNORE INTO telemetry
                       (device_id, zone_id, sequence, event_timestamp,
                        ingestion_timestamp, distance_cm, water_level_cm,
                        water_level_pct, sensor_status, source,
                        is_reconstructed, reconstruction_method,
                        scenario_id, quality_flags)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record.device_id,
                        record.zone_id,
                        record.sequence,
                        record.timestamp.isoformat(),
                        record.ingestion_timestamp.isoformat(),
                        record.distance_cm,
                        record.water_level_cm,
                        record.water_level_pct,
                        record.sensor_status.value,
                        record.source.value,
                        1 if record.is_reconstructed else 0,
                        record.reconstruction_method,
                        record.scenario_id,
                        json.dumps(record.quality_flags),
                    ),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                logger.debug("Duplicate record: %s seq=%d", record.device_id, record.sequence)
                return False
            except Exception:
                logger.exception("Failed to store record")
                return False

    def _rows_to_dicts(self, rows) -> list[dict]:
        return [dict(r) for r in rows]

    def query_latest(self, zone_id: str, limit: int = 1) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT * FROM telemetry WHERE zone_id = ?
                   ORDER BY event_timestamp DESC LIMIT ?""",
                (zone_id, limit),
            )
            return self._rows_to_dicts(cur.fetchall())

    def query_range(
        self, zone_id: str, start: datetime, end: datetime, limit: int = 1000
    ) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT * FROM telemetry
                   WHERE zone_id = ? AND event_timestamp >= ? AND event_timestamp <= ?
                   ORDER BY event_timestamp ASC LIMIT ?""",
                (zone_id, start.isoformat(), end.isoformat(), limit),
            )
            return self._rows_to_dicts(cur.fetchall())

    def query_all_latest(self, limit_per_zone: int = 1) -> dict[str, list[dict]]:
        with self._lock:
            cur = self._conn.execute("SELECT DISTINCT zone_id FROM telemetry")
            zones = [r["zone_id"] for r in cur.fetchall()]
        result = {}
        for z in zones:
            result[z] = self.query_latest(z, limit_per_zone)
        return result

    def export_csv(self, path: Path, zone_id: Optional[str] = None) -> int:
        with self._lock:
            if zone_id:
                cur = self._conn.execute(
                    "SELECT * FROM telemetry WHERE zone_id = ? ORDER BY event_timestamp",
                    (zone_id,),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM telemetry ORDER BY event_timestamp"
                )
            rows = cur.fetchall()

        if not rows:
            return 0

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            for r in rows:
                writer.writerow(tuple(r))
        return len(rows)

    def count(self, zone_id: Optional[str] = None) -> int:
        with self._lock:
            if zone_id:
                cur = self._conn.execute(
                    "SELECT COUNT(*) as c FROM telemetry WHERE zone_id = ?",
                    (zone_id,),
                )
            else:
                cur = self._conn.execute("SELECT COUNT(*) as c FROM telemetry")
            return cur.fetchone()["c"]

    def close(self):
        self._conn.close()


# ── In-Memory Backend ────────────────────────────────────

class MemoryStorage(StorageBackend):
    """In-memory storage for testing and quick demos. Data is lost on restart."""

    def __init__(self):
        self._records: list[IngestedTelemetry] = []
        self._seen: set[tuple[str, int]] = set()
        self._lock = threading.Lock()
        logger.info("In-memory storage initialized")

    def store(self, record: IngestedTelemetry) -> bool:
        key = (record.device_id, record.sequence)
        with self._lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            self._records.append(record)
        return True

    def _to_dict(self, r: IngestedTelemetry) -> dict:
        return r.model_dump(mode="json")

    def query_latest(self, zone_id: str, limit: int = 1) -> list[dict]:
        with self._lock:
            matched = [r for r in self._records if r.zone_id == zone_id]
            matched.sort(key=lambda r: r.timestamp, reverse=True)
            return [self._to_dict(r) for r in matched[:limit]]

    def query_range(
        self, zone_id: str, start: datetime, end: datetime, limit: int = 1000
    ) -> list[dict]:
        with self._lock:
            matched = [
                r for r in self._records
                if r.zone_id == zone_id and start <= r.timestamp <= end
            ]
            matched.sort(key=lambda r: r.timestamp)
            return [self._to_dict(r) for r in matched[:limit]]

    def query_all_latest(self, limit_per_zone: int = 1) -> dict[str, list[dict]]:
        zones = {r.zone_id for r in self._records}
        return {z: self.query_latest(z, limit_per_zone) for z in zones}

    def export_csv(self, path: Path, zone_id: Optional[str] = None) -> int:
        with self._lock:
            if zone_id:
                records = [r for r in self._records if r.zone_id == zone_id]
            else:
                records = list(self._records)

        if not records:
            return 0

        path.parent.mkdir(parents=True, exist_ok=True)
        data = [r.model_dump(mode="json") for r in records]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return len(data)

    def count(self, zone_id: Optional[str] = None) -> int:
        with self._lock:
            if zone_id:
                return sum(1 for r in self._records if r.zone_id == zone_id)
            return len(self._records)


# ── Factory ──────────────────────────────────────────────

def create_storage(backend: Optional[str] = None) -> StorageBackend:
    """Create the appropriate storage backend based on configuration."""
    from backend import config

    backend = backend or config.STORAGE_BACKEND

    if backend == "sqlite":
        return SQLiteStorage(config.SQLITE_DB_PATH)
    elif backend == "memory":
        return MemoryStorage()
    elif backend == "influxdb":
        if not config.INFLUXDB_ENABLED:
            logger.warning(
                "InfluxDB selected but INFLUXDB_ENABLED=false; falling back to SQLite"
            )
            return SQLiteStorage(config.SQLITE_DB_PATH)
        try:
            from backend.storage_influx import InfluxDBStorage
            return InfluxDBStorage()
        except ImportError:
            logger.warning("influxdb-client not available; falling back to SQLite")
            return SQLiteStorage(config.SQLITE_DB_PATH)
        except Exception as e:
            logger.warning("InfluxDB connection failed (%s); falling back to SQLite", e)
            return SQLiteStorage(config.SQLITE_DB_PATH)
    else:
        logger.warning("Unknown storage backend '%s'; using memory", backend)
        return MemoryStorage()
