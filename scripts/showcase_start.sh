#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Final Showcase Startup Orchestrator
# Starts Mosquitto MQTT broker, FastAPI backend, Node-RED, and Two-Node Simulator.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

mkdir -p .run/logs .run/nodered data results/plots results/tables

echo "================================================================================"
echo "  CivicTwin-R — Launching Complete Operational Showcase System"
echo "================================================================================"

# 1. Stop any previous runaway instances
if [ -f "scripts/showcase_stop.sh" ]; then
    bash scripts/showcase_stop.sh > /dev/null 2>&1 || true
fi

# 2. Check Python environment
PYTHON_BIN="$(which python3 || echo "python3")"
echo "[1/5] Checking runtime dependencies... Python: $($PYTHON_BIN --version)"

# 3. Start Mosquitto MQTT Broker
echo "[2/5] Starting Mosquitto MQTT broker on port 1883..."
MOSQUITTO_BIN="/opt/homebrew/sbin/mosquitto"
if [ ! -x "$MOSQUITTO_BIN" ]; then
    MOSQUITTO_BIN="$(which mosquitto || echo "")"
fi

if [ -n "$MOSQUITTO_BIN" ]; then
    nohup "$MOSQUITTO_BIN" -c "$DIR/mqtt/mosquitto_local.conf" < /dev/null > .run/logs/mosquitto.log 2>&1 &
    MOSQ_PID=$!
    disown $MOSQ_PID 2>/dev/null || true
    echo $MOSQ_PID > .run/mosquitto.pid
    sleep 1
    echo "      [OK] Mosquitto broker running (PID: $MOSQ_PID)"
else
    echo "      [WARN] Mosquitto binary not found; continuing in standalone mode"
fi

# 4. Start FastAPI Backend
echo "[3/5] Starting FastAPI backend on http://127.0.0.1:8000..."
nohup $PYTHON_BIN -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 < /dev/null > .run/logs/backend.log 2>&1 &
BACKEND_PID=$!
disown $BACKEND_PID 2>/dev/null || true
echo $BACKEND_PID > .run/backend.pid

# Wait for backend health
echo "      Waiting for backend to be healthy..."
for i in {1..20}; do
    if curl -s http://127.0.0.1:8000/health | grep -q "healthy"; then
        echo "      [OK] FastAPI backend healthy (PID: $BACKEND_PID)"
        break
    fi
    sleep 0.5
done

# 5. Start Node-RED (if installed)
echo "[4/5] Starting Node-RED dashboard on http://127.0.0.1:1880..."
NODE_BIN="$(which node || echo "/opt/homebrew/bin/node")"
RED_JS="$DIR/nodered_runtime/node_modules/node-red/red.js"

if [ -x "$NODE_BIN" ] && [ -f "$RED_JS" ]; then
    mkdir -p "$DIR/.run/nodered"
    if [ ! -e "$DIR/.run/nodered/node_modules" ] && [ -d "$DIR/nodered_runtime/node_modules" ]; then
        ln -s "$DIR/nodered_runtime/node_modules" "$DIR/.run/nodered/node_modules"
    fi
    $PYTHON_BIN -c '
import os, sys, subprocess
NODE_BIN = sys.argv[1]
RED_JS = sys.argv[2]
DIR = sys.argv[3]
env = dict(os.environ)
env["NODE_PATH"] = os.path.join(DIR, "nodered_runtime/node_modules")
env["BACKEND_URL"] = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
with open(".run/logs/nodered.log", "a") as log:
    p = subprocess.Popen(
        [NODE_BIN, RED_JS, "--userDir", os.path.join(DIR, ".run/nodered"), "--port", "1880", os.path.join(DIR, "nodered/flows.json")],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        env=env,
        start_new_session=True
    )
    with open(".run/nodered.pid", "w") as f:
        f.write(str(p.pid))
' "$NODE_BIN" "$RED_JS" "$DIR"
    NODERED_PID=$(cat .run/nodered.pid 2>/dev/null || echo "")
    sleep 3
    echo "      [OK] Node-RED engine running (PID: $NODERED_PID)"
else
    echo "      [INFO] Node-RED runtime not installed; UI available via Showcase Web Center"
fi

# 6. Start Two-Node Live MQTT Simulator
echo "[5/5] Starting Two-Node Live Cyber-Physical Simulator..."
nohup $PYTHON_BIN "$DIR/scripts/mqtt_node_simulator.py" --broker localhost --port 1883 --interval 5.0 < /dev/null > .run/logs/simulator.log 2>&1 &
SIM_PID=$!
disown $SIM_PID 2>/dev/null || true
echo $SIM_PID > .run/simulator.pid
sleep 1
echo "      [OK] Dual-node simulator active (PID: $SIM_PID)"

# 7. Run Verification Check
echo ""
echo "Running system verification..."
bash "$DIR/scripts/showcase_verify.sh"

echo ""
echo "================================================================================"
echo "  CivicTwin-R Showcase is LIVE and READY FOR DEMONSTRATION!"
echo "================================================================================"
echo "  * Engineering Showcase Control Center : http://127.0.0.1:8000/showcase"
echo "  * Interactive Swagger API Docs        : http://127.0.0.1:8000/docs"
if [ -n "$NODERED_BIN" ]; then
echo "  * Node-RED Operational Dashboard      : http://127.0.0.1:1880/ui"
fi
echo "================================================================================"
echo "  Logs: .run/logs/ (mosquitto.log, backend.log, simulator.log, nodered.log)"
echo "  Stop with: ./scripts/showcase_stop.sh"
echo "================================================================================"
