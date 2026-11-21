# General Compose wrapper for product Make targets on Windows.
#
# The backend is detected automatically: setup-windows-accelerator.ps1 probes
# the pinned native runtime for CUDA and Vulkan, and the shared Python policy
# selects the validated device. When no GPU candidate validates the managed
# CPU sidecar container is used instead. An unavailable GPU is a downgrade,
# never a startup failure.
#
# A GPU that works but is SLOWER than the CPU baseline is also not selected:
# the native service and the CPU sidecar are measured with the same corpus
# and the GPU is only kept when it is measurably faster. A measurement that
# cannot be obtained falls back to the CPU profile.
$ErrorActionPreference = 'Stop'
# Restore all process environment changes, including workspace configuration.
$savedEnvironment = @{}
foreach ($item in Get-ChildItem Env:) { $savedEnvironment[$item.Name] = $item.Value }
$composeArgs = $args
. (Join-Path $PSScriptRoot 'workspace.ps1')
. (Join-Path $PSScriptRoot 'container-cuda.ps1')
. (Join-Path $PSScriptRoot 'native-process.ps1')


function Measure-Endpoint([string]$Endpoint, [string[]]$Files) {
    # Measure the embedding latency of a running runtime. Returns the median
    # in milliseconds, or $null when the runtime cannot be measured. The
    # caller supplies the complete applicable Compose topology: a reduced file
    # set would make the running sidecars look like orphans to Compose.
    $raw = Invoke-WorkspaceCompose --env-file deployment.env @Files `
        run --rm --no-deps -T production `
        inference benchmark --endpoint $Endpoint --iterations 20 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    $text = ($raw -join "`n")
    $match = [regex]::Match($text, '"median_ms"\s*:\s*([0-9.]+)')
    if (-not $match.Success) { return $null }
    return [double]$match.Groups[1].Value
}

function Measure-CpuSidecar {
    # Start the managed CPU sidecar, measure it and stop it again.
    $files = @('-f','compose.yaml','-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
    Invoke-WorkspaceCompose --env-file deployment.env @files up -d --wait --wait-timeout 1800 embeddings *> $null
    if ($LASTEXITCODE -ne 0) { return $null }
    try {
        return Measure-Endpoint "http://embeddings:$($env:PI_LLAMA_PORT)" $files
    } finally {
        Invoke-WorkspaceCompose --env-file deployment.env @files stop embeddings *> $null
    }
}

function Resolve-PlanWithMeasurements($Plan, $Measurements) {
    # Ask the shared Python policy again, now with the measured latencies.
    $probeOutput = Get-Content -LiteralPath (Join-Path $PSScriptRoot "accelerator/devices-$($Plan.backend).txt") -Raw
    $errorPath = Join-Path $PSScriptRoot "accelerator/devices-$($Plan.backend)-error.txt"
    if (Test-Path -LiteralPath $errorPath) { $probeOutput += Get-Content -LiteralPath $errorPath -Raw }
    $evidence = @{
        platform = 'windows'
        candidates = @(
            @{ backend = $Plan.backend; ok = $true; exit_code = 0; output = $probeOutput }
            @{ backend = 'cpu'; ok = $true; exit_code = 0; output = '' }
        )
        measurements = $Measurements
    }
    $json = $evidence | ConvertTo-Json -Depth 6 -Compress
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
    # The decision is asked before the backend is known, so the provisional CPU
    # overlay supplies the complete service topology. The plan only runs the
    # production service (--no-deps).
    $raw = Invoke-WorkspaceCompose --env-file deployment.env -f compose.yaml `
        -f compose.accelerator.yaml -f compose.cpu.yaml `
        run --rm --no-deps -T production inference plan --evidence-b64 $encoded 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    try {
        return (($raw -join "`n") | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Get-ExternalLlamaFiles($Plan) {
    $env:PI_NATIVE_LLAMA_ENDPOINT = $Plan.endpoint
    $env:PI_ACCELERATOR = 'auto'
    $env:PI_GPU_DEVICE = ''
    $env:PI_NATIVE_LLAMA_AUTH = $(if ($Plan.auth -eq 'none') { 'none' } else { 'managed-token' })
    $env:PI_NATIVE_LLAMA_PRIVATE = $(if ($Plan.auth -eq 'none') { '1' } else { '0' })
    @('-f','compose.windows-gpu.yaml')
    if ($Plan.auth -eq 'token-file') {
        $env:PI_NATIVE_LLAMA_TOKEN_FILE = $Plan.tokenFile
        @('-f','compose.windows-llama-token.yaml')
    }
}

function Test-ExternalLlamaRoute {
    $port = [int]$env:PI_LLAMA_PORT
    $auth = $env:PI_NATIVE_LLAMA_AUTH
    if ($auth -notin @('managed-token','token-file','none')) {
        throw 'Choose managed-token, token-file, or none for the existing server.'
    }
    if ($workspaceManaged) {
        $context = (Invoke-WorkspaceAgent context | Out-String).Trim()
    } else {
        $context = (& docker context show | Out-String).Trim()
    }
    if (-not $context) { throw 'The local Docker context could not be determined.' }
    $hostSocket = (& docker context inspect $context --format '{{.Endpoints.docker.Host}}' | Out-String).Trim()
    if (-not $workspaceManaged -and $env:DOCKER_HOST -and -not $env:DOCKER_CONTEXT) { $hostSocket = $env:DOCKER_HOST }
    if ($hostSocket -notmatch '^npipe:/{2,4}\./pipe/') {
        throw 'Manual native inference requires a local Windows Docker engine.'
    }
    $addresses = @(Get-PrivateWindowsBridgeAddresses)
    if (-not $addresses -or -not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        throw 'No private WSL/Docker interface is available for the existing llama-server.'
    }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    $listenerAddresses = @($listeners | Select-Object -ExpandProperty LocalAddress -Unique)
    $owners = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($owners.Count -ne 1) { throw 'The selected port must have a single local listener owner.' }
    $candidates = @($addresses | Where-Object { $_ -in $listenerAddresses })
    if ($auth -eq 'none') {
        if (@($listenerAddresses | Where-Object { $_ -notin ($addresses + @('127.0.0.1','::1')) }).Count) {
            throw 'Tokenless llama-server must listen only on a private WSL/Docker address or loopback. Wildcard and LAN listeners require authentication.'
        }
    } elseif ('0.0.0.0' -in $listenerAddresses) {
        $candidates = $addresses
    }
    if (-not $candidates) { throw 'The existing llama-server must listen on a reachable private WSL/Docker address.' }

    $external = [pscustomobject]@{ok=$true;backend='auto';transport='external-windows';auth=$auth;endpoint='';tokenFile=''}
    if ($auth -eq 'token-file') {
        if (-not $env:PI_NATIVE_LLAMA_TOKEN_FILE) { throw 'Supply the existing server token with -TokenFile.' }
        $file = Get-Item -LiteralPath $env:PI_NATIVE_LLAMA_TOKEN_FILE
        if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $file.Length -gt 4096) {
            throw 'The existing server token must be a small regular file.'
        }
        $external.tokenFile = $file.FullName
    }
    $probeFiles = @(Get-ExternalLlamaFiles $external)
    $lock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'accelerator-lock.json') -Raw | ConvertFrom-Json
    $routeArgs = @('--host-only','--port',"$port",'--model',$lock.models.gemma.model_alias)
    foreach ($address in $candidates) { $routeArgs += @('--host-ip',$address) }
    # The authenticated tokens are mounted from a private file. No token
    # bytes are passed to Docker or PowerShell command-line arguments.
    New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'accelerator') | Out-Null
    $raw = Invoke-WorkspaceCompose --env-file deployment.env -f compose.yaml @probeFiles `
        run --rm --no-deps -T production inference native-route @routeArgs 2>$null
    $code = $LASTEXITCODE
    $result = $null
    try { $result = ($raw -join "`n") | ConvertFrom-Json } catch { }
    if ($result) {
        $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath 'accelerator/route-probe.json' -Encoding UTF8
    }
    $allowed = @($candidates | ForEach-Object { "http://${_}:$port" })
    if ($code -ne 0 -or -not $result.ok -or $result.endpoint -notin $allowed) {
        throw 'Existing llama-server failed the model, authentication or embedding check. Inspect accelerator/route-probe.json.'
    }
    $after = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    if ($after.Count -ne $listeners.Count -or
        @($after | Where-Object { $_.OwningProcess -ne $owners[0] -or $_.LocalAddress -notin $listenerAddresses }).Count) {
        throw 'The existing listener changed during validation. Try connecting again.'
    }
    $external.endpoint = $result.endpoint
    return $external
}

Push-Location $PSScriptRoot
try {
    $env:PI_LLAMA_PORT = Get-WorkspaceValue 'PI_LLAMA_PORT'
    if (-not $env:PI_LLAMA_PORT) { $env:PI_LLAMA_PORT = '8769' }
    if ($env:PI_LLAMA_PORT -notmatch '^[1-9][0-9]{0,4}$' -or
        [int]$env:PI_LLAMA_PORT -gt 65535 -or $env:PI_LLAMA_PORT -eq '8770') {
        throw 'PI_LLAMA_PORT must be 1-65535 and must differ from control port 8770'
    }
    if ($composeArgs -contains 'up' -and (Get-WorkspaceValue 'PI_HOST_CA_MODE') -ne 'off') {
        & (Join-Path $PSScriptRoot 'host-trust.ps1')
    }
    if ($composeArgs -contains 'up') {
        & (Join-Path $PSScriptRoot 'registry-preflight.ps1') -Image (Get-WorkspaceValue 'PI_ASSET_IMAGE')
    }
    Initialize-Workspace $composeArgs
    $backend = $env:PI_ACCELERATOR
    if (-not $backend) {
        $line = Get-Content deployment.env | Where-Object { $_ -match '^PI_ACCELERATOR=' } | Select-Object -Last 1
        if ($line) { $backend = $line.Split('=', 2)[1] } else { $backend = 'auto' }
    }
    $model = $env:PI_EMBEDDING_MODEL
    if (-not $model) {
        $line = Get-Content deployment.env | Where-Object { $_ -match '^PI_EMBEDDING_MODEL=' } | Select-Object -Last 1
        if ($line) { $model = $line.Split('=', 2)[1] } else { $model = 'gemma' }
    }
    if (-not $env:PI_GPU_DEVICE) {
        $line = Get-Content deployment.env | Where-Object { $_ -match '^PI_GPU_DEVICE=' } | Select-Object -Last 1
        if ($line) { $env:PI_GPU_DEVICE = $line.Split('=', 2)[1] }
    }
    if ($model -notin @('gemma','gemma-gguf','gemma-torch')) {
        throw "Unknown embedding model '$model'. Use 'gemma' (EmbeddingGemma 2 Q8_0 GGUF, the default) or 'gemma-torch'."
    }
    $requestedBackend = $backend
    $sidecarAuth = Get-WorkspaceValue 'PI_SIDECAR_LLAMA_AUTH'
    if ($sidecarAuth -and $sidecarAuth -notin @('managed-token','none')) {
        throw 'PI_SIDECAR_LLAMA_AUTH must be managed-token or none'
    }
    $strictAccelerator = (Get-WorkspaceValue 'PI_ACCELERATOR_STRICT') -eq '1'
    if ($backend -notin @('auto','cpu','vulkan','cuda')) { throw 'PI_ACCELERATOR must be auto, cpu, vulkan or cuda' }
    if ($composeArgs -contains 'down') {
        & (Join-Path $PSScriptRoot 'stop.ps1') -WorkspacePrepared
        exit 0
    }
    $files = @('-f', 'compose.yaml')
    $planPath = Join-Path $PSScriptRoot 'accelerator/plan.json'
    if ($env:PI_NATIVE_LLAMA_CONNECT -eq '1' -and $composeArgs -contains 'up') {
        if ($model -eq 'gemma-torch') { throw 'Connecting llama-server requires the Gemma GGUF profile.' }
        $external = Test-ExternalLlamaRoute
        $files += @(Get-ExternalLlamaFiles $external)
        Invoke-WorkspaceCompose --env-file deployment.env @files @composeArgs
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed to start with the existing llama-server.' }
        $external | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $planPath -Encoding UTF8
        Write-Output 'Connected to the existing llama-server. Its lifecycle is owned by its operator.'
        exit 0
    }
    if ($model -eq 'gemma-torch') {
        # Native PyTorch binding: no llama.cpp runtime, no probing.
        $env:PI_EMBEDDING_MODEL = 'gemma-torch'
        $env:PI_EMBEDDING_DEVICE = 'cpu'
        Invoke-WorkspaceCompose --env-file deployment.env @files @composeArgs
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
        exit 0
    }
    $env:PI_EMBEDDING_MODEL = 'gemma'
    if ($composeArgs -notcontains 'up') {
        $savedBackend = 'cpu'
        $savedPlan = $null
        if (Test-Path -LiteralPath $planPath) {
            $savedPlan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
            $savedBackend = $savedPlan.backend
        }
        if ($savedPlan.transport -eq 'external-windows') {
            if ($composeArgs -contains 'restart') { throw 'Reconnect the existing llama-server with llama-connect.ps1 to revalidate it before restarting.' }
            $files += @(Get-ExternalLlamaFiles $savedPlan)
        } elseif ($savedBackend -eq 'cuda' -and $savedPlan.transport -eq 'container') {
            $files += @('-f','compose.accelerator.yaml','-f','compose.cuda.yaml')
        } elseif ($savedBackend -eq 'cpu') {
            $files += @('-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
        } else {
            $files += @('-f','compose.windows-gpu.yaml')
            $env:PI_ACCELERATOR = $savedBackend
            $env:PI_GPU_DEVICE = $savedPlan.device
            $env:PI_NATIVE_LLAMA_ENDPOINT = $savedPlan.endpoint
        }
        Invoke-WorkspaceCompose --env-file deployment.env @files @composeArgs
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
        exit 0
    }
    if (Test-Path -LiteralPath $planPath) { Remove-Item -LiteralPath $planPath -Force }
    $containerEvidence = Join-Path $PSScriptRoot 'accelerator/container-probe.json'
    if (Test-Path -LiteralPath $containerEvidence) { Remove-Item -LiteralPath $containerEvidence }
    $containerPlan = Get-ContainerCudaPlan $backend
    if ($requestedBackend -eq 'cpu') {
        # Explicit CPU never copies the multi-GB primary pack onto the host or
        # probes native GPUs. The existing mandatory asset-seed serves models.
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $planPath) | Out-Null
        @{ok=$true;backend='cpu';device='none';fit_target_mib=192;transport='container'} | ConvertTo-Json | Set-Content -LiteralPath $planPath -Encoding UTF8
    } elseif ($containerPlan) {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'accelerator/runtime.pid')) {
            & (Join-Path $PSScriptRoot 'stop.ps1') -KeepWorkspaceSupervisor
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $planPath) | Out-Null
        $containerPlan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
        Write-Output 'Selected CUDA transport: container runtime with the existing host NVIDIA driver'
    } elseif ($sidecarAuth -eq 'none') {
        if ($requestedBackend -ne 'auto') {
            throw 'Tokenless inference requires the private managed sidecar. No container GPU validated for the requested backend.'
        }
        $backend = 'cpu'
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $planPath) | Out-Null
        @{ok=$true;backend='cpu';device='none';fit_target_mib=192;transport='container'} | ConvertTo-Json | Set-Content -LiteralPath $planPath -Encoding UTF8
        Write-Output 'Using the private CPU sidecar for tokenless inference.'
    } else {
        # Native fallback is needed only when managed GPU passthrough is absent.
        try {
            & (Join-Path $PSScriptRoot 'setup-windows-accelerator.ps1') -Backend $backend -Model 'gemma' -Port ([int]$env:PI_LLAMA_PORT)
        } catch {
            Write-Warning "Native GPU setup failed; using the CPU sidecar. $_"
            $nativeFailure = [string]$_
            $failureCode = 'native_setup_failed'
            if ($nativeFailure -match '([a-z_]+):') { $failureCode = $Matches[1] }
            # Asset/probe rejection never tears down a healthy application or
            # an unrelated pre-existing native endpoint.
            $fallback = @{ok=$true;backend='cpu';device='none';fit_target_mib=192;transport='container';
                requestedBackend=$requestedBackend;selectedBackend='cpu';schemaVersion=2;
                rejections=@(@{backend=$requestedBackend;reason_code=$failureCode})}
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $planPath) | Out-Null
            $fallback | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
        }
    }
    $plan = $null
    if (Test-Path -LiteralPath $planPath) {
        $plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
    }
    if ($strictAccelerator -and $requestedBackend -in @('cuda','vulkan') -and (-not $plan -or $plan.backend -ne $requestedBackend)) {
        throw "accelerator_strict_unavailable: requested $requestedBackend unavailable; production/indexing was not started; inspect accelerator/probes.json and plan.json"
    }
    if ($backend -eq 'auto' -and $plan -and $plan.backend -ne 'cpu') {
        # The GPU works. Measure it against the CPU baseline: a GPU that is
        # not measurably faster is not worth its complexity.
        if ($plan.transport -eq 'container') {
            $gpuMedian = $null
            if (Start-ContainerCudaRuntime $plan) {
                $gpuMedian = Measure-Endpoint "http://embeddings:$($env:PI_LLAMA_PORT)" @('-f','compose.yaml','-f','compose.accelerator.yaml','-f','compose.cuda.yaml')
            }
        } else {
            $env:PI_NATIVE_LLAMA_ENDPOINT = $plan.endpoint
            $gpuMedian = Measure-Endpoint $plan.endpoint @('-f','compose.yaml','-f','compose.windows-gpu.yaml')
        }
        $cpuMedian = Measure-CpuSidecar
        if ($gpuMedian -and $cpuMedian) {
            $measurements = @{ cpu = [double]$cpuMedian; $plan.backend = [double]$gpuMedian }
            $decision = Resolve-PlanWithMeasurements $plan $measurements
            if (-not $decision -or -not $decision.ok -or $decision.backend -eq 'cpu') {
                Write-Output "The $($plan.backend) profile is not faster than the CPU baseline; using the CPU profile."
                Write-Output "Rejected inference candidates: $($plan.backend) (not faster than the cpu baseline)"
                & (Join-Path $PSScriptRoot 'stop.ps1') -KeepWorkspaceSupervisor
                $plan = [pscustomobject]@{ ok = $true; backend = 'cpu'; device = $null; fit_target_mib = 192 }
                $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
            } else {
                Write-Output "Measured median latency: $($plan.backend)=$gpuMedian, cpu=$cpuMedian"
            }
        } else {
            Write-Warning 'Could not measure both GPU and CPU; using the CPU profile.'
            & (Join-Path $PSScriptRoot 'stop.ps1') -KeepWorkspaceSupervisor
            $plan = [pscustomobject]@{ ok = $true; backend = 'cpu'; device = $null; fit_target_mib = 192 }
            $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
        }
    }
    if ($plan) {
        $plan | Add-Member -NotePropertyName schemaVersion -NotePropertyValue 2 -Force
        $plan | Add-Member -NotePropertyName requestedBackend -NotePropertyValue $requestedBackend -Force
        $plan | Add-Member -NotePropertyName selectedBackend -NotePropertyValue $plan.backend -Force
        if (-not $plan.transport) { $plan | Add-Member -NotePropertyName transport -NotePropertyValue $(if ($plan.backend -eq 'cpu') { 'container' } else { 'native-windows' }) -Force }
        $containerProbe = Join-Path $PSScriptRoot 'accelerator/container-probe.json'
        if (Test-Path -LiteralPath $containerProbe) {
            $plan | Add-Member -NotePropertyName containerRejection -NotePropertyValue (Get-Content -LiteralPath $containerProbe -Raw | ConvertFrom-Json) -Force
        }
        $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
    }
    if ($plan -and $plan.backend -eq 'cpu') {
        # No native GPU service: the managed CPU sidecar container serves the
        # pinned runtime with GPU devices disabled.
        $env:PI_ACCELERATOR = 'cpu'
        $env:PI_GPU_DEVICE = 'none'
        $env:PI_FIT_TARGET = "$($plan.fit_target_mib)"
        $env:PI_EMBEDDING_DEVICE = 'cpu'
        $files += @('-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
    } elseif ($plan) {
        $env:PI_ACCELERATOR = $plan.backend
        $env:PI_GPU_DEVICE = $plan.device
        $env:PI_FIT_TARGET = "$($plan.fit_target_mib)"
        $env:PI_EMBEDDING_DEVICE = $plan.backend
        if ($plan.transport -eq 'container') {
            $files += @('-f','compose.accelerator.yaml','-f','compose.cuda.yaml')
        } else {
            $env:PI_NATIVE_LLAMA_ENDPOINT = $plan.endpoint
            $files += @('-f','compose.windows-gpu.yaml')
        }
    } else {
        # The plan could not be produced: fall back to the CPU sidecar.
        $env:PI_ACCELERATOR = 'cpu'
        $env:PI_GPU_DEVICE = 'none'
        $env:PI_FIT_TARGET = '192'
        $env:PI_EMBEDDING_DEVICE = 'cpu'
        $files += @('-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
    }
    $startupFailed = $false
    try {
        Invoke-WorkspaceCompose --env-file deployment.env @files @composeArgs
        $startupFailed = ($LASTEXITCODE -ne 0)
    } catch {
        if (-not $plan -or $plan.transport -ne 'container') { throw }
        $startupFailed = $true
    }
    if ($startupFailed -and $plan -and $plan.transport -eq 'container') {
        if ($strictAccelerator) { throw 'accelerator_strict_unavailable: container CUDA startup failed; CPU fallback disabled' }
        Write-Warning 'Container CUDA startup failed; retrying the CPU profile with the same verified model cache.'
        $env:PI_ACCELERATOR = 'cpu'
        $env:PI_EMBEDDING_DEVICE = 'cpu'
        $env:PI_GPU_DEVICE = 'none'
        $env:PI_FIT_TARGET = '192'
        $plan = [pscustomobject]@{ok=$true;backend='cpu';device='none';fit_target_mib=192}
        $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
        $files = @('-f','compose.yaml','-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
        Invoke-WorkspaceCompose --env-file deployment.env @files @composeArgs
        $startupFailed = ($LASTEXITCODE -ne 0)
    }
    if ($startupFailed) { throw 'Docker Compose failed' }
} finally {
    foreach ($item in Get-ChildItem Env:) {
        if (-not $savedEnvironment.ContainsKey($item.Name)) { [Environment]::SetEnvironmentVariable($item.Name, $null, 'Process') }
    }
    foreach ($key in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process') }
    Pop-Location
}
