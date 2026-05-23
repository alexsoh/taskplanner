<#
.SYNOPSIS
    Bootstrap upgrader for TaskPlanner.
    Downloads the latest compiled release from the evalex server, then runs
    upgrade_run.ps1 from the newly downloaded package so the upgrade logic
    is always current.

.PARAMETER SourcePath
    Path to a folder containing new release files. If omitted, downloads the
    latest release from the evalex server.

.PARAMETER Token
    Evalex download token (evlx_...). Required for downloading releases.

.EXAMPLE
    .\upgrade.ps1
    .\upgrade.ps1 -Token evlx_xxxxxxxxxxxx
    .\upgrade.ps1 -SourcePath C:\new-taskplanner
#>
param(
    [string]$SourcePath  = "",
    [string]$Token       = "",
    [string]$EvalexBase  = "https://evalex.duckdns.org"
)

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

$LogDir = Join-Path $AppDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -Path $LogDir -ItemType Directory -Force | Out-Null }
$LogFile = Join-Path $LogDir "upgrade.log"
Start-Transcript -Path $LogFile -Force | Out-Null
Write-Host "=== TaskPlanner Upgrade Log: $(Get-Date) ==="

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "    $msg" -ForegroundColor Red }

$EvalexBase = $EvalexBase.TrimEnd("/")
$AppSlug    = "taskplanner"
$extractDir = Join-Path $AppDir "taskplanner_upgrade_tmp"
$runnerSource = ""

try {
    if ($SourcePath) {
        $runnerSource = $SourcePath
        Write-Ok "Using local source: $SourcePath"
    } else {
        if (-not $Token) {
            throw "Download token is required. Pass -Token evlx_..."
        }

        $platOs   = "windows"
        $platArch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" }
                    elseif ([Environment]::Is64BitOperatingSystem) { "x64" }
                    else { "x86" }

        Write-Step "Downloading release from $EvalexBase ($platOs/$platArch)..."
        $zipPath = Join-Path $AppDir "taskplanner_update.zip"
        $ProgressPreference = 'SilentlyContinue'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

        $downloadUrl = "$EvalexBase/api/download?token=$Token&app=$AppSlug&os=$platOs&arch=$platArch"
        try {
            Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath -UseBasicParsing
        } catch {
            $statusCode = $_.Exception.Response.StatusCode.value__
            if ($statusCode -eq 403) {
                throw "Download token is invalid, expired, or not authorized for this app (403)."
            } elseif ($statusCode -eq 404) {
                throw "No $platOs/$platArch release available for $AppSlug. Try again later (404)."
            } else {
                throw "Download failed (HTTP $statusCode). Check network and Evalex base URL."
            }
        }
        Write-Ok "Downloaded release zip"

        if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
        Write-Step "Extracting package..."
        Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force
        Remove-Item $zipPath -Force -ErrorAction SilentlyContinue

        $innerDir = Get-ChildItem -Path $extractDir -Directory | Select-Object -First 1
        $runnerSource = $innerDir.FullName
        Write-Ok "Extracted to $runnerSource"

        Get-ChildItem -Path $runnerSource -Recurse | Unblock-File -ErrorAction SilentlyContinue
        Write-Ok "Unblocked extracted files"
    }

    $runnerScript = Join-Path $runnerSource "upgrade_run.ps1"
    if (-not (Test-Path $runnerScript)) {
        throw "upgrade_run.ps1 not found in package at $runnerSource"
    }

    Write-Step "Running upgrade logic from new package..."
    $runArgs = @("-ExecutionPolicy", "Bypass", "-File", $runnerScript, "-AppDir", $AppDir, "-SourcePath", $runnerSource)
    powershell @runArgs
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "upgrade_run.ps1 exited with code $LASTEXITCODE"
    }

} catch {
    Write-Fail "Upgrade failed. See logs/upgrade.log."
    if ($_.Exception.Message) {
        $safe = [regex]::Replace($_.Exception.Message, '(?i)(token=)[^&\s]+', '${1}<redacted>')
        Write-Host "    $safe" -ForegroundColor Yellow
    }
    $script:upgradeExitCode = 1
} finally {
    if (-not $SourcePath -and (Test-Path $extractDir)) {
        Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    try { Stop-Transcript | Out-Null } catch {}
    if ($script:upgradeExitCode) { exit $script:upgradeExitCode }
}
