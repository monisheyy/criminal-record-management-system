# AI-CRMS Automated Testing Strategy

## Scope

The suite targets business behavior, persistence, authorization boundaries, ML outputs, reporting artifacts, notification behavior, and critical frontend workflow contracts. It is intentionally not a startup-only smoke suite.

## Backend

Run from `backend/`:

```bash
pip install -r requirements.txt
pytest -q
```

Coverage areas:

- Authentication: valid/invalid login, unauthenticated access, expired/malformed JWTs, token-type enforcement, RBAC.
- Criminals: CRUD, search, duplicate detection, history, authorization.
- Cases: creation, assignment, criminal linkage, victims, evidence, status/update, report generation, object-level officer access.
- AI: prediction persistence, confidence/probability bounds, risk bounds, review/override, retraining authorization, model metadata.
- Notifications: persistence, visibility, unread filtering, acknowledgement, realtime targeting.
- Reporting: PDF validity and XLSX structure/value validation.
- Security: IDOR/RBAC checks and recovery-token/OTP behavior.

## Frontend

Run from `frontend/`:

```bash
npm test
npm run build
```

`npm test` uses Node's built-in test runner and validates critical workflow contracts without adding a runtime dependency. It verifies that routing, API service calls, and required UI actions remain wired together.

For a full browser-level test stage in CI, add Playwright or Cypress and exercise the same workflows against a test API/database.

## CI recommendation

1. Install backend dependencies.
2. Run `pytest -q`.
3. Install frontend dependencies with `npm ci`.
4. Run `npm test`.
5. Run `npm run build`.
6. Publish coverage with `pytest-cov` once the project CI environment permits installing the plugin.
7. Run browser E2E tests against isolated test data.

## Important findings fixed during this QA pass

- JWTs without the required `type=access` claim were previously accepted. Authentication now requires the access-token type.
- Case-to-criminal linking previously did not verify that the criminal existed. The API now returns 404 instead of creating an invalid relationship.
- Case update linkage now validates all referenced criminals before changing existing links.
- Investigating officers could request an AI assessment for an arbitrary criminal ID even though prediction access was otherwise object-scoped. The prediction endpoint now requires the criminal to be connected to a case assigned to that officer.
- XLSX report generation left an empty row above the header because of openpyxl's default worksheet row. The exporter now removes that blank row.
- Existing report tests were aligned to the actual workbook contract after artifact-level inspection.

## Environment limitation

The current execution environment is missing `python-jose`, and network access is unavailable for installing it. Consequently, the full FastAPI integration suite could not be executed here. ML and report suites were executed independently and passed. Frontend workflow-contract tests were executed and passed.


## ML feature-contract and evaluation regression checks

From the `backend` directory, after installing `requirements.txt`:

```bash
python -m app.ml.evaluate_dataset --output ml_evaluation_report.json
pytest -q tests/test_ml_pipeline.py
pytest -q
```

The evaluation command trains in memory and does not overwrite active artifacts. It reports class distributions, majority-class baselines, balanced accuracy, macro and weighted metrics, predicted class counts, zero-recall classes, and release-readiness limitations. The bundled dataset is synthetic and is never operational-release eligible.

Regression checks must verify that:
- The gang classifier feature list excludes `is_gang_member`, which leaks target membership status.
- Legacy gang artifacts with the old feature count are disabled at inference.
- Candidate activation rejects mismatched pipeline versions and feature schemas.
- Prediction responses report observed, derived, and defaulted input fields.
- Case incident hour is derived only from the recorded `incident_date`, not the crime target.
- Candidate training does not overwrite active model artifacts.

The project may need `python-jose` and other dependencies installed in the virtual environment before the full backend test suite can collect. If installation is blocked, record that as an environment limitation rather than treating the suite as passed.
