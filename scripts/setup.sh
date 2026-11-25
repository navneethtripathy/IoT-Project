#!/usr/bin/env bash
# ==============================================================================
# CivicTwin-R — Reproducible Environment & Geospatial Setup Script
# Safe, idempotent provisioning without exposing hardcoded credentials.
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== CivicTwin-R Environment & Geospatial Setup ==="

if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "Error: Python 3.11+ required." >&2
    exit 1
fi
echo "Python: $($PYTHON --version)"

# 1. Create .env from .env.example with freshly generated local secrets (idempotent)
if [ ! -f .env ]; then
    cp .env.example .env
    RAND_TOKEN=$($PYTHON -c "import secrets; print('ct2_' + secrets.token_hex(24))")
    RAND_PASS=$($PYTHON -c "import secrets; print(secrets.token_urlsafe(16))")
    $PYTHON -c "
from pathlib import Path
p = Path('.env')
txt = p.read_text()
txt = txt.replace('INFLUXDB_TOKEN=<generate-local-token-via-setup-sh>', f'INFLUXDB_TOKEN=${RAND_TOKEN}')
txt = txt.replace('INFLUXDB_PASSWORD=<generate-local-password-via-setup-sh>', f'INFLUXDB_PASSWORD=${RAND_PASS}')
txt = txt.replace('INFLUXDB_ENABLED=false', 'INFLUXDB_ENABLED=true')
if 'INFLUXDB_TOKEN=' in txt and '${RAND_TOKEN}' not in txt:
    txt = txt.replace('INFLUXDB_TOKEN=', f'INFLUXDB_TOKEN=${RAND_TOKEN}')
if 'INFLUXDB_USERNAME=' not in txt:
    txt += f'\nINFLUXDB_USERNAME=civictwin\nINFLUXDB_PASSWORD=${RAND_PASS}\n'
p.write_text(txt)
"
    chmod 600 .env
    echo "[OK] Generated local .env with randomized InfluxDB credentials (mode 600)."
else
    chmod 600 .env 2>/dev/null || true
    echo "[OK] Existing .env preserved."
fi

# 2. Install Python dependencies (editable)
echo "Installing Python dependencies..."
$PYTHON -m pip install -e ".[dev]"

# 3. Ensure directories exist
mkdir -p data/generated data/geo/raw_dem data/geo/raw_wfs data/geo/raw_osm data/geo/processed results/tables results/plots results/logs .run/logs

# 4. Initialize local InfluxDB 2.x idempotently if installed
if command -v brew &>/dev/null && ! curl -s http://127.0.0.1:8086/health 2>/dev/null | grep -q "pass"; then
    if brew list influxdb@2 &>/dev/null; then
        brew services start influxdb@2 >/dev/null 2>&1 || true
        sleep 2
    fi
fi

if curl -s http://127.0.0.1:8086/api/v2/setup 2>/dev/null | grep -q '"allowed":true'; then
    echo "Initializing local InfluxDB 2.x organization & bucket..."
    INFLUX_CFG=$($PYTHON -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
print(os.getenv('INFLUXDB_USERNAME','civictwin'), os.getenv('INFLUXDB_PASSWORD',''), os.getenv('INFLUXDB_ORG','civictwin'), os.getenv('INFLUXDB_BUCKET','telemetry'), os.getenv('INFLUXDB_TOKEN',''))
")
    read -r I_USER I_PASS I_ORG I_BUCKET I_TOK <<< "$INFLUX_CFG"
    if [ -n "$I_PASS" ] && [ -n "$I_TOK" ] && command -v influx &>/dev/null; then
        influx setup --username "$I_USER" --password "$I_PASS" --org "$I_ORG" --bucket "$I_BUCKET" --token "$I_TOK" --retention 0 --force
        echo "[OK] InfluxDB 2.x initialized (org=$I_ORG, bucket=$I_BUCKET)."
    fi
fi

# 5. Provision processed Chennai geospatial assets if absent
if [ ! -f data/geo/processed/south_chennai_dem_utm44n_150m.npz ]; then
    echo "Acquiring and processing Chennai geospatial layers..."
    $PYTHON scripts/acquire_chennai_geodata.py
    $PYTHON scripts/process_chennai_geodata.py
else
    echo "[OK] Processed Chennai DEM and WFS layers verified."
fi

echo "=== CivicTwin-R Setup Complete ==="
echo "Run ./scripts/showcase_start.sh to launch the complete operational stack."
