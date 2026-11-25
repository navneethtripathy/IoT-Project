#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Final Showcase Safe Shutdown Script
# Terminates ONLY project-owned processes tracked in .run/*.pid or exact repo paths.
# Never blindly kills arbitrary external processes listening on system ports.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR" || exit 1

echo "Shutting down CivicTwin-R project-owned services..."

stop_pid_file() {
    local file=$1
    local name=$2
    if [ -f "$file" ]; then
        local pid
        pid=$(cat "$file" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "  Stopping $name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            for _ in {1..10}; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    break
                fi
                sleep 0.3
            done
            if kill -0 "$pid" 2>/dev/null; then
                echo "  Force terminating unresponsive $name (PID: $pid)..."
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$file"
    fi
}

stop_pid_file ".run/simulator.pid" "Dual-Node Simulator"
stop_pid_file ".run/backend.pid" "FastAPI Backend"
stop_pid_file ".run/nodered.pid" "Node-RED Dashboard"
stop_pid_file ".run/mosquitto.pid" "Mosquitto MQTT Broker"
stop_pid_file ".run/influxdb.pid" "Project-spawned InfluxDB 2.x"

# Terminate only exact project-owned leftover child commands matching $DIR (never generic port sweeps)
cleanup_repo_proc() {
    local pattern=$1
    local label=$2
    local pids
    pids=$(pgrep -f "$pattern" 2>/dev/null || true)
    for pid in $pids; do
        if [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null; then
            echo "  Stopping leftover project $label (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
        fi
    done
}

cleanup_repo_proc "$DIR/scripts/mqtt_node_simulator.py" "Simulator"
cleanup_repo_proc "$DIR/mqtt/mosquitto_local.conf" "Mosquitto"
cleanup_repo_proc "$DIR/nodered/flows.json" "Node-RED"

echo "CivicTwin-R project shutdown complete."
