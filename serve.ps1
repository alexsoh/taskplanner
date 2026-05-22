<#
.SYNOPSIS
    TaskPlanner development server on Windows.

.PARAMETER Port
    TCP port (default 8200).

.PARAMETER SkipBuild
    Skip frontend npm build.

.EXAMPLE
    .\serve.ps1
    .\serve.ps1 -Port 8200
    .\serve.ps1 -SkipBuild
#>
param(
    [int]$Port = 8200,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

$Python = Join-Path $AppDir "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = Join-Path $AppDir "python\python.exe"
}
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: Python not found. Run .\setup.ps1 or setup.bat first." -ForegroundColor Red
    exit 1
}

if (-not $SkipBuild) {
    $staticIndex = Join-Path $AppDir "static\index.html"
    if (-not (Test-Path (Join-Path $AppDir "frontend"))) {
        if (-not (Test-Path $staticIndex)) {
            Write-Host "ERROR: frontend/ not found and no pre-built static/. Use -SkipBuild." -ForegroundColor Red
            exit 1
        }
        Write-Host "Using pre-built static/ (no frontend/)" -ForegroundColor Yellow
    } else {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
        if (-not $npm) {
            Write-Host "ERROR: npm not found. Install Node.js or use -SkipBuild." -ForegroundColor Red
            exit 1
        }
        Write-Host "Building frontend..." -ForegroundColor Cyan
        Push-Location (Join-Path $AppDir "frontend")
        & npm install --silent 2>&1 | Out-Null
        & npm run build --silent 2>&1 | Out-Null
        Pop-Location
        Write-Host "Frontend build complete." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Starting TaskPlanner on http://localhost:$Port" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop"
Write-Host ""

& $Python -m uvicorn tp.main:app --host 0.0.0.0 --port $Port --reload
