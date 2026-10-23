# CivicTwin-R — MQTT Topic Contract

## Topic Hierarchy

All topics use the prefix `civictwin/v1/` followed by a resource path.

```
civictwin/v1/zones/{zone_id}/telemetry    — Sensor readings
civictwin/v1/zones/{zone_id}/status       — Device health reports
civictwin/v1/zones/{zone_id}/alerts       — Threshold-crossing alerts
```

## Topic Details

### `civictwin/v1/zones/{zone_id}/telemetry`

**Direction:** Device → Broker → Backend  
**QoS:** 1 (at-least-once)  
**Retain:** false  
**Frequency:** Every 5 seconds (configurable per device)

Payload: See Data Dictionary — Telemetry Message Schema v1.0

Example:
```json
{
  "schema_version": "1.0",
  "device_id": "node_01",
  "zone_id": "zone_01",
  "sequence": 1024,
  "timestamp": "2026-01-15T10:30:00Z",
  "distance_cm": 12.4,
  "water_level_cm": 17.6,
  "water_level_pct": 58.7,
  "sensor_status": "valid",
  "source": "wokwi"
}
```

### `civictwin/v1/zones/{zone_id}/status`

**Direction:** Device → Broker → Backend  
**QoS:** 1  
**Retain:** true (so new subscribers get the last known status)  
**Frequency:** Every 30 seconds

```json
{
  "device_id": "node_01",
  "wifi": true,
  "mqtt": true,
  "uptime_sec": 3600,
  "sequence": 720,
  "alert_state": "normal",
  "heap_free": 245760
}
```

### `civictwin/v1/zones/{zone_id}/alerts`

**Direction:** Device → Broker → Backend  
**QoS:** 1  
**Retain:** false

```json
{
  "zone_id": "zone_01",
  "device_id": "node_01",
  "alert_level": "warning",
  "water_pct": 72.5,
  "threshold": 70.0,
  "timestamp": "2026-01-15T10:30:05Z"
}
```

## QoS Rationale

- **QoS 1 (at-least-once):** Chosen as the balance between reliability and
  overhead. Telemetry messages include a sequence number for duplicate
  detection, so receiving the same message twice is harmless.
- **QoS 0** would risk silent data loss during network instability.
- **QoS 2** adds significant overhead and latency for marginal benefit in
  a monitoring context.

## Retain Rationale

- **Telemetry:** Not retained. New subscribers should get fresh data, not
  a potentially stale historical reading.
- **Status:** Retained so that a newly connecting dashboard or backend
  immediately gets the last known device status.
- **Alerts:** Not retained. Alerts are events, not persistent state.

## Testing Commands

```bash
# Subscribe to all telemetry (requires mosquitto-clients)
mosquitto_sub -h localhost -t "civictwin/v1/zones/+/telemetry" -v

# Subscribe to all topics
mosquitto_sub -h localhost -t "civictwin/v1/#" -v

# Publish a test message
mosquitto_pub -h localhost -t "civictwin/v1/zones/zone_01/telemetry" \
  -m '{"schema_version":"1.0","device_id":"test","zone_id":"zone_01","sequence":1,"timestamp":"2026-01-15T10:00:00Z","water_level_pct":50.0,"sensor_status":"valid","source":"simulator"}'

# Use the Python test publisher
python3 mqtt/examples/test_publisher.py --count 20 --interval 2
```
