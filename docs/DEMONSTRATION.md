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
1. Open `/urban-twin`. The South Chennai offline cartographic terrain (`Copernicus GLO-30 hillshade`, `36` watersheds, `465` official CFM-DSS waterways, `771` waterbodies, `56` verified WFS gauge stations, `18,198` extruded 3D OSM buildings) loads entirely from localhost static/API routes with zero external CDN requests.
2. Click any focus badge (`Velachery`, `Pallikaranai Marsh`, `Saidapet`, `Chembarambakkam`) or search in the top search bar (`747` OSM places, bridges, named buildings, stations).
3. Click any map cell or 3D building to query `/api/urban/point` and inspect coordinates (`WGS84` & `UTM44N`), Copernicus DSM elevation (`EGM2008`), imperviousness, building height provenance (`height_source`), and modeled water depth.
4. Select **Scenario 8 (Chembarambakkam Spillway Surge)** or adjust rainfall, duration, infiltration, and drainage efficiency sliders, then run `Landlab OverlandFlow` and click **Compare Impact Delta** against `reduced_drainage` / `improved_drainage`.
5. Switch to **Cyclone Michaung Dec 2023 Replay** and press **Play** on the storm timeline scrubber to step through hourly modeled accumulation grids and export active flood GeoJSON or JSON summaries.

---

## Phase 2 — Experimental IoT Bench Twin & Resilience (`/showcase`)
1. Verify live header badges polling `/api/services/status` (FastAPI, MQTT 1883, SQLite row count, InfluxDB bucket count, Node-RED UI reachability).
2. Switch to **Tab 3 (Chennai Basin Analytics)** to inspect the 144-hour observed Cyclone Michaung hyetograph, 5 WRD reservoir capacities, and non-spatial 13-subbasin ARG CSV aggregation.
3. Open **Tab 6 (Experimental IoT Tank Digital Twin)** for real-time Three.js tank animations (`tank_01`: 50 cm; `tank_02`: 60 cm), warning (`70%`) and critical (`85%`) hysteresis rings, and **Tab 7** for forward RK4 Torricelli ODE tracking (`dh/dt = (Q_in - k*sqrt(h)) / A`).
4. Open **Tab 8** & **Tab 9** to review causal Setting A vs. retrospective Setting B missing-data MAE comparisons and freshness state transitions (`FRESH` -> `STALE` -> `OFFLINE`).
5. Trigger fault isolation or surge profiles in **Tab 10 (Showcase Laboratory)** and observe real-time SQLite WAL records (**Tab 11**), live MQTT frames (**Tab 12**), and Node-RED gauge/chart updates (`http://127.0.0.1:1880/ui/`).
