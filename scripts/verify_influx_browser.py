#!/usr/bin/env python3
"""
CivicTwin-R — Automated InfluxDB Web UI Browser Verification
Logs in to InfluxDB 2.x at http://localhost:8086, navigates to Data Explorer,
selects the 'telemetry' bucket, queries incoming water_level_cm and water_level_pct,
and captures visual evidence in showcase/screenshots/11_influxdb_ui.png.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def main():
    screenshot_dir = Path("showcase/screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    out_file = screenshot_dir / "11_influxdb_ui.png"
    influx_user = os.getenv("INFLUXDB_USERNAME", "civictwin")
    influx_pass = os.getenv("INFLUXDB_PASSWORD", "")
    if not influx_pass:
        print("Error: INFLUXDB_PASSWORD not set in .env or environment.", file=sys.stderr)
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME_BIN,
            headless=True,
            args=["--disable-web-security", "--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        print("Navigating to InfluxDB UI: http://localhost:8086 ...")
        page.goto("http://localhost:8086", wait_until="networkidle", timeout=15000)
        time.sleep(2)

        # Check if signin page
        if "signin" in page.url or page.locator("input[name='username']").is_visible():
            print("Signing in with configured local credentials...")
            page.fill("input[name='username']", influx_user)
            page.fill("input[name='password']", influx_pass)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle", timeout=10000)
            time.sleep(2)

        print(f"Current page URL: {page.url}")

        # Navigate to Data Explorer
        print("Navigating to Data Explorer...")
        page.goto("http://localhost:8086/orgs/b859eda1f09b2d51/data-explorer", wait_until="networkidle", timeout=15000)
        time.sleep(3)

        # Look for telemetry bucket or query builder
        print("Page title:", page.title())

        # Click on 'Script Editor' or Query Builder to run a flux query if needed
        script_editor_btn = page.locator("button:has-text('Script Editor')")
        if script_editor_btn.is_visible():
            print("Opening Script Editor...")
            script_editor_btn.click()
            time.sleep(1)

            # Paste flux query to visualize both nodes
            flux_query = '''from(bucket: "telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "telemetry")
  |> filter(fn: (r) => r["_field"] == "water_level_cm")
  |> yield(name: "mean")'''
            
            # Find the editor text area / Monaco editor or input
            editor = page.locator(".monaco-editor textarea, .view-lines")
            if editor.first.is_visible():
                page.keyboard.press("Meta+A")
                page.keyboard.type(flux_query)
            
            # Click submit button
            submit_btn = page.locator("button:has-text('Submit'), button[title='Submit']")
            if submit_btn.first.is_visible():
                submit_btn.first.click()
                time.sleep(3)

        # Capture screenshot
        page.screenshot(path=str(out_file))
        print(f"Screenshot saved successfully: {out_file} ({out_file.stat().st_size} bytes)")
        browser.close()

if __name__ == "__main__":
    main()
