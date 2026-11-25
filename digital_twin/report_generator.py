"""
CivicTwin-R — Offline Engineering Dossier & Scientific PDF/CSV Report Generator

Produces reproducible, print-ready A4 PDF engineering reports and structured CSV exports
directly from live Landlab 2D OverlandFlow results, SpatialExposureEngine intersections,
official Neighbourhood/Watershed summaries, and Scenario Comparison deltas.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("civictwin.report_generator")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Print-legible high-contrast report palette aligned with Obsidian Ocean semantic hierarchy
_BRAND_DARK = colors.HexColor("#0C1118")
_BRAND_SLATE = colors.HexColor("#253140")
_BRAND_BLUE = colors.HexColor("#1D6FA5")
_BRAND_TEAL = colors.HexColor("#0E7490")
_BRAND_ALT_BG = colors.HexColor("#F4F7FA")
_BORDER_GRAY = colors.HexColor("#CBD5E1")
_TEXT_MAIN = colors.HexColor("#0F172A")
_TEXT_MUTED = colors.HexColor("#475569")


def _dataset_checksums() -> Dict[str, str]:
    targets = [
        _PROJECT_ROOT / "data" / "processed" / "chennai_arg_rainfall.csv",
        _PROJECT_ROOT / "data" / "processed" / "chennai_reservoirs.csv",
        _PROJECT_ROOT / "data" / "raw" / "cfm_dashboard_raw.json",
        _PROJECT_ROOT / "data" / "raw" / "chennai_michaung_hourly_raw.json",
    ]
    out: Dict[str, str] = {}
    for p in targets:
        if p.exists():
            out[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    return out


def _render_spatial_map_png(
    terrain_engine_obj,
    scenario_result: Dict[str, Any],
) -> Optional[io.BytesIO]:
    """Generate genuine georeferenced Copernicus DSM + Flood Depth map figure in EPSG:32644 km."""
    try:
        elev = terrain_engine_obj.elevation_m
        land = terrain_engine_obj.valid_land_mask
        perm = terrain_engine_obj.perm_water_mask
        depth = np.where(land & (~perm), scenario_result["_final_depth_grid"], np.nan)

        x_km0 = terrain_engine_obj.x_min / 1000.0
        x_km1 = (terrain_engine_obj.x_min + terrain_engine_obj.cols * terrain_engine_obj.dx_m) / 1000.0
        y_km1 = terrain_engine_obj.y_max / 1000.0
        y_km0 = (terrain_engine_obj.y_max - terrain_engine_obj.rows * terrain_engine_obj.dx_m) / 1000.0
        extent = [x_km0, x_km1, y_km0, y_km1]

        fig, ax = plt.subplots(figsize=(8.2, 4.9), dpi=180)
        fig.patch.set_facecolor("#FFFFFF")
        ax.set_facecolor("#E2E8F0")

        # Base terrain relief in meters
        elev_disp = np.where(land, np.clip(elev, 0, 60), np.nan)
        ax.imshow(elev_disp, extent=extent, origin="upper", cmap="Greys_r", alpha=0.55)

        # Permanent waterbodies crisp cyan-slate
        perm_rgba = np.zeros((*perm.shape, 4), dtype=np.float32)
        perm_rgba[perm] = [0.06, 0.35, 0.55, 0.65]
        ax.imshow(perm_rgba, extent=extent, origin="upper")

        # Modeled depth sequential tiers
        cmap = ListedColormap(["#4BA3D9", "#36C2C9", "#E9B65C", "#F16D75"])
        bounds = [0.03, 0.15, 0.30, 0.60, 5.0]
        norm = BoundaryNorm(bounds, cmap.N)
        d_plot = np.where(depth >= 0.03, depth, np.nan)
        im = ax.imshow(d_plot, extent=extent, origin="upper", cmap=cmap, norm=norm, alpha=0.88)

        # Annotate focus basins in UTM km
        for loc in scenario_result.get("location_impacts", []):
            lon, lat = loc["coordinates"]
            ux, uy = terrain_engine_obj._tf_to_utm.transform(lon, lat)
            ax.scatter([ux / 1000.0], [uy / 1000.0], s=18, c="#0F172A", edgecolors="#FFFFFF", linewidths=0.7, zorder=5)
            short_nm = loc["name"].split("(")[0].strip()
            ax.text(
                ux / 1000.0 + 0.25,
                uy / 1000.0 + 0.2,
                f"{short_nm}\n({loc['modeled_max_depth_m']}m)",
                fontsize=6.5,
                color="#0F172A",
                bbox=dict(boxstyle="round,pad=0.15", facecolor="#FFFFFF", edgecolor="#CBD5E1", alpha=0.85),
                zorder=6,
            )

        cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, ticks=[0.09, 0.225, 0.45, 1.2])
        cbar.ax.set_yticklabels(["0.03–0.15m", "0.15–0.30m", "0.30–0.60m", ">=0.60m"], fontsize=7)
        cbar.set_label("Modeled Depth (m)", fontsize=7.5)

        sc = scenario_result["scenario"]
        ax.set_title(
            f"South Chennai (EPSG:32644 · 150m Grid) — {sc['name']}",
            fontsize=9.5,
            fontweight="bold",
            color="#0F172A",
            pad=8,
        )
        ax.set_xlabel("UTM 44N Easting (km)", fontsize=7.5)
        ax.set_ylabel("UTM 44N Northing (km)", fontsize=7.5)
        ax.tick_params(labelsize=7)
        ax.text(0.98, 0.95, "N ▲", transform=ax.transAxes, ha="right", va="top", fontsize=8.5, fontweight="bold", color="#0F172A", bbox=dict(facecolor="#FFFFFF", alpha=0.85, edgecolor="#94A3B8"))
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=180)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as exc:
        logger.warning("Failed to render spatial figure cleanly; using fallback note: %s", exc)
        return None


def _render_summary_charts_png(
    scenario_result: Dict[str, Any],
    exposure_report: Dict[str, Any],
    compare_report: Optional[Dict[str, Any]] = None,
) -> Optional[io.BytesIO]:
    """Generate hydrological mass-balance + infrastructure depth-tier summary chart."""
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.2, 3.0), dpi=170)
        fig.patch.set_facecolor("#FFFFFF")

        mb = scenario_result["summary"]["mass_balance"]
        labels = ["Rain", "Spillway", "Infil", "Drainage", "Outflow", "Stored"]
        vals = [
            mb.get("v_rain_m3", 0.0) / 1e6,
            mb.get("v_upstream_m3", 0.0) / 1e6,
            mb.get("v_infil_m3", 0.0) / 1e6,
            mb.get("v_drain_m3", 0.0) / 1e6,
            mb.get("v_outflow_m3", 0.0) / 1e6,
            mb.get("v_final_m3", 0.0) / 1e6,
        ]
        bar_cols = ["#4BA3D9", "#E9B65C", "#36C2C9", "#43C59E", "#64748B", "#0F172A"]
        ax1.bar(labels, vals, color=bar_cols, width=0.58)
        ax1.set_title("Water-Balance Partition (MCM)", fontsize=8.5, fontweight="bold")
        ax1.set_ylabel("Volume (MCM)", fontsize=7.5)
        ax1.tick_params(axis="x", labelsize=7, rotation=18)
        ax1.tick_params(axis="y", labelsize=7)
        ax1.grid(axis="y", linestyle="--", alpha=0.4)

        b_tiers = exposure_report["buildings"]["depth_tiers_count"]
        t_keys = list(b_tiers.keys())
        t_vals = [b_tiers[k] for k in t_keys]
        t_cols = ["#4BA3D9", "#36C2C9", "#E9B65C", "#F16D75"]
        if compare_report is not None:
            ax2.bar(
                ["Base Vol\n(MCM)", "Alt Vol\n(MCM)", "Base Area\n(km²)", "Alt Area\n(km²)"],
                [
                    compare_report["baseline_summary"]["stored_water_volume_mcm"],
                    compare_report["alternate_summary"]["stored_water_volume_mcm"],
                    compare_report["baseline_summary"]["urban_inundated_area_km2"],
                    compare_report["alternate_summary"]["urban_inundated_area_km2"],
                ],
                color=["#64748B", "#1D6FA5", "#64748B", "#E9B65C"],
                width=0.52,
            )
            ax2.set_title("Baseline vs Alternate Comparison", fontsize=8.5, fontweight="bold")
        else:
            ax2.bar(t_keys, t_vals, color=t_cols[: len(t_keys)], width=0.55)
            ax2.set_title("Potentially Exposed Buildings by Depth Tier", fontsize=8.5, fontweight="bold")
            ax2.set_ylabel("Footprints (count)", fontsize=7.5)
        ax2.tick_params(axis="x", labelsize=7, rotation=12)
        ax2.tick_params(axis="y", labelsize=7)
        ax2.grid(axis="y", linestyle="--", alpha=0.4)

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=170)
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception as exc:
        logger.warning("Failed to render summary chart: %s", exc)
        return None


_TH_STYLE = ParagraphStyle(
    "CTCellHeader",
    fontName="Helvetica-Bold",
    fontSize=7.8,
    leading=10,
    textColor=colors.white,
)
_TD_STYLE = ParagraphStyle(
    "CTCellBody",
    fontName="Helvetica",
    fontSize=7.6,
    leading=10.2,
    textColor=_TEXT_MAIN,
)


def _cell_para(val: Any, is_header: bool) -> Any:
    if isinstance(val, (Paragraph, Table, RLImage)):
        return val
    txt = str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(txt, _TH_STYLE if is_header else _TD_STYLE)


def _styled_table(rows: List[List[Any]], col_widths: Optional[List[float]] = None) -> Table:
    wrapped = [
        [_cell_para(cell, is_header=(r_idx == 0)) for cell in row]
        for r_idx, row in enumerate(rows)
    ]
    tbl = Table(wrapped, colWidths=col_widths, hAlign="LEFT", repeatRows=1)
    tbl.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), _BRAND_DARK),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _BRAND_ALT_BG]),
            ("GRID", (0, 0), (-1, -1), 0.35, _BORDER_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    return tbl


def generate_engineering_pdf_bytes(
    *,
    terrain_engine_obj,
    scenario_result: Dict[str, Any],
    exposure_report: Dict[str, Any],
    neighbourhood_report: Dict[str, Any],
    compare_report: Optional[Dict[str, Any]] = None,
    analysis_objective: str = "South Chennai overland flood scenario screening & infrastructure potential-exposure assessment.",
) -> Dict[str, Any]:
    """
    Generate an offline A4 PDF engineering report returning {'report_id', 'filename', 'pdf_bytes', 'generated_at_utc'}.
    Covers all 20 required metadata, map, exposure, neighbourhood, provenance, and limitation sections.
    """
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()
    sc = scenario_result["scenario"]
    repro = sc.get("reproducibility", {})
    report_hash = hashlib.sha256(f"{sc['id']}:{repro.get('cache_key','')}:{now_iso}".encode()).hexdigest()[:8].upper()
    report_id = f"CTR-{now_dt.strftime('%Y%m%d-%H%M%S')}-{report_hash}"
    filename = f"civictwin_report_{sc['id']}_{now_dt.strftime('%Y%m%d_%H%M%S')}.pdf"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"CivicTwin-R Engineering Report — {sc['name']}",
        author="CivicTwin-R Studio v1.0.0",
    )

    styles = getSampleStyleSheet()
    st_title = ParagraphStyle("CTTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, textColor=_BRAND_DARK, spaceAfter=4)
    st_sub = ParagraphStyle("CTSub", parent=styles["Normal"], fontName="Helvetica", fontSize=9, textColor=_TEXT_MUTED, spaceAfter=10)
    st_h2 = ParagraphStyle("CTH2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, textColor=_BRAND_BLUE, spaceBefore=10, spaceAfter=4)
    st_body = ParagraphStyle("CTBody", parent=styles["Normal"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=_TEXT_MAIN, spaceAfter=4)
    st_note = ParagraphStyle("CTNote", parent=styles["Normal"], fontName="Helvetica-Oblique", fontSize=7.8, leading=11, textColor=_TEXT_MUTED, spaceAfter=4)

    story: List[Any] = []

    # 1–4 Header & Identity
    story.append(Paragraph("CivicTwin-R — Urban Flood Engineering & Exposure Report", st_title))
    story.append(Paragraph(
        f"<b>Report ID:</b> {report_id} &nbsp;|&nbsp; <b>Generated (UTC):</b> {now_iso} &nbsp;|&nbsp; "
        f"<b>Application:</b> CivicTwin-R v{repro.get('app_version', '1.0.0')}",
        st_sub,
    ))
    story.append(Paragraph(f"<b>Scenario:</b> {sc['name']} (<code>{sc['id']}</code>, Mode: <code>{sc['mode']}</code>)", st_body))
    story.append(Paragraph(f"<b>Analysis Objective:</b> {analysis_objective}", st_body))

    # 5–7 Study Area, Grid & Scenario Parameters
    dom = scenario_result["domain"]
    story.append(Paragraph("1. Study Area, Computational Grid & Scenario Parameters", st_h2))
    param_rows = [
        ["Parameter / Domain Property", "Value", "Units / Provenance"],
        ["Study Area & Bounds", "South Chennai Pilot (80.044°E–80.286°E, 12.905°N–13.056°N)", f"{dom['valid_land_km2']} km² active land ({dom['crs']})"],
        ["Computational Resolution", f"{dom['grid_shape'][0]} x {dom['grid_shape'][1]} structured raster", f"{dom['dx_m']} m ({dom['cell_area_m2']:.0f} m²/cell)"],
        ["Numerical Solver", scenario_result["summary"]["solver"], repro.get("solver_version", "Landlab 2.x")],
        ["Rainfall Intensity", f"{sc['rainfall_intensity_mm_hr']}", "mm/hr (Hyetograph if historical)"],
        ["Storm Duration", f"{sc['duration_hours']}", "hours"],
        ["Urban Drainage Capacity", f"{sc['drainage_efficiency_pct']}% of {sc['nominal_drain_cap_mm_hr']} nominal", "mm/hr lumped stormwater sink"],
        ["Permeable Soil Infiltration", f"{sc['infiltration_rate_mm_hr']}", "mm/hr on pervious fraction"],
        ["Chembarambakkam Release", f"{sc['chembarambakkam_discharge_cusecs']}", "cusecs (Adyar spillway node)"],
        ["Manning Roughness / Initial Depth", f"n={sc['mannings_n']}, h0={sc.get('initial_depth_m', 0.0)} m", "Shallow-water friction & init state"],
    ]
    story.append(_styled_table(param_rows, col_widths=[58 * mm, 64 * mm, 56 * mm]))

    # 8–9 Actual Spatial Map Figure
    story.append(Paragraph("2. Geographical Study Domain & Modelled Inundation Map", st_h2))
    map_buf = _render_spatial_map_png(terrain_engine_obj, scenario_result)
    if map_buf is not None:
        story.append(RLImage(map_buf, width=176 * mm, height=105 * mm))
        story.append(Paragraph(
            "Figure 1: Copernicus GLO-30 terrain (150 m UTM 44N grid) overlaid with Landlab OverlandFlow modeled surface depth (>= 0.03 m). Permanent lakes/coastline masked separately.",
            st_note,
        ))
    else:
        story.append(Paragraph(
            "Spatial raster figure generation unavailable cleanly in current headless environment; numerical tables below report exact solver outputs.",
            st_note,
        ))

    # 10–11 Hydrological Results & Water Balance
    story.append(Paragraph("3. Hydrological Simulation Results & Water-Balance Conservation", st_h2))
    s = scenario_result["summary"]
    mb = s["mass_balance"]
    wb_rows = [
        ["Hydrological Metric", "Value", "Hydrological Budget Term", "Volume (m³ / MCM)"],
        ["Stored Water Volume", f"{s['stored_water_volume_mcm']} MCM", "Rainfall Input Volume", f"{mb['v_rain_m3']:,.1f} m³ ({mb['v_rain_m3']/1e6:.3f} MCM)"],
        ["Modelled Urban Flooded Area", f"{s['urban_inundated_area_km2']} km² (>=0.05m)", "Spillway Boundary Inflow", f"{mb['v_upstream_m3']:,.1f} m³ ({mb['v_upstream_m3']/1e6:.3f} MCM)"],
        ["Wetland Retention Area", f"{s['wetland_accumulation_area_km2']} km²", "Permeable Infiltration", f"{mb['v_infil_m3']:,.1f} m³ ({mb['v_infil_m3']/1e6:.3f} MCM)"],
        ["Peak Urban Depth", f"{s['max_urban_depth_m']} m", "Storm Drainage Removal", f"{mb['v_drain_m3']:,.1f} m³ ({mb['v_drain_m3']/1e6:.3f} MCM)"],
        ["Mean Flooded Urban Depth", f"{s['mean_flooded_urban_depth_m']} m", "Coastal / Boundary Outflow", f"{mb['v_outflow_m3']:,.1f} m³ ({mb['v_outflow_m3']/1e6:.3f} MCM)"],
        ["Computation Latency", f"{s['computation_time_ms']} ms", "Mass-Balance Residual", f"{mb['residual_m3']:,.3f} m³ ({mb['relative_error']*100:.4f}%)"],
    ]
    story.append(_styled_table(wb_rows, col_widths=[45 * mm, 44 * mm, 44 * mm, 45 * mm]))

    chart_buf = _render_summary_charts_png(scenario_result, exposure_report, compare_report)
    if chart_buf is not None:
        story.append(Spacer(1, 3 * mm))
        story.append(RLImage(chart_buf, width=176 * mm, height=64 * mm))

    story.append(PageBreak())

    # 12. Infrastructure Exposure Estimates
    story.append(Paragraph("4. Projected Infrastructure Exposure Analysis (EPSG:32644)", st_h2))
    cov = exposure_report["coverage"]
    bld = exposure_report["buildings"]
    rds = exposure_report["roads"]
    crit = bld["critical_civic_facilities"]
    story.append(Paragraph(
        f"Exposure depth threshold: <b>&ge; {exposure_report['depth_threshold_m']} m</b>. Domain asset coverage: "
        f"{cov['buildings_in_domain']:,} / {cov['buildings_total']:,} indexed buildings inside domain; "
        f"{cov['roads_in_domain']:,} / {cov['roads_total_deduplicated']:,} deduplicated roads inside domain.",
        st_body,
    ))
    exp_rows = [
        ["Infrastructure Asset Category", "Exposed Quantity", "Spatial Extent / Depth Metrics"],
        ["Modelled Potentially Exposed Buildings", f"{bld['exposed_count']:,} ({bld['exposed_pct_of_in_domain']}% of in-domain)", f"Footprint: {bld['exposed_footprint_area_m2']:,.1f} m² ({bld['exposed_footprint_area_ha']} ha), Max: {bld['max_depth_at_building_m']} m"],
        ["Civic / Critical-Tag Facilities (OSM)", f"{crit['total_exposed']} facilities", ", ".join(f"{k}: {v}" for k, v in crit["by_type"].items()) or "None above threshold"],
        ["Modelled Potentially Exposed Roads", f"{rds['exposed_segments_count']:,} segments", f"Total Length: {rds['exposed_length_km']} km, Max depth: {rds['max_depth_at_road_m']} m"],
        ["Road Bridges (Intersect Wet Cells)", f"{exposure_report['bridges']['intersecting_wet_cells_count']}", "Crossings intersecting >= threshold depth cells"],
    ]
    story.append(_styled_table(exp_rows, col_widths=[56 * mm, 46 * mm, 76 * mm]))

    # Top highway classes
    if rds["by_highway_class"]:
        story.append(Spacer(1, 3 * mm))
        rw_rows = [["Road Classification (OSM)", "Exposed Segments", "Exposed Length (km)", "Max Cell Depth (m)"]]
        for rc in rds["by_highway_class"][:8]:
            rw_rows.append([rc["highway_class"], str(rc["segments"]), f"{rc['exposed_length_km']:.3f}", f"{rc['max_depth_m']:.3f}"])
        story.append(_styled_table(rw_rows, col_widths=[56 * mm, 38 * mm, 42 * mm, 42 * mm]))

    # 13. Neighbourhood / Watershed Summaries
    story.append(Paragraph(f"5. Neighbourhood & Official Boundary Summaries ({neighbourhood_report['source_dataset']})", st_h2))
    nb_rows = [["Region Name", "Domain Cov %", "Inundated (km² / %)", "Max Depth (m)", "Exp. Bldgs", "Exp. Roads (km)"]]
    in_dom_regions = [r for r in neighbourhood_report["regions"] if r["in_computational_domain"]][:12]
    for rg in in_dom_regions:
        nb_rows.append([
            f"{rg['name']} ({rg['sublabel']})" if rg["sublabel"] else rg["name"],
            f"{rg['domain_coverage_pct']}%",
            f"{rg['inundated_area_km2']} ({rg['inundated_pct_of_in_domain']}%)",
            f"{rg['max_depth_m']}",
            f"{rg['exposed_buildings_count']}",
            f"{rg['exposed_roads_km']}",
        ])
    story.append(_styled_table(nb_rows, col_widths=[48 * mm, 24 * mm, 34 * mm, 24 * mm, 22 * mm, 26 * mm]))

    # 14. Scenario Comparison (if provided)
    if compare_report is not None:
        story.append(Paragraph("6. Counterfactual Scenario Comparison Summary", st_h2))
        cmp_rows = [
            ["Metric", compare_report["baseline_scenario"][:28], compare_report["alternate_scenario"][:28], "Delta (% Change)"],
            [
                "Stored Volume (MCM)",
                str(compare_report["baseline_summary"]["stored_water_volume_mcm"]),
                str(compare_report["alternate_summary"]["stored_water_volume_mcm"]),
                f"{compare_report['delta_stored_volume_mcm']:+.4f} ({compare_report['pct_delta_stored_volume']}%)" if compare_report["pct_delta_stored_volume"] is not None else f"{compare_report['delta_stored_volume_mcm']:+.4f} (N/A)",
            ],
            [
                "Flooded Urban Area (km²)",
                str(compare_report["baseline_summary"]["urban_inundated_area_km2"]),
                str(compare_report["alternate_summary"]["urban_inundated_area_km2"]),
                f"{compare_report['delta_inundated_area_km2']:+.2f} ({compare_report['pct_delta_inundated_area']}%)" if compare_report["pct_delta_inundated_area"] is not None else f"{compare_report['delta_inundated_area_km2']:+.2f} (N/A)",
            ],
            [
                "Peak Urban Depth (m)",
                str(compare_report["baseline_summary"]["max_urban_depth_m"]),
                str(compare_report["alternate_summary"]["max_urban_depth_m"]),
                f"{compare_report['delta_max_urban_depth_m']:+.3f} m",
            ],
        ]
        if "infrastructure_exposure_comparison" in compare_report:
            ic = compare_report["infrastructure_exposure_comparison"]
            cmp_rows.append([
                f"Exposed Buildings (>={ic['depth_threshold_m']}m)",
                str(ic["baseline"]["exposed_buildings_count"]),
                str(ic["alternate"]["exposed_buildings_count"]),
                f"{ic['deltas']['exposed_buildings_count']:+d}",
            ])
            cmp_rows.append([
                "Exposed Roads (km)",
                str(ic["baseline"]["exposed_roads_km"]),
                str(ic["alternate"]["exposed_roads_km"]),
                f"{ic['deltas']['exposed_roads_km']:+.3f} km",
            ])
        story.append(_styled_table(cmp_rows, col_widths=[45 * mm, 44 * mm, 44 * mm, 45 * mm]))

    # 16–20 Provenance, Assumptions, Limitations, Reproducibility
    story.append(Paragraph("7. Data Provenance, Assumptions, Limitations & Reproducibility", st_h2))
    story.append(Paragraph(
        "<b>Data Provenance:</b> Terrain grid from Copernicus GLO-30 DEM (EPSG:4326 -> UTM 44N EPSG:32644, 150 m). "
        "Vectors from geofabrik OpenStreetMap PBF (18,198 footprints, 48,769 deduplicated roads, 1,229 bridges), "
        "official Tamil Nadu CFM-DSS WFS (200 GCC wards, 36 South Chennai watersheds, 465 waterways, 771 waterbodies, 56 stations), "
        "WRD reservoirs, and ERA5/IMD Cyclone Michaung 2023 hourly rainfall records.",
        st_body,
    ))
    story.append(Paragraph(
        "<b>Exposure & Boundary Assumptions:</b> Projected EPSG:32644 cell intersections evaluate geometric overlap without duplicate counting. "
        f"{exposure_report['scientific_disclaimer']}",
        st_body,
    ))
    for idx, lim in enumerate(scenario_result["summary"]["limitations"], start=1):
        story.append(Paragraph(f"• Limitation {idx}: {lim}", st_note))

    checksums = _dataset_checksums()
    chk_text = ", ".join(f"{k}: {v}" for k, v in checksums.items())
    story.append(Paragraph(
        f"<b>Reproducibility Verification:</b> Scenario Cache Key <code>{repro.get('cache_key', 'N/A')}</code> | "
        f"Solver: <code>{repro.get('solver_version', 'Landlab')}</code> | Protected Dataset SHA-256 Prefixes: <code>{chk_text}</code>.",
        st_note,
    ))

    doc.build(story)
    return {
        "report_id": report_id,
        "filename": filename,
        "generated_at_utc": now_iso,
        "pdf_bytes": buf.getvalue(),
    }


def generate_scenario_csv_text(
    scenario_result: Dict[str, Any],
    exposure_report: Dict[str, Any],
    neighbourhood_report: Dict[str, Any],
) -> str:
    """Export combined numerical scenario summary, exposure breakdown, and neighbourhood table as CSV."""
    out = io.StringIO()
    w = csv.writer(out)
    sc = scenario_result["scenario"]
    s = scenario_result["summary"]
    mb = s["mass_balance"]

    w.writerow(["section", "metric_or_region", "value", "unit_or_detail"])
    w.writerow(["scenario", "id", sc["id"], sc["mode"]])
    w.writerow(["scenario", "name", sc["name"], ""])
    w.writerow(["scenario", "rainfall_intensity", sc["rainfall_intensity_mm_hr"], "mm/hr"])
    w.writerow(["scenario", "duration", sc["duration_hours"], "hours"])
    w.writerow(["scenario", "drainage_efficiency", sc["drainage_efficiency_pct"], "%"])
    w.writerow(["scenario", "stored_water_volume", s["stored_water_volume_mcm"], "MCM"])
    w.writerow(["scenario", "urban_inundated_area", s["urban_inundated_area_km2"], "km2"])
    w.writerow(["scenario", "max_urban_depth", s["max_urban_depth_m"], "m"])
    w.writerow(["scenario", "mass_balance_residual", mb["residual_m3"], "m3"])

    bld = exposure_report["buildings"]
    rds = exposure_report["roads"]
    w.writerow(["exposure", "depth_threshold_m", exposure_report["depth_threshold_m"], "m"])
    w.writerow(["exposure", "exposed_buildings_count", bld["exposed_count"], "footprints (modelled potential)"])
    w.writerow(["exposure", "exposed_buildings_area_m2", bld["exposed_footprint_area_m2"], "m2"])
    w.writerow(["exposure", "exposed_roads_km", rds["exposed_length_km"], "km"])
    w.writerow(["exposure", "exposed_critical_facilities", bld["critical_civic_facilities"]["total_exposed"], "OSM critical_tag count"])

    for rg in neighbourhood_report["regions"]:
        if not rg["in_computational_domain"]:
            continue
        w.writerow([
            f"neighbourhood_{neighbourhood_report['boundary_type']}",
            f"{rg['name']} ({rg['sublabel']})",
            rg["inundated_area_km2"],
            f"km2 inundated ({rg['inundated_pct_of_in_domain']}% of {rg['in_domain_area_km2']} km2 in-domain); bldgs={rg['exposed_buildings_count']}; roads_km={rg['exposed_roads_km']}",
        ])

    return out.getvalue()
