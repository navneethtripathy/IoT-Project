"""
CivicTwin-R — Sensor Simulator (Python MQTT Publisher)

Generates water-level telemetry from digital twin zones and publishes to MQTT
or routes directly into IngestionService when running in standalone mode.
"""

from __future__ import annotations

import json
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Optional

from digital_twin.model import DigitalTwinEngine, create_default_zones
from backend.models import TelemetryMessage, SensorStatus, DataSource
from backend import config

logger = logging.getLogger("civictwin.simulator")


class SensorSimulator:
    """Simulates multi-zone water level sensors and publishes telemetry."""

    def __init__(
        self,
        engine: Optional[DigitalTwinEngine] = None,
        mqtt_client=None,
        direct_callback=None,
        interval_sec: float = 5.0,
    ):
        self._engine = engine or self._create_default_engine()
        self._mqtt_client = mqtt_client
        self._direct_callback = direct_callback
        self._interval = interval_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sequence_counters: dict[str, int] = {}
        self._stats = {
            "messages_published": 0,
            "publish_failures": 0,
        }

    def _create_default_engine(self) -> DigitalTwinEngine:
        engine = DigitalTwinEngine(seed=config.RANDOM_SEED)
        for zone in create_default_zones():
            engine.add_zone(zone)
        return engine

    @property
    def engine(self) -> DigitalTwinEngine:
        return self._engine

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="sensor-sim")
        self._thread.start()
        logger.info("Sensor simulator started with %.1fs interval", self._interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=self._interval * 2)
        logger.info("Sensor simulator stopped")

    def generate_one_step(self, dt_sec: Optional[float] = None) -> list[dict]:
        dt = dt_sec or self._interval
        readings = self._engine.step_all(dt)
        messages = []

        for reading in readings:
            device_id = f"sim_{reading.zone_id}"
            seq = self._sequence_counters.get(device_id, 0) + 1
            self._sequence_counters[device_id] = seq

            if not reading.sensor_ok:
                status = SensorStatus.INVALID
            elif not reading.network_ok:
                status = SensorStatus.OFFLINE
            else:
                status = SensorStatus.SIMULATED

            container_h = self._engine.zones[reading.zone_id].container_height_cm
            distance_cm = None
            if reading.observed_level_cm is not None:
                distance_cm = round(container_h - reading.observed_level_cm, 2)

            msg = TelemetryMessage(
                schema_version="1.0",
                device_id=device_id,
                zone_id=reading.zone_id,
                sequence=seq,
                timestamp=reading.timestamp,
                distance_cm=distance_cm,
                water_level_cm=reading.observed_level_cm,
                water_level_pct=reading.observed_level_pct,
                sensor_status=status,
                source=DataSource.PYTHON_SIMULATED,
                quality_flags=reading.quality_flags,
            )

            messages.append(msg.model_dump(mode="json"))

        return messages

    def _run_loop(self):
        while self._running:
            try:
                messages = self.generate_one_step()
                for msg in messages:
                    self._publish(msg)
                    self._stats["messages_published"] += 1
            except Exception:
                logger.exception("Simulator step cycle failed")
                self._stats["publish_failures"] += 1

            time.sleep(self._interval)

    def _publish(self, msg: dict):
        zone_id = msg.get("zone_id", "unknown")
        topic = f"{config.MQTT_TOPIC_PREFIX}/zones/{zone_id}/telemetry"

        if msg.get("sensor_status") == SensorStatus.OFFLINE.value:
            logger.debug("Skipping transmission for offline sensor: %s", zone_id)
            return

        if self._mqtt_client:
            try:
                payload = json.dumps(msg)
                result = self._mqtt_client.publish(topic, payload, qos=config.MQTT_QOS)
                if result.rc != 0:
                    logger.warning("MQTT publish error rc=%d for %s", result.rc, topic)
                    self._stats["publish_failures"] += 1
            except Exception as e:
                logger.warning("MQTT client publish error: %s", e)
                self._stats["publish_failures"] += 1
                if self._direct_callback:
                    self._direct_callback(msg)
        elif self._direct_callback:
            self._direct_callback(msg)


def create_demo_dataset(
    steps: int = 200,
    seed: int = 42,
    interval_sec: float = 5.0,
) -> list[dict]:
    engine = DigitalTwinEngine(seed=seed)
    for zone in create_default_zones():
        engine.add_zone(zone)

    sim = SensorSimulator(engine=engine, interval_sec=interval_sec)
    all_messages = []

    for _ in range(steps):
        messages = sim.generate_one_step()
        all_messages.extend(messages)

    logger.info("Generated %d messages across %d steps", len(all_messages), steps)
    return all_messages
