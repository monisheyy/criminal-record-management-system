# Operations runbook

## 1. Configuration

All settings come from environment variables (see [`.env.example`](../.env.example)) and are validated at start-up by `backend/app/config.py`. With `APP_ENV=production` the API **refuses to start** unless:

| Setting | Production requirement |
|---|---|
| `SECRET_KEY` | ≥ 32 random characters, not a placeholder. Store in a secret manager, never in the image. |
| `CORS_ORIGINS` | Explicit `https://` origins only |
| `TRUSTED_HOSTS` | The public host name(s) |
| `COOKIE_SECURE` | `true` (HTTPS only) |
| `SEED_DEMO_DATA` | `false` |
| `RECOVERY_PROVIDER` | `smtp` (the `dev` provider logs one-time codes) |
| `AI_ALLOW_SYNTHETIC_MODELS` | `false` — demo-trained models cannot run |

API docs (`/docs`) are disabled in production unless `ENABLE_API_DOCS=true`.

The browser must reach the frontend and API on the **same site** (e.g. both behind `https://crms.example.gov`, as the bundled nginx does) for the SameSite session cookie to work. In local development use `localhost` for both (not `127.0.0.1` for one and `localhost` for the other).

## 2. Deployment

```bash
cp .env.example .env              # set SECRET_KEY, POSTGRES_PASSWORD, CORS_ORIGINS, TRUSTED_HOSTS ...
docker compose up -d --build      # db -> migrate (alembic upgrade head) -> backend -> frontend
```

* Terminate TLS in front of the `frontend` container (load balancer / ingress) and keep HSTS on.
* Health: liveness `GET /api/health`, readiness `GET /api/health/ready` (database reachable + schema at head).
* Without Docker: `pip install -r backend/requirements.txt`, `alembic upgrade head`, then
  `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers 2` (never `--reload` in production); `npm ci && npm run build` and serve `frontend/dist` with `frontend/nginx.conf`.

## 3. Database migrations

* Create: `cd backend && alembic revision --autogenerate -m "describe change"` — **review the generated file**.
* Test: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check` (CI does this).
* Deploy: **back up first** (§4), then `alembic upgrade head`; then start the new API version.
* Development/test start-up applies migrations automatically and adopts pre-Alembic databases.
* SQLite caveat: batch alterations recreate tables and drop the append-only triggers on `audit_logs` / `ai_prediction_reviews`; recreate them in the same migration (see `0002`).

## 4. Backup and restore

**SQLite** (`backend/scripts/backup_db.py`, safe while the API runs):

```bash
cd backend
python -m scripts.backup_db backup --db acrms.db --out /secure/backups   # online backup + integrity check + .sha256
python -m scripts.backup_db verify /secure/backups/acrms-<stamp>.db
# restore: stop the API first
python -m scripts.backup_db restore /secure/backups/acrms-<stamp>.db --db acrms.db --yes
```

Restore verifies checksum and integrity first and keeps a `*.pre-restore-*.db` safety copy.

**PostgreSQL:** `pg_dump -Fc crms > crms-<stamp>.dump`; restore with `pg_restore --clean -d crms crms-<stamp>.dump`.

**Policy to agree locally** (recommended starting point): daily backups retained 35 days + monthly retained 1 year, encrypted, stored off-host; RPO ≤ 24 h, RTO ≤ 4 h; quarterly restore drill into a scratch environment followed by `GET /api/health/ready` and `GET /api/admin/audit-logs/verify`. Also back up `AI_CRMS_MODEL_DIR` (active + candidate model artifacts).

## 5. Secret rotation

`SECRET_KEY` signs session tokens, audit-entry HMACs, OTP hashes and ML artifact signatures. After rotating it:

1. All users are signed out (expected).
2. Audit entries written before rotation report as *tampered* in verification — record the rotation time and verify historical entries with the previous key archived in your secret manager.
3. The active model fails its signature check and predictions return 503 until an admin trains a candidate and activates it (or you re-sign artifacts with the old key retired).

## 6. Dependency updates

1. Dependabot opens weekly PRs (`.github/dependabot.yml`).
2. CI must pass: tests, `pip-audit`, `npm audit --audit-level=high`, build, E2E.
3. For a security advisory outside the weekly cycle: bump the pin in `requirements*.txt` / `package.json`, run the full suite locally (`VERIFY_AI_CRMS.ps1`), merge, redeploy.

## 7. Monitoring

* Logs: set `LOG_JSON=true`; each line has `request_id`, route template, status and latency — never query strings or record content.
* Metrics: `GET /api/admin/metrics` (admin) — per-route request counts, 5xx counts, average/max latency (per worker process). Scrape into your monitoring system or front the API with an OpenTelemetry collector.
* Alert on: readiness failures, 5xx rate, `USER_LOGIN_BLOCKED` / `USER_LOGIN_FAILED` spikes, `AUDIT_LOG_VERIFIED` with status `failure`, AI status `artifact_integrity != verified`.
* Run **Audit trail → Verify integrity** on a schedule (e.g. weekly) and after any incident.

## 8. Incident response

1. **Contain:** deactivate affected accounts (sessions end immediately); if the API host is compromised, rotate `SECRET_KEY` and database credentials; set `AI_PREDICTIONS_ENABLED=false` if model artifacts are suspect.
2. **Preserve evidence:** take a backup (§4) *before* changing data; export audit logs filtered by time window / `request_id`; keep application logs.
3. **Assess:** run audit integrity verification; review `USER_LOGIN*`, `*_DELETED`, `ROLE_CHANGED`, `MODEL_*` events; correlate with log `request_id`s.
4. **Recover:** restore from the last known-good backup if data was altered; re-verify integrity and readiness.
5. **Notify:** follow your organisation's legal/regulatory breach-notification obligations for personal and criminal-justice data.
6. **Review:** record root cause and corrective actions; add a regression test.
