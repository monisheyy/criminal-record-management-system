# AI-CRMS Verification Status

Last verified: 2 October 2026, Windows 11, Python 3.13, Node 24, on branch `audit-remediation`.

## Results

| Check | Command | Result |
|---|---|---|
| Backend tests (fresh virtualenv from `requirements-dev.txt`) | `cd backend; pytest -q` | **213 passed** |
| Python dependency vulnerabilities | `pip-audit -r requirements-dev.txt` | **No known vulnerabilities** (19 found and fixed during remediation) |
| Migrations | `alembic upgrade head` → `downgrade base` → `upgrade head` → `alembic check` | Pass, no model/migration drift |
| Existing database upgrade | migrated a copy of the project's `acrms.db` | Pass: data intact, confidences normalised, 8 legacy reviews preserved, all endpoints 200 |
| Frontend lint | `npm run lint` | 0 errors (remaining warnings are the standard fetch-in-effect pattern) |
| Frontend unit/contract tests | `npm test` | **19 passed** |
| Frontend production build | `npm run build` | Pass (initial bundle 340 KB, was 661 KB) |
| npm dependency vulnerabilities | `npm audit` | **0 vulnerabilities** |
| End-to-end (real browser + real API) | `PW_CHANNEL=msedge npm run test:e2e` | **6 passed** |
| Release hygiene | `python scripts/package_release.py --check` | Pass |

## Not verified here

* **Docker images / `docker compose`** — Docker is not installed in this environment; the Dockerfiles, nginx config and compose file are written but have not been built or run.
* **GitHub Actions CI** — the workflow runs once the branch is pushed to GitHub.
* **PostgreSQL** — the code, driver, migrations and audit triggers support it, but the test suite ran on SQLite.
* **Manual accessibility audit** with a screen reader.

## Reproduce

```powershell
.\VERIFY_AI_CRMS.ps1          # dependencies, audits, backend tests, migrations, lint, unit tests, build, hygiene
cd frontend; npm run test:e2e # add $env:PW_CHANNEL='msedge' to use the installed Edge instead of downloading Chromium
```

## Model caveat

The ML evaluation uses synthetic demonstration data and is not evidence of real-world validity. Production configuration disables synthetic models. See [docs/MODEL_CARD.md](docs/MODEL_CARD.md).
