#!/usr/bin/env python3
"""
CivicTwin-R — Live Two-Node MQTT Cyber-Physical Telemetry Simulator

Simulates two distinct physical monitoring nodes:
  - Node 01: Tank 1 (Adyar Basin / Saidapet Prototype) — Area 299.87 cm², H_max 50 cm, k=4.5
  - Node 02: Tank 2 (Cooum Basin / Urban Retention Prototype) — Area 450.13 cm², H_max 60 cm, k=6.0

Publishes real-time telemetry, node health status, and edge alerts over native MQTT (1883).
Supports live interactive control: pause, resume, sensor dropout, surge inflow, and fault injection.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import signal
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import paho.mqtt.client as mqtt

from backend import config
from digital_twin.edge_warning import EdgeWarningEvaluator
from digital_twin.tank_twin import PhysicalTankModel, TankGeometry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.mqtt_sim")

CONTROL_FILE = PROJECT_ROOT / ".run" / "simulator_control.json"


def _initial_sequence_for_node(node_id: str) -> int:
    """Return a monotonic starting sequence strictly above persisted SQLite rows."""
    base = int(time.time())
    db_path = Path(config.SQLITE_DB_PATH)
    if not db_path.exists():
        return base
    try:
        with sqlite3.connect(str(db_path), timeout=2.0) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM telemetry WHERE device_id = ?",
                (node_id,),
            ).fetchone()
            max_seq = int(row[0]) if row and row[0] is not None else 0
            return max(base, max_seq)
    except sqlite3.Error as exc:
        logger.debug("Could not inspect max sequence for %s: %s", node_id, exc)
        return base


class SimulatedNode:
    """Represents a simulated IoT node running tank physics and local edge logic."""

    def __init__(
        self,
        node_id: str,
        zone_id: str,
        tank_model: PhysicalTankModel,
        seed: int = 42,
        speed_multiplier: float = 1.0,
        initial_sequence: int = 0,
    ):
        self.node_id = node_id
        self.zone_id = zone_id
        self.tank = tank_model
        self.rng = random.Random(seed + hash(node_id))
        self.sequence = initial_sequence
        self.is_paused = False
        self.is_disconnected = False
        self.sensor_fault = False
        self.noise_stddev = 0.2
        self.inflow_override: float | None = None
        self.speed_multiplier = speed_multiplier

        self.evaluator = EdgeWarningEvaluator(
            warn_threshold_pct=config.WATER_LEVEL_WARN_PCT,
            crit_threshold_pct=config.WATER_LEVEL_CRIT_PCT,
            hysteresis_pct=config.WATER_LEVEL_HYSTERESIS_PCT,
        )

        self.last_status_time = 0.0
        self.start_time = time.time()

    def get_inflow(self, elapsed_sec: float) -> float:
        if self.inflow_override is not None:
            return max(0.0, self.inflow_override)
        # Dynamic sinusoidal inflow mimicking changing urban runoff / pumping
        base_q = self.tank.default_q_in
        amplitude = base_q * 0.4
        freq = 0.03 if self.node_id == "node_01" else 0.02
        return max(2.0, base_q + amplitude * math.sin(freq * elapsed_sec))

    def step(self, dt_sec: float) -> dict | None:
        """Advances physics and generates a telemetry packet."""
        if self.is_paused or self.is_disconnected:
            return None

        elapsed = time.time() - self.start_time
        q_in = self.get_inflow(elapsed)

        # RK4 physics step
        scaled_dt = dt_sec * self.speed_multiplier
        self.tank.step_rk4(dt_sec=scaled_dt, q_in=q_in)
        true_level = self.tank.current_level_cm
        max_h = self.tank.geometry.max_height_cm

        self.sequence += 1

        if self.sensor_fault:
            status = "invalid"
            dist_cm = None
            measured_level = None
            measured_pct = None
            flags = ["sensor_echo_timeout", "fault_injected"]
        else:
            status = "valid"
            noise = self.rng.gauss(0, self.noise_stddev)
            noisy_level = max(0.0, min(max_h, true_level + noise))
            dist_cm = round(max_h - noisy_level, 2)
            measured_level = round(noisy_level, 2)
            measured_pct = round((noisy_level / max_h) * 100.0, 2)
            flags = []

        # Local edge warning evaluation
        alert_state, led_mode = self.evaluator.evaluate(
            water_pct=measured_pct,
            is_valid=(status == "valid"),
        )

        # Simulated rain sensor
        rain_raw = int(2048 + 1024 * math.sin(0.01 * elapsed))
        rain_pct = round((rain_raw / 4095.0) * 100.0, 2)

        return {
            "schema_version": "1.0",
            "device_id": self.node_id,
            "zone_id": self.zone_id,
            "sequence": self.sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "distance_cm": dist_cm,
            "water_level_cm": measured_level,
            "water_level_pct": measured_pct,
            "rain_sensor_raw": rain_raw,
            "rain_indicator_pct": rain_pct,
            "sensor_status": status,
            "source": "PYTHON_SIMULATED",
            "quality_flags": flags,
            "alert_state": alert_state.value,
            "led_indicator": led_mode.value,
            "inflow_cm3_s": round(q_in, 2),
        }

    def get_status_payload(self) -> dict:
        """Returns node diagnostic health heartbeat."""
        uptime = int(time.time() - self.start_time)
        return {
            "device_id": self.node_id,
            "node_id": self.node_id,
            "wifi": not self.is_disconnected,
            "mqtt": True,
            "uptime_sec": uptime,
            "sequence": self.sequence,
            "alert_state": self.evaluator.current_state.value,
            "heap_free": 240128 + self.rng.randint(-1024, 1024),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class MultiNodeMqttSimulator:
    """Manages dual simulated nodes and handles real MQTT publishing."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        step_interval_sec: float = 5.0,
        seed: int = 42,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.interval = step_interval_sec
        self.running = False
        self.client: mqtt.Client | None = None
        self.connected = False

        # Initialize Tank Models
        geom1 = TankGeometry(
            tank_id="tank_01",
            node_id="node_01",
            name="Tank 1 (Saidapet Prototype)",
            diameter_cm=19.54,
            max_height_cm=50.0,
        )
        geom2 = TankGeometry(
            tank_id="tank_02",
            node_id="node_02",
            name="Tank 2 (Cooum Retention Prototype)",
            diameter_cm=23.94,
            max_height_cm=60.0,
        )

        tank1 = PhysicalTankModel(geometry=geom1, drainage_k=4.5, initial_level_cm=15.0, default_q_in_cm3_s=25.0)
        tank2 = PhysicalTankModel(geometry=geom2, drainage_k=6.0, initial_level_cm=18.0, default_q_in_cm3_s=35.0)

        self.nodes = {
            "node_01": SimulatedNode(
                "node_01",
                "zone_01",
                tank1,
                seed=seed,
                initial_sequence=_initial_sequence_for_node("node_01"),
            ),
            "node_02": SimulatedNode(
                "node_02",
                "zone_02",
                tank2,
                seed=seed + 100,
                initial_sequence=_initial_sequence_for_node("node_02"),
            ),
        }

        self._lock = threading.Lock()
        self.prefix = config.MQTT_TOPIC_PREFIX

    def connect(self) -> bool:
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="civictwin_multinode_sim",
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect

            logger.info("Connecting simulator to MQTT broker %s:%d...", self.broker_host, self.broker_port)
            self.client.connect(self.broker_host, self.broker_port, keepalive=30)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error("Failed to connect to MQTT broker: %s", e)
            return False

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self.connected = True
            logger.info("Simulator connected to MQTT broker successfully.")
        else:
            logger.warning("Simulator MQTT connect returned code: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self.connected = False
        logger.warning("Simulator disconnected from MQTT broker (rc=%s)", reason_code)

    def read_control_file(self):
        """Reads interactive control instructions written by the showcase dashboard."""
        if not CONTROL_FILE.exists():
            return
        try:
            with open(CONTROL_FILE, "r") as f:
                data = json.load(f)

            modified = False
            with self._lock:
                for node_id, params in data.get("nodes", {}).items():
                    if node_id in self.nodes:
                        node = self.nodes[node_id]
                        if "paused" in params:
                            node.is_paused = params["paused"]
                        if "disconnected" in params:
                            node.is_disconnected = params["disconnected"]
                        if "sensor_fault" in params:
                            node.sensor_fault = params["sensor_fault"]
                        if "inflow_override" in params:
                            node.inflow_override = params["inflow_override"]
                        if "drainage_k_override" in params:
                            node.tank.drainage_k = params["drainage_k_override"]
                        if "reset_level" in params:
                            node.tank.current_level_cm = params.pop("reset_level")
                            modified = True

            if modified:
                try:
                    with open(CONTROL_FILE, "w") as f_out:
                        json.dump(data, f_out, indent=2)
                except OSError as e:
                    logger.debug("Control file write skipped: %s", e)
        except Exception as e:
            logger.debug("Control file read skipped: %s", e)

    def start(self):
        self.running = True
        self.connect()

        last_step = time.time()
        last_status = time.time()

        logger.info("CivicTwin-R Two-Node MQTT Simulator active (interval=%.1fs)", self.interval)

        while self.running:
            now = time.time()
            self.read_control_file()

            if now - last_step >= self.interval:
                dt = now - last_step
                last_step = now

                with self._lock:
                    for _node_id, node in self.nodes.items():
                        reading = node.step(dt)
                        if reading and self.connected and self.client:
                            payload = json.dumps(reading)
                            # Dual-topic dispatch: to node and zone hierarchies
                            t_node = f"{self.prefix}/nodes/{node.node_id}/telemetry"
                            t_zone = f"{self.prefix}/zones/{node.zone_id}/telemetry"
                            self.client.publish(t_node, payload, qos=1)
                            self.client.publish(t_zone, payload, qos=1)

                            logger.debug(
                                "[TX] %s -> Level=%.1fcm (%.1f%%) Status=%s Alert=%s",
                                node.node_id,
                                reading["water_level_cm"] or 0.0,
                                reading["water_level_pct"] or 0.0,
                                reading["sensor_status"],
                                reading["alert_state"],
                            )

                            # Publish alert event if threshold breached
                            if reading["alert_state"] in ("warning", "critical"):
                                alert_payload = json.dumps({
                                    "device_id": node.node_id,
                                    "node_id": node.node_id,
                                    "zone_id": node.zone_id,
                                    "alert_level": reading["alert_state"],
                                    "water_pct": reading["water_level_pct"],
                                    "threshold": 70.0 if reading["alert_state"] == "warning" else 85.0,
                                    "timestamp": reading["timestamp"],
                                })
                                self.client.publish(f"{self.prefix}/nodes/{node.node_id}/alerts", alert_payload)
                                self.client.publish(f"{self.prefix}/zones/{node.zone_id}/alerts", alert_payload)

            # Node health heartbeats every 30 seconds
            if now - last_status >= 30.0:
                last_status = now
                with self._lock:
                    for _node_id, node in self.nodes.items():
                        if self.connected and self.client and not node.is_disconnected:
                            status_data = node.get_status_payload()
                            st_payload = json.dumps(status_data)
                            self.client.publish(f"{self.prefix}/nodes/{node.node_id}/status", st_payload)
                            self.client.publish(f"{self.prefix}/zones/{node.zone_id}/status", st_payload)

            time.sleep(0.5)

    def stop(self):
        logger.info("Stopping two-node simulator...")
        self.running = False
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
        logger.info("Simulator stopped.")


def main():
    parser = argparse.ArgumentParser(description="CivicTwin-R Two-Node MQTT Simulator")
    parser.add_argument("--broker", default=config.MQTT_BROKER_HOST, help="MQTT broker host")
    parser.add_argument("--port", type=int, default=config.MQTT_BROKER_PORT, help="MQTT broker port")
    parser.add_argument("--interval", type=float, default=5.0, help="Publish interval in seconds")
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED, help="Random seed")
    args = parser.parse_args()

    # Ensure .run directory exists
    CONTROL_FILE.parent.mkdir(parents=True, exist_ok=True)

    sim = MultiNodeMqttSimulator(
        broker_host=args.broker,
        broker_port=args.port,
        step_interval_sec=args.interval,
        seed=args.seed,
    )

    def _sig_handler(sig, frame):
        sim.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    sim.start()


if __name__ == "__main__":
    main()
