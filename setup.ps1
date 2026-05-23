<#
.SYNOPSIS
    Sets up a portable Python environment for TaskPlanner on Windows.
    No system-wide Python installation required.

.PARAMETER PythonVersion
    Python version to install. Default: 3.11.9

.PARAMETER SkipFrontend
    Skip the frontend build step (uses pre-built static/ from the repo).

.EXAMPLE
    .\setup.ps1
    .\setup.ps1 -SkipFrontend
#>
param(
    [string]$PythonVersion = "3.11.9",
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

$PythonDir = Join-Path $AppDir "python"
$PythonExe = Join-Path $PythonDir "python.exe"

$MajorMinor = ($PythonVersion -split '\.')[0..1] -join ''
$PthFile = Join-Path $PythonDir "python${MajorMinor}._pth"

$EmbedUrl = "https://www.python.org/ftp/python/${PythonVersion}/python-${PythonVersion}-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "    $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TaskPlanner Setup (Portable Python) " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# --- Step 1: Download embedded Python ---
Write-Step "Downloading Python ${PythonVersion} embeddable package..."

if (Test-Path $PythonExe) {
    Write-Ok "Portable Python already exists at $PythonDir -- skipping download"
} else {
    $zipPath = Join-Path $AppDir "python-embed.zip"

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $EmbedUrl -OutFile $zipPath -UseBasicParsing
        Write-Ok "Downloaded python-${PythonVersion}-embed-amd64.zip"
    } catch {
        Write-Fail "Download failed: $_"
        Write-Host "You can manually download from: $EmbedUrl"
        exit 1
    }

    Write-Step "Extracting to $PythonDir..."
    if (Test-Path $PythonDir) { Remove-Item $PythonDir -Recurse -Force }
    Expand-Archive -Path $zipPath -DestinationPath $PythonDir -Force
    Remove-Item $zipPath -Force
    Write-Ok "Extracted"
}

# --- Step 2: Enable pip by patching ._pth file ---
Write-Step "Enabling pip support..."

if (Test-Path $PthFile) {
    $content = Get-Content $PthFile -Raw
    if ($content -match '#import site') {
        $content = $content -replace '#import site', 'import site'
        Set-Content -Path $PthFile -Value $content -NoNewline
        Write-Ok "Patched $PthFile (uncommented 'import site')"
    } else {
        Write-Ok "Already patched"
    }
} else {
    Write-Fail "Could not find $PthFile -- Python version mismatch?"
    exit 1
}

# --- Step 3: Bootstrap pip ---
Write-Step "Bootstrapping pip..."

$PipExe = Join-Path $PythonDir "Scripts\pip.exe"
if (Test-Path $PipExe) {
    Write-Ok "pip already installed -- skipping"
} else {
    $getPipPath = Join-Path $AppDir "get-pip.py"
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $GetPipUrl -OutFile $getPipPath -UseBasicParsing
        & $PythonExe $getPipPath --no-warn-script-location 2>&1 | Out-Null
        Remove-Item $getPipPath -Force -ErrorAction SilentlyContinue
        Write-Ok "pip installed"
    } catch {
        Write-Fail "pip bootstrap failed: $_"
        exit 1
    }
}

# --- Step 4: Install Python dependencies ---
Write-Step "Installing Python dependencies..."
& $PythonExe -m pip install --no-warn-script-location -q -r (Join-Path $AppDir "requirements.txt") 2>&1 | ForEach-Object { Write-Host "    $_" }
Write-Ok "Dependencies installed"

# --- Step 5: Build frontend ---
$staticDir = Join-Path $AppDir "static"
if ($SkipFrontend) {
    Write-Step "Skipping frontend build (-SkipFrontend)"
} elseif (Test-Path (Join-Path $staticDir "index.html")) {
    Write-Step "Frontend already pre-built in static/ -- skipping"
    Write-Ok "Using existing static/ folder"
} else {
    Write-Step "Building frontend..."

    $npmPath = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmPath) {
        Write-Fail "npm not found and no pre-built frontend in static/"
        Write-Host "    Install Node.js 18+ from https://nodejs.org and re-run,"
        Write-Host "    or re-run with -SkipFrontend to skip."
        exit 1
    }

    Set-Location (Join-Path $AppDir "frontend")
    & npm install --silent 2>&1 | Out-Null
    & npm run build --silent 2>&1 | Out-Null
    Set-Location $AppDir
    Write-Ok "Frontend built to static/"
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup complete!                       " -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Python: $PythonExe"
Write-Host ""
Write-Host "  To start TaskPlanner:"
Write-Host "    .\serve.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To install as a Windows service:"
Write-Host "    .\install_service.bat  (run as Administrator)" -ForegroundColor Yellow
Write-Host ""
