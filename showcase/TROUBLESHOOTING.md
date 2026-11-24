# CivicTwin-R — Rapid Diagnostic & Troubleshooting Playbook

**Target Audience:** Operators, Engineers, Demonstration Facilitators  
**Scope:** Immediate diagnostic actions and recovery steps for common demonstration anomalies.

---

## Quick Diagnostic Command
To instantly evaluate the health of all running showcase processes and ports:
```bash
./scripts/showcase_verify.sh
```

---

## 1. Port Conflict / Port Already Bound

### Symptoms
- Startup script reports `Address already in use` on port `8000`, `1883`, or `1880`.
- Backend or broker fails to launch.

### Root Cause
An orphaned process from a previous test or terminal session is holding the socket.

### Resolution
Execute the safe cleanup sweep:
```bash
./scripts/showcase_stop.sh
```
Or surgically identify and terminate the offending PID:
```bash
# Check port 8000 (FastAPI), 1883 (MQTT), 1880 (Node-RED)
lsof -ti :8000 -ti :1883 -ti :1880 | xargs kill -9 2>/dev/null || true
```
Then relaunch cleanly:
```bash
./scripts/showcase_start.sh
```

---

## 2. Mosquitto Broker Not Running / MQTT Disconnected

### Symptoms
- Showcase header shows `MQTT (1883): DISCONNECTED (Standalone Fallback)`.
- Backend logs show `MQTT broker not reached`.

### Root Cause
Mosquitto binary is not installed in the system PATH, or permissions on the local config prevented socket binding.

### Resolution
1. Verify Mosquitto binary exists:
   ```bash
   which mosquitto || echo "/opt/homebrew/sbin/mosquitto"
   ```
2. If Mosquitto is installed via Homebrew:
   ```bash
   brew services start mosquitto
   # Or run directly:
   /opt/homebrew/sbin/mosquitto -c mqtt/mosquitto_local.conf &
   ```
3. Verify listening state on port 1883:
   ```bash
   nc -z 127.0.0.1 1883 && echo "MQTT port open"
   ```
4. Note that if MQTT is unavailable, the backend gracefully falls back to internal simulation mode without crashing.

---

## 3. Node-RED Stopped or Port 1880 Not Responding

### Symptoms
- Accessing `http://127.0.0.1:1880/ui/` returns connection refused.
- Automated live integration test reports `test_live_node_red_reachability FAILED`.

### Root Cause
On macOS, Node.js attaches a `SIGHUP` listener in `red.js` that shuts down flows when a terminal subshell exits unless detached in an independent process session.

### Resolution
Start Node-RED in an independent session via Python subprocess:
```bash
python3 -c '
import os, sys, subprocess
NODE_BIN = "/opt/homebrew/bin/node" if os.path.exists("/opt/homebrew/bin/node") else "node"
RED_JS = os.path.abspath("nodered_runtime/node_modules/node-red/red.js")
user_dir = os.path.abspath(".run/nodered")
flows = os.path.abspath("nodered/flows.json")
env = dict(os.environ)
env["NODE_PATH"] = os.path.abspath("nodered_runtime/node_modules")
env["BACKEND_URL"] = "http://127.0.0.1:8000"
with open(".run/logs/nodered.log", "a") as log:
    p = subprocess.Popen([NODE_BIN, RED_JS, "--userDir", user_dir, "--port", "1880", flows],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=env, start_new_session=True)
    with open(".run/nodered.pid", "w") as f:
        f.write(str(p.pid))
print(f"Node-RED started (PID {p.pid})")
'
```
Wait 3 seconds, then confirm HTTP 200:
```bash
curl -s -I http://127.0.0.1:1880/ui/ | head -n 1
```

---

## 4. Telemetry Counter Not Incrementing / Static Gauges

### Symptoms
- Showcase dashboard gauges do not move.
- `Records Stored` count in the status bar remains fixed.

### Root Cause
The dual-node simulator process terminated or `simulator_control.json` contains a frozen override.

### Resolution
1. Check simulator process:
   ```bash
   ps aux | grep mqtt_node_simulator.py | grep -v grep
   ```
2. Restart the dual-node simulator:
   ```bash
   nohup python3 scripts/mqtt_node_simulator.py --broker localhost --port 1883 --interval 5.0 < /dev/null > .run/logs/simulator.log 2>&1 &
   ```
3. Reset control overrides to normal:
   ```bash
   curl -s -X POST http://127.0.0.1:8000/api/showcase/scenario/return_to_normal
   ```

---

## 5. SQLite Database Locked / Concurrency Contention

### Symptoms
- Backend logs report `sqlite3.OperationalError: database is locked`.

### Root Cause
An external utility opened `data/civictwin.db` in exclusive locking mode, or WAL checkpointing stalled.

### Resolution
1. Check database journal mode:
   ```bash
   python3 -c "import sqlite3; con = sqlite3.connect('data/civictwin.db'); print(con.execute('PRAGMA journal_mode;').fetchone())"
   ```
2. If not `wal`, re-enable WAL mode:
   ```bash
   python3 -c "import sqlite3; con = sqlite3.connect('data/civictwin.db'); con.execute('PRAGMA journal_mode=WAL;'); con.execute('PRAGMA synchronous=NORMAL;'); con.commit(); con.close()"
   ```
3. Perform a clean database vacuum:
   ```bash
   python3 -c "import sqlite3; con = sqlite3.connect('data/civictwin.db'); con.execute('VACUUM;'); con.close()"
   ```

---

## 6. Emergency Offline Demonstration Fallback

If network hardware or local ports encounter catastrophic unresolvable conflicts right before a presentation:
1. Open the high-resolution captured screenshot walkthrough:
   - `showcase/screenshots/01_overview.png` through `showcase/screenshots/11_nodered_dashboard.png`
2. Present the verified academic benchmarks from `showcase/RESULTS.md`.
3. Demonstrate the automated test verification suite:
   ```bash
   python3 -m pytest tests/ -v
   ```
   (All 126 unit, physics, and integration tests execute and pass within 10 seconds).
