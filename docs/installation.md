# CivicTwin-R — Installation Guide

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | 3.12 or 3.14 tested |
| pip | 22+ | Package installer |
| Git | 2.x | Version control |
| Node.js | 18+ | For Node-RED (optional) |
| Docker | 24+ | For full stack (optional) |

## Quick Start (Mode B — No Docker)

This is the fastest way to get CivicTwin-R running. It uses SQLite for
storage and runs the sensor simulator directly without MQTT.

```bash
# 1. Clone or navigate to the project
cd CivicTwin-R

# 2. Create .env from template
cp .env.example .env

# 3. Install Python dependencies
python3 -m pip install -e ".[dev]"

# 4. Run tests to verify installation
python3 -m pytest tests/ -v

# 5. Run experiments and generate plots
python3 -m experiments.run_experiments

# 6. Start the backend API
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 7. Open in browser
#    API docs: http://127.0.0.1:8000/docs
#    Health:   http://127.0.0.1:8000/health
```

## Full Stack Setup (Mode A — Docker)

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Start all services
docker-compose up -d

# 3. Verify services
python3 scripts/health_check.py

# Services available at:
#   Backend API:  http://127.0.0.1:8000/docs
#   Node-RED:     http://127.0.0.1:1880
#   InfluxDB UI:  http://127.0.0.1:8086
```

## Node-RED Dashboard Setup

If Node-RED is installed (via Docker or standalone):

1. Open Node-RED at http://127.0.0.1:1880
2. Go to Menu → Import → Clipboard
3. Paste the contents of `nodered/flows.json`
4. Click "Import" then "Deploy"
5. Install required dashboard nodes if prompted:
   - `node-red-dashboard` (for Node-RED < 4.0)
   - Or use the built-in `@flowfuse/node-red-dashboard` for Node-RED 4.0+
6. Access the dashboard at http://127.0.0.1:1880/ui

## Wokwi ESP32 Simulation

1. Go to [wokwi.com](https://wokwi.com)
2. Create a new ESP32 project
3. Replace `diagram.json` with `firmware/wokwi/diagram.json`
4. Replace the sketch with `firmware/esp32/src/main.ino`
5. Update `MQTT_BROKER` in the sketch to point to your broker
   - For local testing: Use a public broker like `test.mosquitto.org`
   - For local network: Use your machine's IP address
6. Run the simulation
7. Adjust the HC-SR04 distance slider to simulate water level changes

**Note:** Wokwi's simulated WiFi may not reach a local Mosquitto broker.
Use the Python sensor simulator as the primary data source.

## Troubleshooting

See `docs/troubleshooting.md` for common issues and solutions.
