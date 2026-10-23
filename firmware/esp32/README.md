# CivicTwin-R — ESP32 Firmware

## Overview

Arduino firmware for ESP32 with HC-SR04 ultrasonic distance sensor.
Reads water level, applies local threshold logic with hysteresis, and
publishes JSON telemetry over MQTT.

## Wiring (Physical Hardware)

| HC-SR04 Pin | ESP32 Pin | Notes |
|-------------|-----------|-------|
| VCC | VIN (5V) | HC-SR04 requires 5V |
| GND | GND | Common ground |
| TRIG | GPIO 5 | 3.3V output is sufficient for TRIG |
| ECHO | GPIO 18 | **⚠ REQUIRES VOLTAGE DIVIDER** |

### Voltage Protection

The HC-SR04 ECHO pin outputs 5V logic. The ESP32 GPIO is 3.3V tolerant.
For physical deployment, use a voltage divider:

```
HC-SR04 ECHO ──┬── 2.2kΩ ──── ESP32 GPIO 18
               │
              3.3kΩ
               │
              GND
```

Output voltage: 5V × 3.3k / (2.2k + 3.3k) ≈ 3.0V (safe for ESP32)

**In Wokwi simulation, no voltage divider is needed.**

## Building

### Wokwi (Recommended for Demo)

1. Go to [wokwi.com](https://wokwi.com) → New Project → ESP32
2. Replace `diagram.json` with `firmware/wokwi/diagram.json`
3. Paste `firmware/esp32/src/main.ino` into the code editor
4. Click Run
5. Adjust the HC-SR04 slider to simulate water level changes

### PlatformIO (Physical Hardware)

```bash
# Install PlatformIO
pip install platformio

# Build and upload
cd firmware/esp32
pio run -t upload
```

## Configuration

Edit these constants in `main.ino`:

| Constant | Default | Description |
|----------|---------|-------------|
| `WIFI_SSID` | `"Wokwi-GUEST"` | WiFi network name |
| `MQTT_BROKER` | `"test.mosquitto.org"` | MQTT broker hostname |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `CONTAINER_HEIGHT_CM` | `30.0` | Channel/container height |
| `READ_INTERVAL_MS` | `5000` | Sensor read interval (ms) |
| `WARN_THRESHOLD_PCT` | `70.0` | Warning threshold (%) |
| `CRIT_THRESHOLD_PCT` | `85.0` | Critical threshold (%) |

## Features

- Median filtering (5 readings) for noise reduction
- Local threshold evaluation with hysteresis (±5%)
- Continues threshold checking when MQTT is disconnected
- Invalid readings are NOT treated as zero water level
- Periodic status reports (uptime, heap, alert state)
- Non-blocking WiFi and MQTT reconnection
