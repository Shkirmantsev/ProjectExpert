# Downloads only pinned public assets; keeps upstream DLLs and license notices.
#
# The backend is detected automatically: the pinned native llama.cpp runtime is
# probed for the candidate backends (CUDA first, then Vulkan) and the validated
# device is selected by the shared Python policy. When no GPU candidate
# validates, the caller falls back to the managed CPU sidecar container.
param(
    [ValidateSet('auto','cpu','vulkan','cuda')][string]$Backend = 'auto',
    [ValidateSet('gemma','gemma-torch')][string]$Model = 'gemma'
)
$ErrorActionPreference = 'Stop'
$lock = Get-Content (Join-Path $PSScriptRoot 'accelerator-lock.json') -Raw | ConvertFrom-Json
$modelSpec = $lock.models.$Model
if (-not $modelSpec) { throw "The deployment lock has no model record for '$Model'" }
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

# --- Cheap host hints -------------------------------------------------------
# These hints only decide which pinned archive is worth downloading. They never
# select a backend: the runtime's own --list-devices output is the only
# evidence that decides.
function Test-NvidiaPresent {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { return $true }
    return $false
}
function Test-VulkanLoaderPresent {
    foreach ($dir in @($env:SystemRoot, "${env:ProgramFiles}", "${env:ProgramFiles(x86)}")) {
        if (-not $dir) { continue }
        if (Test-Path -LiteralPath (Join-Path $dir 'System32\vulkan-1.dll')) { return $true }
    }
    return $false
}

# --- Candidate ordering -----------------------------------------------------
$candidates = @()
if ($Backend -eq 'auto') {
    if (Test-NvidiaPresent) { $candidates += 'cuda' }
    if (Test-VulkanLoaderPresent) { $candidates += 'vulkan' }
} else {
    $candidates += $Backend
}

# --- Native runtime acquisition and probing --------------------------------
$evidence = @()
$runtimeRoot = Join-Path $cache ("{0}-native" -f $lock.runtime_version)
$deviceOutput = @{}
foreach ($candidate in $candidates) {
    $assets = $lock.windows.$candidate
    if (-not $assets) {
        $evidence += @{ backend = $candidate; ok = $false; exit_code = -1
                        output = "no pinned native runtime is published for $candidate" }
        continue
    }
    $runtimeDir = Join-Path $runtimeRoot $candidate
    New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
    try {
    foreach ($asset in $assets) {
        $archive = Join-Path $cache $asset.name
        Get-VerifiedFile ("https://github.com/ggml-org/llama.cpp/releases/download/{0}/{1}" -f $lock.runtime_version,$asset.name) $archive $asset.sha256
        Expand-Archive -LiteralPath $archive -DestinationPath $runtimeDir -Force
    }
    $server = Get-ChildItem -LiteralPath $runtimeDir -Filter llama-server.exe -Recurse | Select-Object -First 1
    if (-not $server) {
        $evidence += @{ backend = $candidate; ok = $false; exit_code = -1
                        output = "the pinned archive did not contain llama-server.exe" }
        continue
    }
    $outFile = Join-Path $cache ("devices-{0}.txt" -f $candidate)
    $errFile = Join-Path $cache ("devices-{0}-error.txt" -f $candidate)
    $probe = Start-Process -FilePath $server.FullName -ArgumentList '--list-devices' -PassThru -NoNewWindow `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    if (-not $probe.WaitForExit(15000)) {
        Stop-Process -Id $probe.Id -ErrorAction SilentlyContinue
        throw 'GPU device probe timed out'
    }
    $probe.Refresh()
    $text = ''
    if (Test-Path -LiteralPath $outFile) { $text += (Get-Content -LiteralPath $outFile -Raw) }
    if (Test-Path -LiteralPath $errFile) { $text += (Get-Content -LiteralPath $errFile -Raw) }
    $deviceOutput[$candidate] = $text
    $evidence += @{ backend = $candidate
                    ok = ($probe.ExitCode -eq 0)
                    exit_code = $probe.ExitCode
                    output = $text }
    } catch {
        $evidence += @{ backend = $candidate; ok = $false; exit_code = -1; output = "runtime acquisition/probe failed: $_" }
    }
}

# The CPU profile is always valid: the managed sidecar container runs the
# pinned runtime with GPU devices disabled.
$evidence += @{ backend = 'cpu'; ok = $true; exit_code = 0; output = "Available devices:`n  (none)" }

$evidenceJson = @{ platform = 'windows'; candidates = $evidence } | ConvertTo-Json -Depth 6 -Compress
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($evidenceJson))

# --- The shared Python decision --------------------------------------------
# The decision is owned by the application code so the Windows and Linux
# launchers cannot drift apart. It runs in the application container.
# The application image entrypoint is already `python -m pi_platform.cli`, so
# the command arguments are the CLI subcommand path. The provisional CPU
# overlay supplies the complete service topology: a reduced file set would make
# the running sidecars look like orphans to Compose. The plan only runs the
# production service (--no-deps).
$composeArgs = @('--env-file','deployment.env','-f','compose.yaml','-f','compose.accelerator.yaml',
                 '-f','compose.cpu.yaml','run','--rm','--no-deps','-T','production',
                 'inference','plan','--evidence-b64',$encoded)
$planRaw = & docker compose @composeArgs 2>$null
if ($LASTEXITCODE -ne 0 -or -not $planRaw) {
    Write-Warning 'The inference plan was unavailable; falling back to the validated CPU profile.'
    [pscustomobject]@{ ok = $true; backend = 'cpu'; device = $null; fit_target_mib = 192
                       reason = 'inference plan unavailable'; rejected = @()
                       server_args = @(); compose = @{ PI_ACCELERATOR = 'cpu'; PI_GPU_DEVICE = 'none'; PI_FIT_TARGET = '192' } }
    exit 0
}
$plan = ($planRaw -join "`n") | ConvertFrom-Json
if (-not $plan.ok) {
    Write-Warning "The inference plan was invalid; falling back to the validated CPU profile. $($plan.error)"
    $plan = [pscustomobject]@{ ok = $true; backend = 'cpu'; device = $null; fit_target_mib = 192
                               reason = 'inference plan invalid'; rejected = @()
                               server_args = @(); compose = @{ PI_ACCELERATOR = 'cpu'; PI_GPU_DEVICE = 'none'; PI_FIT_TARGET = '192' } }
}

if ($plan.backend -eq 'cpu') {
    # No native service is started: the managed CPU sidecar container serves
    # the pinned runtime with GPU devices disabled.
    Write-Output "Selected inference backend: cpu (managed sidecar container)"
    if ($plan.rejected -and $plan.rejected.Count -gt 0) {
        $rejected = ($plan.rejected | ForEach-Object { "$($_.backend) ($($_.reason))" }) -join '; '
        Write-Output "Rejected inference candidates: $rejected"
    } else {
        Write-Output 'Rejected inference candidates: none'
    }
    $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cache 'plan.json') -Encoding UTF8
    exit 0
}

# --- Native GPU service -----------------------------------------------------
$backend = $plan.backend
$device = $plan.device
if (-not $device) { throw "The inference plan selected '$backend' without a device" }
$deviceText = $deviceOutput[$backend]
if ($deviceText -notmatch ("(?m)(?:^|\s)" + [regex]::Escape($device) + ":")) {
    throw "The selected device $device was not reported by the $backend runtime."
}
if ($Backend -ne 'auto' -and $Backend -ne $backend) {
    Write-Warning "The explicit backend '$Backend' did not validate; using the detected '$backend' backend."
}

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
    Write-Output "Selected inference backend: $backend (device $device; an instance is already running)"
    $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cache 'plan.json') -Encoding UTF8
    exit 0
}

# Download the weights only after the selected device has passed its probe.
Get-VerifiedFile $modelSpec.model_url (Join-Path $cache $modelSpec.model_filename) $modelSpec.model_sha256
if ($modelSpec.projector_filename) {
    Get-VerifiedFile $modelSpec.projector_url (Join-Path $cache $modelSpec.projector_filename) $modelSpec.projector_sha256
}

$runtimeDir = Join-Path $runtimeRoot $backend
$server = Get-ChildItem -LiteralPath $runtimeDir -Filter llama-server.exe -Recurse | Select-Object -First 1
if (-not $server) { throw "The pinned $backend runtime is not available in $runtimeDir" }

# The launch arguments come from the shared Python policy, with the native
# Windows paths substituted for the container paths.
$modelPath = Join-Path $cache $modelSpec.model_filename
$projectorPath = Join-Path $cache $modelSpec.projector_filename
$serverArgs = @()
foreach ($arg in $plan.server_args) {
    $value = [string]$arg
    if ($value -eq '/models/embeddinggemma-2-Q8_0.gguf') { $value = $modelPath }
    elseif ($value -eq '/models/mmproj-embeddinggemma-2-Q8_0.gguf') { $value = $projectorPath }
    elseif ($value -eq '/models/llama-api-key') { $value = $keyPath }
    $serverArgs += $value
}
$arguments = @($serverArgs | ForEach-Object { '"' + $_ + '"' })
$process = Start-Process -FilePath $server.FullName -ArgumentList $arguments -PassThru -NoNewWindow `
    -RedirectStandardOutput (Join-Path $cache 'runtime.log') -RedirectStandardError (Join-Path $cache 'runtime-error.log')
[IO.File]::WriteAllText((Join-Path $cache 'runtime.pid'), [string]$process.Id)
[IO.File]::WriteAllText((Join-Path $cache 'backend.txt'), $backend)
[IO.File]::WriteAllText((Join-Path $cache 'device.txt'), $device)
$ready = $false
for ($attempt = 0; $attempt -lt 120; $attempt++) {
    if ($process.HasExited) { throw 'The GPU runtime exited; inspect accelerator/runtime-error.log, or use the CPU profile.' }
    try {
        $models = Invoke-RestMethod -Uri 'http://127.0.0.1:8769/v1/models' -Headers @{Authorization="Bearer $token"} -TimeoutSec 2
        if ($models.data.id -contains $modelSpec.model_alias) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if ($process.HasExited -or -not $ready) { throw 'The GPU runtime did not become ready; using the CPU fallback.' }
Write-Output "Selected inference backend: $backend (device $device, fit target $($plan.fit_target_mib) MiB)"
$plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cache 'plan.json') -Encoding UTF8
