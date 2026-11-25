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
from datetime import datetime
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

    def get_table_names(self) -> list[str]:
        return ["telemetry"]

    def get_table_schema(self, table_name: str) -> list[dict]:
        return []

    def query_records_paginated(
        self,
        table_name: str = "telemetry",
        zone_id: Optional[str] = None,
        device_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        return {"table": table_name, "total": 0, "limit": limit, "offset": offset, "rows": []}

    def get_database_stats(self) -> dict:
        return {
            "backend": self.backend_type,
            "db_path": "memory",
            "size_bytes": 0,
            "size_kb": 0.0,
            "total_telemetry_rows": 0,
            "earliest_timestamp": None,
            "latest_timestamp": None,
            "records_by_device": {},
            "journal_mode": "none",
        }

    def close(self):  # noqa: B027
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
        rain_sensor_raw INTEGER,
        rain_indicator_pct REAL,
        inflow_cm3_s REAL,
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
    CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
        ON telemetry(device_id, event_timestamp);
    """

    def __init__(self, db_path: str, is_fallback: bool = False, secondary_storage: Optional[StorageBackend] = None):
        self._db_path = db_path
        self._is_fallback = is_fallback
        self._secondary_storage = secondary_storage
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(self._CREATE_TABLE)
        self._migrate_telemetry_table()
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_telemetry_zone_time ON telemetry(zone_id, event_timestamp);",
            "CREATE INDEX IF NOT EXISTS idx_telemetry_device_time ON telemetry(device_id, event_timestamp);",
        ]:
            self._conn.execute(idx)
        self._conn.commit()
        logger.info("SQLite storage initialized at: %s (fallback=%s, secondary=%s)", db_path, is_fallback, type(secondary_storage).__name__ if secondary_storage else "None")

    def _migrate_telemetry_table(self):
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(telemetry)").fetchall()
        }
        migrations = {
            "rain_sensor_raw": "ALTER TABLE telemetry ADD COLUMN rain_sensor_raw INTEGER",
            "rain_indicator_pct": "ALTER TABLE telemetry ADD COLUMN rain_indicator_pct REAL",
            "inflow_cm3_s": "ALTER TABLE telemetry ADD COLUMN inflow_cm3_s REAL",
        }
        for column, statement in migrations.items():
            if column not in columns:
                self._conn.execute(statement)

    @property
    def backend_type(self) -> str:
        return "sqlite"

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    @property
    def secondary_storage(self) -> Optional[StorageBackend]:
        return self._secondary_storage

    def store(self, record: IngestedTelemetry) -> bool:
        stored = False
        with self._lock:
            try:
                src_val = record.source.value if hasattr(record.source, "value") else str(record.source)
                status_val = record.sensor_status.value if hasattr(record.sensor_status, "value") else str(record.sensor_status)
                cur = self._conn.execute(
                    """INSERT OR IGNORE INTO telemetry
                       (device_id, zone_id, sequence, event_timestamp,
                        ingestion_timestamp, distance_cm, water_level_cm,
                        water_level_pct, rain_sensor_raw, rain_indicator_pct,
                        inflow_cm3_s, sensor_status, source,
                        is_reconstructed, reconstruction_method,
                        scenario_id, quality_flags)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record.device_id,
                        record.zone_id,
                        record.sequence,
                        record.timestamp.isoformat(),
                        record.ingestion_timestamp.isoformat(),
                        record.distance_cm,
                        record.water_level_cm,
                        record.water_level_pct,
                        record.rain_sensor_raw,
                        record.rain_indicator_pct,
                        record.inflow_cm3_s,
                        status_val,
                        src_val,
                        1 if record.is_reconstructed else 0,
                        record.reconstruction_method,
                        record.scenario_id,
                        json.dumps(record.quality_flags),
                    ),
                )
                self._conn.commit()
                if cur.rowcount == 0:
                    logger.debug("Duplicate record ignored: %s seq=%d", record.device_id, record.sequence)
                    return False
                stored = True
            except sqlite3.IntegrityError:
                logger.debug("Duplicate record: %s seq=%d", record.device_id, record.sequence)
                return False
            except Exception:
                logger.exception("Failed to store record")
                return False

        if stored and self._secondary_storage is not None:
            try:
                self._secondary_storage.store(record)
            except Exception as e:
                logger.warning("Secondary storage write failed: %s", e)

        return stored

    def _rows_to_dicts(self, rows) -> list[dict]:
        return [dict(r) for r in rows]

    def query_latest(self, zone_id: str, limit: int = 1) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT * FROM telemetry
                   WHERE device_id = ? OR zone_id = ?
                   ORDER BY event_timestamp DESC LIMIT ?""",
                (zone_id, zone_id, limit),
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
                   WHERE (device_id = ? OR zone_id = ?) AND event_timestamp >= ? AND event_timestamp <= ?
                   ORDER BY event_timestamp ASC LIMIT ?""",
                (zone_id, zone_id, start.isoformat(), end.isoformat(), limit),
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
                    "SELECT * FROM telemetry WHERE device_id = ? OR zone_id = ? ORDER BY event_timestamp ASC",
                    (zone_id, zone_id),
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
                    "SELECT COUNT(*) FROM telemetry WHERE device_id = ? OR zone_id = ?",
                    (zone_id, zone_id),
                )
            else:
                cur = self._conn.execute("SELECT COUNT(*) FROM telemetry")
            return cur.fetchone()[0]

    def get_table_names(self) -> list[str]:
        with self._lock:
            cur = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            return [row["name"] for row in cur.fetchall()]

    def get_table_schema(self, table_name: str) -> list[dict]:
        with self._lock:
            allowed = self.get_table_names()
            if table_name not in allowed or table_name != "telemetry":
                return []
            cur = self._conn.execute("PRAGMA table_info(telemetry)")
            return [dict(row) for row in cur.fetchall()]

    _PAGINATED_SQL = {
        (False, False): (
            "SELECT COUNT(*) FROM telemetry",
            "SELECT * FROM telemetry ORDER BY id DESC LIMIT ? OFFSET ?",
        ),
        (True, False): (
            "SELECT COUNT(*) FROM telemetry WHERE zone_id = ?",
            "SELECT * FROM telemetry WHERE zone_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        ),
        (False, True): (
            "SELECT COUNT(*) FROM telemetry WHERE device_id = ?",
            "SELECT * FROM telemetry WHERE device_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        ),
        (True, True): (
            "SELECT COUNT(*) FROM telemetry WHERE zone_id = ? AND device_id = ?",
            "SELECT * FROM telemetry WHERE zone_id = ? AND device_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
        ),
    }

    def query_records_paginated(
        self,
        table_name: str = "telemetry",
        zone_id: Optional[str] = None,
        device_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        with self._lock:
            allowed_tables = self.get_table_names()
            if table_name not in allowed_tables or table_name != "telemetry":
                table_name = "telemetry"

            params: list = []
            if zone_id:
                params.append(zone_id)
            if device_id:
                params.append(device_id)

            count_sql, query_sql = self._PAGINATED_SQL[(bool(zone_id), bool(device_id))]
            count_cur = self._conn.execute(count_sql, params)
            total_count = count_cur.fetchone()[0]

            cur = self._conn.execute(query_sql, params + [limit, offset])
            rows = self._rows_to_dicts(cur.fetchall())

            return {
                "table": table_name,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "rows": rows,
            }

    def get_database_stats(self) -> dict:
        with self._lock:
            size_bytes = Path(self._db_path).stat().st_size if Path(self._db_path).exists() else 0
            cur = self._conn.execute("SELECT COUNT(*) FROM telemetry")
            telemetry_count = cur.fetchone()[0]

            cur = self._conn.execute("SELECT MIN(event_timestamp), MAX(event_timestamp) FROM telemetry")
            row = cur.fetchone()
            min_ts = row[0] if row else None
            max_ts = row[1] if row else None

            cur = self._conn.execute("SELECT device_id, COUNT(*) as cnt FROM telemetry GROUP BY device_id")
            device_counts = {r["device_id"]: r["cnt"] for r in cur.fetchall()}

            try:
                jmode = self._conn.execute("PRAGMA journal_mode").fetchone()[0]
            except Exception:
                jmode = "unknown"

            return {
                "backend": self.backend_type,
                "db_path": self._db_path,
                "size_bytes": size_bytes,
                "size_kb": round(size_bytes / 1024, 1),
                "total_telemetry_rows": telemetry_count,
                "earliest_timestamp": min_ts,
                "latest_timestamp": max_ts,
                "records_by_device": device_counts,
                "journal_mode": jmode,
                "influxdb_active": self._secondary_storage is not None,
            }

    def close(self):
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error as e:
                logger.debug("SQLite close ignored error: %s", e)
        if self._secondary_storage is not None:
            try:
                self._secondary_storage.close()
            except Exception as e:
                logger.debug("Secondary storage close ignored error: %s", e)


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
            matched = [
                r for r in self._records
                if r.zone_id == zone_id or r.device_id == zone_id
            ]
            matched.sort(key=lambda r: r.timestamp, reverse=True)
            return [self._to_dict(r) for r in matched[:limit]]

    def query_range(
        self, zone_id: str, start: datetime, end: datetime, limit: int = 1000
    ) -> list[dict]:
        with self._lock:
            matched = [
                r for r in self._records
                if (r.zone_id == zone_id or r.device_id == zone_id) and start <= r.timestamp <= end
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
        secondary = None
        if config.INFLUXDB_ENABLED:
            try:
                from backend.storage_influx import InfluxDBStorage
                secondary = InfluxDBStorage()
                logger.info("Parallel InfluxDB 2.x storage attached to SQLite primary")
            except Exception as e:
                logger.warning("InfluxDB secondary initialization failed: %s; using SQLite only", e)
        return SQLiteStorage(config.SQLITE_DB_PATH, is_fallback=False, secondary_storage=secondary)
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
