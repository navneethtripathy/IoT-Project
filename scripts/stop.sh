#!/bin/bash
# CivicTwin-R — Stop Services
echo "Stopping CivicTwin-R services..."

# Kill backend
pkill -f "uvicorn backend.app.main:app" 2>/dev/null && echo "✅ Backend stopped" || echo "⚠ Backend not running"

# Stop Docker if running
if command -v docker-compose &>/dev/null; then
    docker-compose down 2>/dev/null && echo "✅ Docker services stopped" || true
fi

echo "Done."
