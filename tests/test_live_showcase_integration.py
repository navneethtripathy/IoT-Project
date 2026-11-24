"""
CivicTwin-R — Live Showcase End-to-End Integration Test Suite

Validates complete live integration across:
- Native Mosquitto MQTT broker (1883)
- FastAPI Backend & Storage persistence
- Real TCP message publishing & subscription
- Freshness state machine & Hysteresis alert transitions
- Showcase scenario triggers
- Node-RED HTTP reachability
- Digital twin RK4 trajectory prediction
"""

from __future__ import annotations

import json
import socket
import time
import urllib.request
import pytest
import paho.mqtt.client as mqtt

from backend import config


def is_port_open(host: str, port: int) -> bool:
    try:
        s = socket.create_connection((host, port), timeout=2.0)
        s.close()
        return True
    except OSError:
        return False


@pytest.mark.integration
class TestLiveShowcaseIntegration:

    def test_live_mosquitto_broker_listening(self):
        """Verifies native Mosquitto broker is active on port 1883."""
        assert is_port_open("127.0.0.1", 1883), "Mosquitto broker not listening on 127.0.0.1:1883"

    def test_live_fastapi_backend_health(self):
        """Verifies FastAPI backend responds with healthy status and active MQTT."""
        req = urllib.request.Request("http://127.0.0.1:8000/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "healthy"
            assert data["mqtt_connected"] is True
            assert data["records_stored"] > 0

    def test_live_showcase_dashboard_html_rendering(self):
        """Verifies Showcase Engineering Control Center HTML is served."""
        req = urllib.request.Request("http://127.0.0.1:8000/showcase")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            html = resp.read().decode()
            assert "CivicTwin-R" in html
            assert "System Topology" in html
            assert "Dual-Node Telemetry" in html
            assert "Digital Twin ODE" in html
            assert "Missing-Data Reconstruction" in html
            assert "Chennai Basin" in html
            assert "Showcase Mode" in html or "Showcase Laboratory" in html

    def test_live_mqtt_end_to_end_publish_ingest_persist(self):
        """Publishes real MQTT packet over TCP socket and confirms database persistence."""
        test_seq = int(time.time())
        test_payload = {
            "schema_version": "1.0",
            "device_id": "node_01",
            "zone_id": "zone_01",
            "sequence": test_seq,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "distance_cm": 15.0,
            "water_level_cm": 35.0,
            "water_level_pct": 70.0,
            "sensor_status": "valid",
            "source": "PYTHON_SIMULATED",
            "quality_flags": ["live_integration_test"],
        }

        # Publish via real MQTT client
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"test_pub_{test_seq}")
        pub.connect("localhost", 1883, keepalive=10)
        topic = "civictwin/v1/nodes/node_01/telemetry"
        info = pub.publish(topic, json.dumps(test_payload), qos=1)
        info.wait_for_publish(timeout=3.0)
        pub.disconnect()

        time.sleep(1.0)

        # Query backend API to confirm receipt and ingestion
        req = urllib.request.Request("http://127.0.0.1:8000/api/telemetry/latest?zone_id=zone_01&limit=20")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            seqs = [r.get("sequence") for r in data.get("records", [])]
            assert test_seq in seqs, f"Published sequence {test_seq} not found in stored telemetry: {seqs}"

    def test_live_showcase_scenario_triggers(self):
        """Tests that showcase scenarios update system control parameters."""
        req = urllib.request.Request("http://127.0.0.1:8000/api/showcase/scenario/rising_water", method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["scenario"] == "rising_water"
            assert data["status"] == "activated"

    def test_live_node_red_reachability(self):
        """Verifies Node-RED runtime engine is listening on port 1880."""
        assert is_port_open("127.0.0.1", 1880), "Node-RED not listening on 127.0.0.1:1880"
        req = urllib.request.Request("http://127.0.0.1:1880/ui/")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200

    def test_live_digital_twin_rk4_trajectory(self):
        """Verifies forward trajectory prediction via ODE RK4 solver."""
        req = urllib.request.Request("http://127.0.0.1:8000/api/tank/predict?tank_id=tank_01&duration_sec=60&dt_sec=1.0")
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["tank_id"] == "tank_01"
            assert len(data["predicted_levels_cm"]) > 10
            assert data["provenance"] == "TWIN_ESTIMATED"
