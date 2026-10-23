# CivicTwin-R — Limitations and Verification Checklist

## Known Limitations

### Hardware
- **No physical ESP32 tested.** All sensor data is from the Python simulator
  or Wokwi. Physical HC-SR04 echo pin requires a voltage divider (5V → 3.3V)
  that has not been verified with real hardware.
- **Wokwi networking.** The Wokwi simulator's WiFi sandbox cannot reach a
  local Mosquitto broker. A public broker or the Python simulator must be used.

### Networking
- **Simulated outages only.** Network outage tests modify the
  `network_availability` parameter in the digital twin. This simulates the
  *effect* of an outage, not a real WiFi or TCP disconnection.
- **No real MQTT broker tested.** The development environment does not have
  Mosquitto installed. MQTT functionality is implemented but untested with a
  live broker.

### Digital Twin
- **Simplified physics.** The water-level model uses a linear
  inflow-minus-drainage equation. It does not model hydraulic dynamics,
  pipe friction, terrain, or weather. It is a controlled approximation
  for demonstration purposes.
- **No external data integration.** Real weather APIs, river gauge data, or
  GIS systems are not integrated.

### Reconstruction
- **Baseline methods only.** LOCF and linear interpolation are well-known
  baselines. No advanced methods (Kalman filter, ML) are implemented.
  No novelty is claimed.
- **Interpolation during abrupt changes.** Linear interpolation underperforms
  when water levels change rapidly during a gap (e.g., flash flood onset).
  LOCF is even worse in this case — it holds the pre-event level.

### Dashboard
- **Node-RED dashboard not live-tested.** The flows are provided and designed
  to work with the FastAPI backend, but the complete dashboard rendering was
  not verified in a running Node-RED instance during development.
- **No screenshots.** Dashboard screenshots cannot be generated without a
  running Node-RED instance with the dashboard extension.

### Database
- **InfluxDB not tested.** The InfluxDB storage backend is implemented but
  untested because InfluxDB was not available in the development environment.
  SQLite is the verified fallback.

### Security
- **Not production-hardened.** No TLS, no authentication on the API, CORS
  allows all origins. This is a local development prototype.
- **MQTT anonymous access.** The Mosquitto config allows anonymous connections
  for demo convenience.

### Deployment
- **Docker not tested.** Docker was not available in the development
  environment. The `docker-compose.yml` is provided but untested.

## Verification Checklist

| # | Item | Status |
|---|------|--------|
| 1 | Sensor simulator produces valid timestamped readings | ✅ Verified |
| 2 | Readings are validated by ingestion service | ✅ Verified |
| 3 | Duplicate messages are rejected | ✅ Verified |
| 4 | Data persisted to SQLite | ✅ Verified |
| 5 | Data persisted to InfluxDB | ⬜ Not tested (InfluxDB unavailable) |
| 6 | Three digital-twin zones implemented | ✅ Verified |
| 7 | Eight scenarios implemented | ✅ Verified |
| 8 | Scenarios change model behavior predictably | ✅ Verified |
| 9 | LOCF reconstruction implemented | ✅ Verified |
| 10 | Linear interpolation implemented | ✅ Verified |
| 11 | MAE/RMSE computed on held-out points only | ✅ Verified |
| 12 | No data leakage in reconstruction | ✅ Verified |
| 13 | Multiple missing-data rates tested (5/10/20/30%) | ✅ Verified |
| 14 | Threshold alerts generated correctly | ✅ Verified |
| 15 | Sensor dropout simulation works | ✅ Verified |
| 16 | Network outage simulation works | ✅ Verified |
| 17 | ESP32 firmware compiles in Wokwi | ⬜ Not verified |
| 18 | MQTT message delivery works with live broker | ⬜ Not tested |
| 19 | Node-RED dashboard renders correctly | ⬜ Not tested |
| 20 | Docker Compose starts all services | ⬜ Not tested |
| 21 | 48/48 automated tests pass | ✅ Verified |
| 22 | Experiment results reproducible | ✅ Verified |
| 23 | Plots generated from actual data | ✅ Verified |
| 24 | No credentials in source code | ✅ Verified |
| 25 | FastAPI backend starts successfully | ✅ Verified |
| 26 | API endpoints return correct data | ✅ Verified |
| 27 | Physical HC-SR04 sensor tested | ⬜ Not tested |
