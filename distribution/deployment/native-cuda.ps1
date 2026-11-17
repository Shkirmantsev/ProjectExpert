# Explicit offline preparation. This never changes deployment.env or starts a GPU.
param(
    [ValidateSet('inspect','verify')][string]$Action = 'verify',
    [string]$Source,
    [string]$Destination,
    [string]$ManifestSha256
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
} else {
    if ($ManifestSha256 -notmatch '^[0-9a-f]{64}$') { throw 'Verification needs the independently reviewed manifest SHA256' }
    Invoke-AssetDocker run --rm --network none --entrypoint python -v "${Source}:/native:ro" $image `
        -m pi_platform.deployment.native_runtime_assets --source /native --manifest-sha256 $ManifestSha256 `
        --primary-manifest-sha256 $primary
}
