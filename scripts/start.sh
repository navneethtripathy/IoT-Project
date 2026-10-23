#!/bin/bash
# CivicTwin-R — Start Services
set -e

echo "Starting CivicTwin-R..."

# Check if Docker is available for full-stack mode
if command -v docker-compose &>/dev/null || command -v docker &>/dev/null; then
    echo "Docker detected. Use 'docker-compose up -d' for full stack."
fi

# Start backend in background
echo "Starting FastAPI backend on port 8000..."
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  CivicTwin-R Running                     ║"
echo "║                                          ║"
echo "║  API:       http://127.0.0.1:8000        ║"
echo "║  API Docs:  http://127.0.0.1:8000/docs   ║"
echo "║  Health:    http://127.0.0.1:8000/health  ║"
echo "║                                          ║"
echo "║  Press Ctrl+C to stop                    ║"
echo "╚══════════════════════════════════════════╝"

# Wait for the backend process
wait $BACKEND_PID
