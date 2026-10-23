"""
CivicTwin-R — MQTT Ingestion Service

Subscribes to telemetry and status topics, validates messages, detects
duplicates and stale readings, and persists to the configured storage backend.

Can run standalone or be started from the FastAPI application.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

from backend.models import (
    TelemetryMessage, IngestedTelemetry, SensorStatus,
    DataSource, Alert, AlertLevel,
)
from backend import config

logger = logging.getLogger("civictwin.ingestion")

# Stale reading threshold
STALE_TIMEOUT = timedelta(seconds=config.STALE_READING_TIMEOUT_SEC)


class IngestionService:
    """
    Validates, deduplicates, and processes incoming MQTT telemetry messages.

    This service can operate with or without a live MQTT connection.
    In offline mode, messages can be fed directly via process_message().
    """

    def __init__(self, storage):
        self._storage = storage
        self._seen_sequences: dict[str, int] = {}  # device_id -> last sequence
        self._last_timestamps: dict[str, datetime] = {}  # device_id -> last ts
        self._zone_status: dict[str, dict] = {}
        self._alerts: list[Alert] = []
        self._stats = {
            "messages_received": 0,
            "messages_valid": 0,
            "messages_invalid": 0,
            "messages_duplicate": 0,
            "messages_stale": 0,
            "messages_stored": 0,
        }
        self._callbacks: list[Callable] = []
        self._lock = threading.Lock()
        logger.info("IngestionService initialized")

    @property
    def stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    @property
    def alerts(self) -> list[Alert]:
        with self._lock:
            return list(self._alerts)

    @property
    def zone_status(self) -> dict:
        with self._lock:
            return dict(self._zone_status)

    def add_callback(self, cb: Callable):
        """Register a callback to be invoked on each valid ingested message."""
        self._callbacks.append(cb)

    def process_raw(self, topic: str, payload: bytes) -> Optional[IngestedTelemetry]:
        """Process a raw MQTT message (topic + payload bytes)."""
        with self._lock:
            self._stats["messages_received"] += 1

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("Malformed JSON payload on %s: %s", topic, e)
            with self._lock:
                self._stats["messages_invalid"] += 1
            return None

        return self.process_message(data)

    def process_message(self, data: dict) -> Optional[IngestedTelemetry]:
        """
        Validate and process a telemetry message dict.

        Returns the ingested record on success, None on failure.
        """
        ingestion_ts = datetime.now(timezone.utc)

        # ── Schema validation ──────────────────────────
        try:
            msg = TelemetryMessage(**data)
        except Exception as e:
            logger.warning("Schema validation failed: %s", e)
            with self._lock:
                self._stats["messages_invalid"] += 1
            return None

        # ── Duplicate detection ────────────────────────
        device_key = msg.device_id
        is_duplicate = False
        with self._lock:
            last_seq = self._seen_sequences.get(device_key, -1)
            if msg.sequence <= last_seq:
                self._stats["messages_duplicate"] += 1
                is_duplicate = True
                logger.debug(
                    "Duplicate: %s seq=%d (last=%d)", device_key, msg.sequence, last_seq
                )
            else:
                self._seen_sequences[device_key] = msg.sequence

        if is_duplicate:
            return None

        # ── Stale detection ────────────────────────────
        is_stale = False
        with self._lock:
            last_ts = self._last_timestamps.get(device_key)
            if last_ts and (ingestion_ts - msg.timestamp) > STALE_TIMEOUT:
                is_stale = True
                self._stats["messages_stale"] += 1
            self._last_timestamps[device_key] = msg.timestamp

        # ── Quality flags ──────────────────────────────
        quality_flags = list(msg.quality_flags)
        if is_stale:
            quality_flags.append("stale")
        if msg.sensor_status == SensorStatus.INVALID:
            quality_flags.append("invalid_reading")
        if msg.water_level_pct is not None and (msg.water_level_pct < 0 or msg.water_level_pct > 100):
            quality_flags.append("out_of_range")

        # ── Create ingested record ─────────────────────
        msg_data = msg.model_dump()
        msg_data.pop("quality_flags", None)  # We override with enriched flags
        record = IngestedTelemetry(
            **msg_data,
            ingestion_timestamp=ingestion_ts,
            is_duplicate=False,
            is_stale=is_stale,
            quality_flags=quality_flags,
        )

        # ── Persist ────────────────────────────────────
        stored = self._storage.store(record)
        with self._lock:
            self._stats["messages_valid"] += 1
            if stored:
                self._stats["messages_stored"] += 1

        # ── Update zone status ─────────────────────────
        self._update_zone_status(record)

        # ── Check thresholds ───────────────────────────
        self._check_thresholds(record)

        # ── Notify callbacks ───────────────────────────
        for cb in self._callbacks:
            try:
                cb(record)
            except Exception:
                logger.exception("Callback error")

        return record

    def _update_zone_status(self, record: IngestedTelemetry):
        """Track the latest status for each zone."""
        with self._lock:
            self._zone_status[record.zone_id] = {
                "zone_id": record.zone_id,
                "device_id": record.device_id,
                "sensor_status": record.sensor_status.value,
                "water_level_pct": record.water_level_pct,
                "water_level_cm": record.water_level_cm,
                "source": record.source.value,
                "last_update": record.ingestion_timestamp.isoformat(),
                "is_stale": record.is_stale,
                "quality_flags": record.quality_flags,
            }

    def _check_thresholds(self, record: IngestedTelemetry):
        """Evaluate water-level thresholds and generate alerts."""
        if record.water_level_pct is None:
            return
        if record.sensor_status in (SensorStatus.INVALID, SensorStatus.OFFLINE):
            return

        pct = record.water_level_pct
        alert_level = AlertLevel.NORMAL

        if pct >= config.WATER_LEVEL_CRIT_PCT:
            alert_level = AlertLevel.CRITICAL
        elif pct >= config.WATER_LEVEL_WARN_PCT:
            alert_level = AlertLevel.WARNING

        if alert_level != AlertLevel.NORMAL:
            alert = Alert(
                alert_id=f"alert_{record.zone_id}_{record.sequence}",
                zone_id=record.zone_id,
                device_id=record.device_id,
                alert_level=alert_level,
                water_level_pct=pct,
                threshold_pct=(
                    config.WATER_LEVEL_CRIT_PCT
                    if alert_level == AlertLevel.CRITICAL
                    else config.WATER_LEVEL_WARN_PCT
                ),
                message=f"Zone {record.zone_id}: water level at {pct:.1f}% "
                        f"({alert_level.value})",
            )
            with self._lock:
                self._alerts.append(alert)
                # Keep only last 100 alerts
                if len(self._alerts) > 100:
                    self._alerts = self._alerts[-100:]
            logger.warning("ALERT: %s", alert.message)

    def get_health(self) -> dict:
        """Return service health and statistics."""
        return {
            "status": "running",
            "stats": self.stats,
            "zones_tracked": len(self._zone_status),
            "active_alerts": sum(
                1 for a in self._alerts if not a.acknowledged
            ),
        }


class MQTTIngestionClient:
    """
    MQTT client that connects to the broker and feeds messages into
    the IngestionService. Handles connection, reconnection, and
    subscription management.
    """

    def __init__(self, ingestion: IngestionService):
        self._ingestion = ingestion
        self._client = None
        self._connected = False
        self._topic_prefix = config.MQTT_TOPIC_PREFIX

    def start(self) -> bool:
        """Start the MQTT client and subscribe to topics."""
        try:
            import paho.mqtt.client as mqtt

            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=config.MQTT_CLIENT_ID + "_ingestion",
            )

            if config.MQTT_USERNAME:
                self._client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)

            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            self._client.connect_async(config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT)
            self._client.loop_start()
            logger.info(
                "MQTT client connecting to %s:%d",
                config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT,
            )
            return True
        except Exception as e:
            logger.warning("MQTT client start failed: %s", e)
            return False

    def stop(self):
        """Stop the MQTT client."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("MQTT client stopped")

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            self._connected = True
            # Subscribe to all zone telemetry
            topic = f"{self._topic_prefix}/zones/+/telemetry"
            client.subscribe(topic, qos=config.MQTT_QOS)
            logger.info("MQTT connected, subscribed to %s", topic)
        else:
            logger.error("MQTT connection failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._connected = False
        logger.warning("MQTT disconnected (rc=%s)", reason_code)

    def _on_message(self, client, userdata, msg):
        self._ingestion.process_raw(msg.topic, msg.payload)
