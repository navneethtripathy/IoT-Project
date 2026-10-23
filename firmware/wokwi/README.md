# CivicTwin-R — Wokwi Simulation

## Files

- `diagram.json` — Circuit diagram (ESP32 DevKit + HC-SR04 ultrasonic sensor + Alert LED)
- `wokwi.toml` — Local forwarding configuration

## Study Area Association & Provenance

- **Virtual Study Zone:** This simulated node (`node_01`) is mapped to **Adyar Basin (`zone_01` / `zone_adyar`)**.
- **Data Provenance:** Telemetry emitted by this simulation is strictly tagged as **`WOKWI_SIMULATED`**.
- It represents a virtual laboratory prototype and does not reflect direct measurements from Chennai's three river systems.

## How to Run

1. Open [wokwi.com](https://wokwi.com)
2. Create a new ESP32 project
3. Replace the default `diagram.json` with `firmware/wokwi/diagram.json`
4. Replace the sketch with `firmware/esp32/src/main.ino`
5. Press the green **Start Simulation** button

## Simulating Water Levels

- Click the HC-SR04 ultrasonic sensor during simulation.
- Use the slider to change the simulated distance.
- **Formulas:**
  - $\text{Water depth (cm)} = 30.0\text{ cm} - \text{measured distance (cm)}$ (clamped to $[0.0, 30.0]$ cm)
  - $\text{Water level (\%)} = 100 \times \frac{\text{Water depth (cm)}}{30.0\text{ cm}}$ (clamped to $[0.0\%, 100.0\%]$)
- **Threshold Testing:**
  - Warning Alert triggered at $\ge 70.0\%$ (depth $\ge 21.0\text{ cm}$, distance $\le 9.0\text{ cm}$). Onboard LED illuminates.
  - Critical Alert triggered at $\ge 85.0\%$ (depth $\ge 25.5\text{ cm}$, distance $\le 4.5\text{ cm}$).
  - Alerts clear with a $3.0\%$ hysteresis band (level must drop below $67.0\%$ to return to normal).
  - *Disclaimer: These are prototype test thresholds, not official flood warning levels for Chennai.*

## MQTT Connectivity

Wokwi provides simulated Wi-Fi (`Wokwi-GUEST`) that can reach MQTT brokers.
- For local Docker broker: Use desktop client port-forwarding or your host machine's LAN IP address.
- When running offline: The firmware maintains local median filtering, threshold evaluation, and LED alerts independently.
