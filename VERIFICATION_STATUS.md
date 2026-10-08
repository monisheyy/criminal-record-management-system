# AI-CRMS Verification Status

Last verified: 8 October 2026, Linux, Python 3.13, Node 22, on branch `claude/project-thread-s6xque` (earlier run: 2 October 2026, Windows 11, branch `audit-remediation`).

## Results

| Check | Command | Result |
|---|---|---|
| Backend tests (fresh virtualenv from `requirements-dev.txt`) | `cd backend; pytest -q` | **274 passed** (87% line coverage; gangs 100%, admin 97%, notifications 99%, AI predictions 77%) |
| Python dependency vulnerabilities | `pip-audit -r requirements-dev.txt` | **No known vulnerabilities** (19 found and fixed during remediation) |
| Migrations | `alembic upgrade head` → `downgrade base` → `upgrade head` → `alembic check` | Pass, no model/migration drift |
| Existing database upgrade | migrated a copy of the project's `acrms.db` | Pass: data intact, confidences normalised, 8 legacy reviews preserved, all endpoints 200 |
| Frontend lint | `npm run lint` | **0 errors, 0 warnings** (screens load data through `useApiQuery`) |
| Frontend unit/contract tests | `npm test` | **19 passed** |
| Frontend production build | `npm run build` | Pass (initial bundle 340 KB, was 661 KB) |
| npm dependency vulnerabilities | `npm audit` | **0 vulnerabilities** |
| End-to-end (real browser + real API) | `PW_CHANNEL=msedge npm run test:e2e` | **7 passed** (includes incident map and offender photo upload) |
| Docker stack | `docker compose up -d --build` | **All four services healthy**: PostgreSQL, migrate (exit 0), API (2 workers), nginx serving the app on :8080 and `/api/health/ready` = ready |
| Release hygiene | `python scripts/package_release.py --check` | Pass |

## Not verified here

* **GitHub Actions CI** — the workflow runs once the branch is pushed to GitHub.
* **PostgreSQL** — migrations and start-up ran against PostgreSQL 16 in the Docker stack; the test suite itself runs on SQLite.
* **Manual accessibility audit** with a screen reader.

## Reproduce

```powershell
.\VERIFY_AI_CRMS.ps1          # dependencies, audits, backend tests, migrations, lint, unit tests, build, hygiene
cd frontend; npm run test:e2e # add $env:PW_CHANNEL='msedge' to use the installed Edge instead of downloading Chromium
```

## Model caveat

The ML evaluation uses synthetic demonstration data and is not evidence of real-world validity. Production configuration disables synthetic models. See [docs/MODEL_CARD.md](docs/MODEL_CARD.md).
