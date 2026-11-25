#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Operational Service Startup Script
# Launches Mosquitto MQTT, InfluxDB 2.x (if installed), FastAPI backend,
# Node-RED dashboard, and Two-Node Simulator with real readiness checks.
# ==============================================================================

set -e

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

mkdir -p .run/logs .run/nodered data results/plots results/tables results/logs

echo "CivicTwin-R"
echo "Starting application services..."
echo ""

# 1. Stop previous project-owned instances cleanly
if [ -f "scripts/showcase_stop.sh" ]; then
    bash scripts/showcase_stop.sh >/dev/null 2>&1 || true
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Error: python3 not found in PATH." >&2
    exit 1
fi

# 2. InfluxDB 2.x Time-Series Engine
INFLUX_STATE="UNAVAILABLE"
if curl -sf "http://127.0.0.1:8086/health" | grep -q "pass"; then
    INFLUX_STATE="READY"
elif command -v brew >/dev/null 2>&1 && brew services list 2>/dev/null | grep -q "influxdb@2"; then
    brew services start influxdb@2 >/dev/null 2>&1 || true
    for _ in {1..10}; do
        if curl -sf "http://127.0.0.1:8086/health" | grep -q "pass"; then
            INFLUX_STATE="READY"
            break
        fi
        sleep 0.5
    done
elif [ -x "/opt/homebrew/opt/influxdb@2/bin/influxd" ]; then
    nohup /opt/homebrew/opt/influxdb@2/bin/influxd </dev/null >.run/logs/influxdb.log 2>&1 &
    INFLUX_PID=$!
    disown "$INFLUX_PID" 2>/dev/null || true
    echo "$INFLUX_PID" > .run/influxdb.pid
    for _ in {1..12}; do
        if curl -sf "http://127.0.0.1:8086/health" | grep -q "pass"; then
            INFLUX_STATE="READY"
            break
        fi
        sleep 0.5
    done
fi

# 3. Mosquitto MQTT Broker
MQTT_STATE="UNAVAILABLE"
MOSQUITTO_BIN="$(command -v mosquitto || echo "/opt/homebrew/sbin/mosquitto")"
if [ -x "$MOSQUITTO_BIN" ]; then
    nohup "$MOSQUITTO_BIN" -c "$DIR/mqtt/mosquitto_local.conf" </dev/null >.run/logs/mosquitto.log 2>&1 &
    MOSQ_PID=$!
    disown "$MOSQ_PID" 2>/dev/null || true
    echo "$MOSQ_PID" > .run/mosquitto.pid
    for _ in {1..10}; do
        if nc -z 127.0.0.1 "$MQTT_PORT" 2>/dev/null; then
            MQTT_STATE="READY"
            break
        fi
        sleep 0.3
    done
fi

# 4. FastAPI Backend
API_STATE="FAILED"
nohup "$PYTHON_BIN" -m uvicorn backend.app.main:app --host "$API_HOST" --port "$API_PORT" </dev/null >.run/logs/backend.log 2>&1 &
BACKEND_PID=$!
disown "$BACKEND_PID" 2>/dev/null || true
echo "$BACKEND_PID" > .run/backend.pid

for _ in {1..24}; do
    if curl -sf "http://${API_HOST}:${API_PORT}/health" | grep -q "healthy"; then
        API_STATE="READY"
        break
    fi
    sleep 0.5
done

# 5. Node-RED Dashboard
NODERED_STATE="UNAVAILABLE"
NODE_BIN="$(command -v node || echo "/opt/homebrew/bin/node")"
RED_JS="$DIR/nodered_runtime/node_modules/node-red/red.js"
if [ -x "$NODE_BIN" ] && [ -f "$RED_JS" ]; then
    if [ ! -e "$DIR/.run/nodered/node_modules" ] && [ -d "$DIR/nodered_runtime/node_modules" ]; then
        ln -s "$DIR/nodered_runtime/node_modules" "$DIR/.run/nodered/node_modules"
    fi
    "$PYTHON_BIN" -c '
import os, sys, subprocess
NODE_BIN, RED_JS, DIR, NR_PORT, API_URL = sys.argv[1:6]
env = dict(os.environ)
env["NODE_PATH"] = os.path.join(DIR, "nodered_runtime", "node_modules")
env["BACKEND_URL"] = API_URL
with open(os.path.join(DIR, ".run", "logs", "nodered.log"), "a") as log:
    p = subprocess.Popen(
        [NODE_BIN, RED_JS, "--userDir", os.path.join(DIR, ".run", "nodered"), "--port", NR_PORT, os.path.join(DIR, "nodered", "flows.json")],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env, start_new_session=True,
    )
    with open(os.path.join(DIR, ".run", "nodered.pid"), "w") as f:
        f.write(str(p.pid))
' "$NODE_BIN" "$RED_JS" "$DIR" "$NODERED_PORT" "http://${API_HOST}:${API_PORT}"

    for _ in {1..24}; do
        if [ "$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${NODERED_PORT}/ui/")" = "200" ]; then
            NODERED_STATE="READY"
            break
        fi
        sleep 0.5
    done
fi

# 6. Dual-Node Live MQTT Simulator
SIM_STATE="IDLE"
if [ "$MQTT_STATE" = "READY" ]; then
    nohup "$PYTHON_BIN" "$DIR/scripts/mqtt_node_simulator.py" --broker localhost --port "$MQTT_PORT" --interval 5.0 </dev/null >.run/logs/simulator.log 2>&1 &
    SIM_PID=$!
    disown "$SIM_PID" 2>/dev/null || true
    echo "$SIM_PID" > .run/simulator.pid
    sleep 1
    if kill -0 "$SIM_PID" 2>/dev/null; then
        SIM_STATE="READY"
    fi
fi

# 7. Real endpoint readiness checks
SQLITE_STATE="UNAVAILABLE"
URBAN_STATE="UNAVAILABLE"
if [ "$API_STATE" = "READY" ]; then
    if curl -sf "http://${API_HOST}:${API_PORT}/api/database/stats" | grep -q "sqlite"; then
        SQLITE_STATE="READY"
    fi
    if curl -sf "http://${API_HOST}:${API_PORT}/api/urban/geo/dem_metadata" | grep -q "EPSG:32644"; then
        URBAN_STATE="READY"
    fi
fi

printf "%-18s %s\n" "MQTT Broker" "$MQTT_STATE"
printf "%-18s %s\n" "InfluxDB" "$INFLUX_STATE"
printf "%-18s %s\n" "SQLite" "$SQLITE_STATE"
printf "%-18s %s\n" "FastAPI" "$API_STATE"
printf "%-18s %s\n" "Node-RED" "$NODERED_STATE"
printf "%-18s %s\n" "Sensor Node 01" "$SIM_STATE"
printf "%-18s %s\n" "Sensor Node 02" "$SIM_STATE"
printf "%-18s %s\n" "Urban Twin" "$URBAN_STATE"
echo ""
echo "Application: http://${API_HOST}:${API_PORT}/"
echo "Urban Twin:  http://${API_HOST}:${API_PORT}/urban-twin"
echo "API Docs:    http://${API_HOST}:${API_PORT}/docs"
echo "Node-RED:    http://127.0.0.1:${NODERED_PORT}/ui/"
echo "InfluxDB:    http://127.0.0.1:8086/"
echo ""

bash "$DIR/scripts/showcase_verify.sh"
