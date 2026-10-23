# CivicTwin-R — Presentation Demo Outline

## Slide Structure (for 5–10 minute presentation)

### Slide 1: Title
- **CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring**
- Team #5 — IoT Course
- Members: Navneeth Tripathy, Keith Rocha, Neil Nickson, Mohanavel, Pandi Devi Naga Pallavi

### Slide 2: Problem & Motivation
- Urban flooding is increasing due to urbanization and climate change
- IoT sensor networks offer dense, real-time monitoring
- But sensors fail, batteries drain, networks drop — what then?
- **Research question:** How can a digital twin maintain useful warnings during degraded conditions?

### Slide 3: Architecture
- Show the data flow: Sensor → MQTT → Ingestion → Storage → Dashboard
- Digital twin engine with 3 virtual zones
- Two execution modes: Full stack (Mode A) vs Standalone (Mode B)

### Slide 4: Digital Twin Engine
- 3 zones: Riverside Canal, Downtown Storm Drain, Suburban Retention Basin
- Simplified physics model: inflow − drainage, clamped to bounds
- 8 configurable scenarios: normal, heavy rainfall, blocked drain, etc.

### Slide 5: Missing-Data Reconstruction
- Problem: What happens when sensor data is missing?
- Two baseline methods: LOCF and Linear Interpolation
- Show reconstruction_visual.png
- Linear interpolation achieves 10× lower error than LOCF

### Slide 6: Key Results
- Show reconstruction_comparison.png (MAE/RMSE vs missing rate)
- 100% message delivery in software pipeline
- All threshold crossings detected with zero delay
- 48/48 automated tests passing

### Slide 7: Live Demo (if time permits)
- Start backend → show API docs → start scenario → show alerts
- (See docs/demo_script.md for commands)

### Slide 8: Limitations & Future Work
- Simulated only — no physical sensor validation
- Simplified physics model
- MQTT broker not tested live
- Future: physical deployment, advanced ML reconstruction, weather API integration

### Slide 9: Conclusion
- Software-first IoT digital twin is feasible for prototyping
- Linear interpolation significantly outperforms LOCF for missing data
- Modular architecture enables graceful degradation
- Complete, reproducible, honestly documented
