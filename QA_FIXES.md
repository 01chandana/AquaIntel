# QA audit fix map

This file maps the September 24, 2026 QA audit findings to the cleaned codebase.

| Audit ID | Fix in this package |
|---|---|
| AQ-001 | Public signup always creates `viewer`; `create_admin.py` is used for admin creation. |
| AQ-002 | `/static` exposes only the dedicated `static/` directory. |
| AQ-003 | JWT key comes from `AQUAINTEL_SECRET_KEY`; `/me`/auth dependency checks the current user and role. |
| AQ-004 | Frontend table content is created with DOM APIs/`textContent`; prediction text is not injected as HTML. |
| AQ-005 | Asset, telemetry, alert and activity reads require authentication; telemetry writes require admin. |
| AQ-006 | Login/signup credentials are JSON bodies, not query parameters. |
| AQ-007 | Analytics accept a sensor type and query only that type. |
| AQ-008 | Pydantic validation rejects non-finite telemetry and threshold values; ML hours are bounded. |
| AQ-009 | Foreign keys are enabled for SQLite; required relationship columns are non-null with cascading deletes. |
| AQ-010 | Password length is validated to bcrypt's 72-byte limit. |
| AQ-011 | Missing resources and invalid operations return proper 4xx status codes. |
| AQ-012 | Asset, telemetry, rule and authentication inputs have explicit validation. |
| AQ-013 | API timestamps are normalized and serialized as UTC `Z` timestamps. |
| AQ-014 | CORS is allow-list based; security headers/permissions policy and IP+email login throttling are included. |
| AQ-015 | Telemetry and alerts use bounded pagination. |
| AQ-016 | Duplicate alert rules are rejected with a database uniqueness constraint. |
| AQ-017 | Alert rules can be listed/deleted; assets can be deleted; alerts can be acknowledged; dashboard uses active alerts. |
| AQ-018 | Isolation Forest uses `contamination="auto"` rather than forcing 10% anomalies. |
| AQ-019 | Emails are normalized to lowercase during signup/login. |
| AQ-020 | File paths are resolved from the application directory instead of the process working directory. |
| AQ-021 | Frontend calls `/me` to invalidate expired/deleted-user sessions. |
| AQ-022 | CSV export quotes cells and prefixes spreadsheet-formula-leading values. |
| AQ-023 | Asset names are rendered as text nodes, so apostrophes cannot break inline JavaScript. |
| AQ-024 | Signup feedback is shown directly and is not immediately cleared by a mode switch. |
| AQ-025 | Enter in the password field submits login/signup. |
| AQ-026 | Missing/invalid asset IDs produce a clear page message. |
| AQ-027 | Chart rendering is bundled locally in `static/chart.js`; the application no longer depends on a CDN for charts. |
| AQ-028 | `requirements.txt` includes FastAPI, SQLAlchemy, auth, NumPy, scikit-learn, Pydantic, pytest and httpx. |
| AQ-029 | The clean package contains no database and no `.git/`; the old history must be replaced before publishing. |
| AQ-030 | Pycache, database files, `.env`, Git history, virtual environments, Docker artifacts and editor/runtime files are excluded from the clean package; Dockerfile and LICENSE are included. |
| AQ-031 | PyJWT is used instead of `python-jose`, avoiding the audit's noted ecdsa dependency path. |
| AQ-032 | Prediction and anomaly endpoints take an explicit reading type; prediction requires an explicit threshold and the UI can load the matching alert-rule threshold instead of hard-coding 80. |
| AQ-033 | README accurately describes page-level browser notification polling; no unsupported Web Push claim remains. |

## Audit completion note

The clean deliverable intentionally contains no `.git` history or runtime secrets/database. Any credentials that appeared in an older repository history must remain rotated; removing them from a new source package cannot retroactively erase copies that may exist in remote caches.

## Remaining deployment work

The audit was performed against a local portfolio application. This package hardens the documented findings, but an internet-facing deployment should still use HTTPS, a reverse proxy, centralized/shared rate limiting, a managed database and a formal migration/backup/monitoring workflow.
