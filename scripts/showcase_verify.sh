#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Showcase Health & Full Stack Verification Script
# Validates MQTT, InfluxDB, FastAPI, Geospatial/DEM Layers, Terrain Engine, Node-RED, and SQLite.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

FAILURES=0

echo "--- Verifying CivicTwin-R Full-Stack Services ---"

# 1. Check Mosquitto MQTT port 1883
if nc -z 127.0.0.1 1883 2>/dev/null; then
    echo "[PASS] MQTT Broker: listening on 127.0.0.1:1883"
else
    echo "[FAIL] MQTT Broker: port 1883 not listening"
    FAILURES=$((FAILURES + 1))
fi

# 2. Check InfluxDB 2.x Time-Series Engine port 8086
INFLUX_HEALTH=$(curl -s http://127.0.0.1:8086/health 2>/dev/null || echo "")
if echo "$INFLUX_HEALTH" | grep -q "pass"; then
    INFLUX_JSON=$(curl -s http://127.0.0.1:8000/api/storage/influx/status 2>/dev/null || echo "{}")
    INFLUX_COUNT=$(echo "$INFLUX_JSON" | python3 -c "import sys, json; print(json.load(sys.stdin).get('records_count', 0))" 2>/dev/null || echo "0")
    echo "[PASS] InfluxDB 2.x: healthy on http://127.0.0.1:8086 (bucket 'telemetry' records: $INFLUX_COUNT)"
else
    echo "[WARN] InfluxDB 2.x: not healthy on port 8086"
fi

# 3. Check FastAPI Backend health endpoint & live MQTT linkage
HEALTH_RESP=$(curl -s http://127.0.0.1:8000/health 2>/dev/null || echo "")
if echo "$HEALTH_RESP" | grep -q "healthy"; then
    STORED_COUNT=$(echo "$HEALTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('records_stored', 0))" 2>/dev/null || echo "0")
    MQTT_OK=$(echo "$HEALTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('mqtt_connected', False))" 2>/dev/null || echo "False")
    echo "[PASS] FastAPI Backend: 200 OK (SQLite records: $STORED_COUNT, MQTT linked: $MQTT_OK)"
else
    echo "[FAIL] FastAPI Backend: not reachable at http://127.0.0.1:8000/health"
    FAILURES=$((FAILURES + 1))
fi

# 4. Check Urban 3D Twin & Showcase Templates + Offline Vendor Bundles
if curl -s http://127.0.0.1:8000/urban-twin | grep -q "Chennai 3D Urban Flood Digital Twin"; then
    echo "[PASS] Chennai 3D Urban Twin UI: /urban-twin served cleanly"
else
    echo "[FAIL] Chennai 3D Urban Twin UI: /urban-twin failed"
    FAILURES=$((FAILURES + 1))
fi

if curl -s http://127.0.0.1:8000/showcase | grep -q "CivicTwin-R"; then
    echo "[PASS] Showcase Hub UI: /showcase served cleanly"
else
    echo "[FAIL] Showcase Hub UI: /showcase failed"
    FAILURES=$((FAILURES + 1))
fi

# 5. Check Processed Geospatial Assets & Terrain Simulation Engine
GEO_STATUS=$(curl -s http://127.0.0.1:8000/api/urban/geo/dem_metadata 2>/dev/null || echo "")
if echo "$GEO_STATUS" | grep -q "EPSG:32644"; then
    echo "[PASS] Geospatial DEM Metadata: EPSG:32644 UTM 44N grid ready"
else
    echo "[FAIL] Geospatial DEM Metadata missing"
    FAILURES=$((FAILURES + 1))
fi

SCEN_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/urban/scenario -H "Content-Type: application/json" -d '{"scenario_id":"heavy_rainfall"}')
if [ "$SCEN_CODE" = "200" ]; then
    echo "[PASS] Terrain Hydrological Engine (Landlab 2D): POST /api/urban/scenario -> 200 OK"
else
    echo "[FAIL] Terrain Hydrological Engine returned HTTP $SCEN_CODE"
    FAILURES=$((FAILURES + 1))
fi

# 6. Check Node-RED Flow Editor & Dashboard UI
NR_UI_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:1880/ui/)
if [ "$NR_UI_CODE" = "200" ]; then
    echo "[PASS] Node-RED Dashboard: HTTP 200 on http://127.0.0.1:1880/ui/"
elif nc -z 127.0.0.1 1880 2>/dev/null; then
    echo "[WARN] Node-RED listening on 1880 but /ui returned $NR_UI_CODE"
else
    echo "[INFO] Node-RED: not running on port 1880"
fi

# 7. Check Dual-Node Live Telemetry Ingestion & InfluxDB presence
ZONES_RESP=$(curl -s http://127.0.0.1:8000/api/zones 2>/dev/null || echo "")
if echo "$ZONES_RESP" | grep -q "zone_01" && echo "$ZONES_RESP" | grep -q "zone_02"; then
    echo "[PASS] Dual-Node Telemetry: zone_01 & zone_02 reporting in /api/zones"
else
    echo "[WARN] Telemetry zones still warming up"
fi

if [ $FAILURES -eq 0 ]; then
    echo "--- All Critical Services Healthy (Result: PASS) ---"
    exit 0
else
    echo "--- Verification Completed with $FAILURES failure(s) ---"
    exit 1
fi
