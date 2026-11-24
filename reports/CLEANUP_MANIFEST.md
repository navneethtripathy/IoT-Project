# CivicTwin-R — Repository Cleanup & Professional Organization Manifest

**Execution Date:** 2026-11-24  
**Classification:** APPROVED — CLEANED & ORGANIZED  
**Auditor / Architect:** Principal Systems Architect & Lead Software Engineer  

---

## 1. Executive Summary

This manifest documents the structural cleanup and professional reorganization of the **CivicTwin-R** repository in accordance with Phase 1 of the Final Master Completion directive. All temporary test artifacts, obsolete duplicate files, and empty directories were pruned while strictly protecting core datasets, production firmware, models, test suites, and documentation.

---

## 2. Protected Datasets Verification

The four mandatory protected datasets have been verified and preserved with zero modification:

| Protected File Path | File Size | Record / Line Count | Provenance Verification | Status |
|:--------------------|:----------|:--------------------|:------------------------|:-------|
| `data/processed/chennai_arg_rainfall.csv` | 29 KB | 329 lines (117 stations) | CFM-DSS / TNUIFSL rainfall observations | **PRESERVED** |
| `data/processed/chennai_reservoirs.csv` | 678 B | 6 lines (5 reservoirs) | WRD Daily Stage-Storage Bulletins | **PRESERVED** |
| `data/raw/cfm_dashboard_raw.json` | 76 KB | Complete raw JSON | Official CFM-DSS API snapshot | **PRESERVED** |
| `data/raw/chennai_michaung_hourly_raw.json` | 7.2 KB | 144 hourly steps | Cyclone Michaung storm telemetry | **PRESERVED** |

---

## 3. Pruned Artifacts & Cleanup Log

The following ephemeral and obsolete artifacts were safely removed:

1. **Ad-Hoc Ephemeral CSV Exports:**
   - Pruned 29 historical files matching `data/generated/export_all_*.csv` generated during preliminary test runs.
   - Retained core validated benchmarks: `data/generated/demo_dataset.csv` and `data/generated/demo_dataset.json`.

2. **Empty Directory Removal:**
   - Removed unreferenced empty directory `data/sample/`.

3. **Output Directory Preservation:**
   - Added `.gitkeep` markers to operational output directories (`results/logs/`, `reports/figures/`) ensuring proper tracking without tracking ephemeral log sessions.

4. **Runtime State Normalization:**
   - Reset `.run/simulator_control.json` to baseline equilibrium parameters (Inflows: 25.0 cm³/s and 35.0 cm³/s, k: 4.5 and 6.0).

---

## 4. Retained Core Architectural Structure

The resulting repository structure adheres to standard engineering practices:

```
CivicTwin-R/
├── backend/                   # FastAPI backend, storage layer, models, ingestion
│   ├── app/                   # API routes, lifespan handlers, templates
│   │   ├── main.py            # Primary application entry point & REST endpoints
│   │   └── templates/         # Engineering Showcase Control Center (HTML/Tailwind/Three.js)
│   ├── config.py              # Environment configuration & defaults
│   ├── ingestion.py           # Deduplication, freshness engine, MQTT ingestion
│   ├── models.py              # Pydantic v2 domain models
│   ├── simulator.py           # Standalone fallback simulator
│   └── storage.py             # SQLite WAL & Memory storage backends
├── digital_twin/              # Cyber-physical twin mathematics & models
│   ├── edge_warning.py        # 4-state freshness machine, anti-chatter hysteresis
│   ├── forecast.py            # Zero-future-leakage time-aware baseline forecaster
│   ├── model.py               # Multi-zone digital twin engine
│   ├── reconstruction.py      # Setting A (online causal) & Setting B (retrospective)
│   ├── scenarios.py           # Scenario manager & definitions
│   └── tank_twin.py           # RK4 Torricelli mass-balance tank physics & calibration
├── experiments/               # Scientific evaluation & reproduction scripts
├── firmware/                  # ESP32 C++ source (PlatformIO / Arduino) & Wokwi config
├── mqtt/                      # Mosquitto broker configuration & test clients
├── nodered/                   # Node-RED operational flow definitions (flows.json)
├── reports/                   # Audit reports, test reports, cleanup manifest
├── results/                   # Experimental plots, benchmark tables, publication figures
├── scripts/                   # One-command lifecycle scripts (start, stop, verify)
├── showcase/                  # Academic demonstration guides, QA, URLs, screenshots
└── tests/                     # Automated test suites (unit, physics, integration)
```

---

## 5. Certification

All cleanup operations have been verified against the test suite (`pytest`) with zero regressions. The repository is clean, structurally sound, and free of redundant artifacts.
