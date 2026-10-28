# Print the effective browser URL of the deployed control plane.
#
# The port is resolved exactly the way Compose resolves it: the shell
# environment overrides deployment.env, and deployment.env is read as plain
# text -- it is never sourced or executed. The script needs neither Docker nor
# Python and never mutates the deployment.
# Compatible with Windows PowerShell 5.1 and PowerShell 7.
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
    Write-Host "Ready: http://localhost:$port"
} finally { Pop-Location }
