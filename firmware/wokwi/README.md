# CivicTwin-R — Wokwi Simulation

## Files

- `diagram.json` — Circuit diagram (ESP32 + HC-SR04 + LED)

## How to Run

1. Open [wokwi.com](https://wokwi.com)
2. Create a new ESP32 project
3. Replace the default `diagram.json` with this file
4. Replace the sketch with `firmware/esp32/src/main.ino`
5. Press the green Run button

## Simulating Water Levels

- Click the HC-SR04 sensor in the simulation
- Use the distance slider to change the measured distance
- Smaller distance = higher water level
- Formula: `water_level = 30.0 - distance` (cm)

## MQTT Connectivity

Wokwi provides simulated WiFi that can reach public MQTT brokers.
The default configuration uses `test.mosquitto.org`.

**To use a local broker:** Replace `MQTT_BROKER` with your machine's
public IP address (not `localhost` — Wokwi can't resolve it).

## Wokwi Configuration File

Create a `wokwi.toml` in the Wokwi project root if needed:

```toml
[wokwi]
version = 1

[[net.forward]]
from = "localhost:1883"
to = "host.wokwi.internal:1883"
```

This forwards Wokwi's localhost:1883 to your host machine's port 1883,
but requires the Wokwi desktop client or Wokwi for VS Code extension.
