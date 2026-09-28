# AquaIntel — Water Infrastructure Monitoring Platform

A full-stack IoT monitoring and alerting application built with FastAPI, SQLite, SQLAlchemy and vanilla JavaScript. It tracks physical assets, ingests sensor telemetry, raises threshold alerts, detects anomalies and estimates future threshold breaches.

## What was fixed in this release

This version is a security, validation and reliability hardening pass based on the AquaIntel QA audit dated **24 September 2026**.

- Public signup can create **Viewer** accounts only; admin accounts are created with `create_admin.py`.
- JWT signing keys are loaded from environment configuration and tokens are checked against the current database user.
- The API no longer exposes the whole project directory through `/static`.
- Telemetry, asset reads, alerts and activity require authentication; write operations require an admin.
- Login and signup credentials are sent in JSON request bodies instead of URL query strings.
- Input validation rejects invalid statuses, invalid reading types and non-finite numeric values.
- HTTP errors use appropriate 4xx status codes instead of returning successful responses containing an error object.
- SQLite foreign keys are enabled and relationships use cascading deletes.
- Alert rules are unique per asset + reading type, can be listed/deleted, and validate the asset exists.
- Alerts can be acknowledged and the dashboard counts unacknowledged alerts.
- Telemetry and alert endpoints support pagination limits instead of returning the whole table.
- Analytics are scoped to one sensor type, preventing mixed-type calculations.
- Isolation Forest uses automatic contamination handling instead of always forcing 10% of readings to be anomalies.
- Frontend tables render untrusted API values with `textContent` rather than injecting them with `innerHTML`.
- Basic security headers, a configurable CORS allow-list and a restrictive permissions policy are included.
- Failed login attempts are throttled by both client IP and account email in-process.
- A dependency manifest, environment template, Alembic migrations, Dockerfile, license and automated API regression tests are included.
- Runtime databases, Python bytecode, `.env`, Git history and virtual-environment files are excluded from the clean project package.

> > **Security note:** Runtime files such as `.env` and `aquaintel.db` are intentionally excluded from the repository. Never commit secrets, database files, Python bytecode, or other runtime artifacts.

## Features

### Asset management
- Create, list, edit and delete assets (admin only for changes)
- Search and filter by name/status
- CSV export with basic spreadsheet-formula injection protection
- Per-asset detail page

### Telemetry
- Authenticated sensor reading ingestion
- Sensor type and numeric validation
- Optional timestamp input normalized to UTC
- Paginated telemetry retrieval
- Demo simulator on the dashboard using the first available asset

### Alerting
- One threshold rule per asset + reading type
- Automatic alert creation when a reading exceeds its configured maximum
- Alert history with acknowledgement state
- Browser notifications while the application is open (page-level polling; no external push service)

### Analytics
- Statistical anomaly detection using a 2σ threshold
- Isolation Forest ML anomaly detection on a selected sensor type
- Linear trend / threshold-breach prediction for a selected sensor type

### Authentication and authorization
- bcrypt password hashing
- JWT access tokens with configurable expiration
- Database-backed token validation, so deleted/changed users invalidate old tokens
- Viewer and admin roles
- Admin-only asset, telemetry, rule and acknowledgement operations
- Public signup creates Viewer accounts only

## Project structure

```text
aquaintel/
├── main.py
├── models.py
├── database.py
├── auth.py
├── dependencies.py
├── create_admin.py
├── requirements.txt
├── .env.example
├── .gitignore
├── login.html
├── dashboard.html
├── assets.html
├── alerts.html
├── asset-detail.html
├── Dockerfile
├── LICENSE
├── alembic.ini
├── alembic/
│   └── versions/
├── static/
│   ├── auth-check.js
│   └── chart.js
└── tests/
    └── test_api.py
```

The SQLite database file is generated locally on first startup and is intentionally not committed.

## Setup

### 1. Create a virtual environment

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the JWT secret

Copy `.env.example` to `.env` and set a long random value for `AQUAINTEL_SECRET_KEY`.

Example PowerShell session:

```powershell
$env:AQUAINTEL_SECRET_KEY="replace-this-with-a-long-random-secret"
```

For a persistent local setup, load the values with your preferred environment-variable tooling. Never commit `.env`.

### 4. Create/update the database schema

```bash
alembic upgrade head
```

### 5. Start the server

```bash
python -m uvicorn main:app --reload
```

To test from another device on the same LAN:

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Create the first admin securely

After the database has been created:

```bash
python create_admin.py
```

The password is entered interactively and is not placed in a URL or source file.

### 7. Open the application

- Login: `http://127.0.0.1:8000/login-page`
- Dashboard: `http://127.0.0.1:8000/dashboard`
- API documentation: `http://127.0.0.1:8000/docs`

New public signups are Viewer accounts. Use the server-side admin creation script for administrative access.

## API overview

| Method | Endpoint | Authentication | Purpose |
|---|---|---|---|
| POST | `/signup` | Public | Create a Viewer account |
| POST | `/login` | Public | Return a JWT |
| GET | `/me` | User | Validate the current session |
| GET | `/assets` | User | List assets |
| POST | `/assets` | Admin | Create an asset |
| PUT | `/assets/{id}` | Admin | Update an asset |
| DELETE | `/assets/{id}` | Admin | Delete an asset and related records |
| GET | `/assets/{id}` | User | Read asset telemetry |
| GET | `/assets/{id}/anomalies` | User | Statistical anomaly report |
| GET | `/assets/{id}/ml-anomalies` | User | ML anomaly report |
| GET | `/assets/{id}/predict` | User | Trend / breach prediction |
| POST | `/telemetry` | Admin | Ingest a reading and evaluate alert rules |
| GET | `/telemetry` | User | Paginated telemetry retrieval |
| POST | `/alert-rules` | Admin | Create a threshold rule |
| GET | `/alert-rules` | User | List rules |
| DELETE | `/alert-rules/{id}` | Admin | Delete a rule |
| GET | `/alerts` | User | Paginated alert history |
| POST | `/alerts/{id}/acknowledge` | Admin | Acknowledge an alert |
| GET | `/activity` | User | Recent telemetry/alert activity |

## Testing

Run:

```bash
pytest -q
```

The included tests cover viewer-only signup, protected asset access, login and admin-only telemetry ingestion.

## Security notes

- Keep `AQUAINTEL_SECRET_KEY` outside source control and rotate it if it is ever exposed.
- Do not commit `aquaintel.db`, `.env`, `__pycache__` or other runtime artifacts.
- The application uses a simple in-process failed-login throttle. For a multi-worker or internet-facing deployment, use a shared rate limiter/reverse proxy.
- CORS is disabled unless `AQUAINTEL_CORS_ORIGINS` is explicitly configured.
- Browser notification polling is intentionally page-level; it is not a service-worker Web Push implementation.
- SQLite is appropriate for a local/demo deployment. A production deployment should use a managed relational database and a proper migration workflow.

## Analytics notes

**Statistical anomaly detection:** the mean and sample standard deviation are calculated for the selected sensor type. Readings more than 2σ from the mean are reported.

**ML anomaly detection:** an `IsolationForest` is trained on the selected sensor type over a configurable recent time window. `contamination="auto"` avoids hard-coding a 10% anomaly rate.

**Breach prediction:** a least-squares linear trend is fitted to the selected sensor type. If the slope is positive, the estimated time to the configured threshold is returned.

## Audit status

The implementation in this package addresses the 33 findings documented in the 24 September 2026 QA audit, including the previously open UI gaps for asset deletion and alert-rule management, offline chart dependency, explicit prediction thresholds, database integrity checks and repository hygiene. The clean package intentionally contains no `.git` history, `.env`, database or virtual environment.

For an internet-facing deployment, additional operational controls are still appropriate: a shared rate limiter/reverse proxy, managed database, centralized logging/monitoring, CI security scanning, HTTPS and backups. These are deployment controls rather than defects in the audited portfolio build.
