# Exercise Windows launchers with a controlled Docker boundary on Windows CI.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$temp = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temp | Out-Null
$global:Calls = New-Object 'System.Collections.Generic.List[string]'
$global:StartExit = 0
$global:ComposeModel = $null
$global:ComposeDevice = $null
function global:docker {
    $global:Calls.Add(($args -join ' '))
    $global:LASTEXITCODE = 0
    if (($args -join ' ') -match 'up -d') {
        $global:LASTEXITCODE = $global:StartExit
        $global:ComposeModel = $env:PI_EMBEDDING_MODEL
        $global:ComposeDevice = $env:PI_EMBEDDING_DEVICE
    }
}
function global:Invoke-WebRequest { return @{ StatusCode = 200 } }
# This fixture mocks Docker only; managed helpers have their own packaged tests.
$previousWorkspaceMode = $env:PI_WORKSPACE_MODE
$previousHostCA = $env:PI_HOST_CA_MODE
$env:PI_WORKSPACE_MODE = 'bind'
$env:PI_HOST_CA_MODE = 'off'
$env:PI_OPEN_BROWSER = '0'
$env:PI_ACCELERATOR = 'cpu'
$env:PI_EMBEDDING_MODEL = 'gemma'
try {
    Get-ChildItem (Join-Path $repo 'distribution/deployment') -Filter '*.ps1' | ForEach-Object {
        $parseErrors = $null
        $tokens = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
        if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    }
    Copy-Item (Join-Path $repo 'distribution/deployment/*') $temp
    & (Join-Path $temp 'start.ps1')
    if (-not ($global:Calls -match 'compose --env-file deployment.env .*up -d --wait --wait-timeout 1800')) {
        throw 'Bundle launcher did not wait for readiness'
    }
    # Model selection must survive the Windows wrapper into native setup.
    $setupPath = Join-Path $temp 'setup-windows-accelerator.ps1'
    Set-Content -LiteralPath $setupPath -Value @'
param($Backend,$Model)
$global:SelectedAccelerator = "$Backend/$Model"
$cache = Join-Path $PSScriptRoot 'accelerator'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
@{ok=$true; backend=$Backend; device='GPU0'; fit_target_mib=192} | ConvertTo-Json | Set-Content (Join-Path $cache 'plan.json')
'@
    foreach ($model in @('gemma','gemma-gguf')) {
        foreach ($backend in @('vulkan','cuda')) {
            $env:PI_EMBEDDING_MODEL = $model
            $env:PI_ACCELERATOR = $backend
            & (Join-Path $temp 'start.ps1')
            if ($global:SelectedAccelerator -ne "$backend/gemma") { throw 'Windows selected the wrong GPU model' }
            if ($global:ComposeModel -ne 'gemma') { throw 'Container and native runtime models differ' }
            if ($env:PI_EMBEDDING_MODEL -ne $model -or $env:PI_ACCELERATOR -ne $backend) { throw 'Launcher changed the parent model/backend preference' }
        }
    }
    $env:PI_ACCELERATOR = 'cpu'
    $env:PI_EMBEDDING_MODEL = 'gemma'
    & (Join-Path $temp 'start.ps1')
    if ($global:ComposeDevice -ne 'cpu') { throw 'Explicit Gemma CPU selection was lost' }
    $global:SelectedAccelerator = 'not-called'
    & (Join-Path $temp 'compose.ps1') config
    if ($global:SelectedAccelerator -ne 'not-called') { throw 'config unexpectedly started GPU setup' }
    $global:StartExit = 7
    $failed = $false
    try { & (Join-Path $temp 'start.ps1') } catch { $failed = $true }
    if (-not $failed) { throw 'Bundle launcher ignored startup failure' }
    $global:StartExit = 0
    & (Join-Path $repo 'scripts/Start-ProjectIntelligence.ps1') start -Target $temp -NoBrowser
    if (-not ($global:Calls -match '^compose --profile production up -d$')) {
        throw 'Source launcher failed to invoke docker compose as separate arguments'
    }
    $global:StartExit = 7
    $failed = $false
    try { & (Join-Path $repo 'scripts/Start-ProjectIntelligence.ps1') start -Target $temp -NoBrowser } catch { $failed = $true }
    if (-not $failed) { throw 'Source launcher ignored startup failure' }
    # Expected failure assertions leave a nonzero native exit code behind.
    # GitHub's PowerShell wrapper uses LASTEXITCODE even after caught errors.
    $global:LASTEXITCODE = 0
    Write-Host 'PASS: Windows PowerShell launcher defaults, command invocation, readiness and failure propagation'
} finally {
    $env:PI_WORKSPACE_MODE = $previousWorkspaceMode
    $env:PI_HOST_CA_MODE = $previousHostCA
    Remove-Item -Recurse -Force $temp
    Remove-Item Function:\docker
    Remove-Item Function:\Invoke-WebRequest
}
