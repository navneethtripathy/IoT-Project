#!/usr/bin/env python3
"""
CivicTwin-R — Real Geographical Data Acquisition Pipeline (Chennai, India)

Acquires genuine, account-free, zero-API-key geospatial datasets from authoritative
public sources and records full provenance metadata in data/geo/manifest.json:

  1. Copernicus DEM GLO-30 (30m COG GeoTIFFs via AWS S3 Open Data):
     - Tiles covering Greater Chennai (N13E080, N12E080)
  2. Government of Tamil Nadu CFM-DSS Official WFS (EPSG:4326):
     - Administrative boundaries (GCC, CMA), Basin, Subbasins, Watersheds
     - Official rivers, man-made drainage channels, surveyed lakes/reservoirs
     - Verified Rain Gauge (ARG/SRG) & AWLR station coordinates, Flood Spot Heights
  3. OpenStreetMap Overpass API (ODbL):
     - Broad Chennai arterial roads, bridges, waterways, wetlands, parks/landuse
     - Detailed real building footprints & local street networks across South Chennai
       and priority flood corridors

No external API keys required. Cached locally for full offline operation.
"""

from __future__ import annotations

import argparse
import json
import logging
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
GEO_DIR = _PROJECT_ROOT / "data" / "geo"
DEM_DIR = GEO_DIR / "raw_dem"
WFS_DIR = GEO_DIR / "raw_wfs"
OSM_DIR = GEO_DIR / "raw_osm"

for d in (DEM_DIR, WFS_DIR, OSM_DIR):
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("civictwin.acquire_geo")

CFM_WFS_BASE = "https://www.chennaifloodmonitor.tn.gov.in/geohorr/ows"
OVERPASS_MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]

DEM_TILES = {
    "Copernicus_DSM_COG_10_N13_00_E080_00_DEM.tif": (
        "https://copernicus-dem-30m.s3.amazonaws.com/"
        "Copernicus_DSM_COG_10_N13_00_E080_00_DEM/"
        "Copernicus_DSM_COG_10_N13_00_E080_00_DEM.tif"
    ),
    "Copernicus_DSM_COG_10_N12_00_E080_00_DEM.tif": (
        "https://copernicus-dem-30m.s3.amazonaws.com/"
        "Copernicus_DSM_COG_10_N12_00_E080_00_DEM/"
        "Copernicus_DSM_COG_10_N12_00_E080_00_DEM.tif"
    ),
}

WFS_LAYERS = [
    "ChennaiDSS:Basin",
    "ChennaiDSS:subbasinboundary_bulletin",
    "ChennaiDSS:watersheds",
    "ChennaiDSS:GCC_Boundary",
    "ChennaiDSS:CMA_Boundary",
    "ChennaiDSS:Rivers_NaturalChannels",
    "ChennaiDSS:ManMade_Channels",
    "ChennaiDSS:waterways_cma",
    "ChennaiDSS:majorwaterbodies_bulletin",
    "ChennaiDSS:waterbodies_cma",
    "ChennaiDSS:Raingauge_Stations",
    "ChennaiDSS:srg",
    "ChennaiDSS:AWLR_Stations",
    "ChennaiDSS:Flood_Spot_Heights",
    "ChennaiDSS:Keyloactions_of_cma",
]


def _insecure_ssl_ctx() -> ssl.SSLContext:
    # TN CFM-DSS portal serves an intermediate certificate chain not in macOS trust store.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_dem_tiles(force: bool = False) -> list[dict]:
    meta = []
    for fname, url in DEM_TILES.items():
        out_path = DEM_DIR / fname
        if out_path.exists() and out_path.stat().st_size > 1_000_000 and not force:
            logger.info("DEM cached: %s (%.2f MB)", fname, out_path.stat().st_size / 1e6)
        else:
            logger.info("Downloading Copernicus DEM %s ...", fname)
            req = urllib.request.Request(url, headers={"User-Agent": "CivicTwin-R-Research/2.0"})
            with urllib.request.urlopen(req, timeout=180) as resp, open(out_path, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
        meta.append({
            "name": fname,
            "path": str(out_path.relative_to(_PROJECT_ROOT)),
            "source_url": url,
            "license": "Copernicus DEM Licence (ESA / DLR / Airbus)",
            "attribution": "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA",
            "crs": "EPSG:4326 (vertical: EGM2008)",
            "resolution": "1 arc-second (~30m)",
            "units": "meters",
            "limitations": "Digital Surface Model (DSM): reflects rooftops and tree canopy as elevation bias in dense urban blocks; not surveyed ground street levels.",
        })
    return meta


def fetch_wfs_layers(force: bool = False) -> list[dict]:
    ctx = _insecure_ssl_ctx()
    meta = []
    for layer in WFS_LAYERS:
        safe_name = layer.split(":")[-1]
        out_path = WFS_DIR / f"{safe_name}.geojson"
        url = (
            f"{CFM_WFS_BASE}?service=WFS&version=1.0.0&request=GetFeature"
            f"&typeName={urllib.parse.quote(layer)}&outputFormat=application/json&srsName=EPSG:4326"
        )
        if out_path.exists() and out_path.stat().st_size > 100 and not force:
            data = json.loads(out_path.read_text())
            logger.info("WFS cached: %s (%d features)", safe_name, len(data.get("features", [])))
        else:
            logger.info("Fetching official CFM-DSS WFS layer: %s ...", layer)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "CivicTwin-R-Research/2.0"})
                with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
                    raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                out_path.write_text(json.dumps(data))
                logger.info("  Saved %s (%d features, %.1f KB)", safe_name, len(data.get("features", [])), len(raw) / 1024)
            except Exception as e:
                logger.warning("  Failed to fetch WFS %s: %s", layer, e)
                continue
        meta.append({
            "name": layer,
            "path": str(out_path.relative_to(_PROJECT_ROOT)),
            "source_url": url,
            "feature_count": len(data.get("features", [])),
            "crs": "EPSG:4326",
            "license": "Government of Tamil Nadu / Chennai Flood Monitoring & Spatial DSS Public Portal",
            "attribution": "Chennai Flood Monitoring and Spatial Decision Support System (CFM-DSS), Tamil Nadu Water Resources Department / GCC",
        })
    return meta


def _overpass_query(ql: str, label: str, timeout_sec: int = 60) -> dict | None:
    data_bytes = urllib.parse.urlencode({"data": ql}).encode("utf-8")
    for mirror in OVERPASS_MIRRORS:
        try:
            logger.info("Querying OSM Overpass (%s) via %s ...", label, mirror.split("/")[2])
            req = urllib.request.Request(
                mirror,
                data=data_bytes,
                headers={"User-Agent": "CivicTwin-R-Research/2.0 (Academic Urban Flood Twin)"},
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            elems = payload.get("elements", [])
            logger.info("  Retrieved %d OSM elements for %s", len(elems), label)
            return payload
        except Exception as e:
            logger.warning("  Mirror %s failed for %s: %s", mirror.split("/")[2], label, e)
            time.sleep(1.5)
    return None


def fetch_osm_layers(force: bool = False) -> list[dict]:
    # Broad Chennai overview: (12.88, 80.02, 13.22, 80.32)
    # Detailed South Chennai pilot catchment: (12.920, 80.175, 13.035, 80.268) sliced cleanly
    queries = {
        "osm_major_roads": (
            '[out:json][timeout:45];('
            'way["highway"~"^(motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link)$"](12.88,80.02,13.22,80.32);'
            ');out body;>;out skel qt;'
        ),
        "osm_bridges": (
            '[out:json][timeout:30];('
            'way["bridge"]["bridge"!="no"](12.88,80.02,13.22,80.32);'
            ');out body;>;out skel qt;'
        ),
        "osm_waterways_water": (
            '[out:json][timeout:45];('
            'way["waterway"~"^(river|canal|drain|stream)$"](12.88,80.02,13.22,80.32);'
            'way["natural"~"^(water|wetland)$"](12.88,80.02,13.22,80.32);'
            'relation["natural"~"^(water|wetland)$"](12.88,80.02,13.22,80.32);'
            'relation["waterway"="river"](12.88,80.02,13.22,80.32);'
            ');out body;>;out skel qt;'
        ),
        "osm_parks_landuse": (
            '[out:json][timeout:40];('
            'way["leisure"="park"](12.88,80.02,13.22,80.32);'
            'way["landuse"~"^(forest|grass|meadow|reservoir|basin|recreation_ground)$"](12.88,80.02,13.22,80.32);'
            ');out body;>;out skel qt;'
        ),
        # Local street network across South Chennai pilot domain
        "osm_local_streets_south": (
            '[out:json][timeout:45];('
            'way["highway"~"^(residential|unclassified|living_street)$"](12.925,80.180,13.030,80.262);'
            ');out body;>;out skel qt;'
        ),
        # Real building footprints in 4 pilot South Chennai tiles + upstream hubs
        "osm_buildings_velachery_saidapet": (
            '[out:json][timeout:45];('
            'way["building"](12.970,80.200,13.028,80.245);'
            ');out body;>;out skel qt;'
        ),
        "osm_buildings_adyar_perungudi": (
            '[out:json][timeout:45];('
            'way["building"](12.950,80.235,13.015,80.268);'
            ');out body;>;out skel qt;'
        ),
        "osm_buildings_pallikaranai_madipakkam": (
            '[out:json][timeout:45];('
            'way["building"](12.922,80.185,12.972,80.236);'
            ');out body;>;out skel qt;'
        ),
        "osm_buildings_upstream_corridors": (
            '[out:json][timeout:45];('
            'way["building"](12.918,80.095,12.936,80.122);'
            'way["building"](12.960,80.140,12.976,80.162);'
            'way["building"](13.028,80.148,13.046,80.168);'
            'way["building"](13.005,80.052,13.022,80.072);'
            ');out body;>;out skel qt;'
        ),
    }

    meta = []
    for name, ql in queries.items():
        out_path = OSM_DIR / f"{name}.json"
        if out_path.exists() and out_path.stat().st_size > 200 and not force:
            payload = json.loads(out_path.read_text())
            logger.info("OSM cached: %s (%d elements)", name, len(payload.get("elements", [])))
        else:
            payload = _overpass_query(ql, name)
            if payload is None:
                logger.warning("Skipping %s (Overpass unavailable)", name)
                continue
            out_path.write_text(json.dumps(payload))
            time.sleep(1.0)
        meta.append({
            "name": name,
            "path": str(out_path.relative_to(_PROJECT_ROOT)),
            "source_url": "https://www.openstreetmap.org (via Overpass API)",
            "element_count": len(payload.get("elements", [])),
            "crs": "EPSG:4326",
            "license": "Open Database License (ODbL 1.0)",
            "attribution": "© OpenStreetMap contributors",
        })
    return meta


def main():
    parser = argparse.ArgumentParser(description="Acquire real Chennai geographical datasets.")
    parser.add_argument("--force", action="store_true", help="Re-download existing cached files")
    args = parser.parse_args()

    dem_meta = fetch_dem_tiles(force=args.force)
    wfs_meta = fetch_wfs_layers(force=args.force)
    osm_meta = fetch_osm_layers(force=args.force)

    manifest = {
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "geographic_scope": "Chennai Metropolitan Basin & South Chennai Pilot Catchments",
        "extent_wgs84_broad": [80.02, 12.88, 80.32, 13.22],
        "extent_wgs84_pilot": [80.175, 12.920, 80.268, 13.035],
        "dem_datasets": dem_meta,
        "wfs_datasets": wfs_meta,
        "osm_datasets": osm_meta,
    }
    manifest_path = GEO_DIR / "acquisition_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("Saved acquisition manifest: %s", manifest_path)


if __name__ == "__main__":
    main()
