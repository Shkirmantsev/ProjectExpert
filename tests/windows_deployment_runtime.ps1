# Executes under both Windows PowerShell 5.1 and PowerShell 7 in CI.
$ErrorActionPreference = 'Stop'
$kit = Join-Path (Split-Path $PSScriptRoot -Parent) 'distribution/deployment'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $temporary | Out-Null
$previousPath = $env:PATH
$previousMode = $env:PI_WORKSPACE_MODE
$previousHostCA = $env:PI_HOST_CA_MODE
try {
    $env:PI_WORKSPACE_MODE = 'bind'
    $env:PI_HOST_CA_MODE = 'off'
    [IO.File]::WriteAllText((Join-Path $temporary 'docker.cmd'), "@echo off`r`necho native-output`r`necho native-warning 1>&2`r`nexit /b 37`r`n")
    $env:PATH = $temporary + ';' + $env:PATH
    . (Join-Path $kit 'workspace.ps1')
    $output = Invoke-WorkspaceCompose version 2>$null
    if ($LASTEXITCODE -ne 37) { throw "Native exit code lost: $LASTEXITCODE" }
    if (($output -join '') -notmatch 'native-output') { throw 'Native stdout lost' }
    if ($ErrorActionPreference -ne 'Stop') { throw 'ErrorActionPreference was not restored' }
    & (Join-Path $PSScriptRoot 'powershell_native_probe.ps1')
    # Successful assertions must not return the intentional native failure (37)
    # to the Actions shell wrapper. Exceptions above still fail this script.
    $global:LASTEXITCODE = 0
    Write-Output 'PASS: native stderr, exit status and preference restoration'
} finally {
    $env:PATH = $previousPath
    $env:PI_WORKSPACE_MODE = $previousMode
    $env:PI_HOST_CA_MODE = $previousHostCA
    Remove-Item -Recurse -Force -LiteralPath $temporary
}
