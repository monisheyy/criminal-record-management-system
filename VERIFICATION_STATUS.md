# AI-CRMS Verification Status

## Verified in the packaging environment

- ML pipeline unit tests: **24 passed** when run in isolation from the application-wide pytest `conftest.py`.
- Frontend critical-workflow tests: **5 passed**.
- Python syntax compilation and ML evaluation smoke test: passed in the prior implementation pass.
- ZIP archive integrity: verified after packaging.

## Still unverified

- Full backend test suite / app integration tests.
- Frontend production bundle (`vite build`).

The packaging environment has no working package-registry network access. The full backend test collection stops at `ModuleNotFoundError: No module named 'jose'` (the `python-jose` dependency), and pip cannot retrieve it. The frontend build stops at `vite: not found`; `npm ci --offline` confirms the required Vite package is not cached. These are environment dependency blockers, not evidence that the tests or build pass.

## Run full verification on Windows

1. Open PowerShell in the extracted project directory.
2. Activate the project's Python virtual environment, or create one with `python -m venv .venv` and activate it using `.\.venv\Scripts\Activate.ps1`.
3. Ensure internet/package registry access is available.
4. Run:

   ```powershell
   .\VERIFY_AI_CRMS.ps1
   ```

The script installs the backend dependencies from `backend/requirements.txt`, compiles Python files, runs backend tests, installs the frontend dependencies from `frontend/package-lock.json`, runs frontend tests, and builds the production bundle. Review any application-specific test failures rather than treating dependency installation alone as verification.

## Important model caveat

The current ML evaluation uses synthetic/demo data and is not evidence of real-world validity. Do not use its outputs to make or justify real-world criminal-justice decisions. Train and validate against lawfully obtained, representative, quality-controlled data and require appropriate human review before any operational use.
