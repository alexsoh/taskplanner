<#
.SYNOPSIS
    Build a compiled release of TaskPlanner for Windows.
    Compiles tp/ into a native .pyd via Nuitka, builds the frontend,
    and assembles a distributable zip with no source code.

.DESCRIPTION
    Prerequisites (build machine only):
      - Python 3.11 with pip
      - C compiler (MSVC via Visual Studio Build Tools, or MinGW)
      - Node.js 18+ and npm

.EXAMPLE
    .\build_release.ps1
#>

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "    $msg" -ForegroundColor Red }

# Native commands (npm, node) may write warnings to stderr; with $ErrorActionPreference
# Stop that aborts the script even when exit code is 0. Check $LASTEXITCODE instead.
function Run-Ext([scriptblock]$sb, [switch]$NoThrow) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $sb } finally { $ErrorActionPreference = $saved }
    if (-not $NoThrow -and $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "Command failed (exit code $LASTEXITCODE)"
    }
}

# ---------- detect platform ----------
$arch = if ([Environment]::Is64BitOperatingSystem) { "x64" } else { "x86" }

$Python = if (Test-Path (Join-Path $AppDir "python\python.exe")) {
    Join-Path $AppDir "python\python.exe"
} elseif (Test-Path (Join-Path $AppDir "venv\Scripts\python.exe")) {
    Join-Path $AppDir "venv\Scripts\python.exe"
} else { "python" }

$version = & $Python -c "from tp import __version__; print(__version__)"
$releaseName = "taskplanner-$version-windows-$arch"

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  TaskPlanner Release Builder" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Version:  $version"
Write-Host "  Platform: windows-$arch"
Write-Host "  Python:   $(& $Python --version 2>&1)"
Write-Host ""

# ---------- 1. build frontend ----------
Write-Step "[1/3] Building frontend..."
Push-Location frontend
if (-not (Test-Path "node_modules")) {
    Run-Ext { & npm install --silent *> $null }
}
Run-Ext { & npm run build --silent *> $null }
Pop-Location
Write-Ok "Frontend built to static/"

# ---------- 2. compile backend ----------
Write-Step "[2/3] Compiling backend with Nuitka..."
& $Python -m pip install --quiet nuitka ordered-set
& $Python -m nuitka --module tp --include-package=tp --assume-yes-for-downloads
Write-Ok "Backend compiled"

# ---------- 3. assemble release ----------
Write-Step "[3/3] Assembling release..."
$releaseDir = Join-Path "release" $releaseName
if (Test-Path $releaseDir) { Remove-Item -Recurse -Force $releaseDir }
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null

Copy-Item "tp.*.pyd" $releaseDir\
Copy-Item -Recurse "static" (Join-Path $releaseDir "static")
Copy-Item "requirements.txt" $releaseDir\

$scriptFiles = @(
    "serve.sh", "serve.ps1", "upgrade.sh", "upgrade.ps1", "upgrade_run.sh", "upgrade_run.ps1", "setup.sh", "setup.ps1", "README.md"
)
foreach ($f in $scriptFiles) {
    if (Test-Path $f) {
        Copy-Item $f $releaseDir\
    }
}

Set-Content (Join-Path $releaseDir "version.txt") $version -NoNewline
Write-Ok "Release assembled in $releaseDir"

# ---------- 4. zip ----------
Write-Step "[4/4] Creating zip..."
$zipPath = Join-Path "release" "$releaseName.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path $releaseDir -DestinationPath $zipPath -Force

$zipSize = "{0:N1} MB" -f ((Get-Item $zipPath).Length / 1MB)
Write-Ok "$zipPath ($zipSize)"

# ---------- cleanup nuitka build artifacts ----------
Remove-Item -Recurse -Force "tp.build" -ErrorAction SilentlyContinue
Remove-Item "tp.*.pyd" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "  Build complete!" -ForegroundColor Green
Write-Host "  $zipPath" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
