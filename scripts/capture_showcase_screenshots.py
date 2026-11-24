"""
CivicTwin-R — Automated High-Resolution Showcase Screenshot Capturer
Captures publication-grade screenshots of all showcase modules and the Node-RED dashboard.
"""

import os
import sys
import time
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "showcase", "screenshots"))
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

TAB_CONFIG = [
    {
        "id": "overview",
        "file": "01_overview.png",
        "description": "Showcase Overview & System Topology",
        "wait": 2.0,
    },
    {
        "id": "nodes",
        "file": "02_dual_nodes.png",
        "description": "Dual-Node Real-time Gauges & Telemetry Charts",
        "wait": 2.0,
    },
    {
        "id": "twin3d",
        "file": "03_3d_digital_twin.png",
        "description": "Interactive Three.js WebGL 3D Acrylic Twin Tanks",
        "wait": 3.0,
    },
    {
        "id": "twin",
        "file": "04_rk4_prediction.png",
        "description": "RK4 Numerical ODE Prediction vs Live Sensor Data",
        "wait": 2.5,
    },
    {
        "id": "reconstruction",
        "file": "05_reconstruction.png",
        "description": "Missing-Data Reconstruction & Zero-Leakage Benchmark",
        "wait": 2.0,
    },
    {
        "id": "reliability",
        "file": "06_reliability_freshness.png",
        "description": "Node Freshness State Machine, Diagnostics & Alert Log",
        "wait": 2.0,
    },
    {
        "id": "chennai",
        "file": "07_chennai_grounding.png",
        "description": "Chennai Basin Map, Michaung Replay & Reservoir Levels",
        "wait": 2.0,
    },
    {
        "id": "scenarios",
        "file": "08_scenario_lab.png",
        "description": "Scenario Planning Laboratory (10 Cyber-Physical Scenarios)",
        "wait": 2.0,
    },
    {
        "id": "database",
        "file": "09_database_explorer.png",
        "description": "Read-Only Database Inspection Explorer & Pagination",
        "wait": 2.5,
        "action": lambda page: page.evaluate("loadTableRecords()") if page.evaluate("typeof loadTableRecords === 'function'") else None,
    },
    {
        "id": "mqtt",
        "file": "10_mqtt_streamer.png",
        "description": "Native MQTT Live Streamer & Packet Inspector",
        "wait": 2.0,
    },
]


def run():
    print(f"Capturing screenshots to: {SCREENSHOT_DIR}")
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

        print("Navigating to Showcase Control Center...")
        page.goto("http://127.0.0.1:8000/showcase", wait_until="networkidle")
        page.wait_for_timeout(3000)

        for tab in TAB_CONFIG:
            print(f"  Capturing [{tab['id']}] -> {tab['file']}...")
            page.evaluate(f"switchTab('{tab['id']}')")
            page.wait_for_timeout(int(tab["wait"] * 1000))
            if "action" in tab and callable(tab["action"]):
                try:
                    tab["action"](page)
                    page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"    Action notice: {e}")

            out_path = os.path.join(SCREENSHOT_DIR, tab["file"])
            page.screenshot(path=out_path, full_page=False)
            size_kb = os.path.getsize(out_path) / 1024
            results.append((tab["file"], tab["description"], f"{size_kb:.1f} KB"))

        # Node-RED Dashboard
        print("  Capturing Node-RED Dashboard...")
        try:
            page.goto("http://127.0.0.1:1880/ui/", wait_until="load", timeout=10000)
            page.wait_for_timeout(3500)
            nr_file = "11_nodered_dashboard.png"
            nr_path = os.path.join(SCREENSHOT_DIR, nr_file)
            page.screenshot(path=nr_path, full_page=False)
            size_kb = os.path.getsize(nr_path) / 1024
            results.append((nr_file, "Node-RED Operational Dashboard (port 1880/ui)", f"{size_kb:.1f} KB"))
        except Exception as e:
            print(f"    Error capturing Node-RED: {e}")

        browser.close()

    print("\nScreenshot Summary:")
    print("-" * 80)
    for f, desc, size in results:
        print(f"  * {f:30} | {size:10} | {desc}")
    print("-" * 80)
    print(f"Captured {len(results)} screenshots successfully.")


if __name__ == "__main__":
    run()
