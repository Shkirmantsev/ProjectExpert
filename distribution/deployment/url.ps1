# Print the effective browser URL of the deployed control plane.
#
# The port is resolved exactly the way Compose resolves it: the shell
# environment overrides deployment.env, and deployment.env is read as plain
# text -- it is never sourced or executed. The script needs neither Docker nor
# Python and never mutates the deployment.
# Compatible with Windows PowerShell 5.1 and PowerShell 7.
param([switch]$Open, [switch]$OpenIfEnabled)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $port = $env:PI_CONTROL_PORT
    if (-not $port) {
        $envFile = Join-Path $PSScriptRoot 'deployment.env'
        if (Test-Path -LiteralPath $envFile) {
            $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^PI_CONTROL_PORT=' } | Select-Object -Last 1
            if ($line) { $port = $line.Split('=', 2)[1].Trim().Trim('"').Trim("'") }
        }
    }
    if (-not $port) { $port = '8765' }
    Write-Output "Service URL: http://localhost:$port"
} finally { Pop-Location }

Write-Output 'Index readiness: /health/ready (the service can start while indexing is pending)'

if (-not $Open -and (-not $OpenIfEnabled -or $env:PI_OPEN_BROWSER -eq '0')) { return }
try {
    $launcher = Join-Path $PSScriptRoot 'compose.ps1'
    $published = (& $launcher port production 8765 | Out-String).Trim()
    if ($published -notmatch '^(127[.]0[.]0[.]1|\[::1\]):([0-9]{1,5})$') {
        throw 'ProjectExpert is not published on a local loopback port.'
    }
    $browserUrl = "http://localhost:$($Matches[2])/"
    $key = (& $launcher exec -T production python -m pi_platform.deployment.local_ui | Out-String).Trim()
    if ($key -cmatch '^[A-Za-z0-9_-]{43}$') { $browserUrl += "#local-owner=$key" }
    Start-Process $browserUrl
} catch {
    if ($Open) { throw 'Could not open the local ProjectExpert browser. Check the deployment with make platform-status.' }
}
