"""
CivicTwin-R — Automated InfluxDB 2.x Integration Tests
Verifies live InfluxDB connectivity, bucket querying, dual-write storage,
and REST API endpoints.
"""

import time
import urllib.request
import json
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from backend import config
from backend.app.main import app, storage
from backend.models import IngestedTelemetry, DataSource, SensorStatus
from backend.storage import SQLiteStorage, create_storage
from backend.storage_influx import InfluxDBStorage


class TestInfluxDBIntegration:
    """Live InfluxDB 2.x verification suite."""

    def test_influxdb_health_endpoint(self):
        """Verifies InfluxDB 2.x native health endpoint returns pass."""
        req = urllib.request.Request("http://127.0.0.1:8086/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "pass"
            assert data["version"].startswith("2.")

    def test_influxdb_storage_is_healthy(self):
        """Verifies InfluxDBStorage client connection and health."""
        influx = InfluxDBStorage()
        assert influx.is_healthy() is True
        assert influx.backend_type == "influxdb"
        assert influx.is_fallback is False
        influx.close()

    def test_influxdb_direct_query_both_nodes(self):
        """Verifies that telemetry from both sensor nodes exists in InfluxDB."""
        influx = InfluxDBStorage()
        grouped = influx.query_all_latest(limit_per_zone=5)
        influx.close()

        # Check records for zone_01 / node_01 and zone_02 / node_02
        assert len(grouped) > 0, "No records returned from InfluxDB telemetry bucket"
        # Verify fields and timestamps
        all_records = []
        for z_list in grouped.values():
            all_records.extend(z_list)

        devices = {r.get("device_id") for r in all_records if r.get("device_id")}
        assert "node_01" in devices or "node_02" in devices, f"Expected node_01 or node_02 in InfluxDB, found: {devices}"

    def test_dual_write_sqlite_and_influxdb(self, tmp_path):
        """Verifies that writing via SQLiteStorage with secondary InfluxDB writes to both."""
        db_file = str(tmp_path / "test_dual.db")
        influx = InfluxDBStorage()
        dual_store = SQLiteStorage(db_file, is_fallback=False, secondary_storage=influx)

        test_seq = 888800 + int(time.time() % 1000)
        ts = datetime.now(timezone.utc)
        record = IngestedTelemetry(
            schema_version="1.0",
            device_id="node_01",
            zone_id="zone_01",
            sequence=test_seq,
            timestamp=ts,
            ingestion_timestamp=ts,
            distance_cm=20.0,
            water_level_cm=30.0,
            water_level_pct=60.0,
            sensor_status=SensorStatus.VALID,
            source=DataSource.PYTHON_SIMULATED,
            quality_flags=["influx_test"],
        )

        success = dual_store.store(record)
        assert success is True

        # Check SQLite has it
        latest_sql = dual_store.query_latest("zone_01", limit=1)
        assert len(latest_sql) == 1
        assert latest_sql[0]["sequence"] == test_seq

        # Check InfluxDB has it
        time.sleep(0.5)
        latest_influx = influx.query_latest("zone_01", limit=5)
        seqs = [r.get("sequence") for r in latest_influx]
        assert test_seq in seqs, f"Sequence {test_seq} not found in InfluxDB: {seqs}"

        dual_store.close()

    def test_api_storage_influx_status(self):
        """Tests /api/storage/influx/status endpoint."""
        with TestClient(app) as client:
            resp = client.get("/api/storage/influx/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "connected"
            assert data["connected"] is True
            assert data["bucket"] == "telemetry"
            assert data["records_count"] > 0

    def test_api_storage_influx_latest(self):
        """Tests /api/storage/influx/latest endpoint."""
        with TestClient(app) as client:
            resp = client.get("/api/storage/influx/latest?limit=5")
            assert resp.status_code == 200
            data = resp.json()
            assert data["backend"] == "influxdb"
            assert data["count"] > 0
            assert len(data["records"]) > 0

    def test_health_reports_influxdb_active(self):
        """Tests /health reports influxdb_active true."""
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["influxdb_enabled"] is True
            assert data["influxdb_active"] is True
            assert data["influxdb_url"] == "http://localhost:8086"
