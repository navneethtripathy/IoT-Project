#!/usr/bin/env python3
"""
CivicTwin-R — Reproducible Geospatial Preprocessing Runner

Executes DEM processing (EPSG:4326 -> EPSG:32644 UTM Zone 44N), TN CFM-DSS WFS vector
cleanup, and OpenStreetMap PBF feature extraction for Chennai.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from digital_twin.geoprocessor import (
    RAW_OSM_DIR,
    build_dem_utm44n,
    build_wfs_processed_layers,
    extract_osm_from_pbf,
    write_acquisition_manifest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.process_geo")


def main():
    parser = argparse.ArgumentParser(description="Process Chennai DEM, WFS, and OSM layers.")
    parser.add_argument("--skip-osm", action="store_true", help="Skip PBF extraction if running DEM/WFS only")
    args = parser.parse_args()

    logger.info("Step 1/3: Building projected Copernicus GLO-30 DEM (EPSG:32644, dx=150m)...")
    dem_meta = build_dem_utm44n(dx_m=150.0)
    logger.info("DEM ready: %s", dem_meta["grid_shape"])

    logger.info("Step 2/3: Processing official TN CFM-DSS WFS layers...")
    wfs_counts = build_wfs_processed_layers()
    logger.info("WFS layers ready: %s", wfs_counts)

    osm_counts = {}
    pbf_path = RAW_OSM_DIR / "southern-zone-latest.osm.pbf"
    if not args.skip_osm and pbf_path.exists():
        logger.info("Step 3/3: Extracting real OSM buildings, roads, bridges, parks...")
        osm_counts = extract_osm_from_pbf(pbf_path)
        logger.info("OSM layers ready: %s", osm_counts)
    elif not args.skip_osm:
        logger.warning("OSM PBF not present yet (%s); run with --skip-osm or finish PBF download.", pbf_path)

    write_acquisition_manifest(dem_meta, wfs_counts, osm_counts)
    logger.info("Saved deterministic acquisition_manifest.json")


if __name__ == "__main__":
    main()
