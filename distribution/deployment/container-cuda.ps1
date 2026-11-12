# Managed CUDA uses the container's runtime libraries and the host GPU driver.
# It never installs or replaces host drivers, toolkits, or system DLLs.
function Get-ContainerCudaPlan([string]$RequestedBackend) {
    if ($RequestedBackend -notin @('auto','cuda')) { return $null }
    if ($RequestedBackend -eq 'auto' -and -not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { return $null }
    $cudaFiles = @('-f','compose.yaml','-f','compose.accelerator.yaml','-f','compose.cuda.yaml')
    try {
        $probe = Invoke-WorkspaceCompose --env-file deployment.env @cudaFiles `
            run --rm --no-deps -T embeddings --list-devices 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $pinned = Get-WorkspaceValue 'PI_GPU_DEVICE'
        if ($pinned) {
            $match = [regex]::Match(($probe -join "`n"), '(?m)^\s*' + [regex]::Escape($pinned) + ':.*$')
            if (-not $match.Success) { return $null }
            $probe = @($match.Value)
        }
        $evidence = @{ platform = 'linux'; candidates = @(
            @{ backend = 'cuda'; ok = $true; exit_code = 0; output = ($probe -join "`n") }
        ) } | ConvertTo-Json -Depth 6 -Compress
        $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($evidence))
        $raw = Invoke-WorkspaceCompose --env-file deployment.env -f compose.yaml `
            -f compose.accelerator.yaml -f compose.cpu.yaml `
            run --rm --no-deps -T production inference plan --evidence-b64 $encoded 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
        $plan = ($raw -join "`n") | ConvertFrom-Json
        if (-not $plan.ok -or $plan.backend -ne 'cuda' -or -not $plan.device) { return $null }
        $plan | Add-Member -NotePropertyName transport -NotePropertyValue container -Force
        $cache = Join-Path $PSScriptRoot 'accelerator'
        New-Item -ItemType Directory -Force -Path $cache | Out-Null
        [IO.File]::WriteAllText((Join-Path $cache 'devices-cuda.txt'), ($probe -join "`n"))
        return $plan
    } catch {
        Write-Warning "Container CUDA probe unavailable; checking the existing native fallback. $_"
        return $null
    }
}

function Start-ContainerCudaRuntime($Plan) {
    $env:PI_GPU_DEVICE = $Plan.device
    $env:PI_FIT_TARGET = "$($Plan.fit_target_mib)"
    try {
        Invoke-WorkspaceCompose --env-file deployment.env -f compose.yaml `
            -f compose.accelerator.yaml -f compose.cuda.yaml `
            up -d --wait --wait-timeout 1800 embeddings *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}
