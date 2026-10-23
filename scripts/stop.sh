#!/bin/bash
# CivicTwin-R — Stop Services

echo "Stopping CivicTwin-R services..."

# Terminate FastAPI backend
if pkill -f "uvicorn backend.app.main:app" 2>/dev/null; then
    echo "Backend process terminated."
else
    echo "Backend process was not running."
fi

# Stop Docker containers if active
if command -v docker &>/dev/null && docker info &>/dev/null; then
    docker compose down 2>/dev/null || true
fi

echo "Shutdown complete."
