"""
CivicTwin-R — Projected Geospatial Infrastructure Exposure & Neighbourhood Intelligence Engine

Computes genuine vector-raster intersections in metric UTM Zone 44N (EPSG:32644) between
Landlab 2D OverlandFlow flood depth grids and verified OpenStreetMap / TN CFM-DSS / GCC layers:
  - Building footprints (`osm_buildings_south.geojson`, 18,198 footprints)
  - Major roads & local streets (`osm_roads_major.geojson` + `osm_streets_pilot.geojson`, deduplicated by osm_id)
  - Civic / critical-tag facilities strictly from verified OSM `building_type` attributes
  - Road bridges (`osm_bridges.geojson`)
  - Official Watersheds (`watersheds_south.geojson`, 36 South Chennai watersheds)
  - Official Greater Chennai Corporation Wards (`wards_chennai.geojson`, 200 wards)

Scientific & Metric Guarantees:
  - Area and length intersections are computed in EPSG:32644 meters (not WGS84 degrees).
  - Invalid input geometries are repaired via `shapely.validation.make_valid`.
  - Each asset is indexed across intersecting grid cells and counted AT MOST ONCE regardless of
    how many 150 m grid cells or depth tiers it spans.
  - Partial intersections attribute only the wet overlapping area/length >= depth threshold.
  - Assets completely outside the computational grid (`valid_land_mask & ~perm_water_mask`) are
    excluded from exposure counts and explicitly surfaced under data coverage statistics.
  - All outputs represent coarse 150 m grid **modelled potential exposure** screening indicators —
    never confirmed structural damage, road closures, casualties, or financial loss.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from pyproj import Transformer
from shapely import STRtree, box, make_valid
from shapely.geometry import shape
from shapely.ops import transform as shp_transform

logger = logging.getLogger("civictwin.exposure_engine")

WGS84_CRS = "EPSG:4326"
UTM44N_CRS = "EPSG:32644"

# Verified civic/critical OSM building_type tags actually present in osm_buildings_south.geojson
CRITICAL_BUILDING_TYPES = {
    "hospital",
    "clinic",
    "school",
    "university",
    "college",
    "train_station",
    "public",
    "civic",
    "fire_station",
    "police",
}

DEPTH_TIERS: List[Tuple[str, float, float]] = [
    ("0.05-0.15m", 0.05, 0.15),
    ("0.15-0.30m", 0.15, 0.30),
    ("0.30-0.60m", 0.30, 0.60),
    (">=0.60m", 0.60, float("inf")),
]

SCIENTIFIC_EXPOSURE_DISCLAIMER = (
    "Modelled potential exposure derived from 150 m Copernicus GLO-30 OverlandFlow screening "
    "intersected in EPSG:32644 with OSM/CFM-DSS vector geometries. Does not indicate verified "
    "structural building damage, passability/road closure, casualties, or financial cost."
)


@dataclass
class IndexedAsset:
    """Projected asset mapped to intersecting grid cell weights without double counting."""

    asset_id: str
    name: str
    category: str
    total_metric: float  # area_m2 for buildings, length_m for roads, count=1 for points
    in_domain_metric: float
    in_domain: bool
    cell_indices: np.ndarray  # flattened grid index r * cols + c
    cell_weights: np.ndarray  # intersecting area_m2 or length_m within each cell
    centroid_lonlat: Tuple[float, float]
    extra: Dict[str, Any]


@dataclass
class IndexedRegion:
    """Official boundary region (Watershed or GCC Ward) pre-indexed onto the UTM grid."""

    region_id: str
    name: str
    sublabel: str
    region_type: str  # "watershed" | "ward"
    total_area_km2: float
    in_domain_area_km2: float
    domain_coverage_pct: float
    in_domain: bool
    cell_indices: np.ndarray
    cell_weights_m2: np.ndarray
    building_indices: np.ndarray
    road_indices: np.ndarray
    stations_count: int
    waterways_count: int
    reservoirs_nearby: List[str]
    centroid_lonlat: Tuple[float, float]


def _safe_valid_geom(geom):
    """Repair invalid geometries safely without raising TopologyException."""
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        try:
            geom = make_valid(geom)
        except Exception:
            try:
                geom = geom.buffer(0)
            except Exception:
                return None
    if geom.is_empty:
        return None
    return geom


def _safe_pct(num: float, denom: float) -> Optional[float]:
    if denom is None or abs(denom) < 1e-12:
        return None
    return round((num / denom) * 100.0, 2)


def _depth_tier_label(depth_m: float) -> str:
    for lbl, lo, hi in DEPTH_TIERS:
        if lo <= depth_m < hi:
            return lbl
    return "<0.05m"


class SpatialExposureEngine:
    """
    Metric EPSG:32644 vector-raster exposure & neighbourhood engine.
    Supports both production Chennai GeoJSON assets and synthetic test fixtures.
    """

    def __init__(
        self,
        *,
        rows: int,
        cols: int,
        x_min: float,
        y_max: float,
        dx_m: float,
        valid_land_mask: np.ndarray,
        perm_water_mask: np.ndarray,
        buildings_geojson: Optional[Dict[str, Any]] = None,
        roads_geojson: Optional[Dict[str, Any]] = None,
        bridges_geojson: Optional[Dict[str, Any]] = None,
        watersheds_geojson: Optional[Dict[str, Any]] = None,
        wards_geojson: Optional[Dict[str, Any]] = None,
        stations_list: Optional[List[Dict[str, Any]]] = None,
        waterways_geojson: Optional[Dict[str, Any]] = None,
        geo_dir: Optional[Path] = None,
    ):
        self.rows = int(rows)
        self.cols = int(cols)
        self.x_min = float(x_min)
        self.y_max = float(y_max)
        self.dx_m = float(dx_m)
        self.cell_area_m2 = self.dx_m * self.dx_m
        self.geo_dir = geo_dir

        self.valid_land_mask = np.asarray(valid_land_mask, dtype=bool)
        self.perm_water_mask = np.asarray(perm_water_mask, dtype=bool)
        self.urban_domain_mask = (self.valid_land_mask & (~self.perm_water_mask)).ravel()

        self._tf_to_utm = Transformer.from_crs(WGS84_CRS, UTM44N_CRS, always_xy=True)
        self._tf_to_wgs = Transformer.from_crs(UTM44N_CRS, WGS84_CRS, always_xy=True)

        # Inline geojson sources (or lazily load from geo_dir)
        self._raw_buildings = buildings_geojson
        self._raw_roads = roads_geojson
        self._raw_bridges = bridges_geojson
        self._raw_watersheds = watersheds_geojson
        self._raw_wards = wards_geojson
        self._raw_stations = stations_list
        self._raw_waterways = waterways_geojson

        self._built = False
        self._build_time_ms = 0.0
        self.buildings: List[IndexedAsset] = []
        self.buildings_raw_geojson: List[Dict[str, Any]] = []
        self.roads: List[IndexedAsset] = []
        self.roads_raw_geojson: List[Dict[str, Any]] = []
        self.bridges: List[IndexedAsset] = []
        self.watersheds: List[IndexedRegion] = []
        self.wards: List[IndexedRegion] = []
        self._grid_polys: Optional[List[Any]] = None
        self._grid_tree: Optional[STRtree] = None
        self._exposure_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def from_terrain_engine(cls, terrain_engine_obj, geo_dir: Optional[Path] = None) -> "SpatialExposureEngine":
        from digital_twin.terrain_hydrology import PROCESSED_GEO_DIR

        gdir = geo_dir or PROCESSED_GEO_DIR
        return cls(
            rows=terrain_engine_obj.rows,
            cols=terrain_engine_obj.cols,
            x_min=terrain_engine_obj.x_min,
            y_max=terrain_engine_obj.y_max,
            dx_m=terrain_engine_obj.dx_m,
            valid_land_mask=terrain_engine_obj.valid_land_mask,
            perm_water_mask=terrain_engine_obj.perm_water_mask,
            geo_dir=gdir,
        )

    def _to_utm(self, geom):
        return shp_transform(self._tf_to_utm.transform, geom)

    def _to_wgs(self, geom):
        return shp_transform(self._tf_to_wgs.transform, geom)

    def _ensure_built(self) -> None:
        if self._built:
            return
        t0 = time.time()

        # Build exact UTM grid cell boxes ONCE
        polys = []
        for r in range(self.rows):
            y1 = self.y_max - r * self.dx_m
            y0 = y1 - self.dx_m
            for c in range(self.cols):
                x0 = self.x_min + c * self.dx_m
                polys.append(box(x0, y0, x0 + self.dx_m, y1))
        self._grid_polys = polys
        self._grid_tree = STRtree(polys)

        # Load sources from inline dicts or geo_dir
        b_feats = self._load_features(self._raw_buildings, "osm_buildings_south.geojson")
        if self._raw_roads is not None:
            r_feats = self._raw_roads.get("features", [])
        else:
            r_major = self._load_features(None, "osm_roads_major.geojson")
            r_pilot = self._load_features(None, "osm_streets_pilot.geojson")
            r_feats = r_major + r_pilot
        br_feats = self._load_features(self._raw_bridges, "osm_bridges.geojson")
        ws_feats = self._load_features(self._raw_watersheds, "watersheds_south.geojson")
        ward_feats = self._load_features(self._raw_wards, "wards_chennai.geojson")
        stations = self._raw_stations if self._raw_stations is not None else self._load_json_list("verified_stations.json")
        waterways = self._load_features(self._raw_waterways, "waterways_official.geojson")

        self._index_buildings(b_feats)
        self._index_roads(r_feats)
        self._index_bridges(br_feats)

        # Precompute UTM centroids for buildings & roads + stations/waterways trees for neighbourhood stats
        b_centroids_utm = []
        for b in self.buildings:
            bx, by = self._tf_to_utm.transform(b.centroid_lonlat[0], b.centroid_lonlat[1])
            b_centroids_utm.append(box(bx - 0.1, by - 0.1, bx + 0.1, by + 0.1).centroid)
        b_tree = STRtree(b_centroids_utm) if b_centroids_utm else None

        r_centroids_utm = []
        for r in self.roads:
            rx, ry = self._tf_to_utm.transform(r.centroid_lonlat[0], r.centroid_lonlat[1])
            r_centroids_utm.append(box(rx - 0.1, ry - 0.1, rx + 0.1, ry + 0.1).centroid)
        r_tree = STRtree(r_centroids_utm) if r_centroids_utm else None

        st_pts_utm = []
        for st in stations:
            coords = st.get("coordinates")
            if coords and len(coords) >= 2:
                sx, sy = self._tf_to_utm.transform(coords[0], coords[1])
                st_pts_utm.append(box(sx - 0.1, sy - 0.1, sx + 0.1, sy + 0.1).centroid)
        st_tree = STRtree(st_pts_utm) if st_pts_utm else None

        ww_utm = []
        for ww in waterways:
            g = _safe_valid_geom(shape(ww["geometry"])) if ww.get("geometry") else None
            if g is not None:
                ww_utm.append(self._to_utm(g))
        ww_tree = STRtree(ww_utm) if ww_utm else None

        reservoirs_utm = [
            ("Chembarambakkam", self._to_utm(box(80.067, 13.011, 80.069, 13.013).centroid)),
        ]

        self._index_regions(
            ws_feats, "watershed", self.watersheds, b_tree, r_tree, st_tree, ww_tree, reservoirs_utm
        )
        self._index_regions(
            ward_feats, "ward", self.wards, b_tree, r_tree, st_tree, ww_tree, reservoirs_utm
        )

        self._build_time_ms = round((time.time() - t0) * 1000.0, 2)
        self._built = True
        logger.info(
            "SpatialExposureEngine indexed %d buildings, %d roads, %d bridges, %d watersheds, %d wards in %.1f ms",
            len(self.buildings),
            len(self.roads),
            len(self.bridges),
            len(self.watersheds),
            len(self.wards),
            self._build_time_ms,
        )

    def _load_features(self, inline_gj: Optional[Dict[str, Any]], filename: str) -> List[Dict[str, Any]]:
        if inline_gj is not None:
            return inline_gj.get("features", [])
        if self.geo_dir and (self.geo_dir / filename).exists():
            return json.loads((self.geo_dir / filename).read_text()).get("features", [])
        return []

    def _load_json_list(self, filename: str) -> List[Dict[str, Any]]:
        if self.geo_dir and (self.geo_dir / filename).exists():
            data = json.loads((self.geo_dir / filename).read_text())
            return data if isinstance(data, list) else []
        return []

    def _cell_window(self, minx: float, miny: float, maxx: float, maxy: float) -> Tuple[int, int, int, int]:
        c0 = max(0, int(math.floor((minx - self.x_min) / self.dx_m)))
        c1 = min(self.cols - 1, int(math.floor((maxx - self.x_min) / self.dx_m)))
        r0 = max(0, int(math.floor((self.y_max - maxy) / self.dx_m)))
        r1 = min(self.rows - 1, int(math.floor((self.y_max - miny) / self.dx_m)))
        return r0, r1, c0, c1

    def _index_buildings(self, features: Sequence[Dict[str, Any]]) -> None:
        seen_ids = set()
        for idx, feat in enumerate(features):
            raw_geom = feat.get("geometry")
            if not raw_geom:
                continue
            props = feat.get("properties") or {}
            oid = str(props.get("osm_id") or f"b_{idx}")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)

            try:
                g_wgs = _safe_valid_geom(shape(raw_geom))
            except Exception:
                continue
            if g_wgs is None:
                continue

            g_utm = _safe_valid_geom(self._to_utm(g_wgs))
            if g_utm is None or g_utm.area <= 0.0:
                continue

            total_area = float(g_utm.area)
            r0, r1, c0, c1 = self._cell_window(*g_utm.bounds)
            c_idx: List[int] = []
            c_wts: List[float] = []
            in_domain_area = 0.0

            if r0 <= r1 and c0 <= c1:
                if r0 == r1 and c0 == c1:
                    flat_i = r0 * self.cols + c0
                    if self.urban_domain_mask[flat_i]:
                        c_idx.append(flat_i)
                        c_wts.append(total_area)
                        in_domain_area += total_area
                else:
                    for r in range(r0, r1 + 1):
                        for c in range(c0, c1 + 1):
                            flat_i = r * self.cols + c
                            if not self.urban_domain_mask[flat_i]:
                                continue
                            cell_poly = self._grid_polys[flat_i]
                            try:
                                inter = cell_poly.intersection(g_utm)
                                area_m2 = float(inter.area)
                            except Exception:
                                area_m2 = 0.0
                            if area_m2 > 0.01:
                                c_idx.append(flat_i)
                                c_wts.append(area_m2)
                                in_domain_area += area_m2

            cen = g_wgs.centroid
            btype = str(props.get("building_type") or "yes").lower().strip()
            self.buildings.append(
                IndexedAsset(
                    asset_id=oid,
                    name=str(props.get("name") or f"Building #{oid}"),
                    category=btype,
                    total_metric=total_area,
                    in_domain_metric=in_domain_area,
                    in_domain=bool(in_domain_area > 0.01),
                    cell_indices=np.array(c_idx, dtype=np.int32),
                    cell_weights=np.array(c_wts, dtype=np.float32),
                    centroid_lonlat=(round(cen.x, 6), round(cen.y, 6)),
                    extra={
                        "is_critical": btype in CRITICAL_BUILDING_TYPES,
                        "height_m": props.get("height_m"),
                        "floors": props.get("floors"),
                        "height_source": props.get("height_source"),
                    },
                )
            )
            self.buildings_raw_geojson.append(feat)

    def _index_roads(self, features: Sequence[Dict[str, Any]]) -> None:
        seen_ids = set()
        for idx, feat in enumerate(features):
            raw_geom = feat.get("geometry")
            if not raw_geom:
                continue
            props = feat.get("properties") or {}
            oid = str(props.get("osm_id") or f"r_{idx}")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)

            try:
                g_wgs = _safe_valid_geom(shape(raw_geom))
            except Exception:
                continue
            if g_wgs is None:
                continue

            g_utm = _safe_valid_geom(self._to_utm(g_wgs))
            if g_utm is None or g_utm.length <= 0.0:
                continue

            total_len = float(g_utm.length)
            r0, r1, c0, c1 = self._cell_window(*g_utm.bounds)
            c_idx: List[int] = []
            c_wts: List[float] = []
            in_domain_len = 0.0

            if r0 <= r1 and c0 <= c1:
                if r0 == r1 and c0 == c1:
                    flat_i = r0 * self.cols + c0
                    if self.urban_domain_mask[flat_i]:
                        c_idx.append(flat_i)
                        c_wts.append(total_len)
                        in_domain_len += total_len
                else:
                    for r in range(r0, r1 + 1):
                        for c in range(c0, c1 + 1):
                            flat_i = r * self.cols + c
                            if not self.urban_domain_mask[flat_i]:
                                continue
                            cell_poly = self._grid_polys[flat_i]
                            try:
                                inter = cell_poly.intersection(g_utm)
                                seg_len = float(inter.length)
                            except Exception:
                                seg_len = 0.0
                            if seg_len > 0.1:
                                c_idx.append(flat_i)
                                c_wts.append(seg_len)
                                in_domain_len += seg_len

            cen = g_wgs.centroid
            hw = str(props.get("highway") or "unclassified").lower().strip()
            self.roads.append(
                IndexedAsset(
                    asset_id=oid,
                    name=str(props.get("name") or f"{hw.title()} Road"),
                    category=hw,
                    total_metric=total_len,
                    in_domain_metric=in_domain_len,
                    in_domain=bool(in_domain_len > 0.1),
                    cell_indices=np.array(c_idx, dtype=np.int32),
                    cell_weights=np.array(c_wts, dtype=np.float32),
                    centroid_lonlat=(round(cen.x, 6), round(cen.y, 6)),
                    extra={"bridge": props.get("bridge"), "lanes": props.get("lanes")},
                )
            )
            self.roads_raw_geojson.append(feat)

    def _index_bridges(self, features: Sequence[Dict[str, Any]]) -> None:
        seen = set()
        for idx, feat in enumerate(features):
            raw_geom = feat.get("geometry")
            if not raw_geom:
                continue
            props = feat.get("properties") or {}
            oid = str(props.get("osm_id") or f"br_{idx}")
            if oid in seen:
                continue
            seen.add(oid)
            try:
                g_wgs = _safe_valid_geom(shape(raw_geom))
                g_utm = _safe_valid_geom(self._to_utm(g_wgs)) if g_wgs else None
            except Exception:
                continue
            if g_utm is None:
                continue
            r0, r1, c0, c1 = self._cell_window(*g_utm.bounds)
            c_idx: List[int] = []
            c_wts: List[float] = []
            if r0 <= r1 and c0 <= c1:
                for r in range(r0, r1 + 1):
                    for c in range(c0, c1 + 1):
                        flat_i = r * self.cols + c
                        if self.valid_land_mask.ravel()[flat_i] and self._grid_polys[flat_i].intersects(g_utm):
                            c_idx.append(flat_i)
                            c_wts.append(1.0)
            cen = g_wgs.centroid
            self.bridges.append(
                IndexedAsset(
                    asset_id=oid,
                    name=str(props.get("name") or f"Bridge #{oid}"),
                    category=str(props.get("highway") or "bridge"),
                    total_metric=float(g_utm.length),
                    in_domain_metric=float(g_utm.length) if c_idx else 0.0,
                    in_domain=bool(len(c_idx) > 0),
                    cell_indices=np.array(c_idx, dtype=np.int32),
                    cell_weights=np.array(c_wts, dtype=np.float32),
                    centroid_lonlat=(round(cen.x, 6), round(cen.y, 6)),
                    extra={},
                )
            )

    def _index_regions(
        self,
        features: Sequence[Dict[str, Any]],
        region_type: str,
        target_list: List[IndexedRegion],
        b_tree: Optional[STRtree],
        r_tree: Optional[STRtree],
        st_tree: Optional[STRtree],
        ww_tree: Optional[STRtree],
        reservoirs_utm: List[Tuple[str, Any]],
    ) -> None:
        for idx, feat in enumerate(features):
            raw_geom = feat.get("geometry")
            if not raw_geom:
                continue
            props = feat.get("properties") or {}
            try:
                g_wgs = _safe_valid_geom(shape(raw_geom))
                g_utm = _safe_valid_geom(self._to_utm(g_wgs)) if g_wgs else None
            except Exception:
                continue
            if g_utm is None or g_utm.area <= 0.0:
                continue

            total_km2 = float(g_utm.area) / 1e6
            r0, r1, c0, c1 = self._cell_window(*g_utm.bounds)
            c_idx: List[int] = []
            c_wts: List[float] = []
            in_domain_m2 = 0.0

            if r0 <= r1 and c0 <= c1:
                for r in range(r0, r1 + 1):
                    for c in range(c0, c1 + 1):
                        flat_i = r * self.cols + c
                        if not self.urban_domain_mask[flat_i]:
                            continue
                        cell_poly = self._grid_polys[flat_i]
                        try:
                            area_m2 = float(cell_poly.intersection(g_utm).area)
                        except Exception:
                            area_m2 = 0.0
                        if area_m2 > 1.0:
                            c_idx.append(flat_i)
                            c_wts.append(area_m2)
                            in_domain_m2 += area_m2

            in_dom_km2 = in_domain_m2 / 1e6
            cov_pct = round(min(100.0, (in_dom_km2 / max(1e-6, total_km2)) * 100.0), 1)
            in_domain = in_dom_km2 >= 0.01

            b_idx = b_tree.query(g_utm, predicate="intersects") if b_tree is not None and in_domain else np.array([], dtype=np.int32)
            r_idx = r_tree.query(g_utm, predicate="intersects") if r_tree is not None and in_domain else np.array([], dtype=np.int32)
            st_cnt = int(len(st_tree.query(g_utm, predicate="intersects"))) if st_tree is not None else 0
            ww_cnt = int(len(ww_tree.query(g_utm, predicate="intersects"))) if ww_tree is not None else 0
            res_names = [nm for nm, rpt in reservoirs_utm if g_utm.buffer(2500.0).intersects(rpt)]

            if region_type == "watershed":
                rid = f"ws_{props.get('id', idx)}"
                name = str(props.get("name") or f"Watershed {idx}")
                sub = str(props.get("subbasin") or "")
            else:
                ward_no = props.get("ward", props.get("id", idx))
                zone_no = props.get("zone_", "")
                rid = f"ward_{ward_no}"
                name = f"Ward {ward_no}"
                sub = f"GCC Zone {zone_no}" if zone_no != "" else "GCC Boundary"

            cen = g_wgs.centroid
            target_list.append(
                IndexedRegion(
                    region_id=rid,
                    name=name,
                    sublabel=sub,
                    region_type=region_type,
                    total_area_km2=round(total_km2, 3),
                    in_domain_area_km2=round(in_dom_km2, 3),
                    domain_coverage_pct=cov_pct,
                    in_domain=in_domain,
                    cell_indices=np.array(c_idx, dtype=np.int32),
                    cell_weights_m2=np.array(c_wts, dtype=np.float32),
                    building_indices=np.asarray(b_idx, dtype=np.int32),
                    road_indices=np.asarray(r_idx, dtype=np.int32),
                    stations_count=st_cnt,
                    waterways_count=ww_cnt,
                    reservoirs_nearby=res_names,
                    centroid_lonlat=(round(cen.x, 6), round(cen.y, 6)),
                )
            )

    def evaluate_scenario_exposure(
        self,
        depth_grid_m: np.ndarray,
        scenario_id: str,
        scenario_name: str,
        threshold_m: float = 0.15,
        include_highlight_geojson: bool = True,
        max_highlight_features: int = 450,
    ) -> Dict[str, Any]:
        """
        Compute projected building, road, bridge, and critical-facility exposure
        for a given 2D flood depth grid at depth >= threshold_m.
        """
        self._ensure_built()
        t0 = time.time()
        depth_arr = np.asarray(depth_grid_m, dtype=np.float64)
        grid_sig = hashlib.sha256(depth_arr.tobytes()).hexdigest()[:12]
        ckey = f"exp:{grid_sig}:{round(float(threshold_m), 3)}:{include_highlight_geojson}:{max_highlight_features}:{scenario_id}"
        if ckey in self._exposure_cache:
            return self._exposure_cache[ckey]
        depth_flat = depth_arr.ravel()
        thresh = float(threshold_m)

        # Building exposure (zero double counting)
        exp_b_count = 0
        exp_b_area_m2 = 0.0
        exp_b_depths: List[float] = []
        b_tier_counts = {lbl: 0 for lbl, _, _ in DEPTH_TIERS}
        b_tier_areas = {lbl: 0.0 for lbl, _, _ in DEPTH_TIERS}
        critical_by_type: Dict[str, int] = {}
        b_type_breakdown: Dict[str, Dict[str, Any]] = {}
        b_highlights: List[Tuple[float, int, Dict[str, Any]]] = []
        total_b_in_domain = 0
        outside_b_count = 0

        for b_idx, asset in enumerate(self.buildings):
            if not asset.in_domain:
                outside_b_count += 1
                continue
            total_b_in_domain += 1
            d_cells = depth_flat[asset.cell_indices]
            wet_mask = d_cells >= thresh
            if not np.any(wet_mask):
                continue

            exp_b_count += 1
            wet_area = float(asset.cell_weights[wet_mask].sum())
            max_d = float(d_cells[wet_mask].max())
            exp_b_area_m2 += wet_area
            exp_b_depths.append(max_d)

            # Tier breakdown by maximum intersecting cell depth (asset counted once per tier)
            lbl = _depth_tier_label(max_d)
            if lbl in b_tier_counts:
                b_tier_counts[lbl] += 1
                b_tier_areas[lbl] += wet_area

            tb_entry = b_type_breakdown.setdefault(
                asset.category, {"building_type": asset.category, "count": 0, "exposed_area_m2": 0.0}
            )
            tb_entry["count"] += 1
            tb_entry["exposed_area_m2"] += wet_area

            if asset.extra.get("is_critical"):
                critical_by_type[asset.category] = critical_by_type.get(asset.category, 0) + 1

            if include_highlight_geojson and b_idx < len(self.buildings_raw_geojson):
                feat = self.buildings_raw_geojson[b_idx]
                b_highlights.append((max_d, b_idx, {
                    "type": "Feature",
                    "properties": {
                        "asset_kind": "building",
                        "osm_id": asset.asset_id,
                        "name": asset.name,
                        "building_type": asset.category,
                        "is_critical": bool(asset.extra.get("is_critical")),
                        "exposed_area_m2": round(wet_area, 1),
                        "modeled_max_depth_m": round(max_d, 3),
                        "depth_tier": lbl,
                    },
                    "geometry": feat["geometry"],
                }))

        # Road exposure (zero double counting)
        exp_r_count = 0
        exp_r_len_m = 0.0
        exp_r_depths: List[float] = []
        r_by_class: Dict[str, Dict[str, Any]] = {}
        r_tier_km = {lbl: 0.0 for lbl, _, _ in DEPTH_TIERS}
        r_highlights: List[Tuple[float, int, Dict[str, Any]]] = []
        total_r_in_domain = 0
        outside_r_count = 0

        for r_idx, asset in enumerate(self.roads):
            if not asset.in_domain:
                outside_r_count += 1
                continue
            total_r_in_domain += 1
            d_cells = depth_flat[asset.cell_indices]
            wet_mask = d_cells >= thresh
            if not np.any(wet_mask):
                continue

            exp_r_count += 1
            wet_len_m = float(asset.cell_weights[wet_mask].sum())
            max_d = float(d_cells[wet_mask].max())
            exp_r_len_m += wet_len_m
            exp_r_depths.append(max_d)

            lbl = _depth_tier_label(max_d)
            if lbl in r_tier_km:
                r_tier_km[lbl] += wet_len_m / 1000.0

            cls_entry = r_by_class.setdefault(
                asset.category, {"highway_class": asset.category, "segments": 0, "exposed_length_km": 0.0, "max_depth_m": 0.0}
            )
            cls_entry["segments"] += 1
            cls_entry["exposed_length_km"] += wet_len_m / 1000.0
            cls_entry["max_depth_m"] = max(cls_entry["max_depth_m"], max_d)

            if include_highlight_geojson and r_idx < len(self.roads_raw_geojson):
                feat = self.roads_raw_geojson[r_idx]
                r_highlights.append((max_d, r_idx, {
                    "type": "Feature",
                    "properties": {
                        "asset_kind": "road",
                        "osm_id": asset.asset_id,
                        "name": asset.name,
                        "highway": asset.category,
                        "exposed_length_m": round(wet_len_m, 1),
                        "modeled_max_depth_m": round(max_d, 3),
                        "depth_tier": lbl,
                    },
                    "geometry": feat["geometry"],
                }))

        # Bridges exposure
        exp_bridges_count = 0
        for br in self.bridges:
            if not br.in_domain:
                continue
            if np.any(depth_flat[br.cell_indices] >= thresh):
                exp_bridges_count += 1

        # Highlight top affected features cleanly
        b_highlights.sort(key=lambda t: t[0], reverse=True)
        r_highlights.sort(key=lambda t: t[0], reverse=True)
        highlighted_features = (
            [t[2] for t in b_highlights[:max_highlight_features]]
            + [t[2] for t in r_highlights[:max_highlight_features]]
        )

        # Round class breakdowns
        b_types_sorted = sorted(
            [
                {
                    "building_type": v["building_type"],
                    "count": v["count"],
                    "exposed_area_m2": round(v["exposed_area_m2"], 1),
                }
                for v in b_type_breakdown.values()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )
        r_classes_sorted = sorted(
            [
                {
                    "highway_class": v["highway_class"],
                    "segments": v["segments"],
                    "exposed_length_km": round(v["exposed_length_km"], 3),
                    "max_depth_m": round(v["max_depth_m"], 3),
                }
                for v in r_by_class.values()
            ],
            key=lambda x: x["exposed_length_km"],
            reverse=True,
        )

        res = {
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "assessment_label": "modelled_potential_exposure",
            "crs": UTM44N_CRS,
            "computational_resolution_m": self.dx_m,
            "depth_threshold_m": round(thresh, 3),
            "coverage": {
                "buildings_total": len(self.buildings),
                "buildings_in_domain": total_b_in_domain,
                "buildings_outside_domain": outside_b_count,
                "roads_total_deduplicated": len(self.roads),
                "roads_in_domain": total_r_in_domain,
                "roads_outside_domain": outside_r_count,
                "bridges_total": len(self.bridges),
            },
            "buildings": {
                "exposed_count": exp_b_count,
                "exposed_pct_of_in_domain": _safe_pct(exp_b_count, total_b_in_domain) or 0.0,
                "exposed_footprint_area_m2": round(exp_b_area_m2, 1),
                "exposed_footprint_area_ha": round(exp_b_area_m2 / 10000.0, 2),
                "mean_exposed_max_depth_m": round(float(np.mean(exp_b_depths)), 3) if exp_b_depths else 0.0,
                "max_depth_at_building_m": round(float(np.max(exp_b_depths)), 3) if exp_b_depths else 0.0,
                "depth_tiers_count": b_tier_counts,
                "depth_tiers_area_m2": {k: round(v, 1) for k, v in b_tier_areas.items()},
                "by_building_type": b_types_sorted[:15],
                "critical_civic_facilities": {
                    "total_exposed": sum(critical_by_type.values()),
                    "by_type": critical_by_type,
                    "provenance": "Verified OSM building_type tags (hospital/school/university/train_station/public)",
                },
            },
            "roads": {
                "exposed_segments_count": exp_r_count,
                "exposed_length_km": round(exp_r_len_m / 1000.0, 3),
                "mean_exposed_max_depth_m": round(float(np.mean(exp_r_depths)), 3) if exp_r_depths else 0.0,
                "max_depth_at_road_m": round(float(np.max(exp_r_depths)), 3) if exp_r_depths else 0.0,
                "depth_tiers_km": {k: round(v, 3) for k, v in r_tier_km.items()},
                "by_highway_class": r_classes_sorted,
            },
            "bridges": {
                "intersecting_wet_cells_count": exp_bridges_count,
            },
            "highlight_geojson": {
                "type": "FeatureCollection",
                "features": highlighted_features,
            },
            "computation_time_ms": round((time.time() - t0) * 1000.0, 2),
            "scientific_disclaimer": SCIENTIFIC_EXPOSURE_DISCLAIMER,
        }
        if len(self._exposure_cache) > 32:
            self._exposure_cache.pop(next(iter(self._exposure_cache)))
        self._exposure_cache[ckey] = res
        return res

    def evaluate_neighbourhoods(
        self,
        depth_grid_m: np.ndarray,
        scenario_id: str,
        scenario_name: str,
        boundary_type: str = "watersheds",
        threshold_m: float = 0.15,
    ) -> Dict[str, Any]:
        """
        Aggregate scenario depths and exposure across official Watersheds or GCC Wards
        in projected UTM 44N coordinates, keeping coverage separate from severity.
        """
        self._ensure_built()
        depth_flat = np.asarray(depth_grid_m, dtype=np.float64).ravel()
        thresh = float(threshold_m)
        regions = self.wards if boundary_type == "wards" else self.watersheds

        summaries: List[Dict[str, Any]] = []
        for reg in regions:
            if not reg.in_domain or len(reg.cell_indices) == 0:
                summaries.append({
                    "region_id": reg.region_id,
                    "name": reg.name,
                    "sublabel": reg.sublabel,
                    "region_type": reg.region_type,
                    "in_computational_domain": False,
                    "total_area_km2": reg.total_area_km2,
                    "in_domain_area_km2": reg.in_domain_area_km2,
                    "domain_coverage_pct": reg.domain_coverage_pct,
                    "inundated_area_km2": None,
                    "inundated_pct_of_in_domain": None,
                    "mean_depth_m": None,
                    "max_depth_m": None,
                    "exposed_buildings_count": None,
                    "exposed_buildings_area_m2": None,
                    "exposed_roads_km": None,
                    "stations_count": reg.stations_count,
                    "waterways_count": reg.waterways_count,
                    "reservoirs_nearby": reg.reservoirs_nearby,
                    "centroid": list(reg.centroid_lonlat),
                })
                continue

            d_vals = depth_flat[reg.cell_indices]
            wet_mask = d_vals >= thresh
            wet_area_km2 = float(reg.cell_weights_m2[wet_mask].sum()) / 1e6
            pct_inundated = round(min(100.0, (wet_area_km2 / max(1e-6, reg.in_domain_area_km2)) * 100.0), 2)
            mean_d = round(float(d_vals[wet_mask].mean()), 3) if np.any(wet_mask) else 0.0
            max_d = round(float(d_vals.max()), 3)

            b_exp = 0
            b_area = 0.0
            for bi in reg.building_indices:
                b = self.buildings[int(bi)]
                if len(b.cell_indices) > 0:
                    bd = depth_flat[b.cell_indices]
                    bw = bd >= thresh
                    if np.any(bw):
                        b_exp += 1
                        b_area += float(b.cell_weights[bw].sum())

            r_km = 0.0
            for ri in reg.road_indices:
                rd = self.roads[int(ri)]
                if len(rd.cell_indices) > 0:
                    r_vals = depth_flat[rd.cell_indices]
                    rw = r_vals >= thresh
                    if np.any(rw):
                        r_km += float(rd.cell_weights[rw].sum()) / 1000.0

            summaries.append({
                "region_id": reg.region_id,
                "name": reg.name,
                "sublabel": reg.sublabel,
                "region_type": reg.region_type,
                "in_computational_domain": True,
                "total_area_km2": reg.total_area_km2,
                "in_domain_area_km2": reg.in_domain_area_km2,
                "domain_coverage_pct": reg.domain_coverage_pct,
                "inundated_area_km2": round(wet_area_km2, 3),
                "inundated_pct_of_in_domain": pct_inundated,
                "mean_depth_m": mean_d,
                "max_depth_m": max_d,
                "exposed_buildings_count": b_exp,
                "exposed_buildings_area_m2": round(b_area, 1),
                "exposed_roads_km": round(r_km, 3),
                "stations_count": reg.stations_count,
                "waterways_count": reg.waterways_count,
                "reservoirs_nearby": reg.reservoirs_nearby,
                "centroid": list(reg.centroid_lonlat),
            })

        in_dom = [s for s in summaries if s["in_computational_domain"]]
        in_dom.sort(key=lambda s: (s["inundated_area_km2"] or 0.0), reverse=True)
        out_dom = [s for s in summaries if not s["in_computational_domain"]]

        return {
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "boundary_type": boundary_type,
            "source_dataset": "Official GCC Wards (200 boundaries)" if boundary_type == "wards" else "Official South Chennai Watersheds (36 boundaries)",
            "depth_threshold_m": round(thresh, 3),
            "in_domain_regions_count": len(in_dom),
            "outside_domain_regions_count": len(out_dom),
            "regions": in_dom + out_dom,
            "scientific_disclaimer": SCIENTIFIC_EXPOSURE_DISCLAIMER,
        }

    def compare_exposure(
        self,
        base_depth_m: np.ndarray,
        alt_depth_m: np.ndarray,
        base_id: str,
        base_name: str,
        alt_id: str,
        alt_name: str,
        threshold_m: float = 0.15,
    ) -> Dict[str, Any]:
        """Compare potential infrastructure exposure between two scenario depth grids."""
        eb = self.evaluate_scenario_exposure(base_depth_m, base_id, base_name, threshold_m=threshold_m, include_highlight_geojson=False)
        ea = self.evaluate_scenario_exposure(alt_depth_m, alt_id, alt_name, threshold_m=threshold_m, include_highlight_geojson=False)

        b0 = eb["buildings"]["exposed_count"]
        b1 = ea["buildings"]["exposed_count"]
        ba0 = eb["buildings"]["exposed_footprint_area_m2"]
        ba1 = ea["buildings"]["exposed_footprint_area_m2"]
        r0 = eb["roads"]["exposed_length_km"]
        r1 = ea["roads"]["exposed_length_km"]

        return {
            "depth_threshold_m": round(float(threshold_m), 3),
            "baseline": {
                "exposed_buildings_count": b0,
                "exposed_buildings_area_m2": ba0,
                "exposed_roads_km": r0,
                "critical_facilities_exposed": eb["buildings"]["critical_civic_facilities"]["total_exposed"],
            },
            "alternate": {
                "exposed_buildings_count": b1,
                "exposed_buildings_area_m2": ba1,
                "exposed_roads_km": r1,
                "critical_facilities_exposed": ea["buildings"]["critical_civic_facilities"]["total_exposed"],
            },
            "deltas": {
                "exposed_buildings_count": b1 - b0,
                "exposed_buildings_pct_change": _safe_pct(b1 - b0, b0),
                "exposed_buildings_area_m2": round(ba1 - ba0, 1),
                "exposed_buildings_area_pct_change": _safe_pct(ba1 - ba0, ba0),
                "exposed_roads_km": round(r1 - r0, 3),
                "exposed_roads_pct_change": _safe_pct(r1 - r0, r0),
                "critical_facilities_delta": (
                    ea["buildings"]["critical_civic_facilities"]["total_exposed"]
                    - eb["buildings"]["critical_civic_facilities"]["total_exposed"]
                ),
            },
            "scientific_disclaimer": SCIENTIFIC_EXPOSURE_DISCLAIMER,
        }


_DEFAULT_EXPOSURE_ENGINE: Optional[SpatialExposureEngine] = None


def get_exposure_engine() -> SpatialExposureEngine:
    """Return cached singleton SpatialExposureEngine initialized from Chennai UTM44N DEM."""
    global _DEFAULT_EXPOSURE_ENGINE
    if _DEFAULT_EXPOSURE_ENGINE is None:
        from digital_twin.terrain_hydrology import terrain_engine

        _DEFAULT_EXPOSURE_ENGINE = SpatialExposureEngine.from_terrain_engine(terrain_engine)
    return _DEFAULT_EXPOSURE_ENGINE
