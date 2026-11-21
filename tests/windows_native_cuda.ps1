# Resolver fixtures only: no GPU/binary execution or public CUDA assets required.
$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pi-native-' + [Guid]::NewGuid())
$saved = @{}
foreach ($item in Get-ChildItem Env:) { $saved[$item.Name] = $item.Value }
$global:nativeCalls = New-Object System.Collections.Generic.List[string]
$global:invalidNative = $false
function global:docker {
    $global:nativeCalls.Add(($args -join ' '))
    if ($args -contains 'compose') { $global:nativeChildImage = $env:PI_IMAGE }
    $global:LASTEXITCODE = 0
    if ($global:invalidNative) { $global:LASTEXITCODE = 42; return }
    if ($args -contains '/installed') {
        # Real Python closure/integrity tests exercise the verifier separately.
        $root = Join-Path $global:fixtureKit ('accelerator/native-cuda/' + ('3' * 64) + '/windows/cuda')
        New-Item -ItemType Directory -Path $root -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $root 'llama-server.exe'), 'never execute fixture')
    }
}
try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    $global:fixtureKit = $temporary
    Copy-Item (Join-Path $PSScriptRoot '../distribution/deployment/*') $temporary -Recurse
    $env:PI_WORKSPACE_MODE = 'bind'
    $env:PI_HOST_CA_MODE = 'off'
    . (Join-Path $temporary 'workspace.ps1')
    . (Join-Path $temporary 'native-runtime-assets.ps1')
    $env:PI_NATIVE_CUDA_SOURCE = 'disabled'
    $failed = $false
    try { Resolve-OptionalNativeCuda 'app:fixture' ('2' * 64) } catch { $failed = $_ -match 'native_cuda_pack_missing' }
    if (-not $failed -or $global:nativeCalls.Count) { throw 'Absent optional CUDA must not trigger Docker or executable operations' }
    $env:PI_NATIVE_CUDA_SOURCE = 'operator-local'
    $env:PI_NATIVE_CUDA_MANIFEST_SHA256 = '3' * 64
    $env:PI_NATIVE_CUDA_LOCAL_ROOT = Join-Path $temporary 'reviewed'
    New-Item -ItemType Directory -Path $env:PI_NATIVE_CUDA_LOCAL_ROOT | Out-Null
    $directory = Resolve-OptionalNativeCuda 'app:fixture' ('2' * 64)
    if ($directory -notmatch 'native-cuda.*3333.*windows.*cuda') { throw 'Native runtime not isolated by manifest identity' }
    if (($global:nativeCalls -join "`n") -notmatch '--network none.*native_runtime_assets.*--mode operator-local') { throw 'Independent offline verifier not used' }
    $env:PI_IMAGE = 'app:fixture'
    $env:PI_ASSET_MANIFEST_SHA256 = '2' * 64
    & (Join-Path $temporary 'native-cuda.ps1') -Action install -Source $env:PI_NATIVE_CUDA_LOCAL_ROOT -ManifestSha256 ('3' * 64)
    $env:PI_NATIVE_CUDA_SOURCE = ''
    $env:PI_NATIVE_CUDA_MANIFEST_SHA256 = ''
    $env:PI_NATIVE_CUDA_LOCAL_ROOT = ''
    if ((Resolve-OptionalNativeCuda 'app:fixture' ('2' * 64)) -ne $directory) {
        throw 'Installed pack was not selected without environment settings'
    }
    $global:invalidNative = $true
    $failed = $false
    try { Resolve-OptionalNativeCuda 'app:fixture' ('2' * 64) } catch { $failed = $true }
    if (-not $failed) { throw 'Cache-hit CUDA corruption must not reach executable resolution' }
    $global:invalidNative = $false
    # Fresh installed kit resolves the same immutable image as the Go helper.
    $env:PI_IMAGE = ''
    $image = 'ghcr.io/shkirmantsev/project-intelligence@sha256:' + ('a' * 64)
    @{schema_version=1;release_status='verified';application_image=$image} | ConvertTo-Json | Set-Content (Join-Path $temporary 'asset-release.json')
    if ((Get-WorkspaceValue 'PI_IMAGE') -ne $image) { throw 'Kit application identity not resolved on Windows' }
    Invoke-WorkspaceCompose version
    if ($global:nativeChildImage -ne $image -or $env:PI_IMAGE) { throw 'Compose image differs from kit/workspace image or leaked into caller environment' }
    Write-Output 'PASS: optional native CUDA offline resolver, independent verification and cache fail-closed contracts (fixtures only)'
} finally {
    foreach ($item in Get-ChildItem Env:) { if (-not $saved.ContainsKey($item.Name)) { [Environment]::SetEnvironmentVariable($item.Name,$null,'Process') } }
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
    Remove-Item Function:docker -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
$global:LASTEXITCODE = 0
