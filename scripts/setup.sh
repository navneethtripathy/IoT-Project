#!/bin/bash
# CivicTwin-R — Setup Script
# Installs Python dependencies and prepares the environment.

set -e

echo "╔══════════════════════════════════════════╗"
echo "║  CivicTwin-R — Setup                     ║"
echo "╚══════════════════════════════════════════╝"

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "❌ Python not found. Please install Python 3.11+"
    exit 1
fi

echo "Using: $($PYTHON --version)"

# Create .env from template if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env from .env.example"
fi

# Install dependencies
echo "Installing Python dependencies..."
$PYTHON -m pip install -e ".[dev]"

# Create data directories
mkdir -p data/generated data/sample results/tables results/plots results/logs

echo ""
echo "✅ Setup complete!"
echo ""
echo "Quick start:"
echo "  make run          # Start the backend API"
echo "  make test         # Run tests"
echo "  make experiments  # Run experiments and generate plots"
echo "  make help         # Show all available commands"
