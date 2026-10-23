# CivicTwin-R — System Architecture

## Overview

CivicTwin-R is a cyber-physical digital twin system for urban flood monitoring.
It follows a layered pipeline architecture with clear separation of concerns.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  ESP32 +     │  │   Python     │  │   Digital Twin     │    │
│  │  HC-SR04     │  │   Sensor     │  │   Engine           │    │
│  │  (Wokwi)    │  │   Simulator  │  │   (3 virtual zones)│    │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘    │
│         │                 │                    │                │
│         │    JSON/MQTT    │   Direct callback  │                │
└─────────┼─────────────────┼────────────────────┼────────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MESSAGING LAYER                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Mosquitto MQTT Broker (port 1883)                       │   │
│  │  Topics: civictwin/v1/zones/{zone_id}/telemetry          │   │
│  │          civictwin/v1/zones/{zone_id}/status              │   │
│  │          civictwin/v1/zones/{zone_id}/alerts              │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │                                   │
│         OR direct callback when MQTT unavailable                │
└─────────────────────────────┼───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PROCESSING LAYER                              │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Ingestion Service                                     │     │
│  │  • Schema validation (Pydantic)                        │     │
│  │  • Duplicate detection (device_id + sequence)          │     │
│  │  • Stale reading detection (30s timeout)               │     │
│  │  • Quality flag enrichment                             │     │
│  │  • Threshold alert generation                          │     │
│  └────────────────────┬───────────────────────────────────┘     │
│                       │                                         │
│  ┌────────────────────▼───────────────────────────────────┐     │
│  │  FastAPI Backend (port 8000)                            │     │
│  │  • REST API endpoints                                   │     │
│  │  • Scenario management                                  │     │
│  │  • Zone status aggregation                              │     │
│  │  • Experiment results serving                           │     │
│  └────────────────────┬───────────────────────────────────┘     │
└────────────────────────┼────────────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
┌──────────────┐  ┌────────────┐  ┌──────────────┐
│   SQLite     │  │  InfluxDB  │  │  In-Memory   │
│  (default)   │  │  (optional)│  │  (testing)   │
│  Fallback    │  │  2.x       │  │              │
└──────────────┘  └────────────┘  └──────────────┘

                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                            │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Node-RED Dashboard (port 1880)                          │   │
│  │  • System overview & health                              │   │
│  │  • Per-zone water level gauges                           │   │
│  │  • Scenario controls (start/stop/step)                   │   │
│  │  • Alert display                                         │   │
│  │  Polls FastAPI backend every 5–10 seconds                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  FastAPI Swagger UI (/docs)                              │   │
│  │  Interactive API documentation                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Execution Modes

### Mode A — Full Local Integration
All services running: Mosquitto, InfluxDB, Node-RED, backend.
ESP32 or Python simulator publishes via MQTT.

### Mode B — Demo / Offline Development
Backend runs standalone with SQLite storage.
Simulator feeds data directly into ingestion via callback.
No Docker, MQTT broker, or InfluxDB required.

## Component Summary

| Component | Technology | Port | Required? |
|-----------|-----------|------|-----------|
| Sensor Simulator | Python | — | Yes (replaces ESP32) |
| MQTT Broker | Mosquitto 2.0 | 1883 | Optional (Mode A) |
| Backend API | FastAPI + Uvicorn | 8000 | Yes |
| Time-Series DB | InfluxDB 2.7 | 8086 | Optional |
| Fallback DB | SQLite | — | Default |
| Dashboard | Node-RED 4.0 | 1880 | Optional |
| Digital Twin | Python | — | Embedded in backend |

## Data Flow

1. Sensor (physical or simulated) produces a distance measurement
2. Distance is converted to water depth: `depth = container_height - distance`
3. Depth is normalized to percentage: `pct = (depth / container_height) × 100`
4. JSON telemetry message is published (MQTT or direct)
5. Ingestion service validates, deduplicates, and enriches the message
6. Record is persisted to storage (SQLite or InfluxDB)
7. Threshold alerts are generated when levels exceed configured limits
8. Dashboard polls the API and displays current zone states
