"""
CivicTwin-R — Storage Abstraction Layer

Provides a unified interface for persisting and querying telemetry data.
Supports SQLite, InfluxDB 2.x, and in-memory storage.
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

from backend.models import IngestedTelemetry

logger = logging.getLogger("civictwin.storage")


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

    @property
    def backend_type(self) -> str:
        """Name of the active storage engine."""
        return "abstract"

    @property
    def is_fallback(self) -> bool:
        """True if operating as an automatic fallback."""
        return False

    def close(self):
        """Clean up resources."""
        pass


class SQLiteStorage(StorageBackend):
    """SQLite-based storage implementation."""

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

    def __init__(self, db_path: str, is_fallback: bool = False):
        self._db_path = db_path
        self._is_fallback = is_fallback
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(self._CREATE_TABLE)
        self._conn.execute(self._CREATE_INDEX)
        self._conn.commit()
        logger.info("SQLite storage initialized at: %s (fallback=%s)", db_path, is_fallback)

    @property
    def backend_type(self) -> str:
        return "sqlite"

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

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
        self,
        zone_id: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
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
            cur = self._conn.execute(
                """SELECT DISTINCT zone_id FROM telemetry"""
            )
            zones = [row["zone_id"] for row in cur.fetchall()]
            result = {}
            for zid in zones:
                c2 = self._conn.execute(
                    """SELECT * FROM telemetry WHERE zone_id = ?
                       ORDER BY event_timestamp DESC LIMIT ?""",
                    (zid, limit_per_zone),
                )
                result[zid] = self._rows_to_dicts(c2.fetchall())
            return result

    def export_csv(self, path: Path, zone_id: Optional[str] = None) -> int:
        with self._lock:
            if zone_id:
                cur = self._conn.execute(
                    "SELECT * FROM telemetry WHERE zone_id = ? ORDER BY event_timestamp ASC",
                    (zone_id,),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM telemetry ORDER BY event_timestamp ASC"
                )
            rows = self._rows_to_dicts(cur.fetchall())

        if not rows:
            return 0

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def count(self, zone_id: Optional[str] = None) -> int:
        with self._lock:
            if zone_id:
                cur = self._conn.execute(
                    "SELECT COUNT(*) FROM telemetry WHERE zone_id = ?",
                    (zone_id,),
                )
            else:
                cur = self._conn.execute("SELECT COUNT(*) FROM telemetry")
            return cur.fetchone()[0]

    def close(self):
        with self._lock:
            self._conn.close()


class MemoryStorage(StorageBackend):
    """In-memory storage implementation for testing and ephemeral execution."""

    def __init__(self):
        self._records: list[IngestedTelemetry] = []
        self._lock = threading.RLock()

    def store(self, record: IngestedTelemetry) -> bool:
        with self._lock:
            for r in self._records:
                if r.device_id == record.device_id and r.sequence == record.sequence:
                    return False
            self._records.append(record)
            return True

    def _to_dict(self, r: IngestedTelemetry) -> dict:
        d = r.model_dump(mode="json")
        d["event_timestamp"] = d.get("timestamp")
        return d

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
        with self._lock:
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
        data = [self._to_dict(r) for r in records]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return len(data)

    @property
    def backend_type(self) -> str:
        return "memory"

    @property
    def is_fallback(self) -> bool:
        return False

    def count(self, zone_id: Optional[str] = None) -> int:
        with self._lock:
            if zone_id:
                return sum(1 for r in self._records if r.zone_id == zone_id)
            return len(self._records)


def create_storage(backend: Optional[str] = None) -> StorageBackend:
    """Create the storage backend matching configuration."""
    from backend import config

    backend = backend or config.STORAGE_BACKEND

    if backend == "sqlite":
        return SQLiteStorage(config.SQLITE_DB_PATH, is_fallback=False)
    elif backend == "memory":
        return MemoryStorage()
    elif backend == "influxdb":
        if not config.INFLUXDB_ENABLED:
            logger.warning("InfluxDB configured but INFLUXDB_ENABLED=false; using SQLite fallback")
            return SQLiteStorage(config.SQLITE_DB_PATH, is_fallback=True)
        try:
            from backend.storage_influx import InfluxDBStorage
            return InfluxDBStorage()
        except ImportError:
            logger.warning("influxdb-client missing; using SQLite fallback")
            return SQLiteStorage(config.SQLITE_DB_PATH, is_fallback=True)
        except Exception as e:
            logger.warning("InfluxDB connection failed (%s); using SQLite fallback", e)
            return SQLiteStorage(config.SQLITE_DB_PATH, is_fallback=True)
    else:
        logger.warning("Unknown storage backend '%s'; using memory storage", backend)
        return MemoryStorage()
