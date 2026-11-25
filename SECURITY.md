# Security Policy & Responsible Disclosure

## Deployment & Threat Model

**CivicTwin-R** is designed for local research, teaching, and technical demonstration on isolated loopback interfaces (`127.0.0.1` / `localhost`):

- FastAPI (`127.0.0.1:8000`), standalone Mosquitto (`mqtt/mosquitto_local.conf`), and Docker host bindings (`docker-compose.yml`) default to loopback (`127.0.0.1`).
- UI and telemetry ingestion run unauthenticated on localhost by default for research repeatability; **do not expose CivicTwin-R services to the public internet without adding TLS termination, API/broker authentication (`allow_anonymous false` + MQTT password file), and reverse-proxy access controls**.
- Local runtime secrets reside exclusively in gitignored `.env` (`.env.example` contains placeholders only; `./scripts/setup.sh` generates randomized local credentials with `chmod 600 .env`).

## Supported Versions

Only the latest state on the `main` branch of [`navneethtripathy/IoT-Project`](https://github.com/navneethtripathy/IoT-Project) is maintained for security fixes.

## Reporting a Vulnerability

If you discover a security or privacy issue in this repository:

1. **Do not** disclose exploit details or credentials publicly in issues or pull requests.
2. Report privately via **GitHub Security Advisories** (`Security` tab -> `Report a vulnerability`) at [`https://github.com/navneethtripathy/IoT-Project/security/advisories`](https://github.com/navneethtripathy/IoT-Project/security/advisories).
3. Include reproduction steps, affected component/file paths, and potential impact. Maintainers will review and patch legitimate issues on `main`.

## Historical Credential Hygiene Notice

Commits prior to `b0fb8de` included default development InfluxDB credential strings in environment templates. Those local tokens have been revoked/rotated and removed from `.env.example`, though immutable Git commit history still contains those earlier commits. Never reuse historical default tokens or expose development InfluxDB instances externally.
