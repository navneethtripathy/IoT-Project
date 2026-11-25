# Geospatial & Historical Data Sources and Attribution

## 1. Public Geospatial Layers (`data/geo/`)

Large raw extracts (`*.osm.pbf`, Copernicus `*.tif`) are excluded from Git via `.gitignore` and reproduced locally with `scripts/acquire_chennai_geodata.py` and `scripts/process_chennai_geodata.py`. Pre-processed South Chennai GIS bundles (`21 MB` total in `data/geo/processed/`) and TN CFM-DSS WFS extracts (`data/geo/raw_wfs/`, `8.2 MB`) are tracked directly so the UI and tests operate offline without API keys.

| Layer / File | Upstream Source | License / Terms | Native CRS -> Output CRS | Verified Contents |
| :--- | :--- | :--- | :--- | :--- |
| `south_chennai_dem_utm44n_150m.npz`, `chennai_terrain_hillshade.png` | **Copernicus GLO-30 DEM** (`ESA / AWS Open Data`) | Copernicus Open Data License | `EPSG:4326` (`EGM2008`, 30m) -> `EPSG:32644` (`150m`) | `111 × 175` grid (`18,136` land, `1,289` ocean, `1,036` channel cells) |
| `gcc_boundary.geojson`, `watersheds_south.geojson`, `wards_chennai.geojson` | **TN CFM-DSS WFS Geoportal** | Public government portal (`tncfmdss`) | `EPSG:4326` -> `EPSG:4326` | `1` GCC polygon, `36` watersheds, `200` wards |
| `waterways_official.geojson`, `waterbodies_official.geojson`, `historical_flood_spots.geojson` | **TN CFM-DSS WFS Geoportal** | Public government portal (`tncfmdss`) | `EPSG:4326` -> `EPSG:4326` | `465` waterways, `771` waterbodies/wetlands, `230` historical flood spot points |
| `verified_stations.json` | **TN CFM-DSS WFS** (`srg`, `Raingauge_Stations`) | Public government portal | `EPSG:4326` -> `EPSG:4326` | `56` verified geolocated station coordinates |
| `osm_roads_major.geojson`, `osm_streets_pilot.geojson`, `osm_bridges.geojson`, `osm_parks_landuse.geojson`, `osm_buildings_south.geojson`, `osm_places_index.json` | **OpenStreetMap / Geofabrik** (`southern-zone-latest.osm.pbf`) | **ODbL 1.0** | `EPSG:4326` -> `EPSG:4326` | `9,942` major roads, `38,827` pilot streets, `1,229` bridges, `1,123` parks, `18,198` extruded buildings, `747` place names |

### Building Height Provenance (`osm_buildings_south.geojson`)
Every extruded footprint carries `height_source`:
- `osm_height_tag`: explicit OSM `height` tag.
- `osm_levels_derived`: estimated as `building:levels * 3.2 m`.
- `type_fallback_estimate`: disclosed typology fallback (`residential: 9.5m`, `commercial: 15.0m`, `hospital: 16.0m`, etc.) when height tags are absent in OSM.

---

## 2. Preserved Research Datasets (`data/processed/`, `data/raw/`)

| Dataset File | Records | Provenance & Spatial Handling |
| :--- | :---: | :--- |
| `data/processed/chennai_arg_rainfall.csv` | `328` rows (`13` subbasins) | **CFM-DSS ARG**: Contains no lat/lon columns; surfaced strictly in non-spatial basin analytics (`/api/urban/historical/arg-analytics`) so no station positions are ever fabricated. |
| `data/processed/chennai_reservoirs.csv` | `5` WRD reservoirs | **WRD Lake Operation System**: Chembarambakkam (`103.215 MCM`), RedHills, Poondi, Cholavaram, Thervoy Kandigai capacities and live fill percentages. |
| `data/processed/chennai_michaung_hourly.csv` & `data/raw/chennai_michaung_hourly_raw.json` | `144` hourly steps | **ERA5 / IMD Calibrated**: Dec 1–6, 2023 Cyclone Michaung precipitation series (`369.8 mm` 6-day cumulative, `259.4 mm` peak 24h replay window Dec 4–5, `26.1 mm/hr` peak hourly rate) driving historical replay. |
| `data/raw/cfm_dashboard_raw.json` | Raw corpus snapshot | Preserved upstream CFM-DSS JSON payload. |

---

## 3. Third-Party Library Attributions
MapLibre GL JS (BSD-3-Clause), Three.js & OrbitControls (MIT), Chart.js (MIT), Tailwind CSS Play CDN bundle cached locally (MIT), FastAPI (MIT), Landlab (MIT), GeoPandas/Shapely/Rasterio/PyProj (BSD/MIT), PyOsmium (BSD), Eclipse Mosquitto (EPL-2.0/EDL-1.0), Node-RED (Apache-2.0), InfluxDB 2.x (MIT).
