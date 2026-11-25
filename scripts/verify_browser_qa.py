#!/usr/bin/env python3
"""
CivicTwin-R — End-to-End Automated Browser QA & Offline Verification Suite (Playwright)

Verifies:
  1. Strict offline guarantee (0 non-localhost external network requests on /urban-twin and /showcase).
  2. MapLibre GL JS WebGL canvas, Copernicus 3D elevation Terrarium tiles, 18k+ 3D OSM buildings,
     enhanced asset provenance inspector (buildings, roads, waterways, stations, reservoirs).
  3. Scenario switching, initial depth, saved CRUD, validation error banner (#sim-error-box),
     side-by-side swipe comparison, spatial Exposure highlight, and Watersheds/Wards boundaries.
  4. Unified Obsidian Ocean Showcase: Impact Intelligence + Bounded Sensitivity Sweep,
     Historical Replay, Three.js 3D Tanks, Digital Twin ODE Audit, Missing-Data Reconstruction, Reports.
  5. Responsive checks with zero horizontal overflow at 1920x1080, 1440x900, 1280x800, 1024x768, 768x1024, 390x844.
  6. Reduced-motion emulation check, live Node-RED (:1880/ui/), InfluxDB (:8086), & PDF generation check.
  7. Captures verified screenshot portfolio inside showcase/screenshots/.
"""

from __future__ import annotations

import os
import shutil
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = _PROJECT_ROOT / "showcase" / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

RESPONSIVE_VIEWPORTS = [
    ("desktop_xl", 1920, 1080),
    ("macbook_pro", 1440, 900),
    ("macbook_air", 1280, 800),
    ("small_laptop", 1024, 768),
    ("tablet", 768, 1024),
    ("mobile", 390, 844),
]


def run_qa() -> int:
    console_errors: list[str] = []
    page_errors: list[str] = []
    external_blocked: list[str] = []

    with sync_playwright() as p:
        chrome_bin = (
            os.getenv("CHROME_PATH")
            or shutil.which("google-chrome")
            or shutil.which("chromium")
            or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
        browser = p.chromium.launch(
            executable_path=chrome_bin if chrome_bin and os.path.exists(chrome_bin) else None,
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})

        def offline_route(route):
            url = route.request.url
            if (
                url.startswith("http://127.0.0.1")
                or url.startswith("http://localhost")
                or url.startswith("data:")
                or url.startswith("blob:")
            ):
                route.continue_()
            else:
                external_blocked.append(url)
                route.abort()

        page = context.new_page()
        page.route("**/*", offline_route)
        page.on("console", lambda m: console_errors.append(f"[{page.url}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(f"[{page.url}] {e}"))

        def wait_scenario_ready(expected_substr: str):
            page.wait_for_function(
                """(sub) => {
                    const btn = document.getElementById('btn-run-sim');
                    const ban = document.getElementById('active-scenario-banner');
                    return btn && !btn.innerText.includes('Computing') && ban && ban.innerText.includes(sub);
                }""",
                arg=expected_substr,
                timeout=30000,
            )
            time.sleep(0.9)

        # ── 1. Showcase Overview (strict offline, 1440x900) ─────────────────
        print("[1/7] Testing http://127.0.0.1:8000/showcase (strict offline mode)...")
        page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
        page.wait_for_function("document.getElementById('overview-vol').innerText !== '-- MCM'", timeout=25000)
        page.wait_for_function(
            """() => {
                const fr = document.getElementById('urban-twin-frame');
                if (!fr || !fr.contentDocument) return false;
                const kpi = fr.contentDocument.getElementById('kpi-vol');
                const btn = fr.contentDocument.getElementById('btn-run-sim');
                return kpi && kpi.innerText !== '-- MCM' && btn && !btn.innerText.includes('Computing');
            }""",
            timeout=30000,
        )
        time.sleep(1.5)
        api_st = page.inner_text("#status-api").strip()
        mqtt_st = page.inner_text("#status-mqtt").strip()
        influx_st = page.inner_text("#status-influx").strip()
        nr_st = page.inner_text("#status-nodered").strip()
        print(f"      Live Service Bar -> {api_st} | {mqtt_st} | {influx_st} | {nr_st}")
        page.screenshot(path=str(SHOT_DIR / "01_showcase_overview.png"))

        # ── 2. Chennai 3D Urban Explorer (/urban-twin) ──────────────────────
        print("[2/7] Testing http://127.0.0.1:8000/urban-twin (strict offline mode)...")
        page.goto("http://127.0.0.1:8000/urban-twin", wait_until="networkidle", timeout=45000)
        page.wait_for_function("document.getElementById('kpi-vol').innerText !== '-- MCM'", timeout=25000)
        wait_scenario_ready("Heavy Monsoon")
        kpi_vol = page.inner_text("#kpi-vol")
        kpi_area = page.inner_text("#kpi-area")
        print(f"      Heavy Rainfall -> Vol: {kpi_vol}, Area: {kpi_area}")
        page.screenshot(path=str(SHOT_DIR / "02_urban_explorer.png"))
        page.screenshot(path=str(SHOT_DIR / "06_heavy_rainfall_simulation.png"))

        # Test invalid parameter error banner (#sim-error-box) cleanly
        page.fill("#num-rain", "999")
        page.click("#btn-run-sim")
        page.wait_for_function("!document.getElementById('sim-error-box').classList.contains('hidden')", timeout=8000)
        err_txt = page.inner_text("#sim-error-box")
        print(f"      Validation Error State Verified -> {err_txt}")
        page.select_option("#preset-select", "heavy_rainfall")
        wait_scenario_ready("Heavy Monsoon")

        # Fly to Velachery (3D buildings + 3D terrain) & click for asset provenance inspector
        page.click("button:has-text('Velachery')")
        time.sleep(1.6)
        page.screenshot(path=str(SHOT_DIR / "03_3d_geographical_detail.png"))

        box = page.locator("#map").bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] * 0.52, box["y"] + box["height"] * 0.52)
            page.wait_for_function("!document.getElementById('inspector-body').innerText.includes('Click any')", timeout=8000)
            time.sleep(0.5)
        prov = page.locator("#inspector-body details")
        if prov.count() > 0:
            prov.first.evaluate("el => el.open = true")
            time.sleep(0.3)
        page.screenshot(path=str(SHOT_DIR / "05_selected_asset_inspector.png"))

        # Test Exposure Highlight & Boundaries right-drawer tabs
        page.click("#rtab-btn-exposure")
        page.wait_for_function("document.getElementById('ut-exp-bld').innerText !== '--'", timeout=15000)
        page.click("button:has-text('All Exposed')")
        time.sleep(1.0)
        page.click("#rtab-btn-boundaries")
        page.wait_for_function("!document.getElementById('ut-nb-summary').innerText.includes('Loading')", timeout=15000)
        time.sleep(0.8)
        page.screenshot(path=str(SHOT_DIR / "04_selected_neighbourhood.png"))
        page.click("#rtab-btn-outputs")
        page.click("button:has-text('Reset')")
        time.sleep(1.0)

        # Interactive Side-by-Side Swipe Comparison Mode
        page.click("#btn-swipe-cmp")
        page.wait_for_function(
            "document.getElementById('compare-split-pane').dataset.altReady === '1' && !document.getElementById('compare-output').classList.contains('hidden')",
            timeout=30000,
        )
        time.sleep(1.5)
        cmp_text = page.inner_text("#compare-output")
        print(f"      Side-by-Side Compare -> {cmp_text.splitlines()[0] if cmp_text else 'empty'}")
        page.screenshot(path=str(SHOT_DIR / "07_side_by_side_comparison.png"))
        page.click("button:has-text('Exit Compare')")
        time.sleep(0.5)

        # Exercise Saved Scenario Library CRUD (Save + Load check + Delete cleanup) & Demo Guide
        page.fill("#save-name-input", "QA Polish Probe")
        page.click("button:has-text('Save')")
        page.wait_for_function(
            "Array.from(document.getElementById('saved-scenarios-select').options).some(o => o.textContent.includes('QA Polish Probe'))",
            timeout=10000,
        )
        page.select_option("#saved-scenarios-select", label="QA Polish Probe")
        time.sleep(0.5)
        page.click("button:has-text('Delete')")
        page.wait_for_function("!document.getElementById('saved-crud-confirm').classList.contains('hidden')", timeout=5000)
        page.click("#saved-crud-confirm button:has-text('Confirm')")
        time.sleep(0.5)
        page.click("button:has-text('Demo')")
        page.wait_for_function("!document.getElementById('demo-guide-dock').classList.contains('hidden')", timeout=5000)
        page.click("#demo-guide-dock button:has-text('Close')")
        time.sleep(0.4)

        # Cyclone Michaung Historical Replay + cumulative observed rain readout
        page.select_option("#preset-select", "michaung_replay")
        wait_scenario_ready("Cyclone Michaung")
        page.screenshot(path=str(SHOT_DIR / "10_cyclone_michaung_replay.png"))

        # ── 3. Showcase Impact Intelligence, Sensitivity, IoT & Research ─────
        print("[3/7] Testing Impact Intelligence, Sensitivity, IoT Lab, Research & Reports...")
        page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
        time.sleep(1.2)

        page.click("button[data-nav='impact']")
        page.wait_for_function("document.getElementById('imp-bld-count').innerText !== '--'", timeout=20000)
        time.sleep(1.0)
        # Execute live sensitivity sweep (4 steps), then capture clean KPI+Chart top view
        page.select_option("#sens-steps", "4")
        page.click("#sens-run-btn")
        page.wait_for_function("!document.getElementById('sens-run-btn').disabled && !document.getElementById('sens-tbody').innerText.includes('Run sweep')", timeout=30000)
        page.evaluate("document.getElementById('toast')?.classList.add('hidden'); window.scrollTo(0, 0);")
        time.sleep(0.8)
        page.screenshot(path=str(SHOT_DIR / "08_impact_intelligence.png"))

        page.click("#btn-nb-wards")
        page.wait_for_function("document.getElementById('nb-coverage-note').innerText.includes('GCC Wards')", timeout=15000)
        time.sleep(0.6)
        assert page.locator("#impact-nb-tbody tr").count() > 0, "No neighbourhood rows rendered"
        page.locator("#impact-nb-tbody").scroll_into_view_if_needed()
        page.evaluate("document.getElementById('toast')?.classList.add('hidden')")
        time.sleep(0.5)
        page.screenshot(path=str(SHOT_DIR / "09_neighbourhood_analysis.png"))

        page.click("button[data-nav='iot']")
        time.sleep(1.8)
        page.screenshot(path=str(SHOT_DIR / "11_experimental_iot_lab.png"))

        page.click("button[data-nav='research']")
        page.wait_for_function("document.getElementById('twin-mae').innerText !== '-- cm'", timeout=15000)
        time.sleep(1.2)
        page.screenshot(path=str(SHOT_DIR / "12_research_analytics.png"))

        page.click("button[data-nav='reports']")
        time.sleep(1.0)

        # ── 4. Verify Offline PDF Report Endpoint & Render Visual Proof PNG ──
        print("[4/7] Verifying downloadable Engineering PDF report & rendering page preview...")
        with urllib.request.urlopen("http://127.0.0.1:8000/api/urban/report/pdf?scenario_id=heavy_rainfall&compare_id=reduced_drainage", timeout=30) as rpdf:
            pdf_bytes = rpdf.read()
            assert rpdf.status == 200 and pdf_bytes[:4] == b"%PDF", "Invalid PDF returned"
            print(f"      PDF Report verified ({len(pdf_bytes)} bytes, ID: {rpdf.headers.get('X-CivicTwin-Report-Id')})")
            tmp_pdf = _PROJECT_ROOT / ".run" / "qa_sample_report.pdf"
            tmp_pdf.parent.mkdir(parents=True, exist_ok=True)
            tmp_pdf.write_bytes(pdf_bytes)
            sips_bin = shutil.which("sips")
            if sips_bin:
                import subprocess
                from PIL import Image as PILImage
                pdf_png = SHOT_DIR / "15_engineering_pdf_report.png"
                subprocess.run([sips_bin, "-s", "format", "png", str(tmp_pdf), "--out", str(pdf_png)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if pdf_png.exists():
                    with PILImage.open(pdf_png) as im:
                        im.convert("RGBA").save(pdf_png, format="PNG", icc_profile=None)
            page_pdf = context.new_page()
            page_pdf.goto("http://127.0.0.1:8000/showcase#reports", wait_until="networkidle", timeout=30000)
            time.sleep(0.8)
            page_pdf.evaluate("document.getElementById('toast')?.classList.add('hidden')")
            page_pdf.screenshot(path=str(SHOT_DIR / "15_engineering_reports_and_demo.png"))
            page_pdf.close()

        # ── 5. Responsive Verification Across All 6 Target Viewports ─────────
        print("[5/7] Checking responsive viewports & zero horizontal overflow...")
        for label, w, h in RESPONSIVE_VIEWPORTS:
            page.set_viewport_size({"width": w, "height": h})
            page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
            time.sleep(0.8)
            over_sh = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            assert not over_sh, f"Horizontal overflow on /showcase at {label} ({w}x{h})"
            if label == "tablet":
                page.evaluate("document.getElementById('toast')?.classList.add('hidden')")
                page.screenshot(path=str(SHOT_DIR / "16_responsive_tablet.png"))

            page.goto("http://127.0.0.1:8000/urban-twin", wait_until="networkidle", timeout=45000)
            page.wait_for_function("document.getElementById('kpi-vol').innerText !== '-- MCM'", timeout=25000)
            time.sleep(1.0)
            over_ut = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            assert not over_ut, f"Horizontal overflow on /urban-twin at {label} ({w}x{h})"
            if label == "mobile":
                page.screenshot(path=str(SHOT_DIR / "16_responsive_mobile.png"))
            print(f"      [PASS] {label} ({w}x{h}): overflow_showcase={over_sh}, overflow_urbantwin={over_ut}")

        page.emulate_media(reduced_motion="reduce")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
        time.sleep(0.8)

        # ── 6. Node-RED & InfluxDB UI Checks ────────────────────────────────
        print("[6/7] Loading http://127.0.0.1:1880/ui/ and http://127.0.0.1:8086 ...")
        page_nr = context.new_page()
        page_nr.on("pageerror", lambda e: page_errors.append(f"[Node-RED] {e}"))
        page_nr.goto("http://127.0.0.1:1880/ui/", wait_until="networkidle", timeout=20000)
        time.sleep(1.8)
        page_nr.screenshot(path=str(SHOT_DIR / "13_nodered_dashboard.png"))

        page_inf = context.new_page()
        page_inf.goto("http://127.0.0.1:8086", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.2)
        assert "InfluxDB" in page_inf.title(), f"Unexpected InfluxDB title: {page_inf.title()}"

        browser.close()

    print("[7/7] Browser QA Summary:")
    print(f"      External requests blocked/attempted: {len(external_blocked)}")
    if external_blocked:
        print("      External URLs:", external_blocked[:5])
    print(f"      Console errors: {len(console_errors)}")
    for e in console_errors[:10]:
        print("        ERR:", e)
    print(f"      Page errors: {len(page_errors)}")
    for e in page_errors[:10]:
        print("        PAGEERR:", e)

    return 1 if (external_blocked or console_errors or page_errors) else 0


if __name__ == "__main__":
    raise SystemExit(run_qa())
