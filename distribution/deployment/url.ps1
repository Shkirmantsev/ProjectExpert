# Print the effective browser URL of the deployed control plane.
#
# The port is resolved exactly the way Compose resolves it: the shell
# environment overrides deployment.env, and deployment.env is read as plain
# text -- it is never sourced or executed. The script needs neither Docker nor
# Python and never mutates the deployment.
# Compatible with Windows PowerShell 5.1 and PowerShell 7.
param([switch]$Open, [switch]$OpenIfEnabled)
$ErrorActionPreference = 'Stop'
function Get-UiSetting([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value) {
        $envFile = Join-Path $PSScriptRoot 'deployment.env'
        if (Test-Path -LiteralPath $envFile) {
            $line = Get-Content -LiteralPath $envFile | Where-Object { $_.StartsWith($Name + '=') } | Select-Object -Last 1
            if ($line) { $value = $line.Split('=', 2)[1] }
        }
    }
    if ($value) { return $value.Trim().Trim('"').Trim("'") }
}

function Get-BrowserAddress([string]$Address) {
    if ($Address -in @('', '0.0.0.0', '127.0.0.1', '::', '::1', '[::]', '[::1]')) { return 'localhost' }
    return $Address
}

$port = Get-UiSetting PI_CONTROL_PORT
if (-not $port) { $port = '8765' }
$address = Get-BrowserAddress (Get-UiSetting PI_BIND_HOST)
Write-Output "Service URL: http://${address}:$port"

Write-Output 'Index readiness: /health/ready (the service can start while indexing is pending)'

if (-not $Open -and (-not $OpenIfEnabled -or $env:PI_OPEN_BROWSER -eq '0')) { return }
try {
    $launcher = Join-Path $PSScriptRoot 'compose.ps1'
    $published = (& $launcher port production 8765 | Out-String).Trim()
    if ($published -notmatch '^([0-9.]+|\[[0-9a-fA-F:]+\]):([0-9]{1,5})$') {
        throw 'ProjectExpert has no published HTTP port.'
    }
    $publishedPort = $Matches[2]
    $address = Get-BrowserAddress $Matches[1]
    Start-Process "http://${address}:${publishedPort}/"
} catch {
    if ($Open) { throw 'Could not open ProjectExpert in the browser. Check the deployment with make platform-status.' }
}
