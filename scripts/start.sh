#!/bin/bash
# CivicTwin-R — Start Services
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "CivicTwin-R startup"

# Determine python command
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "Error: Python 3 not found. Install Python 3.11+." >&2
    exit 1
fi

# Check for Docker if full-stack mode is preferred
if command -v docker &>/dev/null && docker info &>/dev/null; then
    echo "Docker is running. For multi-container integration (Mosquitto/InfluxDB/Node-RED), use: docker compose up -d"
else
    echo "Running in standalone mode with SQLite storage."
fi

# Ensure data directory exists
mkdir -p data results/logs

echo "Starting FastAPI backend on 127.0.0.1:8000..."
$PYTHON -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
echo "Backend process ID: $BACKEND_PID"

cleanup() {
    echo "Shutting down backend process (PID $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    echo "Backend stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

echo ""
echo "CivicTwin-R active endpoints:"
echo "  API:         http://127.0.0.1:8000"
echo "  API Docs:    http://127.0.0.1:8000/docs"
echo "  Health:      http://127.0.0.1:8000/health"
echo "  Zones:       http://127.0.0.1:8000/api/zones"
echo "  Scenarios:   http://127.0.0.1:8000/api/scenarios"
echo ""
echo "Press Ctrl+C to stop services."

wait $BACKEND_PID
