# Downloads only pinned public assets; keeps upstream DLLs and license notices.
param([ValidateSet('vulkan','cuda')][string]$Backend, [ValidateSet('qwen-gguf','gemma-gguf')][string]$Model = 'qwen-gguf')
$ErrorActionPreference = 'Stop'
$lock = Get-Content (Join-Path $PSScriptRoot 'accelerator-lock.json') -Raw | ConvertFrom-Json
$modelSpec = $lock.models.$Model
$cache = Join-Path $PSScriptRoot 'accelerator'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
function Get-VerifiedFile([string]$Url, [string]$Path, [string]$Hash) {
    if ((Test-Path -LiteralPath $Path) -and ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Hash)) { return }
    $partial = "$Path.partial"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $partial
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $Hash) { throw 'Download checksum mismatch' }
        Move-Item -Force -LiteralPath $partial -Destination $Path
    } finally { if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial } }
}
$modelPath = Join-Path $cache $modelSpec.model_filename
Get-VerifiedFile $modelSpec.model_url $modelPath $modelSpec.model_sha256
$projector = $null
if ($modelSpec.projector_filename) {
    $projector = Join-Path $cache $modelSpec.projector_filename
    Get-VerifiedFile $modelSpec.projector_url $projector $modelSpec.projector_sha256
}
$runtime = Join-Path $cache ("{0}-{1}" -f $lock.runtime_version, $Backend)
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
foreach ($asset in $lock.windows.$Backend) {
    $archive = Join-Path $cache $asset.name
    Get-VerifiedFile ("https://github.com/ggml-org/llama.cpp/releases/download/{0}/{1}" -f $lock.runtime_version,$asset.name) $archive $asset.sha256
    Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
}
$server = Get-ChildItem -LiteralPath $runtime -Filter llama-server.exe -Recurse | Select-Object -First 1
if (-not $server) { throw 'Pinned archive did not contain llama-server.exe' }
$keyPath = Join-Path $cache 'llama-api-key'
if (-not (Test-Path -LiteralPath $keyPath)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [IO.File]::WriteAllText($keyPath, ([BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant()))
}
$token = [IO.File]::ReadAllText($keyPath).Trim()
if ($token.Length -lt 32) { throw 'Invalid runtime key file' }
# An already-running matching service can be reused, but never kill a process by port.
$models = $null
try {
    $models = Invoke-RestMethod -Uri 'http://127.0.0.1:8769/v1/models' -Headers @{Authorization="Bearer $token"} -TimeoutSec 3
} catch { }
if ($models) {
    if ($models.data.id -notcontains $modelSpec.model_alias) { throw 'Stop the previous accelerator with stop.ps1 before switching models.' }
    $runningBackend = Get-Content (Join-Path $cache 'backend.txt') -ErrorAction SilentlyContinue
    if ($runningBackend -eq $Backend) { return }
    throw 'Stop the previous accelerator before switching device.'
}
$device = 'Vulkan0'
if ($Backend -eq 'cuda') { $device = 'CUDA0' }
$probe = Start-Process -FilePath $server.FullName -ArgumentList '--list-devices' -Wait -PassThru -NoNewWindow -RedirectStandardOutput (Join-Path $cache 'devices.txt') -RedirectStandardError (Join-Path $cache 'devices-error.txt')
$devices = (Get-Content (Join-Path $cache 'devices.txt') -Raw) + (Get-Content (Join-Path $cache 'devices-error.txt') -Raw)
if ($probe.ExitCode -ne 0 -or $devices -notmatch [regex]::Escape($device)) {
    throw "No $device device found. Install its vendor driver, or select PI_ACCELERATOR=cpu. See accelerator/devices-error.txt."
}
$arguments = @('--model', ('"'+$modelPath+'"'), '--alias', $modelSpec.model_alias, '--embeddings', '--pooling', $modelSpec.pooling, '--ctx-size', '8192', '--batch-size', '8192', '--ubatch-size', '8192', '--parallel', '1', '--n-gpu-layers', '99', '--device', $device, '--host', '0.0.0.0', '--port', '8769', '--api-key-file', ('"'+$keyPath+'"'))
if ($projector) { $arguments += @('--mmproj', ('"'+$projector+'"')) }
$process = Start-Process -FilePath $server.FullName -ArgumentList $arguments -PassThru -NoNewWindow -RedirectStandardOutput (Join-Path $cache 'runtime.log') -RedirectStandardError (Join-Path $cache 'runtime-error.log')
[IO.File]::WriteAllText((Join-Path $cache 'runtime.pid'), [string]$process.Id)
[IO.File]::WriteAllText((Join-Path $cache 'backend.txt'), $Backend)
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ($process.HasExited) { throw 'GPU runtime exited; inspect accelerator/runtime-error.log, or select CPU.' }
    try {
        $models = Invoke-RestMethod -Uri 'http://127.0.0.1:8769/v1/models' -Headers @{Authorization="Bearer $token"} -TimeoutSec 2
        if ($models.data.id -contains $modelSpec.model_alias) { return }
    } catch { }
    Start-Sleep -Seconds 2
}
throw 'GPU model startup timed out; inspect accelerator/runtime-error.log.'
