# Stop containers and only the native accelerator started by this kit.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    # The complete service topology is used so every service of the
    # deployment is stopped. Orphans are never removed automatically: an
    # unrelated container in the same project must stay visible.
    & docker compose --env-file deployment.env -f compose.yaml -f compose.accelerator.yaml down
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop application containers' }
    $cache = Join-Path $PSScriptRoot 'accelerator'
    $pidFile = Join-Path $cache 'runtime.pid'
    if (Test-Path -LiteralPath $pidFile) {
        $runtimePid = [int](Get-Content -LiteralPath $pidFile)
        $process = Get-Process -Id $runtimePid -ErrorAction SilentlyContinue
        if ($process) {
            $prefix = [IO.Path]::GetFullPath($cache) + [IO.Path]::DirectorySeparatorChar
            if (-not $process.Path -or -not $process.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or $process.Name -ne 'llama-server') {
                throw 'Saved PID belongs to a different process; it was not stopped.'
            }
            Stop-Process -Id $runtimePid
        }
        Remove-Item -LiteralPath $pidFile
    }
} finally { Pop-Location }
