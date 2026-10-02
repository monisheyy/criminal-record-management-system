$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendPath = Join-Path $ProjectRoot 'backend'
$FrontendPath = Join-Path $ProjectRoot 'frontend'

Write-Host 'AI-CRMS verification: dependency installation, backend tests, frontend tests, and production build.' -ForegroundColor Cyan
Write-Host 'Use a project virtual environment before running this script.'

Push-Location $ProjectRoot
try {
    Write-Host "`n[1/5] Installing backend dependencies..." -ForegroundColor Yellow
    python -m pip install -r (Join-Path $BackendPath 'requirements.txt')

    Write-Host "`n[2/5] Checking backend Python syntax..." -ForegroundColor Yellow
    python -m compileall -q $BackendPath
    if ($LASTEXITCODE -ne 0) { throw 'Backend Python compilation failed.' }

    Write-Host "`n[3/5] Running backend tests..." -ForegroundColor Yellow
    python -m pytest $BackendPath -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }

    Push-Location $FrontendPath
    try {
        Write-Host "`n[4/5] Installing frontend dependencies from package-lock.json..." -ForegroundColor Yellow
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }

        Write-Host "`n[5/5] Running frontend tests and production build..." -ForegroundColor Yellow
        npm test
        if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed.' }
    }
    finally {
        Pop-Location
    }

    Write-Host "`nAll verification steps passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
