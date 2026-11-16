# Optional CUDA assets are independent of the model/Docling/Vulkan pack.
# Dot-source after workspace.ps1. No downloads from HF/GitHub, no driver changes.
function Invoke-AssetDocker {
    $previous = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @args
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    if ($code -ne 0) { throw 'native_cuda_pack_invalid: offline asset operation failed; inspect Docker connectivity and the pinned asset identity' }
}
function Assert-NativeAssetDirectory([string]$Root) {
    if (-not [IO.Path]::IsPathRooted($Root) -or -not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw 'native_cuda_pack_missing: configure an absolute local pack directory'
    }
    $item = Get-Item -LiteralPath $Root
    while ($item) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'native_cuda_pack_invalid: linked pack path' }
        $item = $item.Parent
    }
    foreach ($item in Get-ChildItem -LiteralPath $Root -Recurse -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'native_cuda_pack_invalid: linked pack contents' }
    }
}
function Resolve-OptionalNativeCuda([string]$AppImage, [string]$PrimaryDigest) {
    $source = Get-WorkspaceValue 'PI_NATIVE_CUDA_SOURCE'
    if (-not $source -or $source -eq 'disabled') { throw 'native_cuda_pack_missing: import the pinned archives offline or configure a reviewed companion; default pack contains Vulkan only' }
    if ($source -notin @('operator-local','reviewed-oci')) { throw 'native_cuda_pack_unapproved: unsupported CUDA source' }
    $digest = Get-WorkspaceValue 'PI_NATIVE_CUDA_MANIFEST_SHA256'
    if ($digest -notmatch '^[0-9a-f]{64}$') { throw 'native_cuda_manifest_mismatch: missing independent native manifest pin' }
    $base = Join-Path $PSScriptRoot 'accelerator/native-cuda'
    New-Item -ItemType Directory -Force -Path $base | Out-Null
    $final = Join-Path $base $digest
    if (Test-Path -LiteralPath $final) {
        Assert-NativeAssetDirectory $final
        Invoke-AssetDocker run --rm --network none --entrypoint python -v "${final}:/native:ro" $AppImage `
            -m pi_platform.deployment.native_runtime_assets --source /native --manifest-sha256 $digest `
            --primary-manifest-sha256 $PrimaryDigest --mode $source | Out-Host
    } else {
        $root = Get-WorkspaceValue 'PI_NATIVE_CUDA_LOCAL_ROOT'
        $temporary = $null
        try {
            if ($source -eq 'reviewed-oci') {
                $image = Get-WorkspaceValue 'PI_NATIVE_CUDA_IMAGE'
                if ($image -notmatch '^ghcr\.io/shkirmantsev/project-intelligence-native-cuda@sha256:[0-9a-f]{64}$') {
                    throw 'native_cuda_pack_unapproved: companion image requires an immutable approved repository digest'
                }
                # create uses an already pulled immutable image. Never pulls an
                # optional companion for ordinary CPU/Vulkan installations.
                $temporary = Join-Path $base ('.extract-' + [Guid]::NewGuid())
                New-Item -ItemType Directory -Path $temporary | Out-Null
                $container = $null
                try {
                    $container = (Invoke-AssetDocker create --pull never $image | Out-String).Trim()
                    Invoke-AssetDocker cp "${container}:/opt/projectexpert-native-cuda/." $temporary | Out-Host
                } finally { if ($container) { Invoke-AssetDocker rm $container | Out-Host } }
                $root = $temporary
            }
            Assert-NativeAssetDirectory $root
            Invoke-AssetDocker run --rm --network none --entrypoint python -v "${root}:/native:ro" -v "${base}:/installed" $AppImage `
                -m pi_platform.deployment.native_runtime_assets --source /native --destination /installed --manifest-sha256 $digest `
                --primary-manifest-sha256 $PrimaryDigest --mode $source | Out-Host
        } finally { if ($temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force } }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $final 'windows/cuda'))) { throw 'native_cuda_pack_invalid: verified installation missing runtime' }
    return (Join-Path $final 'windows/cuda')
}
