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
$composeArgs = $args


function Measure-Endpoint([string]$Endpoint) {
    # Measure the embedding latency of a running runtime. Returns the median
    # in milliseconds, or $null when the runtime cannot be measured.
    $benchmarkFiles = @('-f', 'compose.yaml')
    if ($Endpoint -like '*host.docker.internal*') {
        $benchmarkFiles += @('-f', 'compose.windows-gpu.yaml')
    }
    $raw = & docker compose --env-file deployment.env @benchmarkFiles `
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
    & docker compose --env-file deployment.env @files up -d --wait --wait-timeout 1800 embeddings *> $null
    if ($LASTEXITCODE -ne 0) { return $null }
    try {
        return Measure-Endpoint 'http://embeddings:8769'
    } finally {
        & docker compose --env-file deployment.env @files stop embeddings *> $null
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
    $raw = & docker compose --env-file deployment.env -f compose.yaml `
        run --rm --no-deps -T production inference plan --evidence-b64 $encoded 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    try {
        return (($raw -join "`n") | ConvertFrom-Json)
    } catch {
        return $null
    }
}
Push-Location $PSScriptRoot
try {
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
    if ($backend -notin @('auto','cpu','vulkan','cuda')) { throw 'PI_ACCELERATOR must be auto, cpu, vulkan or cuda' }
    if ($composeArgs -contains 'down') {
        & (Join-Path $PSScriptRoot 'stop.ps1')
        exit 0
    }
    $files = @('-f', 'compose.yaml')
    if ($model -eq 'gemma-torch') {
        # Native PyTorch binding: no llama.cpp runtime, no probing.
        $env:PI_EMBEDDING_MODEL = 'gemma-torch'
        $env:PI_EMBEDDING_DEVICE = 'cpu'
        docker compose --env-file deployment.env @files @composeArgs
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
        exit 0
    }
    $env:PI_EMBEDDING_MODEL = 'gemma'
    $planPath = Join-Path $PSScriptRoot 'accelerator\plan.json'
    if ($composeArgs -notcontains 'up') {
        $savedBackend = 'cpu'
        if (Test-Path -LiteralPath $planPath) {
            $savedPlan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
            $savedBackend = $savedPlan.backend
        }
        if ($savedBackend -eq 'cpu') {
            $files += @('-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
        } else {
            $files += @('-f','compose.windows-gpu.yaml')
            $env:PI_ACCELERATOR = $savedBackend
        }
        & docker compose --env-file deployment.env @files @composeArgs
        if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
        exit 0
    }
    if (Test-Path -LiteralPath $planPath) { Remove-Item -LiteralPath $planPath -Force }
    # The setup script detects the backend, applies the shared Python policy
    # and starts the native service when a GPU candidate validates.
    try {
        & (Join-Path $PSScriptRoot 'setup-windows-accelerator.ps1') -Backend $backend -Model 'gemma'
    } catch {
        Write-Warning "Native GPU setup failed; using the CPU sidecar. $_"
        & (Join-Path $PSScriptRoot 'stop.ps1')
        if (Test-Path -LiteralPath $planPath) { Remove-Item -LiteralPath $planPath -Force }
    }
    $plan = $null
    if (Test-Path -LiteralPath $planPath) {
        $plan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
    }
    if ($backend -eq 'auto' -and $plan -and $plan.backend -ne 'cpu') {
        # The GPU works. Measure it against the CPU baseline: a GPU that is
        # not measurably faster is not worth its complexity.
        $gpuMedian = Measure-Endpoint 'http://host.docker.internal:8769'
        $cpuMedian = Measure-CpuSidecar
        if ($gpuMedian -and $cpuMedian) {
            $measurements = @{ cpu = [double]$cpuMedian; $plan.backend = [double]$gpuMedian }
            $decision = Resolve-PlanWithMeasurements $plan $measurements
            if (-not $decision -or -not $decision.ok -or $decision.backend -eq 'cpu') {
                Write-Output "The $plan.backend profile is not faster than the CPU baseline; using the CPU profile."
                Write-Output "Rejected inference candidates: $($plan.backend) (not faster than the cpu baseline)"
                & (Join-Path $PSScriptRoot 'stop.ps1')
                $plan = [pscustomobject]@{ ok = $true; backend = 'cpu'; device = $null; fit_target_mib = 192 }
                $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
            } else {
                Write-Output "Measured median latency: $($plan.backend)=$gpuMedian, cpu=$cpuMedian"
            }
        } else {
            Write-Warning 'Could not measure both GPU and CPU; using the CPU profile.'
            & (Join-Path $PSScriptRoot 'stop.ps1')
            $plan = [pscustomobject]@{ ok = $true; backend = 'cpu'; device = $null; fit_target_mib = 192 }
            $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $planPath -Encoding UTF8
        }
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
        $files += @('-f','compose.windows-gpu.yaml')
    } else {
        # The plan could not be produced: fall back to the CPU sidecar.
        $env:PI_ACCELERATOR = 'cpu'
        $env:PI_GPU_DEVICE = 'none'
        $env:PI_FIT_TARGET = '192'
        $env:PI_EMBEDDING_DEVICE = 'cpu'
        $files += @('-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
    }
    docker compose --env-file deployment.env @files @composeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
} finally { Pop-Location }
