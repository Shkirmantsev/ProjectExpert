# Compatible with Windows PowerShell 5.1 and PowerShell 7.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    docker info | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop with Linux containers and WSL2 first.' }
    $timeout = 1800
    if ($env:PI_WAIT_TIMEOUT) { $timeout = [int]$env:PI_WAIT_TIMEOUT }
    & (Join-Path $PSScriptRoot 'compose.ps1') up -d --wait --wait-timeout $timeout
    $port = $env:PI_CONTROL_PORT
    if (-not $port) {
        $line = Get-Content deployment.env | Where-Object { $_ -match '^PI_CONTROL_PORT=' } | Select-Object -Last 1
        if ($line) { $port = $line.Split('=', 2)[1] } else { $port = '8765' }
    }
    $url = "http://localhost:$port"
    Write-Host "Ready: $url"
    if ($env:PI_OPEN_BROWSER -ne '0') { try { Start-Process $url } catch { Write-Host $url } }
} finally {
    Pop-Location
}
