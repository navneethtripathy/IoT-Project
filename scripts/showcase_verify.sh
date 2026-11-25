#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Operational Stack Verification Script
# Validates Mosquitto MQTT, InfluxDB, FastAPI, Geospatial DEM/Landlab Engine,
# Node-RED dashboard, SQLite persistence, and live dual-node telemetry.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

if [ -f ".env" ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
MQTT_PORT="${MQTT_BROKER_PORT:-1883}"
NODERED_PORT="${NODERED_PORT:-1880}"

FAILURES=0

if nc -z 127.0.0.1 "$MQTT_PORT" 2>/dev/null; then
    echo "[PASS] MQTT Broker: listening on 127.0.0.1:${MQTT_PORT}"
else
    echo "[FAIL] MQTT Broker: port ${MQTT_PORT} not listening"
    FAILURES=$((FAILURES + 1))
fi

if curl -sf "http://127.0.0.1:8086/health" | grep -q "pass"; then
    INFLUX_COUNT=$(curl -sf "http://${API_HOST}:${API_PORT}/api/storage/influx/status" | python3 -c "import sys, json; print(json.load(sys.stdin).get('records_count', 0))" 2>/dev/null || echo "0")
    echo "[PASS] InfluxDB 2.x: healthy on http://127.0.0.1:8086 (records: ${INFLUX_COUNT})"
else
    echo "[WARN] InfluxDB 2.x: not responding on port 8086"
fi

HEALTH_RESP=$(curl -sf "http://${API_HOST}:${API_PORT}/health" || echo "")
if echo "$HEALTH_RESP" | grep -q "healthy"; then
    STORED_COUNT=$(echo "$HEALTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('records_stored', 0))" 2>/dev/null || echo "0")
    MQTT_OK=$(echo "$HEALTH_RESP" | python3 -c "import sys, json; print(json.load(sys.stdin).get('mqtt_connected', False))" 2>/dev/null || echo "False")
    echo "[PASS] FastAPI Backend: healthy (SQLite rows: ${STORED_COUNT}, MQTT connected: ${MQTT_OK})"
else
    echo "[FAIL] FastAPI Backend: unreachable at http://${API_HOST}:${API_PORT}/health"
    FAILURES=$((FAILURES + 1))
fi

if curl -sf "http://${API_HOST}:${API_PORT}/urban-twin" | grep -q "Chennai 3D Urban Flood Digital Twin"; then
    echo "[PASS] Urban Twin UI: /urban-twin OK"
else
    echo "[FAIL] Urban Twin UI: /urban-twin check failed"
    FAILURES=$((FAILURES + 1))
fi

if curl -sf "http://${API_HOST}:${API_PORT}/showcase" | grep -q "CivicTwin-R"; then
    echo "[PASS] Showcase UI: /showcase OK"
else
    echo "[FAIL] Showcase UI: /showcase check failed"
    FAILURES=$((FAILURES + 1))
fi

if curl -sf "http://${API_HOST}:${API_PORT}/api/urban/geo/dem_metadata" | grep -q "EPSG:32644"; then
    echo "[PASS] Geospatial DEM: EPSG:32644 grid ready"
else
    echo "[FAIL] Geospatial DEM: metadata missing"
    FAILURES=$((FAILURES + 1))
fi

SCEN_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "http://${API_HOST}:${API_PORT}/api/urban/scenario" -H "Content-Type: application/json" -d '{"scenario_id":"heavy_rainfall"}')
if [ "$SCEN_CODE" = "200" ]; then
    echo "[PASS] Landlab 2D Hydrology: POST /api/urban/scenario -> 200 OK"
else
    echo "[FAIL] Landlab 2D Hydrology: HTTP ${SCEN_CODE}"
    FAILURES=$((FAILURES + 1))
fi

TILE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${API_HOST}:${API_PORT}/api/urban/geo/terrain_tiles/12/2960/1899.png")
if [ "$TILE_CODE" = "200" ]; then
    echo "[PASS] 3D Copernicus Terrarium Tiles: HTTP 200"
else
    echo "[FAIL] 3D Copernicus Terrarium Tiles: HTTP ${TILE_CODE}"
    FAILURES=$((FAILURES + 1))
fi

EXP_JSON=$(curl -sf "http://${API_HOST}:${API_PORT}/api/urban/exposure?scenario_id=heavy_rainfall&include_geojson=false" || echo "")
if echo "$EXP_JSON" | grep -q "modelled_potential_exposure"; then
    echo "[PASS] Spatial Exposure Engine: /api/urban/exposure OK"
else
    echo "[FAIL] Spatial Exposure Engine: /api/urban/exposure check failed"
    FAILURES=$((FAILURES + 1))
fi

PDF_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://${API_HOST}:${API_PORT}/api/urban/report/pdf?scenario_id=heavy_rainfall")
if [ "$PDF_CODE" = "200" ]; then
    echo "[PASS] Engineering PDF Report: HTTP 200"
else
    echo "[FAIL] Engineering PDF Report: HTTP ${PDF_CODE}"
    FAILURES=$((FAILURES + 1))
fi

NR_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${NODERED_PORT}/ui/")
if [ "$NR_CODE" = "200" ]; then
    echo "[PASS] Node-RED Dashboard: HTTP 200 on http://127.0.0.1:${NODERED_PORT}/ui/"
else
    echo "[WARN] Node-RED Dashboard: returned HTTP ${NR_CODE}"
fi

ZONES_RESP=$(curl -sf "http://${API_HOST}:${API_PORT}/api/zones" || echo "")
if echo "$ZONES_RESP" | grep -q "zone_01" && echo "$ZONES_RESP" | grep -q "zone_02"; then
    echo "[PASS] Dual-Node Telemetry: zone_01 & zone_02 active"
else
    echo "[WARN] Dual-Node Telemetry: zone state initializing"
fi

if [ "$FAILURES" -eq 0 ]; then
    echo "All required services verified."
    exit 0
else
    echo "Verification failed with ${FAILURES} critical error(s)." >&2
    exit 1
fi
