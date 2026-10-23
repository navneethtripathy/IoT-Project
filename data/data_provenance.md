# CivicTwin-R — Data Provenance & Environmental Observation Registry

Geographical Scope: **Chennai Metropolitan Basin, Tamil Nadu, India**  
Basin Geographic Bounds: Latitude 12°40'N to 13°40'N, Longitude 79°10'E to 80°25'E; Total Area: 4,974 km²  
Sub-Basins: **Adyar**, **Cooum**, **Kosasthalaiyar**, **Kovalam**, **Nandiyar**, **Nagariyar**

---

## Dataset 1: Real-Time Automatic Rain Gauge (ARG) Observations

- **Original Source & Dataset Title**: Chennai Flood Monitoring and Spatial Decision Support System (CFM-DSS) — Automatic Rain Gauges (RTDAS ARG Network).
- **Official URL / Download Reference**: [https://www.chennaifloodmonitor.tn.gov.in/](https://www.chennaifloodmonitor.tn.gov.in/)
- **Supervising Agencies**: Government of Tamil Nadu, Commissionerate of Revenue Administration (CRA), Greater Chennai Corporation (GCC), Water Resources Department (WRD), SECON-JBA JV, IIT Madras.
- **Retrieval Date**: October 23, 2026.
- **Coverage**: 328 telemetry records across 117 telemetry-equipped sub-basin rain gauges covering Adyar, Cooum, Kosasthalaiyar, Kovalam, Vegavati, Kiliyar, Araniyar.
- **Station Identifiers**: Official ARG IDs (e.g., `CHN06Z068W19`, `CHN13Z183W44`, `CHN04Z040W15`, `CHN05Z058W16`, `RPTWALVIS17`, `CHN07Z086W25`).
- **Timestamp & Time Zone**: ISO-8601 timestamps (`time_of_measurement`, `date`) in Indian Standard Time (IST, UTC+05:30).
- **Measurement Name & Units**: Rainfall (`rainfall_mm`) and prior-period rainfall (`previous_rainfall_mm`) in millimetres (mm).
- **Quality Limitations**: Variable reporting intervals; periods of dry weather naturally reflect 0.0 mm; network drops in certain remote stations.
- **Data Classification**: `observed` (real-world automated field measurement).
- **Transformations Applied**: JSON extraction from official dashboard HTML payload, unicode unescaping, null-coalescing of missing prior rainfall, exported to canonical CSV.
- **Storage Location**:
  - Raw: `data/raw/cfm_dashboard_raw.json`
  - Cleaned: `data/processed/chennai_arg_rainfall.csv`

---

## Dataset 2: Chennai Major Reservoirs & Lakes Capacity Metrics

- **Original Source & Dataset Title**: CFM-DSS Lake Operation Guidance System (LOGS) & Real-Time Storage Telemetry.
- **Official URL / Download Reference**: [https://www.chennaifloodmonitor.tn.gov.in/](https://www.chennaifloodmonitor.tn.gov.in/)
- **Retrieval Date**: October 23, 2026.
- **Monitored Reservoirs**:
  1. `TNCH-07-T0726` — **Chembarambakkam Reservoir** (Adyar Basin upstream regulator; Gross: 103.22 MCM, Live: 42.45 MCM, 41.12% fill)
  2. `Po001` — **Poondi Reservoir** (Kosasthalaiyar Basin upstream regulator; Gross: 91.49 MCM, Live: 13.82 MCM, 15.10% fill)
  3. `RD001` — **RedHills / Puzhal Lake** (North-Central Chennai drinking water supply; Gross: 93.45 MCM, Live: 68.33 MCM, 73.12% fill)
  4. `Cho001` — **Cholavaram Lake** (Kosasthalaiyar tributary; Gross: 30.61 MCM, Live: 4.08 MCM, 13.32% fill)
  5. `TK-001` — **Thervoy Kandigai Reservoir** (Tiruvallur storage; Gross: 14.16 MCM, Live: 6.91 MCM, 48.80% fill)
- **Measurement Name & Units**: Gross storage capacity (`MCM`), Live storage capacity (`MCM`), Dead storage (`MCM`), Storage fill percentage (`%`). 1 MCM = $10^6 \text{ m}^3$.
- **Quality Limitations**: Gate operation adjustments and dead-storage silting variations; values reflect official WRD hydrological telemetry.
- **Data Classification**: `observed`.
- **Transformations Applied**: Structured into normalized CSV records with human-readable reservoir names and percentage fill calculations.
- **Storage Location**:
  - Raw: `data/raw/cfm_dashboard_raw.json`
  - Cleaned: `data/processed/chennai_reservoirs.csv`

---

## Dataset 3: Cyclone Michaung Extreme Rainstorm Hourly Time-Series

- **Original Source & Dataset Title**: ECMWF ERA5 Reanalysis calibrated against IMD ground precipitation for the Cyclone Michaung extreme rainfall disaster (December 1 to December 6, 2023).
- **Official URL / Reference**: Open-Meteo Open Climate Historical Archive (`https://archive-api.open-meteo.com/v1/archive`)
- **Geographic Coordinates**: Latitude 13.0827°N, Longitude 80.2707°E (Chennai City Centre / Nungambakkam-Saidapet basin centroid).
- **Retrieval Date**: October 23, 2026.
- **Event Period**: 2023-12-01T00:00 to 2023-12-06T23:00 (144 continuous hourly observations).
- **Timestamp & Time Zone**: Hourly intervals, `Asia/Kolkata` (IST, UTC+05:30).
- **Measurements & Units**: Hourly precipitation (`mm/hr`), Cumulative rainfall (`mm`). Peak hourly rate: 26.1 mm/hr; total storm rainfall: 369.8 mm.
- **Quality Limitations**: Reanalysis model re-calibrated with radar and ground-gauge records; small micro-urban drainage variations exist across localized streets.
- **Data Classification**: `observed` / `replayed_historical` (used for controlled replay through IoT telemetry ingestion).
- **Transformations Applied**: Hourly alignment, cumulative rainfall summation, ISO-8601 time formatting, schema standardization.
- **Storage Location**:
  - Raw: `data/raw/chennai_michaung_hourly_raw.json`
  - Cleaned: `data/processed/chennai_michaung_hourly.csv`

---

## Provenance Labeling Standard

Every data point traversing CivicTwin-R carries an explicit provenance tag:

| Tag | Definition | Example Usage |
|---|---|---|
| `observed` | Real physical measurement from official sensors or gauges | CFM-DSS ARG rain gauge readings, reservoir levels |
| `replayed_historical` | Historical observations streamed through the IoT pipeline at a controlled rate | Cyclone Michaung Dec 2023 hourly rainfall stream |
| `forecast` | Predictive projection from digital-twin models with horizon metadata | 15-min and 60-min catchment water-level forecasts |
| `digital_twin_simulation` | Water-balance simulation calculated by DigitalTwinEngine | Zone discrete-time states under scenarios |
| `python_simulator` | Locally synthesized sensor telemetry for fault/resilience testing | Noise, dropout, and threshold stress tests |
| `wokwi` | Microcontroller simulation telemetry streamed from virtual ESP32 | Ultrasonic sensor distance readings via virtual firmware |
| `physical_sensor` | Telemetry from physical hardware | Benchmarked hardware sensor attached via serial/MQTT |
| `reconstructed` | Value inferred by LOCF or linear interpolation to replace missing points | Held-out recovery benchmark evaluations |
