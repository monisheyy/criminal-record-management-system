# AI-CRMS Testing Strategy

Tests target business behaviour, authorization boundaries, data integrity, AI governance and real browser workflows — not just "the app starts".

## Layers

| Layer | Location | Runs | What it proves |
|---|---|---|---|
| Backend unit/API/integration | `backend/tests/` (pytest, in-memory DB built by the real Alembic migrations) | `cd backend && pytest -q` | API contracts, validation, authorization, transactions, ML metrics |
| Migrations | `test_integrity_and_operations.py` + CI `alembic upgrade/downgrade/check` | pytest, CI | Schema history applies, rolls back, matches models; legacy DBs are adopted |
| Frontend unit & contract | `frontend/tests/*.test.mjs` (node:test) | `npm test` | Formatting/error helpers; screens use API field names and enums |
| End-to-end | `frontend/tests/e2e/` (Playwright, real API + throw-away DB) | `npm run test:e2e` | Cookie sessions, forced password change, case workflow, role restrictions, AI review, audit verification |
| Static & supply chain | oxlint, `pip-audit`, `npm audit`, release-hygiene scan | CI / `VERIFY_AI_CRMS.ps1` | Code quality, known vulnerabilities, no secrets in the repository |

## Backend coverage by area

* **Authentication & sessions** (`test_security_hardening.py`): lockout and unlock, identical errors for unknown users, logout revocation, forced password change, session invalidation on role change, HttpOnly/SameSite cookie, CSRF header, rate limiting, production configuration guards, demo-credential disabling.
* **Authorization** (`test_authorization_matrix.py`, `test_security_rbac.py`): every protected route rejects anonymous calls (generated from the OpenAPI schema, with a guard against an empty matrix); admin-only endpoints; officer object-level access for every case endpoint incl. exports; clerk AI restrictions; per-user notification visibility.
* **Validation** (`test_input_validation.py`): malicious/invalid inputs, vocabulary normalisation, date rules, duplicates, pagination/sort limits, wildcard escaping, spreadsheet formula injection.
* **Integrity & operations** (`test_integrity_and_operations.py`): audit HMAC + tamper detection, append-only enforcement, transactional rollback, case lifecycle, chain of custody, migrations, backup/restore drill.
* **AI governance** (`test_ai_governance.py`, `test_ml_pipeline.py`): advisory notices and units, mandatory reasoned review and correction history, demo-mode gating, calibration/subgroup/quality-gate metrics, artifact tamper detection, justified/gated activation, leakage and determinism checks.
* **Workflows, reports, notifications, recovery, network** (`test_business_workflows.py`, `test_reports.py`, `test_notifications_realtime.py`, `test_password_recovery.py`, `test_intelligence_network.py`, `test_api.py`).

## Conventions

* Tests never touch `backend/acrms.db` or the active model directory (`AI_CRMS_MODEL_DIR` points to a temp dir).
* Each test creates its own users/records where state matters; session-scoped tokens belong to users no test mutates.
* A bug fix lands with a regression test.
