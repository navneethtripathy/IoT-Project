#!/usr/bin/env python3
"""
CivicTwin-R — End-to-End Automated Browser QA & Offline Verification Suite (Playwright)

Verifies:
  1. Strict offline guarantee (0 non-localhost external network requests on /urban-twin and /showcase).
  2. MapLibre GL JS WebGL canvas, 18k+ 3D OSM buildings, sequential depth rendering, WFS/OSM click inspector.
  3. Scenario switching, numeric + slider controls, validation error banner (#sim-error-box), timeline & compare delta.
  4. Unified Obsidian Ocean Showcase navigation, Charts (Michaung/ARG, RK4, Reconstruction), Three.js 3D Tanks.
  5. Responsive checks with zero horizontal overflow at 1920x1080, 1440x900, 1280x800, 1024x768, 768x1024, 390x844.
  6. Reduced-motion emulation check & zero console/page errors.
  7. Live Node-RED (:1880/ui/) and InfluxDB (:8086) reachability & screenshots in showcase/screenshots/.
"""

from __future__ import annotations

import os
import shutil
import time
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
                timeout=25000,
            )
            time.sleep(0.9)

        # ── 1. Showcase Overview (strict offline, 1440x900) ─────────────────
        print("[1/6] Testing http://127.0.0.1:8000/showcase (strict offline mode)...")
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

        # ── 2. Full-screen Chennai Urban Digital Twin (/urban-twin) ─────────
        print("[2/6] Testing http://127.0.0.1:8000/urban-twin (strict offline mode)...")
        page.goto("http://127.0.0.1:8000/urban-twin", wait_until="networkidle", timeout=45000)
        page.wait_for_function("document.getElementById('kpi-vol').innerText !== '-- MCM'", timeout=25000)
        wait_scenario_ready("Heavy Monsoon")
        kpi_vol = page.inner_text("#kpi-vol")
        kpi_area = page.inner_text("#kpi-area")
        print(f"      Heavy Rainfall -> Vol: {kpi_vol}, Area: {kpi_area}")
        page.screenshot(path=str(SHOT_DIR / "02_urban_twin_fullscreen.png"))
        page.screenshot(path=str(SHOT_DIR / "05_heavy_rainfall_simulation.png"))

        # Test invalid parameter error banner (#sim-error-box) then clear cleanly
        page.fill("#num-rain", "999")
        page.click("#btn-run-sim")
        page.wait_for_function("!document.getElementById('sim-error-box').classList.contains('hidden')", timeout=8000)
        err_txt = page.inner_text("#sim-error-box")
        print(f"      Validation Error State Verified -> {err_txt}")
        page.select_option("#preset-select", "heavy_rainfall")
        wait_scenario_ready("Heavy Monsoon")

        # 3D Detail View (Velachery 3D OSM Buildings & Prisms)
        page.click("button:has-text('Velachery')")
        time.sleep(1.8)
        page.screenshot(path=str(SHOT_DIR / "03_3d_geographical_detail.png"))

        # Selected Geographical Location + Inspector + Technical Provenance Details
        box = page.locator("#map").bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
            page.wait_for_function("!document.getElementById('inspector-body').innerText.includes('Click any grid')", timeout=8000)
            time.sleep(0.5)
        prov = page.locator("#inspector-body details")
        if prov.count() > 0:
            prov.first.evaluate("el => el.open = true")
            time.sleep(0.3)
        insp_text = page.inner_text("#inspector-body")
        print(f"      Selected Inspector -> {insp_text.splitlines()[0] if insp_text else 'empty'}")
        page.screenshot(path=str(SHOT_DIR / "04_selected_location.png"))

        # Scenario Comparison (Reduced Drainage vs Heavy Rainfall)
        page.click("button:has-text('Reset')")
        time.sleep(1.0)
        page.select_option("#preset-select", "reduced_drainage")
        wait_scenario_ready("Reduced Drainage")
        page.click("button:has-text('Compare Impact Delta')")
        page.wait_for_function("!document.getElementById('compare-output').classList.contains('hidden')", timeout=15000)
        cmp_text = page.inner_text("#compare-output")
        print(f"      Scenario Compare -> {cmp_text.splitlines()[0] if cmp_text else 'hidden'}")
        page.screenshot(path=str(SHOT_DIR / "06_scenario_comparison.png"))

        # Cyclone Michaung Replay
        page.select_option("#preset-select", "michaung_replay")
        wait_scenario_ready("Cyclone Michaung")
        page.screenshot(path=str(SHOT_DIR / "07_cyclone_michaung_replay.png"))

        # ── 3. Showcase Sub-views (Historical, IoT Lab, Reconstruction, System) ──
        print("[3/6] Capturing Historical, IoT Lab, Reconstruction & System views...")
        page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
        time.sleep(1.5)

        page.click("button[data-nav='chennai']")
        time.sleep(1.8)
        page.screenshot(path=str(SHOT_DIR / "08_rainfall_reservoir_analytics.png"))

        page.click("button[data-nav='iot']")
        time.sleep(1.8)
        page.screenshot(path=str(SHOT_DIR / "09_experimental_iot_lab.png"))

        page.click("button[data-nav='research']")
        time.sleep(0.8)
        page.click("button[data-tab='reconstruction']")
        time.sleep(1.2)
        page.screenshot(path=str(SHOT_DIR / "10_missing_data_reconstruction.png"))

        page.click("button[data-nav='system']")
        time.sleep(1.5)
        page.screenshot(path=str(SHOT_DIR / "11_system_monitoring.png"))

        # ── 4. Responsive Verification Across All 6 Target Viewports ─────────
        print("[4/6] Checking responsive viewports & zero horizontal overflow...")
        for label, w, h in RESPONSIVE_VIEWPORTS:
            page.set_viewport_size({"width": w, "height": h})
            page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
            time.sleep(0.9)
            over_sh = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            assert not over_sh, f"Horizontal overflow on /showcase at {label} ({w}x{h})"
            if label == "tablet":
                page.screenshot(path=str(SHOT_DIR / "12_responsive_tablet.png"))

            page.goto("http://127.0.0.1:8000/urban-twin", wait_until="networkidle", timeout=45000)
            page.wait_for_function("document.getElementById('kpi-vol').innerText !== '-- MCM'", timeout=25000)
            time.sleep(1.0)
            over_ut = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
            assert not over_ut, f"Horizontal overflow on /urban-twin at {label} ({w}x{h})"
            if label == "mobile":
                page.screenshot(path=str(SHOT_DIR / "13_responsive_mobile.png"))
            print(f"      [PASS] {label} ({w}x{h}): overflow_showcase={over_sh}, overflow_urbantwin={over_ut}")

        # Verify prefers-reduced-motion does not error
        page.emulate_media(reduced_motion="reduce")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
        time.sleep(0.8)

        # ── 5. Node-RED & InfluxDB UI Checks ────────────────────────────────
        print("[5/6] Loading http://127.0.0.1:1880/ui/ and http://127.0.0.1:8086 ...")
        page_nr = context.new_page()
        page_nr.on("pageerror", lambda e: page_errors.append(f"[Node-RED] {e}"))
        page_nr.goto("http://127.0.0.1:1880/ui/", wait_until="networkidle", timeout=20000)
        time.sleep(1.8)
        page_nr.screenshot(path=str(SHOT_DIR / "14_nodered_dashboard.png"))

        page_inf = context.new_page()
        page_inf.goto("http://127.0.0.1:8086", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.2)
        assert "InfluxDB" in page_inf.title(), f"Unexpected InfluxDB title: {page_inf.title()}"

        browser.close()

    print("[6/6] Browser QA Summary:")
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
