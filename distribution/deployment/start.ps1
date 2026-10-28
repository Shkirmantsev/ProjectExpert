# Compatible with Windows PowerShell 5.1 and PowerShell 7.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers and WSL2 first.' }
    $timeout = 1800
    if ($env:PI_WAIT_TIMEOUT) { $timeout = [int]$env:PI_WAIT_TIMEOUT }
    & (Join-Path $PSScriptRoot 'compose.ps1') up -d --wait --wait-timeout $timeout
    # The readiness line is produced by the shared resolver, so the reported
    # URL is the effective one (shell environment, then deployment.env, then
    # default).
    $ready = (& (Join-Path $PSScriptRoot 'url.ps1') | Out-String).Trim()
    Write-Host $ready
    if ($env:PI_OPEN_BROWSER -ne '0') {
        try { Start-Process ($ready -replace '^Ready:\s*', '') } catch { Write-Host $ready }
    }
} finally {
    Pop-Location
}
