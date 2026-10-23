# CivicTwin-R

**A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning**

*Team #5 — Internet of Things (IoT) Course Project*

---

## Overview

CivicTwin-R is an IoT-based flood monitoring system that demonstrates how a digital twin can maintain useful monitoring and warning capability when sensors fail, readings are missing, or network connectivity is lost.

**Core research question:** How can an IoT-based flood-monitoring digital twin maintain useful monitoring and warning capability when sensor readings are missing, unreliable, or temporarily disconnected?

### Key Features

- **3 Virtual Monitoring Zones** — Riverside Canal, Downtown Storm Drain, Suburban Retention Basin
- **8 Configurable Scenarios** — Normal, heavy rainfall, blocked drain, sudden rise, sensor dropout, noisy sensor, network outage, multi-zone stress
- **2 Reconstruction Methods** — LOCF and linear interpolation evaluated against hidden ground truth
- **Complete Data Pipeline** — ESP32 → MQTT → Ingestion → Storage → Dashboard
- **Resilience Testing** — Sensor failure, network outage, stale data detection, local threshold evaluation
- **48 Automated Tests** — All passing
- **Reproducible Experiments** — Deterministic with seed=42

---

## Quick Start

```bash
cd CivicTwin-R

# Install dependencies
python3 -m pip install -e ".[dev]"

# Run tests
python3 -m pytest tests/ -v

# Run experiments and generate plots
python3 -m experiments.run_experiments

# Start the backend API
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# Open API docs: http://127.0.0.1:8000/docs
# Health check:  http://127.0.0.1:8000/health
```

## Project Structure

```
CivicTwin-R/
├── README.md                    ← You are here
├── backend/                     ← FastAPI backend, ingestion, storage, simulator
│   ├── app/main.py              ← API endpoints
│   ├── config.py                ← Centralized configuration
│   ├── models.py                ← Pydantic data models
│   ├── ingestion.py             ← MQTT message processing
│   ├── simulator.py             ← Python sensor simulator
│   └── storage.py               ← Storage abstraction (SQLite/InfluxDB/Memory)
├── digital_twin/                ← Digital twin engine
│   ├── model.py                 ← Zone model and engine
│   ├── scenarios.py             ← 8 configurable scenarios
│   └── reconstruction.py        ← Missing-data reconstruction
├── firmware/                    ← ESP32 firmware
│   ├── esp32/src/main.ino       ← Arduino sketch
│   └── wokwi/diagram.json      ← Wokwi wiring diagram
├── experiments/                 ← Experiment runner
│   └── run_experiments.py       ← Runs all experiments, generates plots
├── nodered/flows.json           ← Node-RED dashboard flows
├── mqtt/mosquitto.conf          ← MQTT broker configuration
├── tests/test_all.py            ← 48 automated tests
├── results/                     ← Generated experiment outputs
│   ├── plots/                   ← Report-ready charts (PNG)
│   └── tables/                  ← JSON/CSV result data
├── docs/                        ← Documentation
├── scripts/                     ← Setup, start, stop, health check
├── reports/                     ← Final report
├── docker-compose.yml           ← Full-stack Docker configuration
├── Makefile                     ← Convenience targets
└── pyproject.toml               ← Python project manifest
```

## Architecture

```
ESP32/Simulator → MQTT (optional) → Ingestion → SQLite/InfluxDB → Dashboard
                                        ↑
                              Digital Twin Engine
                              (3 zones, 8 scenarios)
```

See [docs/architecture.md](docs/architecture.md) for the full architecture diagram.

## Execution Modes

| Mode | Description | Requirements |
|------|-------------|-------------|
| **Mode B (Recommended)** | Backend + simulator standalone | Python 3.11+ only |
| **Mode A** | Full stack with Docker | Docker, Mosquitto, InfluxDB, Node-RED |

Mode B is the default and runs everything with zero external dependencies.

## Team

| Name | Reg. No. | Department |
|------|----------|------------|
| Navneeth Tripathy | 145611085 | B.E. CSE (AI & ML) |
| Keith Rocha | 145611335 | B.E. CSE (AI & ML) |
| Neil Nickson | 145611086 | B.E. CSE (AI & ML) |
| Mohanavel | 145611076 | B.E. CSE (AI & ML) |
| Pandi Devi Naga Pallavi | 145614120 | B.E. CSE with CS |

## Documentation

- [Installation Guide](docs/installation.md)
- [Architecture](docs/architecture.md)
- [Data Dictionary](docs/data_dictionary.md)
- [MQTT Contract](docs/mqtt_contract.md)
- [Testing Guide](docs/testing.md)
- [Demo Script](docs/demo_script.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Limitations](docs/limitations.md)

## License

MIT — See [LICENSE](LICENSE)
