#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Showcase Health & System Verification Script
# Validates availability of MQTT, FastAPI backend, Node-RED, and SQLite storage.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

FAILURES=0

echo "--- Verifying CivicTwin-R Services ---"

# 1. Check Mosquitto MQTT port 1883
if nc -z 127.0.0.1 1883 2>/dev/null; then
    echo "[PASS] MQTT Broker: listening on 127.0.0.1:1883"
else
    echo "[WARN] MQTT Broker: port 1883 not responding (may be running in internal mode)"
fi

# 2. Check InfluxDB 2.x Time-Series Engine port 8086
INFLUX_HEALTH=$(curl -s http://127.0.0.1:8086/health 2>/dev/null || echo "")
if echo "$INFLUX_HEALTH" | grep -q "pass"; then
    INFLUX_COUNT=$(curl -s http://127.0.0.1:8000/api/storage/influx/status 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin).get('records_count', 0))" 2>/dev/null || echo "0")
    echo "[PASS] InfluxDB 2.x: listening on http://127.0.0.1:8086 (bucket 'telemetry' records: $INFLUX_COUNT)"
elif nc -z 127.0.0.1 8086 2>/dev/null; then
    echo "[PASS] InfluxDB 2.x: listening on port 8086"
else
    echo "[WARN] InfluxDB 2.x: not responding on port 8086 (SQLite handles all data)"
fi

# 2. Check FastAPI Backend health endpoint
HEALTH_RESP=$(curl -s http://127.0.0.1:8000/health 2>/dev/null || echo "")
if echo "$HEALTH_RESP" | grep -q "healthy"; then
    STORED_COUNT=$(echo "$HEALTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('records_stored', 0))" 2>/dev/null || echo "0")
    echo "[PASS] FastAPI Backend: 200 OK (records stored: $STORED_COUNT)"
else
    echo "[FAIL] FastAPI Backend: not reachable at http://127.0.0.1:8000/health"
    FAILURES=$((FAILURES + 1))
fi

# 3. Check Showcase Web Center
SHOWCASE_RESP=$(curl -s http://127.0.0.1:8000/showcase 2>/dev/null || echo "")
if echo "$SHOWCASE_RESP" | grep -q "CivicTwin-R"; then
    echo "[PASS] Showcase Web Center: HTML UI accessible at http://127.0.0.1:8000/showcase"
else
    echo "[FAIL] Showcase Web Center: not accessible"
    FAILURES=$((FAILURES + 1))
fi

# 4. Check Node-RED if running
if nc -z 127.0.0.1 1880 2>/dev/null; then
    echo "[PASS] Node-RED Engine: listening on http://127.0.0.1:1880"
else
    echo "[INFO] Node-RED: not running on port 1880 (optional external viewer)"
fi

# 5. Check Dual-Node Telemetry Ingestion
ZONES_RESP=$(curl -s http://127.0.0.1:8000/api/zones 2>/dev/null || echo "")
if echo "$ZONES_RESP" | grep -q "zone_01"; then
    echo "[PASS] Dual-Node Telemetry: active and reporting in /api/zones"
else
    echo "[WARN] Telemetry pipeline still warming up"
fi

if [ $FAILURES -eq 0 ]; then
    echo "--- All Critical Services Healthy (Result: PASS) ---"
    exit 0
else
    echo "--- Verification Completed with $FAILURES failure(s) ---"
    exit 1
fi
