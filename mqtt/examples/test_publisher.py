#!/usr/bin/env python3
"""
CivicTwin-R — MQTT Test Publisher

Publishes sample telemetry messages to the MQTT broker for testing.
Run with a local Mosquitto broker running.

Usage:
    python mqtt/examples/test_publisher.py
    python mqtt/examples/test_publisher.py --count 20 --interval 2
"""

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip install paho-mqtt")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="CivicTwin-R MQTT Test Publisher")
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--count", type=int, default=10, help="Number of messages")
    parser.add_argument("--interval", type=float, default=3.0, help="Seconds between messages")
    parser.add_argument("--zone", default="zone_01", help="Zone ID")
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="test_publisher")

    try:
        client.connect(args.broker, args.port)
        client.loop_start()
        print(f"Connected to {args.broker}:{args.port}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        sys.exit(1)

    rng = random.Random(42)
    water_level = 5.0

    for seq in range(1, args.count + 1):
        # Simulate slowly rising water
        water_level += rng.uniform(-0.5, 1.0)
        water_level = max(0, min(30, water_level))
        water_pct = (water_level / 30.0) * 100.0

        msg = {
            "schema_version": "1.0",
            "device_id": f"test_{args.zone}",
            "zone_id": args.zone,
            "sequence": seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "distance_cm": round(30.0 - water_level, 2),
            "water_level_cm": round(water_level, 2),
            "water_level_pct": round(water_pct, 2),
            "sensor_status": "valid",
            "source": "simulator",
        }

        topic = f"civictwin/v1/zones/{args.zone}/telemetry"
        payload = json.dumps(msg)
        result = client.publish(topic, payload, qos=1)

        print(f"[{seq}/{args.count}] {topic} → level={water_level:.1f}cm ({water_pct:.1f}%)")
        time.sleep(args.interval)

    client.loop_stop()
    client.disconnect()
    print("Done.")


if __name__ == "__main__":
    main()
