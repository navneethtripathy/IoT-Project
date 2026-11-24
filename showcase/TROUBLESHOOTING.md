# CivicTwin-R — Live Demonstration Troubleshooting Guide

---

## 1. Port Conflict & Process Cleanup

### Symptom: `Address already in use` on port 8000, 1883, or 1880.
**Cause:** A previously executed background process did not terminate cleanly.
**Immediate Fix:**
```bash
./scripts/showcase_stop.sh
```
If an orphan process still holds the port:
```bash
# Find and terminate process on port 8000 (FastAPI)
lsof -ti :8000 | xargs kill -9 2>/dev/null || true

# Find and terminate process on port 1883 (MQTT)
lsof -ti :1883 | xargs kill -9 2>/dev/null || true

# Find and terminate process on port 1880 (Node-RED)
lsof -ti :1880 | xargs kill -9 2>/dev/null || true
```

---

## 2. Mosquitto MQTT Broker Issues

### Symptom: Backend reports `MQTT broker not reached; continuing in standalone simulation mode`.
**Diagnosis:**
```bash
/opt/homebrew/sbin/mosquitto -c mqtt/mosquitto_local.conf
```
**Fix:**
Ensure `mqtt/mosquitto_local.conf` does not specify non-existent paths. Use:
```bash
/opt/homebrew/sbin/mosquitto -c mqtt/mosquitto_local.conf -d -p 1883
```

---

## 3. Node-RED Flow or Dashboard Missing

### Symptom: `http://127.0.0.1:1880/ui` returns 404 or says `No dashboard flows`.
**Fix:**
Ensure `node-red-dashboard` package is installed in the local runtime directory:
```bash
cd "/Users/navneethtripathy/Desktop/IoT Project/CivicTwin-R"
npm install --prefix ./nodered_runtime node-red-dashboard
./scripts/showcase_start.sh
```

---

## 4. SQLite Database Reset

### Symptom: Stored records exceed thousands or contain outdated test artifacts.
**Fix:**
```bash
rm -f data/civictwin.db
./scripts/showcase_start.sh
```
FastAPI automatically recreates the schema, tables, and indices on startup with zero data loss to raw datasets.

---

## 5. UI Polling Paused

### Symptom: Numbers on `http://127.0.0.1:8000/showcase` stop updating.
**Fix:**
1. Check if the browser tab was put to sleep by the operating system. Click anywhere on the dashboard or refresh (`Cmd + R`).
2. Verify simulator is running:
   ```bash
   ps aux | grep mqtt_node_simulator
   ```
   If stopped, re-run `./scripts/showcase_start.sh`.
