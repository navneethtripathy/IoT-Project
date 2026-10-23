# CivicTwin-R — Testing Guide

## Test Suite Overview

The project uses pytest with 48 tests across 7 test classes.

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run a specific test class
python3 -m pytest tests/test_all.py::TestZoneModel -v

# Run with coverage (if pytest-cov installed)
python3 -m pytest tests/ --cov=backend --cov=digital_twin -v
```

## Test Categories

### Unit Tests

| Class | Tests | What it covers |
|-------|-------|---------------|
| `TestZoneModel` | 10 | Digital twin zone physics, clamping, sensor/network failure |
| `TestDigitalTwinEngine` | 5 | Multi-zone management, determinism, parameter injection |
| `TestScenarios` | 6 | Scenario definitions, controller lifecycle, completion |
| `TestReconstruction` | 11 | LOCF, linear interp, masking, evaluation, data leakage |
| `TestModels` | 4 | Pydantic validation, clamping, ISO timestamp parsing |
| `TestStorage` | 5 | SQLite and memory backends, duplicate rejection, queries |
| `TestIngestion` | 5 | Message processing, validation, duplicates, alerts |

### Integration Tests

| Class | Tests | What it covers |
|-------|-------|---------------|
| `TestIntegration` | 2 | End-to-end simulator → ingestion → storage pipeline; scenario data production |

## Key Test Guarantees

1. **Determinism:** Two runs with the same seed produce identical results
2. **No data leakage:** Reconstruction algorithms never see hidden ground truth
3. **Duplicate rejection:** Same (device_id, sequence) is stored only once
4. **Threshold correctness:** Critical and warning levels trigger at correct percentages
5. **Physical bounds:** Water level is always clamped to [0, container_height]
6. **Schema validation:** Invalid messages are rejected with clear errors

## Manual Testing

### API Endpoints (backend must be running)

```bash
# Health check
curl http://127.0.0.1:8000/health | python3 -m json.tool

# List zones
curl http://127.0.0.1:8000/api/zones | python3 -m json.tool

# Latest telemetry
curl http://127.0.0.1:8000/api/telemetry/latest | python3 -m json.tool

# Start a scenario
curl -X POST http://127.0.0.1:8000/api/scenarios/heavy_rainfall/start

# Advance scenario
curl -X POST "http://127.0.0.1:8000/api/scenarios/step?steps=50"

# View alerts
curl http://127.0.0.1:8000/api/alerts | python3 -m json.tool

# System statistics
curl http://127.0.0.1:8000/api/stats | python3 -m json.tool
```
