#!/usr/bin/env python3
"""
CivicTwin-R — Health Check Script

Checks connectivity to all CivicTwin-R services and reports status.
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def check_url(name: str, url: str) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            print(f"  ✅ {name}: {url} — OK")
            if "status" in data:
                print(f"     Status: {data['status']}")
            return True
    except urllib.error.URLError as e:
        print(f"  ❌ {name}: {url} — {e.reason}")
        return False
    except Exception as e:
        print(f"  ❌ {name}: {url} — {e}")
        return False


def check_mqtt() -> bool:
    try:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="healthcheck")
        client.connect("localhost", 1883, keepalive=5)
        client.disconnect()
        print("  ✅ MQTT Broker: localhost:1883 — OK")
        return True
    except Exception as e:
        print(f"  ❌ MQTT Broker: localhost:1883 — {e}")
        return False


def main():
    print("╔══════════════════════════════════════════╗")
    print("║  CivicTwin-R — Health Check              ║")
    print("╚══════════════════════════════════════════╝\n")

    results = {}

    print("Backend API:")
    results["backend"] = check_url("FastAPI", "http://127.0.0.1:8000/health")

    print("\nNode-RED:")
    results["nodered"] = check_url("Node-RED", "http://127.0.0.1:1880")

    print("\nInfluxDB:")
    results["influxdb"] = check_url("InfluxDB", "http://127.0.0.1:8086/health")

    print("\nMQTT:")
    results["mqtt"] = check_mqtt()

    print("\n" + "=" * 45)
    healthy = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Result: {healthy}/{total} services healthy")

    if healthy < total:
        print("\nNote: Not all services need to be running.")
        print("The backend works standalone with SQLite (Mode B).")
        print("Run 'make run' to start the backend without Docker.")

    return 0 if results["backend"] else 1


if __name__ == "__main__":
    sys.exit(main())
