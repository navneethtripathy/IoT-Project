"""
CivicTwin-R — InfluxDB 2.x Time-Series Storage Backend

Persists telemetry records to an InfluxDB 2.x instance and provides
Flux-based range and latest-value queries.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend import config
from backend.models import IngestedTelemetry
from backend.storage import StorageBackend

logger = logging.getLogger("civictwin.storage.influx")


class InfluxDBStorage(StorageBackend):
    """InfluxDB 2.x implementation of StorageBackend."""

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None,
    ):
        import influxdb_client
        from influxdb_client.client.write_api import SYNCHRONOUS

        self._url = url or config.INFLUXDB_URL
        self._token = token or config.INFLUXDB_TOKEN
        self._org = org or config.INFLUXDB_ORG
        self._bucket = bucket or config.INFLUXDB_BUCKET

        self._client = influxdb_client.InfluxDBClient(
            url=self._url,
            token=self._token,
            org=self._org,
            timeout=5000,
        )
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        self._query_api = self._client.query_api()
        logger.info("InfluxDB storage initialized for org='%s', bucket='%s'", self._org, self._bucket)

    @property
    def backend_type(self) -> str:
        return "influxdb"

    @property
    def is_fallback(self) -> bool:
        return False

    def store(self, record: IngestedTelemetry) -> bool:
        from influxdb_client import Point

        try:
            point = (
                Point("telemetry")
                .tag("zone_id", record.zone_id)
                .tag("device_id", record.device_id)
                .tag("source", record.source.value)
                .tag("sensor_status", record.sensor_status.value)
                .field("sequence", int(record.sequence))
                .time(record.timestamp)
            )

            if record.distance_cm is not None:
                point.field("distance_cm", float(record.distance_cm))
            if record.water_level_cm is not None:
                point.field("water_level_cm", float(record.water_level_cm))
            if record.water_level_pct is not None:
                point.field("water_level_pct", float(record.water_level_pct))

            point.field("is_reconstructed", int(record.is_reconstructed))
            if record.reconstruction_method:
                point.tag("reconstruction_method", record.reconstruction_method)
            if record.scenario_id:
                point.tag("scenario_id", record.scenario_id)

            self._write_api.write(bucket=self._bucket, org=self._org, record=point)
            return True
        except Exception as e:
            logger.warning("Failed to write to InfluxDB: %s", e)
            return False

    def query_latest(self, zone_id: str, limit: int = 1) -> list[dict]:
        query = f'''
        from(bucket: "{self._bucket}")
            |> range(start: -30d)
            |> filter(fn: (r) => r["_measurement"] == "telemetry")
            |> filter(fn: (r) => r["zone_id"] == "{zone_id}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: {limit})
        '''
        return self._run_query(query)

    def query_range(
        self,
        zone_id: str,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[dict]:
        start_iso = start.isoformat()
        end_iso = end.isoformat()
        query = f'''
        from(bucket: "{self._bucket}")
            |> range(start: {start_iso}, stop: {end_iso})
            |> filter(fn: (r) => r["_measurement"] == "telemetry")
            |> filter(fn: (r) => r["zone_id"] == "{zone_id}")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> sort(columns: ["_time"], desc: false)
            |> limit(n: {limit})
        '''
        return self._run_query(query)

    def query_all_latest(self, limit_per_zone: int = 1) -> dict[str, list[dict]]:
        query = f'''
        from(bucket: "{self._bucket}")
            |> range(start: -30d)
            |> filter(fn: (r) => r["_measurement"] == "telemetry")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
            |> group(columns: ["zone_id"])
            |> sort(columns: ["_time"], desc: true)
            |> limit(n: {limit_per_zone})
        '''
        records = self._run_query(query)
        grouped: dict[str, list[dict]] = {}
        for r in records:
            zid = r.get("zone_id", "unknown")
            grouped.setdefault(zid, []).append(r)
        return grouped

    def count(self, zone_id: Optional[str] = None) -> int:
        filter_zone = f'|> filter(fn: (r) => r["zone_id"] == "{zone_id}")' if zone_id else ""
        query = f'''
        from(bucket: "{self._bucket}")
            |> range(start: -30d)
            |> filter(fn: (r) => r["_measurement"] == "telemetry")
            {filter_zone}
            |> count()
        '''
        try:
            tables = self._query_api.query(query, org=self._org)
            total = 0
            for table in tables:
                for record in table.records:
                    total += record.get_value() or 0
            return total
        except Exception as e:
            logger.warning("Failed to count InfluxDB records: %s", e)
            return 0

    def export_csv(self, path: Path, zone_id: Optional[str] = None) -> int:
        if zone_id:
            records = self.query_latest(zone_id, limit=5000)
        else:
            all_latest = self.query_all_latest(limit_per_zone=5000)
            records = []
            for z_records in all_latest.values():
                records.extend(z_records)

        if not records:
            return 0

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        return len(records)

    def close(self):
        try:
            self._write_api.close()
            self._client.close()
            logger.info("InfluxDB client closed")
        except Exception:
            pass

    def _run_query(self, flux: str) -> list[dict]:
        try:
            tables = self._query_api.query(flux, org=self._org)
            rows = []
            for table in tables:
                for record in table.records:
                    row = dict(record.values)
                    row["event_timestamp"] = row.get("_time", "").isoformat() if hasattr(row.get("_time"), "isoformat") else str(row.get("_time", ""))
                    row.pop("_start", None)
                    row.pop("_stop", None)
                    row.pop("table", None)
                    row.pop("result", None)
                    rows.append(row)
            return rows
        except Exception as e:
            logger.warning("InfluxDB query failed: %s", e)
            return []
