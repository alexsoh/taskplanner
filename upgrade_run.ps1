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

try {
    Write-Step "Stopping TaskPlanner service..."
    Run-Ext -NoThrow { & $Python service.py stop 2>$null }

    # Wait for service to stop
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

    # Try to release file locks
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
    Write-Ok "Service stopped"

    Write-Step "Backing up current source..."
    $excludes = @("python", "venv", "node_modules", "logs", "settings.json", ".git", "backups", "taskplanner_backup_*", "taskplanner_upgrade_tmp")
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

    Write-Step "Reinstalling Python dependencies..."
    $reqFile = Join-Path $AppDir "requirements.txt"
    if (Test-Path $reqFile) {
        Run-Ext { & $Python -m pip install --quiet -r $reqFile }
        Write-Ok "Dependencies installed"
    }

    Write-Step "Starting TaskPlanner service..."
    Run-Ext -NoThrow { & $Python service.py start 2>$null }
    Write-Ok "Service started"

    Write-Step "Health check..."
    $maxRetry = 30
    for ($i = 0; $i -lt $maxRetry; $i++) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8200/api/health" -ErrorAction SilentlyContinue
            if ($response.StatusCode -eq 200) {
                Write-Ok "Application is responding"
                break
            }
        } catch {}
        if ($i -lt $maxRetry - 1) { Start-Sleep -Seconds 1 }
    }

    Write-Host ""
    Write-Host "=== Upgrade completed successfully ===" -ForegroundColor Green
    Write-Ok "New version is live at http://localhost:8200"
    Write-Ok "Backup: $backupDir"

} catch {
    Write-Fail "Upgrade failed: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "Attempting to restore from backup..." -ForegroundColor Yellow
    
    if (Test-Path $backupDir) {
        Write-Step "Restoring backup..."
        foreach ($item in (Get-ChildItem -Path $backupDir)) {
            $dest = Join-Path $AppDir $item.Name
            if (Test-Path $dest) { Remove-Item -Path $dest -Recurse -Force -ErrorAction SilentlyContinue }
            Copy-Item -Path $item.FullName -Destination $dest -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-Ok "Backup restored"
        
        Write-Step "Restarting service..."
        Run-Ext -NoThrow { & $Python service.py start 2>$null }
        Write-Ok "Service restarted"
    }
    
    exit 1
}
