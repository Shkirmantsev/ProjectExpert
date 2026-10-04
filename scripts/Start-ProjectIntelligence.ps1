# Phase 1 launcher skeleton for the v0.8 Project Intelligence Platform (Windows).
# Final one-click behaviour ships in Phase 9. This Phase 1 version:
#   1. verifies that docker (with compose) is available;
#   2. prepares the runtime volume directory;
#   3. starts the default "core-headless" profile via docker compose;
#   4. waits for the control-plane health check.
#
# Usage:
#   pwsh scripts/Start-ProjectIntelligence.ps1 -Action start [-TargetRepo <path>]
#   pwsh scripts/Start-ProjectIntelligence.ps1 -Action stop
#   pwsh scripts/Start-ProjectIntelligence.ps1 -Action status

[CmdletBinding()]
param(
    [ValidateSet("start", "stop", "status")]
    [string]$Action = "status",
    [string]$TargetRepo,
    [int]$ControlPort = 8765,
    [int]$UiPort = 8766,
    [string]$Profile = "core-headless"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

if (-not $TargetRepo) {
    $TargetRepo = (Get-Location).Path
}
$TargetRepo = (Resolve-Path $TargetRepo).Path

function Write-Log([string]$msg) {
    Write-Host "[project-intelligence] $msg"
}

function Test-ContainerRuntime {
    try {
        $null = docker info 2>$null
        if ($LASTEXITCODE -eq 0) { return "docker compose" }
    } catch {}
    try {
        $null = podman info 2>$null
        if ($LASTEXITCODE -eq 0) {
            $composeCmd = Get-Command podman-compose -ErrorAction SilentlyContinue
            if ($composeCmd) { return "podman-compose" }
        }
    } catch {}
    throw "neither docker compose nor podman-compose is usable"
}

$env:PI_TARGET_REPO = $TargetRepo
$env:PI_CONTROL_PORT = "$ControlPort"
$env:PI_UI_PORT = "$UiPort"

$Compose = Test-ContainerRuntime
Write-Log "using runtime: $Compose"
Write-Log "target repo:  $TargetRepo"
Write-Log "profile:      $Profile"

Push-Location $ProjectRoot
try {
    switch ($Action) {
        "start" {
            & $Compose --profile $Profile up -d --build
            Write-Log "waiting for health check on http://localhost:$ControlPort/health"
            for ($i = 0; $i -lt 30; $i++) {
                try {
                    $resp = Invoke-WebRequest -Uri "http://localhost:$ControlPort/health" -UseBasicParsing -TimeoutSec 2
                    if ($resp.StatusCode -eq 200) {
                        Write-Log "platform is healthy"
                        return
                    }
                } catch {}
                Start-Sleep -Seconds 2
            }
            Write-Log "WARNING: health check did not respond within 60s; check compose logs"
        }
        "stop" {
            & $Compose --profile $Profile down
        }
        "status" {
            & $Compose --profile $Profile ps
        }
    }
} finally {
    Pop-Location
}