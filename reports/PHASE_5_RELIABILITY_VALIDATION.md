# CivicTwin-R — Phase 5 Reliability, Alerts & Multi-Node Validation Report

**Date:** 2026-11-23  
**Auditor:** Principal IoT Systems & Reliability Engineer  
**Project:** CivicTwin-R: A Resilient Cyber-Physical Digital Twin for Urban Flood Monitoring and Scenario Planning  
**Status:** **AUDIT COMPLETE — PASSED**

---

## 1. Executive Summary

This report evaluates system reliability under degraded communications, packet drops, sensor hardware faults, and concurrent dual-node operation. All core reliability features—including timestamp-driven freshness state machines, edge warning hysteresis, optical LED signalling patterns, and complete logical isolation between independent sensor nodes—have been verified.

---

## 2. Real-Time Data Freshness State Machine

The freshness engine in `backend/ingestion.py` evaluates incoming observation timestamps relative to current system time using non-blocking chronological evaluation.

### 2.1 State Definitions and Transition Rules

```
                      Age < 30s
     ┌────────────────────────────────────────┐
     │                                        │
     ▼                                        │
┌─────────┐      Age ≥ 30s       ┌─────────┐  │   Age ≥ 90s      ┌──────────┐
│  FRESH  │ ───────────────────► │  STALE  │ ─┴────────────────► │ OFFLINE  │
└─────────┘                      └─────────┘                     └──────────┘
     ▲                                                                │
     │                 Valid Packet Arrives (< 30s)                   │
     └────────────────────────────────────────────────────────────────┘
```

- **`FRESH` ($t_{\text{age}} < 30.0\text{ s}$):** Active node streaming at expected cadence ($5\text{ s}$). Connection state: `"online"`.
- **`STALE` ($30.0\text{ s} \le t_{\text{age}} < 90.0\text{ s}$):** Missing 6+ consecutive intervals; data may not reflect current physical status. Connection state: `"stale"`.
- **`OFFLINE` ($t_{\text{age}} \ge 90.0\text{ s}$ or no valid readings):** Communication severed or node unpowered. Connection state: `"disconnected"`.
- **`INVALID`:** Sensor reporting physical echo failure or out-of-range bounds ($< 2\text{ cm}$ or $> 400\text{ cm}$). Connection state: `"error"`.

### 2.2 Automated Lifecycle Verification
Automated test `test_freshness_lifecycle` validates transitions:
- $t = 0\text{ s}$: Valid reading ingested $\rightarrow$ `FRESH` (age $0.0\text{ s}$).
- $t = 35\text{ s}$: No new reading $\rightarrow$ `STALE` (age $35.0\text{ s}$).
- $t = 95\text{ s}$: No new reading $\rightarrow$ `OFFLINE` (age $95.0\text{ s}$).
- $t = 100\text{ s}$: New valid reading ingested $\rightarrow$ Recovers immediately to `FRESH`.

---

## 3. Autonomous Edge Warning & Hysteresis Logic

The ESP32 firmware (`firmware/esp32/src/main.ino`) and testable Python counterpart (`digital_twin/edge_warning.py`) implement local autonomy without backend round-trip latency.

### 3.1 Threshold Specifications
- **Warning Threshold:** $70.0\%$ container height ($35.0\text{ cm}$ in Tank 1, $42.0\text{ cm}$ in Tank 2).
- **Critical Threshold:** $85.0\%$ container height ($42.5\text{ cm}$ in Tank 1, $51.0\text{ cm}$ in Tank 2).
- **Hysteresis Band:** $3.0\%$ container height.

### 3.2 Anti-Chatter Suppression Verification
Water surface turbulence and surface ripples cause noisy instantaneous readings near threshold boundaries.
- **Rising Transition:** Triggered instantly upon crossing $70.0\%$ (Warning) or $85.0\%$ (Critical).
- **Falling Transition:** Level must drop strictly below $(70.0\% - 3.0\% = 67.0\%)$ to clear Warning, and below $(85.0\% - 3.0\% = 82.0\%)$ to downgrade Critical to Warning.
- Automated test `test_anti_chatter_oscillation_suppression` injected 20 cycles alternating between $69.8\%$ and $70.2\%$; alert state remained rock-solid in `WARNING` without flapping.

### 3.3 Optical LED Signalling Modes
The physical GPIO 2 LED / buzzer outputs distinct optical signatures:
1. **`NORMAL`:** LED `OFF` (digital LOW).
2. **`WARNING`:** 1 Hz periodic blink ($500\text{ ms}$ ON, $500\text{ ms}$ OFF) to visually distinguish from critical alert.
3. **`CRITICAL`:** Continuous solid illumination (digital HIGH).
4. **`FAULT`:** 5 Hz rapid strobe ($100\text{ ms}$ toggling) upon 5 consecutive sensor echo dropouts.

---

## 4. Multi-Node Logical Isolation

CivicTwin-R enforces strict architectural and logical separation between dual sensor nodes:
- `node_01` (Adyar / Tank 1): Diameter $19.54\text{ cm}$, Height $50.0\text{ cm}$, Topic `civictwin/v1/nodes/node_01/telemetry`.
- `node_02` (Cooum / Tank 2): Diameter $23.94\text{ cm}$, Height $60.0\text{ cm}$, Topic `civictwin/v1/nodes/node_02/telemetry`.

### 4.1 Concurrent Interleaving Verification
Automated test `test_concurrent_dual_node_isolation`:
1. Injected 10 interleaved messages alternating between `node_01` and `node_02`.
2. Verified sequence numbers advance independently (`node_01` seq 1-5, `node_02` seq 1-5).
3. Verified separate storage records, separate water level percentages, and separate freshness states.
4. An out-of-order sequence on `node_01` was dropped without impacting `node_02`.

---

## 5. Acceptance Decision

**Verdict: ACCEPTED (PASS)**  
The reliability mechanics—freshness tracking, edge-warning autonomy, anti-chatter hysteresis, and multi-node logical isolation—are fully verified and operational.
