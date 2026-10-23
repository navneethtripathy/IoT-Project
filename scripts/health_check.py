#!/usr/bin/env python3
"""
CivicTwin-R — Health Check Script

Validates availability and responsiveness of configured services:
FastAPI REST API, Node-RED dashboard, InfluxDB, and Mosquitto MQTT broker.
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_url(name: str, url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "CivicTwin-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            content_type = resp.headers.get("content-type", "")
            raw = resp.read()
            status_text = "reachable"
            if "application/json" in content_type:
                try:
                    data = json.loads(raw)
                    status_text = data.get("status", "ok")
                except Exception:
                    pass
            print(f"[OK] {name} ({url}) - status: {status_text} (HTTP {resp.status})")
            return True
    except urllib.error.URLError as e:
        print(f"[UNAVAILABLE] {name} ({url}) - reason: {e.reason}")
        return False
    except Exception as e:
        print(f"[ERROR] {name} ({url}) - {e}")
        return False


def check_mqtt(host: str = "localhost", port: int = 1883) -> bool:
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="healthcheck")
        client.connect(host, port, keepalive=5)
        client.disconnect()
        print(f"[OK] MQTT Broker ({host}:{port}) - reachable")
        return True
    except Exception as e:
        print(f"[UNAVAILABLE] MQTT Broker ({host}:{port}) - {e}")
        return False


def main():
    print("CivicTwin-R service health status:\n")

    results = {}
    results["backend"] = check_url("FastAPI API", "http://127.0.0.1:8000/health")
    results["nodered"] = check_url("Node-RED UI", "http://127.0.0.1:1880")
    results["influxdb"] = check_url("InfluxDB 2.x", "http://127.0.0.1:8086/health")
    results["mqtt"] = check_mqtt("localhost", 1883)

    healthy = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\nResult: {healthy}/{total} services active.")

    if not results["backend"]:
        print("\nNote: Backend is offline. Run 'make run' or './scripts/start.sh' to start standalone mode.")

    return 0 if results["backend"] else 1


if __name__ == "__main__":
    sys.exit(main())
