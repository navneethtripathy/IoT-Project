# Contributing to CivicTwin-R

Contributions that improve numerical accuracy, geospatial reproducibility, security hardening, test coverage, or documentation clarity are welcome.

## Development Setup

```bash
git clone https://github.com/navneethtripathy/IoT-Project.git
cd CivicTwin-R
./scripts/setup.sh
```

Ensure all services remain bound to `127.0.0.1` when testing locally and never commit `.env`, `.db*`, runtime logs (`.run/`), or personal filesystem paths.

## Code Quality & Verification Before Opening a Pull Request

Run all static checks and portable automated tests locally:

```bash
# Static syntax, lint & Python security scan
ruff check backend digital_twin experiments scripts tests --select E9,F,B
bandit -r backend digital_twin -ll
for s in scripts/*.sh; do bash -n "$s"; done

# Core offline test suite (matches GitHub Actions CI)
PYTHONPATH=. pytest \
  tests/test_all.py \
  tests/test_tank_twin.py \
  tests/test_chennai_twin.py \
  tests/test_terrain_hydrology.py \
  tests/test_urban_twin.py \
  tests/test_urban_intelligence.py -v
```

When modifying UI templates (`backend/app/templates/`), also run offline browser verification (`python3 scripts/verify_browser_qa.py`) with `./scripts/showcase_start.sh` active to confirm zero external network requests, zero console errors, and clean responsive rendering.

## Data & Scientific Integrity Guidelines

- Keep `data/processed/chennai_arg_rainfall.csv`, `data/processed/chennai_reservoirs.csv`, `data/raw/cfm_dashboard_raw.json`, and `data/raw/chennai_michaung_hourly_raw.json` unmodified.
- Maintain offline vendored dependencies under `backend/app/static/vendor/` rather than referencing external CDNs.
- Explicitly distinguish `OBSERVED`, `DERIVED`, `ESTIMATED`, `MODELED`, and `UNAVAILABLE` provenance indicators in both API responses and UI labels.
