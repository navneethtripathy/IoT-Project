#!/bin/bash
# CivicTwin-R — Setup Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "CivicTwin-R environment setup"

if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "Error: Python not found. Install Python 3.11+." >&2
    exit 1
fi

echo "Python version: $($PYTHON --version)"

if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env configuration from .env.example."
fi

echo "Installing project and dependencies..."
$PYTHON -m pip install -e ".[dev]"

mkdir -p data/generated results/tables results/plots results/logs

echo "Setup completed successfully."
echo "Execute 'make run' or './scripts/start.sh' to launch."
