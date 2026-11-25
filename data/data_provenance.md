# CivicTwin-R — Spatial & Hydrological Data Provenance Registry

**Project:** CivicTwin-R (Urban Flood Monitoring & Scenario Planning Digital Twin)  
**Study Domain:** Greater Chennai Context (`[80.000, 12.840, 80.350, 13.260]`) & South Chennai Quantitative Pilot (`EPSG:32644`, `111x175` cells at `dx = 150m`)

---

## 1. Authoritative Public Geospatial Sources (No API Keys Required)

| Dataset Layer | Source Provider & License | Native CRS -> Output CRS | Verified Artifacts |
|---|---|---|---|
| **Topography (DSM)** | **Copernicus GLO-30 DEM** (`Copernicus_DSM_COG_10_N12_00_E080_00_DEM.tif`, `N13_00`), ESA / AWS Open Data (`Public / Copernicus License`) | `EPSG:4326` (`EGM2008`, 30m) -> `EPSG:32644` (`150m` grid) | `south_chennai_dem_utm44n_150m.npz`, `chennai_terrain_hillshade.png`, `dem_metadata.json` |
| **Administrative & Basins** | **Tamil Nadu CFM-DSS WFS Geoportal** (`GCC_Boundary`, `watersheds`, `ward_boundary`) | `EPSG:4326` -> `EPSG:4326` | `gcc_boundary.geojson` (1), `watersheds_south.geojson` (36), `wards_chennai.geojson` (200) |
| **Waterways & Waterbodies** | **Tamil Nadu CFM-DSS WFS** (`Rivers_NaturalChannels`, `waterways_cma`, `ManMade_Channels`, `majorwaterbodies_bulletin`, `waterbodies_cma`) | `EPSG:4326` -> `EPSG:4326` + rasterized masks (`UTM 44N`) | `waterways_official.geojson` (465), `waterbodies_official.geojson` (771) |
| **Geolocated Weather Stations** | **CFM-DSS WFS** (`srg.geojson`, `Raingauge_Stations.geojson`) — strictly verified WGS84 station locations | `EPSG:4326` -> `EPSG:4326` | `verified_stations.json` (56 deduplicated official locations) |
| **Historical Flood Spots** | **CFM-DSS WFS** (`Flood_Spot_Heights.geojson`) — tagged purely as historical vulnerability reference markers | `EPSG:4326` -> `EPSG:4326` | `historical_flood_spots.geojson` (230 records) |
| **Roads, Bridges, Parks, Buildings, Places** | **OpenStreetMap / Geofabrik** (`southern-zone-latest.osm.pbf`, `ODbL 1.0`) extracted deterministically via `pyosmium` | `EPSG:4326` -> `EPSG:4326` | `osm_roads_major.geojson` (9,942), `osm_streets_pilot.geojson` (38,827), `osm_bridges.geojson` (1,229), `osm_parks_landuse.geojson` (1,123), `osm_buildings_south.geojson` (18,198), `osm_places_index.json` (747) |

---

## 2. Preserved Quantitative Environmental Datasets (Read-Only Checksum Protected)

| Preserved File | Role & Spatial Grounding Status |
|---|---|
| `data/processed/chennai_arg_rainfall.csv` | 328 Automatic Rain Gauge rows across 13 Chennai subbasins (`mm` rainfall). **Contains no lat/lon columns**, so it is intentionally excluded from spatial point plotting and surfaced exclusively in non-spatial ARG basin analytics. |
| `data/processed/chennai_reservoirs.csv` | WRD daily storage-capacity records (MCM, FTL, fill %) for Chennai's 5 major reservoirs (Chembarambakkam, Poondi, Red Hills, Cholavaram, Kannankottai Thervoy Kandigai). |
| `data/raw/chennai_michaung_hourly_raw.json` & `data/processed/chennai_michaung_hourly.csv` | 144 hourly precipitation observations from Dec 2023 Cyclone Michaung (ERA5/IMD calibrated) driving historical spatial replay in `terrain_hydrology.py`. |
| `data/raw/cfm_dashboard_raw.json` | Raw CFM-DSS reference corpus snapshot (untouched). |

---

## 3. Explicit Scientific Limitations & Modeling Honesty

1. **Copernicus GLO-30 DSM Bias:** The underlying 30m surface model captures rooftops and tree canopies rather than surveyed bare-earth LiDAR DTM; channel beds along Adyar River, Chembarambakkam surplus, Buckingham Canal, Cooum, and Okkiyam Maduvu were hydro-conditioned using official CFM-DSS waterway alignments solely to prevent artificial bridge-deck dams.
2. **2D Shallow-Water Screening Approximation:** Surface routing uses `Landlab OverlandFlow` (`150m` grid, Manning's `n`, lumped spatially varying infiltration + nominal stormwater removal sink) without subterranean SWMM storm-drain pipe networks or bathymetric surveyed river cross-sections.
3. **No Surveyed River Stage Validation Raster:** Reported urban depths and focus-location indices are scenario/historical-hyetograph reconstructions, never real-time hardware street sensors or surveyed inundation ground truth.
4. **Building Height Provenance:** Each building in `osm_buildings_south.geojson` tracks `height_source` explicitly (`osm_height_tag`, `osm_levels_derived`, or `type_fallback_estimate`).
5. **Separated Dual Workstreams:** Live MQTT -> Mosquitto -> FastAPI -> SQLite/InfluxDB -> Node-RED telemetry originates from the two virtual ultrasonic ESP32/JSN-SR04T bench-tank laboratory nodes (`node_01`, `node_02`), which remain strictly isolated from the Chennai hydrological terrain domain.
