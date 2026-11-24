#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Final Showcase Safe Shutdown Script
# Terminates all running services and releases ports cleanly.
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "Shutting down CivicTwin-R showcase services..."

stop_pid_file() {
    local file=$1
    local name=$2
    if [ -f "$file" ]; then
        local pid=$(cat "$file" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "Stopping $name (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 0.5
            if kill -0 "$pid" 2>/dev/null; then
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

# Sweep port 8000, 1883, 1880 if orphan processes remain
sweep_port() {
    local port=$1
    local pids=$(lsof -ti :$port 2>/dev/null || echo "")
    if [ -n "$pids" ]; then
        echo "Cleaning up lingering processes on port $port..."
        kill -9 $pids 2>/dev/null || true
    fi
}

sweep_port 8000
sweep_port 1883
sweep_port 1880

echo "CivicTwin-R shutdown complete. All ports released."
