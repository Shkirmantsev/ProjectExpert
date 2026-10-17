<#
  One-click launcher for the v0.8 Project Intelligence Platform (Phase 9).

  DUTIES: verify-runtime export-env create-volumes mount-repo start-profile
          wait-readiness open-browser print-status

  The DUTIES line above is the single source of truth for the launcher's
  duty set. The duty-parity test (tests/test_phase_9_launch_smoke.py)
  asserts that the bash and PowerShell launchers advertise the same duties.

  Usage:
    powershell -ExecutionPolicy Bypass -File scripts\Start-ProjectIntelligence.ps1 start   [-Target <repo>] [-Profile <p>]
    powershell -ExecutionPolicy Bypass -File scripts\Start-ProjectIntelligence.ps1 stop    [-Target <repo>] [-Profile <p>]
    powershell -ExecutionPolicy Bypass -File scripts\Start-ProjectIntelligence.ps1 status  [-Target <repo>] [-Profile <p>]
    powershell -ExecutionPolicy Bypass -File scripts\Start-ProjectIntelligence.ps1 version

  Environment:
    $env:PI_CONTROL_PORT  - UI/API port on the host (default 8765)
    $env:PI_TARGET_REPO   - target repository path (default: current directory)
    $env:PI_PROFILE       - compose profile to start (default: desktop-lite)
    $env:PI_OPEN_BROWSER  - set to "0" to suppress browser opening (default: auto)
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'version')]
    [string]$Command = 'start',

    [string]$Target = ($env:PI_TARGET_REPO ?? (Get-Location).Path),
    [string]$Profile = ($env:PI_PROFILE ?? 'desktop-lite'),
    [string]$Port = ($env:PI_CONTROL_PORT ?? '8765'),
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..')).Path

function Write-Log([string]$Message) {
    Write-Host "[project-intelligence] $Message"
}

function Write-Fail([string]$Message) {
    Write-Host "[project-intelligence] ERROR: $Message"
    exit 1
}

function Show-Usage {
    Get-Content $MyInvocation.MyCommand.Path -TotalCount 18 | ForEach-Object {
        Write-Host ($_ -replace '^# ?', '')
    }
    exit 0
}

# ---- duty: verify-runtime -------------------------------------------------
function Get-ComposeCommand {
    if ($null -ne (Get-Command 'docker' -ErrorAction SilentlyContinue)) {
        try {
            docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) { return 'docker compose' }
        } catch {
            # fall through to podman
        }
    }
    if ($null -ne (Get-Command 'podman' -ErrorAction SilentlyContinue)) {
        if ($null -ne (Get-Command 'podman-compose' -ErrorAction SilentlyContinue)) {
            return 'podman-compose'
        }
        Write-Fail 'podman found without podman-compose; install podman-compose or use docker'
    }
    Write-Fail 'neither docker compose nor podman-compose is usable; install one and ensure the daemon is running'
}

# ---- duty: export-env -----------------------------------------------------
function Initialize-TargetRepo {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        Write-Fail "target repository does not exist: $Path"
    }
    $resolved = (Resolve-Path -LiteralPath $Path).Path
    $env:PI_TARGET_REPO = $resolved
    $env:PI_CONTROL_PORT = $Port
    $env:PI_PROFILE = $Profile
    return $resolved
}

# ---- duty: create-volumes -------------------------------------------------
function Initialize-Volumes {
    param([Parameter(Mandatory = $true)][string]$ComposeCmd)
    if (-not $env:PI_SKIP_VOLUME_CREATE) {
        Push-Location $ProjectRoot
        try {
            & $ComposeCmd -Profile $env:PI_PROFILE config | Out-Null
        } finally {
            Pop-Location
        }
    }
}

# ---- duty: mount-repo ------------------------------------------------------
function Mount-TargetRepo {
    Write-Log "mounting ${env:PI_TARGET_REPO} at /repo inside the container"
}

# ---- duty: start-profile --------------------------------------------------
function Start-Profile {
    param([Parameter(Mandatory = $true)][string]$ComposeCmd)
    Write-Log "runtime:  $ComposeCmd"
    Write-Log "target:   $($env:PI_TARGET_REPO)"
    Write-Log "profile:  $env:PI_PROFILE"
    Write-Log "port:     $env:PI_CONTROL_PORT"
    Push-Location $ProjectRoot
    try {
        $containerfile = Join-Path $ProjectRoot 'Containerfile'
        if (($env:PI_PULL_ONLY -eq '1') -or (-not (Test-Path -LiteralPath $containerfile))) {
            & $ComposeCmd --profile $env:PI_PROFILE up -d
        } elseif ($env:PI_BUILD -eq '1') {
            & $ComposeCmd --profile $env:PI_PROFILE up -d --build
        } else {
            & $ComposeCmd --profile $env:PI_PROFILE up -d
            if ($LASTEXITCODE -ne 0) {
                & $ComposeCmd --profile $env:PI_PROFILE up -d --build
            }
        }
    } finally {
        Pop-Location
    }
}

# ---- duty: wait-readiness -------------------------------------------------
function Wait-Readiness {
    param(
        [Parameter(Mandatory = $true)][string]$Port,
        [Parameter(Mandatory = $true)][string]$ComposeCmd
    )
    $url = "http://localhost:${Port}/health/ready"
    Write-Log "waiting for $url (readiness, not liveness)"
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -eq 200) {
                Write-Log "platform reports ready after $attempt attempt(s)"
                return
            }
        } catch {
            # not ready yet, keep polling
        }
        Start-Sleep -Seconds 2
    }
    Write-Fail "platform did not become ready within 120s; check '${ComposeCmd} logs'"
}

# ---- duty: open-browser ---------------------------------------------------
function Open-Browser {
    param([Parameter(Mandatory = $true)][string]$Port)
    if ($NoBrowser -or ($env:PI_OPEN_BROWSER -eq '0')) {
        return
    }
    $url = "http://localhost:${Port}/"
    try {
        Start-Process $url -ErrorAction Stop
        return
    } catch {
        Write-Log "no browser opener detected; print the URL manually"
    }
}

# ---- duty: print-status ----------------------------------------------------
function Show-Status {
    Write-Host 'project-intelligence ready'
    Write-Host "  url:      http://localhost:$Port/"
    Write-Host "  api:      http://localhost:$Port/api/v1/"
    Write-Host "  health:   http://localhost:$Port/health"
    Write-Host "  readiness http://localhost:$Port/health/ready"
    Write-Host "  profile:  $env:PI_PROFILE"
    Write-Host "  target:   $($env:PI_TARGET_REPO)"
}

function Stop-Profile {
    param([Parameter(Mandatory = $true)][string]$ComposeCmd)
    Push-Location $ProjectRoot
    try {
        & $ComposeCmd --profile $env:PI_PROFILE down
    } finally {
        Pop-Location
    }
}

function Show-ComposeStatus {
    param([Parameter(Mandatory = $true)][string]$ComposeCmd)
    Push-Location $ProjectRoot
    try {
        & $ComposeCmd --profile $env:PI_PROFILE ps
    } finally {
        Pop-Location
    }
}

switch ($Command) {
    'version' { Write-Host 'project-intelligence launcher 1.0.0 (Phase 9)'; return }
    'start' {
        $compose = Get-ComposeCommand
        $resolved = Initialize-TargetRepo -Path $Target
        Initialize-Volumes -ComposeCmd $compose
        Mount-TargetRepo
        Start-Profile -ComposeCmd $compose
        Wait-Readiness -Port $Port -ComposeCmd $compose
        Open-Browser -Port $Port
        Show-Status
    }
    'stop' {
        $compose = Get-ComposeCommand
        Initialize-TargetRepo -Path $Target | Out-Null
        Stop-Profile -ComposeCmd $compose
    }
    'status' {
        $compose = Get-ComposeCommand
        Initialize-TargetRepo -Path $Target | Out-Null
        Show-ComposeStatus -ComposeCmd $compose
    }
}