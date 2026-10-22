# General Compose wrapper for product Make targets on Windows.
$ErrorActionPreference = 'Stop'
$composeArgs = $args
Push-Location $PSScriptRoot
try {
    $backend = $env:PI_ACCELERATOR
    if (-not $backend) {
        $line = Get-Content deployment.env | Where-Object { $_ -match '^PI_ACCELERATOR=' } | Select-Object -Last 1
        if ($line) { $backend = $line.Split('=', 2)[1] } else { $backend = 'cpu' }
    }
    $model = $env:PI_EMBEDDING_MODEL
    if (-not $model) {
        $line = Get-Content deployment.env | Where-Object { $_ -match '^PI_EMBEDDING_MODEL=' } | Select-Object -Last 1
        if ($line) { $model = $line.Split('=', 2)[1] } else { $model = 'qwen' }
    }
    if ($model -notin @('gemma','qwen','gemma-gguf','qwen-gguf')) { throw 'Unknown embedding model' }
    if ($composeArgs -contains 'down') {
        & (Join-Path $PSScriptRoot 'stop.ps1')
        exit 0
    }
    $files = @('-f', 'compose.yaml')
    if ($backend -in @('vulkan','cuda')) {
        $env:PI_ACCELERATOR = $backend
        $env:PI_RUNTIME_MODEL = 'qwen-gguf'
        if ($model -like 'gemma*') { $env:PI_RUNTIME_MODEL = 'gemma-gguf' }
        if ($composeArgs -contains 'up') { & (Join-Path $PSScriptRoot 'setup-windows-accelerator.ps1') -Backend $backend -Model $env:PI_RUNTIME_MODEL }
        $files += @('-f', 'compose.windows-gpu.yaml')
    } elseif ($backend -eq 'cpu' -and $model -like '*-gguf') {
        $files += @('-f','compose.accelerator.yaml','-f','compose.cpu.yaml')
        if ($model -eq 'gemma-gguf') { $files += @('-f','compose.gemma-gguf.yaml') }
    } elseif ($backend -ne 'cpu') { throw 'PI_ACCELERATOR must be cpu, vulkan or cuda' }
    if ($backend -eq 'cpu') { $env:PI_EMBEDDING_DEVICE = 'cpu' }
    docker compose --env-file deployment.env @files @composeArgs
    if ($LASTEXITCODE -ne 0) { throw 'Docker Compose failed' }
} finally { Pop-Location }
