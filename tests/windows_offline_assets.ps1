# Exercise actual native-setup extraction/failure ordering without executing GPUs.
$ErrorActionPreference = 'Stop'
$temp = Join-Path ([IO.Path]::GetTempPath()) ('pi-offline-native-' + [Guid]::NewGuid())
$saved = @{}
foreach ($name in @('PI_ASSET_IMAGE','PI_ASSET_MANIFEST_SHA256','PI_WORKSPACE_MODE','PI_HOST_CA_MODE')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$global:offlineCalls = New-Object System.Collections.Generic.List[string]
$global:rejectPack = $false
function global:docker {
    $call = $args -join ' '
    $global:offlineCalls.Add($call)
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'create') { 'fixture-container'; return }
    if ($args[0] -eq 'run') {
        if ($global:rejectPack) { $global:LASTEXITCODE = 31 }
        return
    }
    if ($call -match 'inference plan') {
        '{"ok":true,"backend":"cpu","device":null,"rejected":[]}'
    }
}
try {
    New-Item -ItemType Directory -Path $temp | Out-Null
    Copy-Item -Path (Join-Path $PSScriptRoot '../distribution/deployment/*') -Destination $temp -Recurse
    $env:PI_ASSET_IMAGE = 'ghcr.io/shkirmantsev/project-intelligence-assets@sha256:' + ('1' * 64)
    $env:PI_ASSET_MANIFEST_SHA256 = '2' * 64
    $env:PI_WORKSPACE_MODE = 'bind'
    $env:PI_HOST_CA_MODE = 'off'
    & (Join-Path $temp 'setup-windows-accelerator.ps1') -Backend cpu
    if ($global:LASTEXITCODE -ne 0) { throw 'Verified offline setup unexpectedly failed' }
    $calls = $global:offlineCalls -join "`n"
    if ($calls -notmatch 'cp fixture-container:/opt/projectexpert-assets/\.' -or
        $calls -notmatch 'run --rm --network none.*offline_assets --root /pack' -or
        $calls -notmatch 'rm fixture-container') { throw 'OCI extraction/verification/cleanup contract missing' }
    if ($calls.IndexOf('offline_assets --root /pack') -gt $calls.IndexOf('inference plan')) {
        throw 'Native planning occurred before asset verification'
    }
    $global:offlineCalls.Clear()
    $global:rejectPack = $true
    $failed = $false
    try { & (Join-Path $temp 'setup-windows-accelerator.ps1') -Backend cpu }
    catch { $failed = $_.Exception.Message -match 'Offline asset verification failed' }
    if (-not $failed) { throw 'Corrupt offline assets were not rejected' }
    if (($global:offlineCalls -join "`n") -match 'inference plan') {
        throw 'Invalid assets reached runtime planning'
    }
    Write-Output 'PASS: native Windows OCI extraction, verification ordering and fail-closed setup'
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    Remove-Item Function:docker -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Variable -Name offlineCalls,rejectPack -Scope Global -ErrorAction SilentlyContinue
}
$global:LASTEXITCODE = 0
