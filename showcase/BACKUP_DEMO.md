# CivicTwin-R — Offline & Backup Demonstration Protocol

**Purpose:** Fallback demonstration procedure for presentations conducted without internet connectivity, external hardware, or local package manager privileges.

---

## 1. Zero-Internet Demonstration Capability

CivicTwin-R is completely self-contained. It requires **zero active internet connection**:
1. All Python dependencies (`fastapi`, `paho-mqtt`, `pydantic`, `matplotlib`, `pytest`) are installed locally.
2. The SQLite database is local (`data/civictwin.db`).
3. Historical Chennai rainfall (`cfm_dashboard_raw.json`) and reservoir data (`chennai_reservoirs.csv`) are bundled in the repository.
4. Pre-computed publication figures and CSV tables are archived in `results/plots/` and `results/tables/`.

---

## 2. Minimal Standalone Mode (Zero External Infrastructure)

If Mosquitto or Node-RED are prohibited or cannot be launched:
```bash
# Start standalone mode using Python standard runtime
./scripts/start.sh
```
- Ingestion runs via internal thread callback.
- Storage falls back to local SQLite.
- Digital twin runs on Python threads.
- All 25+ REST API endpoints function normally on `http://127.0.0.1:8000`.
- The Engineering Showcase Control Center is fully accessible at `http://127.0.0.1:8000/showcase`.

---

## 3. Static Artifact Presentation Fallback

If browser execution is disrupted during an exam, walk through the pre-generated evidence artifacts:
1. **System Screenshots:** Show high-resolution captures in `showcase/SCREENSHOTS/`:
   - `showcase_overview.png`: Complete system topology and live health dials.
   - `showcase_nodes.png`: Dual tank columns showing water levels and edge warning states.
   - `showcase_twin.png`: RK4 forward trajectory vs measured values.
   - `showcase_reconstruction.png`: Comparative bar chart across gap lengths.
   - `showcase_chennai.png`: Cyclone Michaung hourly storm timeline.
2. **Scientific Plots:**
   - `results/plots/three_method_gap_length_mae.png`
   - `results/plots/three_method_reconstruction_trajectories.png`
3. **Automated Test Matrix:**
   ```bash
   python3 -m pytest tests/ -v
   ```
   Proves all 126 unit, integration, and physical twin tests pass deterministically.

---

## 4. Honest Scientific Disclosure Script

If questioned about physical hardware:
> "In accordance with strict academic integrity, we disclose that physical ultrasonic sensors and acrylic plumbing rigs are not physically connected during this computer demonstration. The sensor tiers run as a calibrated cyber-physical software emulator executing identical Torricelli differential equations and 5V-to-3V voltage divider schematics prepared for physical ESP32 flashing. All displayed metrics represent genuine algorithmic executions."
