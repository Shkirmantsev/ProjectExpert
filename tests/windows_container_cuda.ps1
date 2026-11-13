# Container CUDA must use the host driver without native CUDA downloads/setup.
$ErrorActionPreference = 'Stop'
$temp = Join-Path ([IO.Path]::GetTempPath()) ('pi-container-cuda-' + [Guid]::NewGuid())
$saved = @{}
foreach ($name in @('PI_ACCELERATOR','PI_EMBEDDING_MODEL','PI_WORKSPACE_MODE','PI_HOST_CA_MODE','PI_GPU_DEVICE')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$global:cudaCalls = New-Object System.Collections.Generic.List[string]
$global:probeFails = $false
$global:gpuSlower = $false
$global:nativeCalls = 0
$global:cudaStartFails = $false
function global:nvidia-smi { }
function global:docker {
    $call = $args -join ' '
    $global:cudaCalls.Add($call)
    $global:LASTEXITCODE = 0
    if ($call -match 'embeddings --list-devices') {
        if ($global:probeFails) { $global:LASTEXITCODE = 7; return }
        'Available devices:'
        '  CUDA1: fixture GPU (8192 MiB, 4096 MiB free)'
    } elseif ($call -match 'inference plan') {
        $request = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($args[-1])) | ConvertFrom-Json
        $backend = 'cuda'
        if ($request.measurements -and $global:gpuSlower) { $backend = 'cpu' }
        @{ok=$true;backend=$backend;device='CUDA1';fit_target_mib=192} | ConvertTo-Json
    } elseif ($call -match 'inference benchmark') {
        $median = 10
        if ($call -match 'compose.cuda.yaml') { $median = 5; if ($global:gpuSlower) { $median = 20 } }
        @{median_ms=$median} | ConvertTo-Json
    } elseif ($call -match ' up ') {
        if ($global:cudaStartFails -and $call -match 'compose.cuda.yaml') { $global:LASTEXITCODE = 71 }
        $global:childDevice = $env:PI_GPU_DEVICE
    }
}
try {
    New-Item -ItemType Directory -Path $temp | Out-Null
    Copy-Item -Path (Join-Path $PSScriptRoot '../distribution/deployment/*') -Destination $temp -Recurse
    @'
param($Backend,$Model)
$global:nativeCalls++
$cache = Join-Path $PSScriptRoot 'accelerator'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
@{ok=$true;backend='cpu';device='none';fit_target_mib=192} | ConvertTo-Json | Set-Content (Join-Path $cache 'plan.json')
'@ | Set-Content (Join-Path $temp 'setup-windows-accelerator.ps1')
    $env:PI_ACCELERATOR = 'cuda'
    $env:PI_EMBEDDING_MODEL = 'gemma'
    $env:PI_WORKSPACE_MODE = 'bind'
    $env:PI_HOST_CA_MODE = 'off'
    $env:PI_GPU_DEVICE = 'CUDA1'
    & (Join-Path $temp 'compose.ps1') up -d
    $plan = Get-Content (Join-Path $temp 'accelerator/plan.json') -Raw | ConvertFrom-Json
    if ($plan.transport -ne 'container' -or $global:nativeCalls -ne 0) { throw 'Managed CUDA unnecessarily entered native host setup' }
    if ($global:childDevice -ne 'CUDA1') { throw 'Container did not receive the validated GPU device' }
    $global:cudaCalls.Clear()
    & (Join-Path $temp 'compose.ps1') config
    if (($global:cudaCalls -join "`n") -notmatch 'compose.cuda.yaml config') { throw 'Saved managed CUDA transport was lost' }
    if (($global:cudaCalls -join "`n") -match 'compose.windows-gpu.yaml|--list-devices') { throw 'Read-only config reprobed or switched to native transport' }
    $env:PI_ACCELERATOR = 'auto'
    & (Join-Path $temp 'compose.ps1') up -d
    $plan = Get-Content (Join-Path $temp 'accelerator/plan.json') -Raw | ConvertFrom-Json
    if ($plan.transport -ne 'container' -or $global:nativeCalls -ne 0) { throw 'Auto failed to retain the faster container GPU' }
    $global:gpuSlower = $true
    & (Join-Path $temp 'compose.ps1') up -d
    $plan = Get-Content (Join-Path $temp 'accelerator/plan.json') -Raw | ConvertFrom-Json
    if ($plan.backend -ne 'cpu') { throw 'Auto retained a slower CUDA container' }
    $env:PI_ACCELERATOR = 'cuda'
    $global:cudaStartFails = $true
    & (Join-Path $temp 'compose.ps1') up -d
    $plan = Get-Content (Join-Path $temp 'accelerator/plan.json') -Raw | ConvertFrom-Json
    if ($plan.backend -ne 'cpu' -or $global:nativeCalls -ne 0) { throw 'Failed managed CUDA startup did not retry the CPU profile' }
    $global:cudaStartFails = $false
    $global:probeFails = $true
    & (Join-Path $temp 'compose.ps1') up -d
    if ($global:nativeCalls -ne 1) { throw 'Unavailable Docker GPU did not use the existing fallback' }
    if ($env:PI_GPU_DEVICE -ne 'CUDA1' -or $env:PI_ACCELERATOR -ne 'cuda') { throw 'Host environment was changed' }
    $global:probeFails = $false
    $env:PI_GPU_DEVICE = 'CUDA7'
    & (Join-Path $temp 'compose.ps1') up -d
    if ($global:nativeCalls -ne 2) { throw 'Container selected a different GPU than the explicit device pin' }
    Write-Output 'PASS: Windows container CUDA preference, saved transport, benchmark policy and fallback without host CUDA installation'
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    Remove-Item Function:docker,Function:nvidia-smi -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Variable -Name cudaCalls,probeFails,gpuSlower,nativeCalls,childDevice,cudaStartFails -Scope Global -ErrorAction SilentlyContinue
}
$global:LASTEXITCODE = 0
