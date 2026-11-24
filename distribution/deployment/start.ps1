# Compatible with Windows PowerShell 5.1 and PowerShell 7.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start the Docker engine selected by your CLI context in Linux-container mode. Check docker context show and docker info.' }
    $timeout = 1800
    if ($env:PI_WAIT_TIMEOUT) { $timeout = [int]$env:PI_WAIT_TIMEOUT }
    & (Join-Path $PSScriptRoot 'compose.ps1') up -d --wait --wait-timeout $timeout
    & (Join-Path $PSScriptRoot 'url.ps1') -OpenIfEnabled
} finally {
    Pop-Location
}
