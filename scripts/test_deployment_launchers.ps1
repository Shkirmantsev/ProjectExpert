# Exercise Windows launchers with a controlled Docker boundary on Windows CI.
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$temp = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temp | Out-Null
$global:Calls = New-Object 'System.Collections.Generic.List[string]'
$global:StartExit = 0
function global:docker {
    $global:Calls.Add(($args -join ' '))
    $global:LASTEXITCODE = 0
    if (($args -join ' ') -match 'up -d') { $global:LASTEXITCODE = $global:StartExit }
}
function global:Invoke-WebRequest { return @{ StatusCode = 200 } }
$env:PI_OPEN_BROWSER = '0'
try {
    Get-ChildItem (Join-Path $repo 'distribution/deployment') -Filter '*.ps1' | ForEach-Object {
        $parseErrors = $null
        $tokens = $null
        [System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$parseErrors) | Out-Null
        if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    }
    Copy-Item (Join-Path $repo 'distribution/deployment/*') $temp
    & (Join-Path $temp 'start.ps1')
    if (-not ($global:Calls -match 'compose --env-file deployment.env -f compose.yaml up -d --wait --wait-timeout 1800')) {
        throw 'Bundle launcher did not wait for readiness'
    }
    # Model selection must survive the Windows wrapper into native setup.
    $setupPath = Join-Path $temp 'setup-windows-accelerator.ps1'
    Set-Content -LiteralPath $setupPath -Value 'param($Backend,$Model); $global:SelectedAccelerator = "$Backend/$Model"'
    foreach ($model in @('gemma','qwen')) {
        foreach ($backend in @('vulkan','cuda')) {
            $env:PI_EMBEDDING_MODEL = $model
            $env:PI_ACCELERATOR = $backend
            & (Join-Path $temp 'start.ps1')
            if ($global:SelectedAccelerator -ne "$backend/$model-gguf") { throw 'Windows selected the wrong GPU model' }
            if ($env:PI_RUNTIME_MODEL -ne "$model-gguf") { throw 'Container and native runtime models differ' }
        }
    }
    $env:PI_ACCELERATOR = 'cpu'
    $env:PI_EMBEDDING_MODEL = 'qwen'
    & (Join-Path $temp 'start.ps1')
    if ($env:PI_EMBEDDING_DEVICE -ne 'cpu') { throw 'Explicit Qwen CPU selection was lost' }
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
    Remove-Item -Recurse -Force $temp
    Remove-Item Function:\docker
    Remove-Item Function:\Invoke-WebRequest
}
