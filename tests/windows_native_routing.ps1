# Exercise actual setup with controlled process/Docker boundaries. No EXE runs.
$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pi-routing-' + [Guid]::NewGuid())
$saved = @{}
foreach ($item in Get-ChildItem Env:) { $saved[$item.Name] = $item.Value }
$global:routingModel = 'fixture-model'
$global:routingStarted = $false
$global:routingSelectedPath = ''
$global:routingSmoke = 0
$global:routingCudaMissing = $false
$global:routingRoot = $temporary
function global:Start-Process {
    param($FilePath,$ArgumentList,$WorkingDirectory,[switch]$PassThru,[switch]$NoNewWindow,$RedirectStandardOutput,$RedirectStandardError)
    if ($FilePath -notmatch 'windows[\\/]cuda[\\/]llama-server.exe|windows[\\/]vulkan[\\/]llama-server.exe') { throw 'Wrong native executable path' }
    if ($ArgumentList -notcontains '"0.0.0.0"') { throw 'Native host is unreachable from container' }
    $global:routingStarted = $true
    $global:routingSelectedPath = $FilePath
    return [pscustomobject]@{Id=12345;StartTime=[DateTime]::UtcNow;HasExited=$false}
}
function global:Invoke-RestMethod {
    if (-not $global:routingStarted) { throw 'not started' }
    return @{data=@(@{id=$global:routingModel})}
}
function global:docker {
    $global:LASTEXITCODE=0
    if ($args[0] -eq 'create') { 'fixture-container'; return }
    if ($args[0] -eq 'cp') {
        $dest = $args[-1]
        New-Item -ItemType Directory -Path (Join-Path $dest 'windows/vulkan') -Force | Out-Null
        [IO.File]::WriteAllText((Join-Path $dest 'windows/vulkan/llama-server.exe'),'never execute')
        New-Item -ItemType Directory -Path (Join-Path $dest 'embedding') -Force | Out-Null
        foreach ($file in @('embeddinggemma-2-Q8_0.gguf','mmproj-embeddinggemma-2-Q8_0.gguf')) {
            [IO.File]::WriteAllText((Join-Path $dest ('embedding/'+$file)),'fixture')
        }
        @{native_backends=@('vulkan')} | ConvertTo-Json | Set-Content (Join-Path $dest 'manifest.json')
        return
    }
    $call = $args -join ' '
    if ($call -match 'inference plan') {
        $request = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($args[-1])) | ConvertFrom-Json
        $candidate = @($request.candidates | Where-Object { $_.ok -and $_.backend -ne 'cpu' }) | Select-Object -First 1
        $backend='cpu';$device=$null
        if ($candidate) { $backend=$candidate.backend; $device=$(if ($backend -eq 'cuda') {'CUDA0'} else {'Vulkan1'}) }
        @{ok=$true;backend=$backend;device=$device;fit_target_mib=192;rejected=@();server_args=@('--host','0.0.0.0','--model','/models/embeddinggemma-2-Q8_0.gguf')} | ConvertTo-Json -Depth 8
    } elseif ($call -match 'inference benchmark') {
        $global:routingSmoke++
        '{"ok":true,"median_ms":2.5}'
    }
}
try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    Copy-Item (Join-Path $PSScriptRoot '../distribution/deployment/*') $temporary -Recurse
    # Replace hardware boundary helpers only; the actual setup/routing runs.
    @'
function Invoke-PinnedNativeProbe {
    param($Executable,$Arguments)
    $device = $(if ($Executable -match 'windows[\\/]cuda') {'CUDA0'} else {'Vulkan1'})
    return [pscustomobject]@{ok=$true;exit_code=0;stdout="Available devices:`n  ${device}: fixture GPU (8192 MiB, 4096 MiB free)";stderr='';reason='completed'}
}
function ConvertTo-NativeArgument([string]$Value) { return '"'+$Value+'"' }
function Stop-OwnedNativeRuntime { throw 'A healthy process should not be stopped by this fixture' }
'@ | Set-Content (Join-Path $temporary 'native-process.ps1')
    @'
function Assert-NativeAssetDirectory { }
function Resolve-OptionalNativeCuda {
    if ($global:routingCudaMissing) { throw 'native_cuda_pack_missing: fixture absent' }
    $path = Join-Path $PSScriptRoot 'accelerator/native-cuda/verified/windows/cuda'
    New-Item -ItemType Directory -Path $path -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $path 'llama-server.exe'),'never execute')
    return $path
}
'@ | Set-Content (Join-Path $temporary 'native-runtime-assets.ps1')
    $lockPath = Join-Path $temporary 'accelerator-lock.json'
    $lock = Get-Content $lockPath -Raw | ConvertFrom-Json
    $sample = Join-Path $temporary 'sample'; [IO.File]::WriteAllText($sample,'fixture')
    $hash = (Get-FileHash $sample -Algorithm SHA256).Hash.ToLowerInvariant()
    $lock.models.gemma.model_sha256=$hash; $lock.models.gemma.projector_sha256=$hash; $lock.models.gemma.model_alias=$global:routingModel
    $lock | ConvertTo-Json -Depth 10 | Set-Content $lockPath
    $env:PI_ASSET_IMAGE='ghcr.io/shkirmantsev/project-intelligence-assets@sha256:'+('1'*64)
    $env:PI_ASSET_MANIFEST_SHA256='2'*64
    $env:PI_IMAGE='app:fixture';$env:PI_WORKSPACE_MODE='bind';$env:PI_HOST_CA_MODE='off';$env:PI_GPU_DEVICE=''
    foreach ($request in @('cuda','vulkan','auto','cpu')) {
        $global:routingStarted=$false
        Remove-Item (Join-Path $temporary 'accelerator/runtime-identity.json') -ErrorAction SilentlyContinue
        & (Join-Path $temporary 'setup-windows-accelerator.ps1') -Backend $request
        $plan=Get-Content (Join-Path $temporary 'accelerator/plan.json') -Raw | ConvertFrom-Json
        $expected=$(if ($request -eq 'auto') {'cuda'} else {$request})
        if ($plan.backend -ne $expected -or $plan.requestedBackend -ne $request) { throw 'Native selection lost request or selected backend' }
        if ($expected -ne 'cpu' -and (-not $plan.embeddingSmoke.ok -or -not $global:routingStarted)) { throw 'Native GPU lacks serving-path smoke' }
    }
    $global:routingCudaMissing=$true;$global:routingStarted=$false
    & (Join-Path $temporary 'setup-windows-accelerator.ps1') -Backend auto
    $plan=Get-Content (Join-Path $temporary 'accelerator/plan.json') -Raw | ConvertFrom-Json
    if ($plan.backend -ne 'vulkan' -or $plan.rejections[0].reason_code -ne 'native_cuda_pack_missing') { throw 'Auto lost Intel/Vulkan fallback or precise cause' }
    $global:routingStarted=$false
    & (Join-Path $temporary 'setup-windows-accelerator.ps1') -Backend cuda
    $plan=Get-Content (Join-Path $temporary 'accelerator/plan.json') -Raw | ConvertFrom-Json
    if ($plan.backend -ne 'cpu' -or $global:routingStarted) { throw 'Explicit unavailable CUDA must not select Vulkan' }
    Write-Output 'PASS: actual native setup CUDA/Vulkan/iGPU/CPU routing and embedding-smoke ordering (hardware boundaries mocked)'
} finally {
    foreach ($item in Get-ChildItem Env:) { if (-not $saved.ContainsKey($item.Name)) { [Environment]::SetEnvironmentVariable($item.Name,$null,'Process') } }
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
    Remove-Item Function:docker,Function:Start-Process,Function:Invoke-RestMethod -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
$global:LASTEXITCODE=0
