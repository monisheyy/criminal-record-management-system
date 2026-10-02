# AI-CRMS — Criminal Records Management System

A FastAPI + React application for managing offender records, case files (FIR, victims, evidence, linked persons) and an **AI decision-support** workflow in which every model output must be reviewed by a qualified human.

> ⚠️ **The bundled AI models are trained on synthetic demonstration data.** They have no real-world validity and are disabled in production configuration. See [docs/MODEL_CARD.md](docs/MODEL_CARD.md).

## Architecture

```
Browser (React SPA) ──HTTPS──> nginx ──/api, /api/notifications/ws──> FastAPI ──> PostgreSQL / SQLite
                                 │                                       │
                         static assets                         ML artifacts (signed, verified before load)
```

* **Backend** (`backend/`): FastAPI, SQLAlchemy 2, Alembic migrations, PyJWT sessions in HttpOnly cookies, role + object-level authorization, append-only HMAC-signed audit trail, scikit-learn pipeline with quality gates and artifact integrity checks, PDF/Excel reports.
* **Frontend** (`frontend/`): React 19 + Vite, route-level code splitting and error boundaries, accessible dialogs/tables, server-side pagination.
* **Roles:** administrator, investigating officer, record clerk — see [docs/SECURITY.md](docs/SECURITY.md).

## Quick start (development)

Requirements: Python 3.13, Node 22+.

```powershell
# 1. Configuration
copy .env.example .env          # then set SECRET_KEY (python -c "import secrets; print(secrets.token_urlsafe(48))")

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1    # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --host localhost --port 8000
```

On first start the database is migrated and (in development) seeded with fictional demo data. Demo accounts — `admin / admin123`, `officer1 / officer123`, `clerk1 / clerk123` — **must change their password at first sign-in**.

```powershell
# 3. Frontend (second terminal)
cd frontend
npm ci
npm run dev                      # http://localhost:5173
```

Use `localhost` (not `127.0.0.1`) for both servers so the session cookie is same-site.

## Tests

```powershell
cd backend;  pytest -q                      # 213 tests: API, authorization matrix, security, integrity, migrations, ML
cd frontend; npm run lint; npm test; npm run build
cd frontend; npx playwright install chromium; npm run test:e2e   # real browser + real API
.\VERIFY_AI_CRMS.ps1                        # everything above + dependency audits
```

CI runs all of this on every pull request (`.github/workflows/ci.yml`).

## Production

`docker compose up -d --build` (PostgreSQL, explicit migration step, API, nginx). Production mode refuses unsafe configuration — read [docs/OPERATIONS.md](docs/OPERATIONS.md) first.

Release archives: `python scripts/package_release.py` (git-tracked files only; fails on secrets, databases, caches).

## Documentation

| Document | Contents |
|---|---|
| [docs/AUDIT_REMEDIATION.md](docs/AUDIT_REMEDIATION.md) | Item-by-item response to the project audit, with evidence |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, controls, residual risks |
| [docs/MODEL_CARD.md](docs/MODEL_CARD.md) | AI model scope, evaluation, limitations |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Deployment, migrations, backup/restore, key rotation, monitoring, incident response |
| [TESTING_STRATEGY.md](TESTING_STRATEGY.md) | Test layers and coverage |
| [VERIFICATION_STATUS.md](VERIFICATION_STATUS.md) | Latest verified results |
| [ML_IMPLEMENTATION_NOTES.md](ML_IMPLEMENTATION_NOTES.md), [backend/DATABASE_SCHEMA_AUDIT.md](backend/DATABASE_SCHEMA_AUDIT.md) | Earlier design notes |
