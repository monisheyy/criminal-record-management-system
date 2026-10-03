$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPath = Join-Path $ProjectRoot 'backend'
$FrontendPath = Join-Path $ProjectRoot 'frontend'

Write-Host 'AI-CRMS verification: dependencies, audits, tests, migrations, lint and production build.' -ForegroundColor Cyan
Write-Host 'Run inside the project virtual environment (backend\.venv).'

function Step($label, [scriptblock]$action) {
    Write-Host "`n$label" -ForegroundColor Yellow
    & $action
    if ($LASTEXITCODE -ne 0) { throw "$label failed (exit $LASTEXITCODE)." }
}

Push-Location $BackendPath
try {
    Step '[1/8] Installing backend dependencies' { python -m pip install -r requirements-dev.txt }
    Step '[2/8] Auditing Python dependencies for known vulnerabilities' { python -m pip_audit -r requirements-dev.txt }
    Step '[3/8] Running backend tests' { python -m pytest -q }
    $env:DATABASE_URL = 'sqlite:///./verify-migrations.db'
    if (-not $env:SECRET_KEY) { $env:SECRET_KEY = 'verify-script-only-secret-key-0123456789abcdef' }
    try {
        Step '[4/8] Checking migrations (upgrade, downgrade, drift)' {
            python -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { return }
            python -m alembic downgrade base; if ($LASTEXITCODE -ne 0) { return }
            python -m alembic upgrade head; if ($LASTEXITCODE -ne 0) { return }
            python -m alembic check
        }
    } finally {
        Remove-Item Env:DATABASE_URL
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $BackendPath 'verify-migrations.db')
    }
} finally { Pop-Location }

Push-Location $FrontendPath
try {
    Step '[5/8] Installing frontend dependencies from package-lock.json' { npm ci }
    Step '[6/8] Auditing npm dependencies' { npm audit --audit-level=high }
    Step '[7/8] Lint and unit/contract tests' { npm run lint; if ($LASTEXITCODE -eq 0) { npm test } }
    Step '[8/8] Production build' { npm run build }
} finally { Pop-Location }

Step 'Release hygiene scan' { python (Join-Path $ProjectRoot 'scripts\package_release.py') --check }

Write-Host "`nAll checks passed. End-to-end tests: cd frontend; npm run test:e2e" -ForegroundColor Green
