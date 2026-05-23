<#
.SYNOPSIS
    Performs the actual TaskPlanner upgrade. Called by upgrade.ps1 after it has
    downloaded and extracted the new package. Do not run this directly.

.PARAMETER AppDir
    Path to the live TaskPlanner installation directory.

.PARAMETER SourcePath
    Path to the folder containing the new source files (extracted package).
#>
param(
    [string][Parameter(Mandatory)]$AppDir,
    [string][Parameter(Mandatory)]$SourcePath
)

$ErrorActionPreference = "Stop"
Set-Location $AppDir

$timestamp = Get-Date -Format "yyyyMMdd_HHmm"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "    $msg" -ForegroundColor Red }

function Run-Ext([scriptblock]$sb, [switch]$NoThrow) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $sb } finally { $ErrorActionPreference = $saved }
    if (-not $NoThrow -and $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "Command failed (exit code $LASTEXITCODE)"
    }
}

$Python = if (Test-Path (Join-Path $AppDir "python\python.exe")) {
    Join-Path $AppDir "python\python.exe"
} elseif (Test-Path (Join-Path $AppDir "venv\Scripts\python.exe")) {
    Join-Path $AppDir "venv\Scripts\python.exe"
} else { "python" }

$versionFile = Join-Path $AppDir "version.txt"
$curVersion = if (Test-Path $versionFile) { (Get-Content $versionFile).Trim() } else { "unknown" }
$backupDir = Join-Path $AppDir "backups\v${curVersion}_${timestamp}"

$Port = 8200
try {
    $portOut = & $Python -c "from tp.db import SessionLocal; from tp.settings_store import get_server_port; db=SessionLocal(); print(get_server_port(db)); db.close()" 2>$null
    if ($LASTEXITCODE -eq 0 -and $portOut) {
        $Port = [int]($portOut.ToString().Trim())
    }
} catch {
    # keep default
}

$excludes = @(
    "python", "venv", "node_modules", "logs", "data", ".git", "backups",
    "taskplanner_backup_*", "taskplanner_upgrade_tmp"
)

try {
    Write-Step "Stopping TaskPlanner service..."
    Run-Ext -NoThrow { & $Python service.py stop 2>$null }

    $svcName = "TaskPlanner"
    $maxWait = 30
    for ($i = 0; $i -lt $maxWait; $i++) {
        try {
            $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
            if (-not $svc -or $svc.Status -eq 'Stopped') { break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    Start-Sleep -Seconds 2

    $pydFile = Get-ChildItem -Path $AppDir -Filter "tp.*.pyd" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pydFile) {
        try {
            [IO.File]::Open($pydFile.FullName, 'Open', 'Read', 'Read').Close()
        } catch {
            Write-Fail "File still locked: $($pydFile.Name) -- attempting force kill"
            Get-Process python*, pythonw* -ErrorAction SilentlyContinue |
                Where-Object { $_.Path -and $_.Path.StartsWith($AppDir) } |
                ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 3
        }
    }
    Write-Ok "Service stopped (using $Python)"

    Write-Step "Backing up current source to $backupDir..."
    $items = Get-ChildItem -Path $AppDir -Exclude $excludes -ErrorAction SilentlyContinue
    New-Item -Path $backupDir -ItemType Directory -Force | Out-Null
    foreach ($item in $items) {
        Copy-Item -Path $item.FullName -Destination (Join-Path $backupDir $item.Name) -Recurse -Force -ErrorAction SilentlyContinue
    }
    Write-Ok "Backup created: $backupDir"

    Write-Step "Copying new files from $SourcePath..."
    foreach ($item in (Get-ChildItem -Path $SourcePath)) {
        if ($excludes -contains $item.Name) { continue }
        $dest = Join-Path $AppDir $item.Name
        if (Test-Path $dest) { Remove-Item -Path $dest -Recurse -Force }
        Copy-Item -Path $item.FullName -Destination $dest -Recurse -Force
    }
    Write-Ok "Files updated"

    $reqFile = Join-Path $AppDir "requirements.txt"
    if (Test-Path $reqFile) {
        $reqHash = (Get-FileHash -Path $reqFile -Algorithm MD5).Hash
        $hashFile = Join-Path $AppDir ".req_hash"
        $storedHash = if (Test-Path $hashFile) { (Get-Content $hashFile).Trim() } else { "" }

        if ($reqHash -eq $storedHash) {
            Write-Ok "Python dependencies unchanged, skipping install"
        } else {
            Write-Step "Reinstalling Python dependencies..."
            Run-Ext { & $Python -m pip install --no-warn-script-location -q -r $reqFile }
            Set-Content -Path $hashFile -Value $reqHash -NoNewline
            Write-Ok "Dependencies installed"
        }
    }

    $frontendDir = Join-Path $AppDir "frontend"
    $staticIndex = Join-Path $AppDir "static\index.html"
    $npmPath = Get-Command npm -ErrorAction SilentlyContinue
    if (-not (Test-Path $frontendDir)) {
        Write-Step "Pre-built release -- using existing static/"
        Write-Ok "Skipped frontend build (compiled release)"
    } elseif ($npmPath) {
        Write-Step "Rebuilding frontend..."
        Set-Location $frontendDir
        Run-Ext { & npm install --silent }
        Run-Ext { & npm run build --silent }
        Set-Location $AppDir
        Write-Ok "Frontend rebuilt"
    } elseif (Test-Path $staticIndex) {
        Write-Step "Frontend already pre-built in static/ -- skipping (npm not found)"
    } else {
        Write-Fail "No pre-built frontend and npm not found. Install Node.js 18+ to rebuild."
        throw "Frontend build required but npm not available"
    }

    Write-Step "Updating service registration..."
    Run-Ext -NoThrow { & $Python service.py update 2>$null }
    Write-Ok "Service registration updated"

    Write-Step "Starting TaskPlanner service..."
    Run-Ext { & $Python service.py start }
    Start-Sleep -Seconds 3
    Write-Ok "Service started"

    Run-Ext -NoThrow { sc.exe failure TaskPlanner reset= 86400 actions= restart/10000/restart/30000/restart/60000 } | Out-Null
    Write-Ok "Auto-restart on crash: enabled (10s / 30s / 60s backoff)"

    Write-Step "Verifying service..."
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 10
        if ($response.StatusCode -eq 200) {
            Write-Ok "Service is running and healthy"
        }
    } catch {
        Write-Fail "Service health check failed, but it may still be starting up"
    }

    Write-Host ""
    Write-Host "=== Upgrade completed successfully ===" -ForegroundColor Green
    Write-Ok "New version is live at http://localhost:$Port"
    Write-Ok "Backup: $backupDir"

} catch {
    Write-Fail "Upgrade failed: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "Attempting to restore from backup..." -ForegroundColor Yellow

    try {
        Run-Ext -NoThrow { & $Python service.py stop 2>$null }
        if (Test-Path $backupDir) {
            Write-Step "Restoring backup..."
            foreach ($item in (Get-ChildItem -Path $backupDir)) {
                $dest = Join-Path $AppDir $item.Name
                if (Test-Path $dest) { Remove-Item -Path $dest -Recurse -Force -ErrorAction SilentlyContinue }
                Copy-Item -Path $item.FullName -Destination $dest -Recurse -Force -ErrorAction SilentlyContinue
            }
            Write-Ok "Backup restored"
        }
        Run-Ext -NoThrow { & $Python service.py start 2>$null }
        Write-Ok "Previous version restarted"
    } catch {
        Write-Fail "Rollback also failed. Check backup and logs."
        Write-Host "Manual intervention required. Backup at: $backupDir"
    }
    exit 1
}
