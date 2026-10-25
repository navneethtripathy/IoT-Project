# CivicTwin-R — ESP32 Cyber-Physical Firmware

## Overview

Arduino C++ firmware for the ESP32 paired with the **JSN-SR04T waterproof ultrasonic distance sensor** (or HC-SR04 for desktop simulation).
Reads distance, computes water depth and percentage level, applies local threshold logic with anti-chatter hysteresis, controls an autonomous local warning indicator (LED / buzzer), and publishes structured JSON telemetry over MQTT to dual topic hierarchies (`zones` and `nodes`).

> **Important Deployment & Study Area Disclaimer:**  
> In laboratory simulation mode (Wokwi or test harness), virtual nodes (`node_01` and `node_02`) represent scaled cyber-physical tank prototypes. They do **not** imply that physical hardware has been submerged into Chennai rivers, nor do two laboratory tanks simulate real-time flood inundation across the entire metropolitan area. Hardware tests must be clearly identified as laboratory prototypes.

---

## Sensor Selection: JSN-SR04T Waterproof Ultrasonic Sensor

The project utilizes the **JSN-SR04T waterproof ultrasonic distance transducer**, which replaces consumer HC-SR04 sensors for damp, outdoor, and water-tank monitoring:

| Specification | JSN-SR04T (Physical Hardware) | HC-SR04 (Wokwi Simulation Stand-in) |
|---|---|---|
| **Enclosure** | IP67 sealed waterproof probe with 2.5m coaxial cable | Open transducer mesh (non-waterproof) |
| **Operating Voltage** | 5.0 V DC (from ESP32 VIN / USB rail) | 5.0 V DC |
| **Echo Output Level** | **5.0 V TTL Logic** (Requires voltage divider!) | **5.0 V TTL Logic** (Requires voltage divider!) |
| **Operating Frequency** | 40 kHz | 40 kHz |
| **Blind Distance (Dead Zone)** | **20 cm to 25 cm** | 2 cm |
| **Max Detection Range** | 450 cm (4.5 m) | 400 cm (4.0 m) |
| **Mounting Requirement** | Mount $\ge 25\text{ cm}$ above maximum expected water crest | Mount $\ge 5\text{ cm}$ above crest |

---

## Circuit Wiring & Electrical Protection

| Sensor Pin | ESP32 Pin | Function | Electrical Notes |
|---|---|---|---|
| **VCC** | **VIN (5V)** | Power Supply | JSN-SR04T board requires 5.0V supply |
| **GND** | **GND** | Ground | Common reference ground |
| **TRIG** | **GPIO 5** | Trigger Input | ESP32 3.3V logic level reliably triggers the 5V sensor board |
| **ECHO** | **GPIO 18** | Echo Pulse Output | **⚠ REQUIRES VOLTAGE DIVIDER ON PHYSICAL HARDWARE (5V $\rightarrow$ 3.0V)** |
| **Status LED** | **GPIO 2** | Threshold Alert | Active HIGH (internal LED / external LED via 220Ω resistor) |
| **Rain Pin** | **GPIO 36 (VP)** | Analog Rain Sensor | ADC1 input (0–4095) uncalibrated rain indicator |

### Critical Electrical Safety: 5V Echo Voltage Divider

The ESP32 microcontroller GPIO pins are **NOT 5V tolerant**. Exposing GPIO 18 directly to the 5V Echo pin will degrade or destroy the ESP32 input gate. A passive resistor voltage divider is mandatory:

```
Sensor ECHO (5V TTL) ──┬── [R1: 2.2 kΩ] ──── ESP32 GPIO 18 (3.0V logic)
                       │
                  [R2: 3.3 kΩ]
                       │
                      GND
```

$$V_{\text{out}} = 5.0\text{ V} \times \frac{3.3\text{ k}\Omega}{2.2\text{ k}\Omega + 3.3\text{ k}\Omega} = 5.0\text{ V} \times \frac{3.3}{5.5} = 3.00\text{ V}$$

$3.00\text{ V}$ is safely within the ESP32 input specification ($V_{\text{IH}} \ge 2.45\text{ V}$, $V_{\text{max}} = 3.6\text{ V}$).

---

## Two-Node Laboratory Architecture

The firmware is parameterized to compile for either of the two laboratory tank nodes by toggling `#define NODE_SELECT`:

| Parameter | Node 01 (`NODE_SELECT 1`) | Node 02 (`NODE_SELECT 2`) |
|---|---|---|
| **Device ID** | `node_01` | `node_02` |
| **Physical Tank ID** | `tank_01` | `tank_02` |
| **Associated Basin Zone** | `zone_01` (Saidapet Drainage Runoff) | `zone_02` (Cooum Urban Retention) |
| **Tank Geometry** | Cylindrical $\varnothing 19.54\text{ cm}$ ($A = 300.0\text{ cm}^2$) | Cylindrical $\varnothing 23.94\text{ cm}$ ($A = 450.0\text{ cm}^2$) |
| **Container Depth ($H_{\text{ref}}$)**| $50.0\text{ cm}$ | $60.0\text{ cm}$ |
| **Discharge Coeff ($k$)** | $4.50\text{ cm}^{2.5}/\text{s}$ | $6.00\text{ cm}^{2.5}/\text{s}$ |
| **Inlet Flow Rate ($Q_{\text{in}}$)** | $25.0\text{ cm}^3/\text{s}$ ($1.5\text{ L/min}$) | $35.0\text{ cm}^3/\text{s}$ ($2.1\text{ L/min}$) |
| **Warning Threshold** | $70.0\%$ ($35.0\text{ cm}$) | $70.0\%$ ($42.0\text{ cm}$) |
| **Critical Threshold** | $85.0\%$ ($42.5\text{ cm}$) | $85.0\%$ ($51.0\text{ cm}$) |
| **Telemetry Topics** | `civictwin/v1/zones/zone_01/telemetry`<br>`civictwin/v1/nodes/node_01/telemetry` | `civictwin/v1/zones/zone_02/telemetry`<br>`civictwin/v1/nodes/node_02/telemetry` |

---

## Water Level Calculation & Geometry

The downward-facing ultrasonic sensor measures distance $D$ from the probe face to the water surface:

$$\text{Water Depth (cm)} = H_{\text{ref}} - D_{\text{measured}}$$
$$\text{Water Level (\%)} = 100 \times \frac{\text{Water Depth (cm)}}{H_{\text{ref}}}$$

- **Boundaries:** Depth clamped to $[0.0, H_{\text{ref}}]\text{ cm}$; Percentage clamped to $[0.0\%, 100.0\%]$.
- **Invalid Readings:** Echo timeouts or distances outside $[S_{\text{min}}, 400.0]\text{ cm}$ trigger outlier rejection and are marked `sensor_status: "invalid"`. Null values (`nullptr` / `None`) are published rather than fabricating a false zero-depth reading.

---

## Edge Warning Logic with Hysteresis

To prevent alert chatter when water ripples or surface fluctuations occur near the alert boundaries:
- **Warning Threshold:** $\ge 70.0\%$
- **Critical Threshold:** $\ge 85.0\%$
- **Anti-Chatter Hysteresis Band:** $3.0\%$
  - Warning alert only clears when water level drops below $70.0\% - 3.0\% = 67.0\%$.
  - Critical alert only drops to Warning when level drops below $85.0\% - 3.0\% = 82.0\%$.
- **Offline Autonomy:** Warning evaluation occurs locally in the micro-controller loop independent of Wi-Fi or MQTT broker connectivity. If network connectivity fails, GPIO 2 activates immediately upon breach.
