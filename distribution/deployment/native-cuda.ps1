# Explicit offline preparation. This never changes deployment.env or starts a GPU.
param(
    [ValidateSet('inspect','verify','install')][string]$Action = 'verify',
    [string]$Source = $env:PI_GPU_PACK_ROOT,
    [string]$Destination,
    [string]$ManifestSha256 = $env:PI_GPU_PACK_SHA256
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'workspace.ps1')
. (Join-Path $PSScriptRoot 'native-runtime-assets.ps1')
$image = Get-WorkspaceValue 'PI_IMAGE'
if (-not $image) { throw 'Use the matching published kit or set PI_IMAGE explicitly' }
$primary = Get-WorkspaceValue 'PI_ASSET_MANIFEST_SHA256'
if ($primary -notmatch '^[0-9a-f]{64}$') { throw 'Missing primary asset manifest pin' }
Assert-NativeAssetDirectory $Source
if ($Action -eq 'inspect') {
    if (-not $Destination -or (Test-Path -LiteralPath $Destination)) { throw 'Inspection requires a new absolute destination directory' }
    $destinationPath = [IO.Path]::GetFullPath($Destination)
    $parent = Split-Path -Parent $destinationPath
    Assert-NativeAssetDirectory $parent
    $name = Split-Path -Leaf $destinationPath
    Invoke-AssetDocker run --rm --network none --entrypoint python -v "${Source}:/archives:ro" -v "${parent}:/output" $image `
        -m pi_platform.deployment.native_runtime_assets --source /archives --destination "/output/$name" `
        --primary-manifest-sha256 $primary --inspect-archives
} elseif ($Action -eq 'verify') {
    if ($ManifestSha256 -notmatch '^[0-9a-f]{64}$') { throw 'Verification needs the independently reviewed manifest SHA256' }
    Invoke-AssetDocker run --rm --network none --entrypoint python -v "${Source}:/native:ro" $image `
        -m pi_platform.deployment.native_runtime_assets --source /native --manifest-sha256 $ManifestSha256 `
        --primary-manifest-sha256 $primary
} else {
    if ($ManifestSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'Installation needs the approved native manifest SHA256' }
    $installed = Join-Path $PSScriptRoot 'accelerator/native-cuda'
    New-Item -ItemType Directory -Path $installed -Force | Out-Null
    Assert-NativeAssetDirectory $installed
    Invoke-AssetDocker run --rm --network none --entrypoint python -v "${Source}:/native:ro" -v "${installed}:/installed" $image `
        -m pi_platform.deployment.native_runtime_assets --source /native --destination /installed `
        --manifest-sha256 $ManifestSha256 --primary-manifest-sha256 $primary --mode operator-local
    $state = Join-Path $installed 'selected.json'
    $stage = Join-Path $installed ([IO.Path]::GetRandomFileName())
    try {
        @{schemaVersion=1;nativeManifestSha256=$ManifestSha256;primaryManifestSha256=$primary} |
            ConvertTo-Json -Compress | Set-Content -LiteralPath $stage -Encoding ASCII
        if ([IO.File]::Exists($state)) { [IO.File]::Replace($stage, $state, $null) }
        else { [IO.File]::Move($stage, $state) }
    } finally {
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage }
    }
    Write-Output 'Verified CUDA pack is selected for subsequent accelerator startup.'
}
