# System Walkthrough & Demonstration Guide

This guide walks through the verified workflows across both CivicTwin-R workstreams once `./scripts/showcase_start.sh` reports services `READY`.

## Primary Interfaces
- **Dedicated 3D Chennai Urban Twin:** `http://127.0.0.1:8000/urban-twin`
- **Unified Hub (Urban + Experimental IoT Tank Lab):** `http://127.0.0.1:8000/showcase`
- **Node-RED Dashboard & Flow Editor:** `http://127.0.0.1:1880/ui/` and `http://127.0.0.1:1880/`
- **InfluxDB 2.x Data Explorer:** `http://127.0.0.1:8086/`
- **FastAPI OpenAPI Swagger UI:** `http://127.0.0.1:8000/docs`

---

## Phase 1 — Chennai 3D Urban Flood Digital Twin (`/urban-twin`)
1. Open `/urban-twin` (or launch the 13-step Guided Tour via the `Demo` button). The South Chennai offline cartographic terrain (`Copernicus GLO-30 Terrarium 3D DEM`, `36` watersheds, `200` GCC wards, `465` official CFM-DSS waterways, `771` waterbodies, `56` verified WFS gauge stations, `18,198` extruded 3D OSM buildings) loads strictly offline with zero external CDN requests.
2. Click `3D DEM 3x` / `1x` / `0x`, `North`, focus badges (`Velachery`, `Pallikaranai Marsh`, `Saidapet`, `Chembarambakkam`), save a camera viewpoint (`+View`), or search `747` OSM places, bridges, buildings, and stations.
3. Click any map cell or 3D building to query `/api/urban/point` and inspect provenance-tagged telemetry (`OBSERVED`, `DERIVED`, `ESTIMATED`, `MODELED`, `UNAVAILABLE`) or trigger an out-of-domain notice outside the `111x175` grid.
4. Select presets or adjust rainfall, duration, infiltration, drainage efficiency, and `initial_depth_m` sliders; run `Landlab OverlandFlow`, click **Swipe Split Map** for synchronized side-by-side scenario comparison & delta rasters, and manage custom presets (`save`, `load`, `duplicate`, `rename`, `delete`).
5. Inspect the right-drawer **Exposure** & **Boundaries** tabs, switch to **Cyclone Michaung Dec 2023 Replay** for hourly storm playback (`cum mm`), and open **Reports** (`/showcase#reports`) or click **Download PDF Report** for an A4 ReportLab dossier and CSV/GeoJSON export.

---

## Phase 2 — Impact Intelligence, Experimental IoT Bench & Resilience (`/showcase`)
1. Verify live header badges polling `/api/services/status` (FastAPI, MQTT 1883, SQLite row count, InfluxDB bucket count, Node-RED UI reachability).
2. Open **Impact** (`/showcase` -> `Impact`) to inspect `EPSG:32644` infrastructure exposure metrics, toggle **Watersheds (36)** vs **GCC Wards (200)**, and execute live bounded **Landlab 2D Parameter Sensitivity** sweeps (`3–7` steps).
3. Switch to **Historical** to inspect the 144-hour observed Cyclone Michaung hyetograph, 5 WRD reservoir capacities, and non-spatial 13-subbasin ARG CSV aggregation.
4. Open **IoT Lab** (`3D Tank Laboratory`, `Dual-Node Telemetry`, `Showcase Laboratory`) for real-time Three.js tank animations (`tank_01`: 50 cm; `tank_02`: 60 cm), warning (`70%`) and critical (`85%`) hysteresis rings, and **Research** (`Digital Twin ODE`, `Missing-Data Reconstruction`, `Freshness & Hysteresis`, `Benchmarks`) for causal RK4 tracking & fault recovery validation.
5. Trigger fault isolation or surge profiles in **Showcase Laboratory** and inspect real-time SQLite WAL records (**System -> Database Explorer**), live MQTT frames (**MQTT Streamer**), Node-RED (`http://127.0.0.1:1880/ui/`), and InfluxDB Data Explorer (`http://127.0.0.1:8086/`).
