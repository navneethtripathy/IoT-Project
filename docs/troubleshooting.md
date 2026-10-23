# CivicTwin-R — Troubleshooting Guide

## Common Issues

### "ModuleNotFoundError: No module named 'backend'"

**Cause:** Python can't find the project modules.

**Fix:** Run commands from the `CivicTwin-R/` directory, or install with:
```bash
cd CivicTwin-R
python3 -m pip install -e ".[dev]"
```

### "Connection refused" when starting the backend

**Cause:** MQTT broker is not running. This is OK — the backend falls back
to direct mode.

**Fix:** The warning `"MQTT broker not available — running in direct/offline mode"`
is informational. The backend works without MQTT using direct callbacks.

### Tests fail with import errors

**Fix:**
```bash
cd CivicTwin-R
python3 -m pip install -e ".[dev]"
python3 -m pytest tests/ -v
```

### Node-RED dashboard shows no data

**Cause:** The FastAPI backend is not running.

**Fix:**
1. Start the backend: `python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`
2. Verify: `curl http://127.0.0.1:8000/health`
3. Reimport flows if needed: Node-RED → Menu → Import → `nodered/flows.json`

### InfluxDB connection errors

**Cause:** InfluxDB is not running or token is incorrect.

**Fix:** Set `INFLUXDB_ENABLED=false` in `.env` to use SQLite fallback.
The backend works identically with SQLite.

### Wokwi simulation can't reach local MQTT

**Cause:** Wokwi's simulated WiFi runs in a sandbox and can't access
`localhost` on your machine.

**Fix:** Use the Python sensor simulator instead:
```bash
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
This automatically starts the built-in simulator. For Wokwi, point the
firmware's `MQTT_BROKER` to a public broker like `test.mosquitto.org`.

### Port already in use

```bash
# Find what's using port 8000
lsof -i :8000

# Kill it
kill -9 <PID>
```

### Experiment plots not generated

**Cause:** matplotlib is not installed.

**Fix:**
```bash
python3 -m pip install matplotlib
python3 -m experiments.run_experiments
```
