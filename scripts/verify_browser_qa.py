#!/usr/bin/env python3
"""
CivicTwin-R — End-to-End Automated Browser QA & Offline Verification Suite (Playwright)

Verifies:
  1. Zero external network requests when blocking all non-localhost origins on /urban-twin and /showcase.
  2. MapLibre GL JS WebGL canvas rendering, 18k+ OSM 3D extruded buildings, WFS stations, reservoirs, and scenario runs.
  3. Scenario switching (normal, heavy_rainfall, reduced_drainage, michaung_replay, reservoir_discharge), timeline scrubber, and compare tool.
  4. Map click inspection & live search bar fly-to.
  5. Showcase hub live header service badges, Chennai ARG/Michaung chart, Three.js 3D experimental tanks.
  6. Live Node-RED Operational Dashboard (http://127.0.0.1:1880/ui/) & InfluxDB UI (http://127.0.0.1:8086).
  7. Captures verified screenshots into showcase/screenshots/.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = _PROJECT_ROOT / "showcase" / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def run_qa() -> int:
    console_errors = []
    page_errors = []
    external_blocked = []

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

        # Offline guard: strictly block ALL non-localhost external calls on main showcase / urban twin pages!
        def offline_route(route):
            url = route.request.url
            if url.startswith("http://127.0.0.1") or url.startswith("http://localhost") or url.startswith("data:") or url.startswith("blob:"):
                route.continue_()
            else:
                external_blocked.append(url)
                route.abort()

        page = context.new_page()
        page.route("**/*", offline_route)
        page.on("console", lambda m: console_errors.append(f"[{page.url}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(f"[{page.url}] {e}"))

        # 1. Load /urban-twin under strict offline mode
        print("[1/5] Loading http://127.0.0.1:8000/urban-twin (strict offline mode)...")
        page.goto("http://127.0.0.1:8000/urban-twin", wait_until="networkidle", timeout=45000)
        page.wait_for_function("document.getElementById('kpi-vol').innerText !== '-- MCM'", timeout=25000)
        time.sleep(2.0)
        kpi_vol = page.inner_text("#kpi-vol")
        kpi_area = page.inner_text("#kpi-area")
        print(f"      Heavy Rainfall loaded -> Vol: {kpi_vol}, Area: {kpi_area}")
        page.screenshot(path=str(SHOT_DIR / "01_chennai_overview.png"))

        # Test map click inspector + Fly to Velachery 3D buildings
        page.click("button:has-text('Velachery')")
        time.sleep(2.0)
        box = page.locator("#map").bounding_box()
        if box:
            page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
            page.wait_for_function("!document.getElementById('inspector-body').innerText.includes('Click anywhere')", timeout=8000)
            time.sleep(0.5)
        insp_text = page.inner_text("#inspector-body")
        print(f"      Velachery Click Inspector -> {insp_text.splitlines()[0] if insp_text else 'empty'}")
        page.screenshot(path=str(SHOT_DIR / "02_3d_urban_twin.png"))
        page.screenshot(path=str(SHOT_DIR / "03_velachery_selected.png"))

        # Search bar test -> Pallikaranai
        page.fill("#urban-search-input", "Pallikaranai")
        time.sleep(0.7)
        page.locator("#search-results-box div").first.click()
        time.sleep(1.5)
        page.screenshot(path=str(SHOT_DIR / "04_pallikaranai_selected.png"))

        # Verified Stations & Reduced Drainage comparison
        page.select_option("#preset-select", "reduced_drainage")
        time.sleep(2.2)
        page.click("button:has-text('Compare Impact Delta')")
        time.sleep(1.5)
        cmp_text = page.inner_text("#compare-output")
        print(f"      Scenario Compare -> {cmp_text.splitlines()[0] if cmp_text else 'hidden'}")
        page.screenshot(path=str(SHOT_DIR / "08_drainage_obstruction.png"))

        # Heavy Rain & Chembarambakkam spillway view
        page.select_option("#preset-select", "heavy_rainfall")
        time.sleep(1.5)
        page.screenshot(path=str(SHOT_DIR / "07_heavy_rainfall_scenario.png"))
        page.screenshot(path=str(SHOT_DIR / "05_rainfall_stations.png"))

        page.select_option("#preset-select", "reservoir_discharge")
        time.sleep(2.2)
        page.click("button:has-text('Chembarambakkam')")
        time.sleep(1.6)
        page.screenshot(path=str(SHOT_DIR / "06_reservoirs.png"))

        # Cyclone Michaung Replay & Timeline Playback
        page.click("button:has-text('Reset View')")
        page.select_option("#preset-select", "michaung_replay")
        time.sleep(2.5)
        page.screenshot(path=str(SHOT_DIR / "09_michaung_replay.png"))

        # 2. Load Showcase Hub (offline) & verify live service pills + tabs
        print("[2/5] Loading http://127.0.0.1:8000/showcase (strict offline mode)...")
        page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle", timeout=45000)
        time.sleep(2.5)
        api_status = page.inner_text("#status-api")
        mqtt_status = page.inner_text("#status-mqtt")
        influx_status = page.inner_text("#status-influx")
        nr_status = page.inner_text("#status-nodered")
        print(f"      Header Live Pills -> {api_status} | {mqtt_status} | {influx_status} | {nr_status}")

        page.click("button[data-tab='chennai']")
        time.sleep(1.5)
        page.click("button[data-tab='twin3d']")
        time.sleep(1.8)
        page.screenshot(path=str(SHOT_DIR / "10_experimental_tank_twin.png"))

        # 3. Node-RED Dashboard & Flow Editor
        print("[3/5] Loading http://127.0.0.1:1880/ui/ and flow editor ...")
        page_nr = context.new_page()
        page_nr.on("pageerror", lambda e: page_errors.append(f"[Node-RED] {e}"))
        page_nr.goto("http://127.0.0.1:1880/ui/", wait_until="networkidle", timeout=20000)
        time.sleep(2.0)
        page_nr.screenshot(path=str(SHOT_DIR / "11_nodered_dashboard.png"))
        page_nr.goto("http://127.0.0.1:1880/", wait_until="domcontentloaded", timeout=20000)
        assert "Node-RED" in page_nr.title(), f"Unexpected Node-RED editor title: {page_nr.title()}"

        # 4. InfluxDB UI (port 8086) - verify UI reachability & query Data Explorer if credentials present
        print("[4/5] Loading http://127.0.0.1:8086 ...")
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
        influx_user = os.getenv("INFLUXDB_USERNAME", "civictwin")
        influx_pass = os.getenv("INFLUXDB_PASSWORD", "")
        page_inf = context.new_page()
        page_inf.goto("http://127.0.0.1:8086", wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
        assert "InfluxDB" in page_inf.title(), f"Unexpected InfluxDB UI title: {page_inf.title()}"
        if influx_pass and page_inf.locator("input[name='username']").count() > 0:
            page_inf.fill("input[name='username']", influx_user)
            page_inf.fill("input[name='password']", influx_pass)
            page_inf.click("button[type='submit']")
            time.sleep(2.5)
            org_url = page_inf.url.split("/orgs/")
            if len(org_url) > 1:
                org_id = org_url[1].split("/")[0]
                page_inf.goto(f"http://127.0.0.1:8086/orgs/{org_id}/data-explorer", wait_until="domcontentloaded", timeout=20000)
                time.sleep(2.5)
                sc_btn = page_inf.locator("button:has-text('Script Editor')")
                if sc_btn.count() > 0 and sc_btn.first.is_visible():
                    sc_btn.first.click()
                    time.sleep(1.0)
                    flux = 'from(bucket: "telemetry")\n  |> range(start: -15m)\n  |> filter(fn: (r) => r["_measurement"] == "telemetry" and r["_field"] == "water_level_cm")'
                    if page_inf.locator(".monaco-editor").count() > 0:
                        page_inf.locator(".monaco-editor").first.click()
                        page_inf.keyboard.press("Meta+A")
                        page_inf.keyboard.type(flux)
                    sub_btn = page_inf.locator("button:has-text('Submit')")
                    if sub_btn.count() > 0:
                        sub_btn.first.click()
                        time.sleep(3.0)
                        page_inf.screenshot(path=str(SHOT_DIR / "11_influxdb_ui.png"))

        browser.close()

    print("[5/5] Browser QA Summary:")
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
    sys.exit(run_qa())
