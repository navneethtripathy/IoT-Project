"""
CivicTwin-R — Capture Chennai Urban Digital Twin Screenshots
Captures publication-grade screenshots of the 3D Chennai geospatial digital twin,
locations, flood scenarios, and the experimental tank twin using Playwright & Chrome.
"""

import os
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "showcase", "screenshots"))
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def capture_all():
    print(f"[SCREENSHOTS] Target directory: {SCREENSHOT_DIR}")
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_BIN,
            headless=True,
            args=["--disable-web-security", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1600, "height": 1050},
            device_scale_factor=1.5,
        )
        page = context.new_page()

        # 1. Chennai Geographical Overview (/urban-twin)
        print("Capturing 01_chennai_overview.png...")
        page.goto("http://127.0.0.1:8000/urban-twin", wait_until="networkidle")
        page.wait_for_timeout(3500)
        p1 = os.path.join(SCREENSHOT_DIR, "01_chennai_overview.png")
        page.screenshot(path=p1)
        results.append(("01_chennai_overview.png", "Chennai Geographical Overview & South Basin Catchment"))

        # 2. 3D Urban Environment (Tilted 60 deg view with buildings)
        print("Capturing 02_3d_urban_twin.png...")
        page.evaluate("map.flyTo({center: [80.218, 12.9815], zoom: 14.2, pitch: 65, bearing: -25})")
        page.wait_for_timeout(2500)
        p2 = os.path.join(SCREENSHOT_DIR, "02_3d_urban_twin.png")
        page.screenshot(path=p2)
        results.append(("02_3d_urban_twin.png", "3D Urban Environment with Extruded Building Geometry"))

        # 3. Velachery Selected
        print("Capturing 03_velachery_selected.png...")
        page.evaluate("flyToLocation('velachery'); switchSidebarTab('info');")
        page.wait_for_timeout(2500)
        p3 = os.path.join(SCREENSHOT_DIR, "03_velachery_selected.png")
        page.screenshot(path=p3)
        results.append(("03_velachery_selected.png", "Velachery Depression Basin & Infrastructure Detail"))

        # 4. Pallikaranai Selected
        print("Capturing 04_pallikaranai_selected.png...")
        page.evaluate("flyToLocation('pallikaranai'); selectLocation('pallikaranai'); switchSidebarTab('info');")
        page.wait_for_timeout(2500)
        p4 = os.path.join(SCREENSHOT_DIR, "04_pallikaranai_selected.png")
        page.screenshot(path=p4)
        results.append(("04_pallikaranai_selected.png", "Pallikaranai Marsh Wetland Sink & Inundation Detail"))

        # 5. Rainfall Monitoring Layer (Stations)
        print("Capturing 05_rainfall_stations.png...")
        page.evaluate("switchSidebarTab('layers'); resetCameraView();")
        page.wait_for_timeout(2500)
        p5 = os.path.join(SCREENSHOT_DIR, "05_rainfall_stations.png")
        page.screenshot(path=p5)
        results.append(("05_rainfall_stations.png", "Automatic Rain Gauge Stations & Catchment Boundaries"))

        # 6. Reservoir Layer (Chembarambakkam)
        print("Capturing 06_reservoirs.png...")
        page.evaluate("flyToLocation('chembarambakkam'); selectLocation('chembarambakkam'); switchSidebarTab('info');")
        page.wait_for_timeout(2500)
        p6 = os.path.join(SCREENSHOT_DIR, "06_reservoirs.png")
        page.screenshot(path=p6)
        results.append(("06_reservoirs.png", "Chembarambakkam Reservoir Headworks & Storage Level"))

        # 7. Heavy Rainfall Scenario
        print("Capturing 07_heavy_rainfall_scenario.png...")
        page.evaluate("switchSidebarTab('scenarios'); applyPresetScenario('heavy_rain'); resetCameraView();")
        page.wait_for_timeout(2500)
        p7 = os.path.join(SCREENSHOT_DIR, "07_heavy_rainfall_scenario.png")
        page.screenshot(path=p7)
        results.append(("07_heavy_rainfall_scenario.png", "Heavy Rainfall Scenario (45 mm/hr) & Inundation Overlay"))

        # 8. Drainage Obstruction Scenario
        print("Capturing 08_drainage_obstruction.png...")
        page.evaluate("applyPresetScenario('drainage_obstruction'); flyToLocation('pallikaranai');")
        page.wait_for_timeout(2500)
        p8 = os.path.join(SCREENSHOT_DIR, "08_drainage_obstruction.png")
        page.screenshot(path=p8)
        results.append(("08_drainage_obstruction.png", "Drainage Obstruction Scenario (25% Capacity Choke)"))

        # 9. Cyclone Michaung Historical Replay
        print("Capturing 09_michaung_replay.png...")
        page.evaluate("applyPresetScenario('michaung_replay'); resetCameraView();")
        page.wait_for_timeout(2500)
        p9 = os.path.join(SCREENSHOT_DIR, "09_michaung_replay.png")
        page.screenshot(path=p9)
        results.append(("09_michaung_replay.png", "Cyclone Michaung Dec 2023 Extreme Storm Reconstruction"))

        # 10. Experimental IoT Tank Digital Twin (Showcase Tab 6)
        print("Capturing 10_experimental_tank_twin.png...")
        page.goto("http://127.0.0.1:8000/showcase#twin3d", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.evaluate("switchTab('twin3d')")
        page.wait_for_timeout(3000)
        p10 = os.path.join(SCREENSHOT_DIR, "10_experimental_tank_twin.png")
        page.screenshot(path=p10)
        results.append(("10_experimental_tank_twin.png", "Experimental IoT Tank Digital Twin (Laboratory Bench)"))

        # Update 01_overview.png on Showcase center
        print("Updating 01_overview.png...")
        page.goto("http://127.0.0.1:8000/showcase#urbantwin", wait_until="networkidle")
        page.wait_for_timeout(1000)
        page.evaluate("switchTab('urbantwin')")
        page.wait_for_timeout(3500)
        p_overview = os.path.join(SCREENSHOT_DIR, "01_overview.png")
        page.screenshot(path=p_overview)

        browser.close()

    print("\n[SUCCESS] Captured All 10 Screenshots:")
    print("-" * 80)
    for fname, desc in results:
        fpath = os.path.join(SCREENSHOT_DIR, fname)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"  * {fname:32} | {size_kb:8.1f} KB | {desc}")
    print("-" * 80)


if __name__ == "__main__":
    capture_all()
