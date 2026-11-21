# Extracts only the reviewed immutable OCI assets; never downloads host models or runtimes.
#
# The backend is detected automatically: the pinned native llama.cpp runtime is
# probed for the candidate backends (CUDA first, then Vulkan) and the validated
# device is selected by the shared Python policy. When no GPU candidate
# validates, the caller falls back to the managed CPU sidecar container.
param(
    [ValidateSet('auto','cpu','vulkan','cuda')][string]$Backend = 'auto',
    [ValidateSet('gemma','gemma-torch')][string]$Model = 'gemma',
    [ValidateRange(1,65535)][int]$Port = 8769,
    [switch]$RepairAssets,
    [switch]$AssetsOnly
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'native-process.ps1')
. (Join-Path $PSScriptRoot 'native-runtime-assets.ps1')
$lock = Get-Content (Join-Path $PSScriptRoot 'accelerator-lock.json') -Raw | ConvertFrom-Json
$modelSpec = $lock.models.$Model
if (-not $modelSpec) { throw "The deployment lock has no model record for '$Model'" }
$cache = Join-Path $PSScriptRoot 'accelerator'
New-Item -ItemType Directory -Force -Path $cache | Out-Null

# Keep the complete inventory and notices together; verify before executing any EXE.
. (Join-Path $PSScriptRoot 'workspace.ps1')
$assetImage = Get-WorkspaceValue 'PI_ASSET_IMAGE'
$manifestDigest = Get-WorkspaceValue 'PI_ASSET_MANIFEST_SHA256'
if ($assetImage -notmatch '^ghcr\.io/shkirmantsev/project-intelligence-assets@sha256:[0-9a-f]{64}$' -or
    $manifestDigest -notmatch '^[0-9a-f]{64}$') {
    throw 'Missing reviewed offline asset release. Upgrade the kit with --upgrade and review preserved deployment.env; native setup will not download from HF or GitHub.'
}
$offlineRoot = Join-Path $cache ("asset-pack-" + $manifestDigest)
$publishedRoot = $offlineRoot
$stagedAssets = $false
if ($RepairAssets -or -not (Test-Path -LiteralPath $publishedRoot)) {
    $offlineRoot = $publishedRoot + '.staging-' + [Guid]::NewGuid().ToString('N')
    $stagedAssets = $true
}
if (-not (Test-Path -LiteralPath $offlineRoot)) {
    New-Item -ItemType Directory -Path $offlineRoot | Out-Null
    $assetContainer = $null
    try {
        $assetContainer = docker create --pull never $assetImage
        if ($LASTEXITCODE -ne 0) { throw 'Cannot create the pinned offline asset container' }
        docker cp "${assetContainer}:/opt/projectexpert-assets/." $offlineRoot
        if ($LASTEXITCODE -ne 0) { throw 'Cannot extract the pinned offline assets' }
    } catch {
        Remove-Item -LiteralPath $offlineRoot -Recurse -Force
        throw
    } finally {
        if ($assetContainer) { docker rm $assetContainer | Out-Null }
    }
}
Assert-NativeAssetDirectory $offlineRoot
$appImage = Get-WorkspaceValue 'PI_IMAGE'
if (-not $appImage) { throw 'Missing published kit application image: set PI_IMAGE or upgrade the matching kit' }
$diagnosticPath = Join-Path $cache 'asset-verification.json'
$previousErrorAction = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    $verificationOutput = @(docker run --rm --network none --entrypoint python -v "${offlineRoot}:/pack:ro" $appImage `
        -m pi_platform.deployment.offline_assets --root /pack --manifest-sha256 $manifestDigest --diagnostic-json 2>&1)
    $verificationExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousErrorAction }
$verification = $null
try { $verification = ($verificationOutput -join "`n") | ConvertFrom-Json } catch { }
$verificationCode = 'verifier-container-failed'
if ($verification -and $verification.code) { $verificationCode = [string]$verification.code }
$diagnostic = @{schema_version=1; stage='offline-pack-verification'; code=$verificationCode;
    requested_backend=$Backend; application_image=$appImage; asset_image=$assetImage;
    expected_manifest_sha256=$manifestDigest; exit_code=$verificationExit; staged=$stagedAssets}
if ($verification -and $verification.asset) { $diagnostic.asset = $verification.asset }
foreach ($field in @('actual_manifest_sha256','expected_asset_sha256','actual_asset_sha256')) {
    if ($verification -and $verification.$field) { $diagnostic[$field] = $verification.$field }
}
$diagnostic | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ($diagnosticPath + '.tmp') -Encoding UTF8
Move-Item -LiteralPath ($diagnosticPath + '.tmp') -Destination $diagnosticPath -Force
if ($verificationExit -ne 0 -or -not $verification -or -not $verification.ok) {
    # Discard only this invocation's new temporary extraction. Existing packs stay intact.
    if ($stagedAssets) { Remove-Item -LiteralPath $offlineRoot -Recurse -Force -ErrorAction SilentlyContinue }
    throw "Offline asset verification failed [$verificationCode]; inspect accelerator/asset-verification.json. Existing packs are preserved. Retry with -RepairAssets after reviewing the paired image/asset pins."
}
if ($stagedAssets) {
    if (Test-Path -LiteralPath $publishedRoot) {
        # Explicit repair preserves the old pack until the replacement verifies.
        Move-Item -LiteralPath $publishedRoot -Destination ($publishedRoot + '.previous-' + [Guid]::NewGuid().ToString('N'))
    }
    Move-Item -LiteralPath $offlineRoot -Destination $publishedRoot
    $offlineRoot = $publishedRoot
}
if ($AssetsOnly) {
    Write-Output 'Pinned offline assets verified, including the native Vulkan runtime.'
    return
}

function Get-VerifiedFile([string]$Name, [string]$Path, [string]$Hash) {
    $source = Join-Path (Join-Path $offlineRoot 'embedding') $Name
    if (-not (Test-Path -LiteralPath $source) -or
        (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $Hash) {
        throw "Missing or corrupt offline embedding asset: $Name"
    }
    if ((Test-Path -LiteralPath $Path) -and ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Hash)) { return }
    Copy-Item -LiteralPath $source -Destination $Path -Force
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash) { throw 'Offline copy checksum mismatch' }
}

# --- Candidate ordering -----------------------------------------------------
$candidates = @()
if ($Backend -eq 'auto') {
    # An exact runtime probe decides availability, not PATH/driver hints. Intel
    # iGPU Vulkan and NVIDIA CUDA remain discoverable without nvidia-smi on PATH.
    $candidates += @('cuda', 'vulkan')
} else {
    $candidates += $Backend
}

# --- Native runtime acquisition and probing --------------------------------
$evidence = @()
$runtimeRoot = Join-Path $offlineRoot 'windows'
$deviceOutput = @{}
$runtimeDirs = @{}
$includedNative = @((Get-Content (Join-Path $offlineRoot 'manifest.json') -Raw | ConvertFrom-Json).native_backends)
foreach ($candidate in $candidates) {
    try {
    if ($candidate -in $includedNative) {
        $runtimeDir = Join-Path $runtimeRoot $candidate
    } elseif ($candidate -eq 'cuda') {
        $runtimeDir = Resolve-OptionalNativeCuda $appImage $manifestDigest
    } else {
        throw "native_pack_missing: no verified runtime for $candidate"
    }
    $runtimeDirs[$candidate] = $runtimeDir
    $server = Get-ChildItem -LiteralPath $runtimeDir -Filter llama-server.exe -Recurse | Select-Object -First 1
    if (-not $server) {
        $evidence += @{ backend = $candidate; ok = $false; exit_code = -1
                        output = "the pinned archive did not contain llama-server.exe" }
        continue
    }
    $outFile = Join-Path $cache ("devices-{0}.txt" -f $candidate)
    $errFile = Join-Path $cache ("devices-{0}-error.txt" -f $candidate)
    $probe = Invoke-PinnedNativeProbe -Executable $server.FullName -Arguments @('--list-devices')
    [IO.File]::WriteAllText($outFile, $probe.stdout)
    [IO.File]::WriteAllText($errFile, $probe.stderr)
    if (-not $probe.ok) { throw $probe.reason }
    $text = $probe.stdout + "`n" + $probe.stderr
    $pinned = Get-WorkspaceValue 'PI_GPU_DEVICE'
    if ($pinned) {
        $match = [regex]::Match($text, '(?m)^\s*' + [regex]::Escape($pinned) + ':.*$')
        if ($match.Success) { $text = $match.Value }
        else { throw "native_device_not_found: requested device $pinned was not reported by $candidate" }
    }
    $deviceOutput[$candidate] = $text
    $evidence += @{ backend = $candidate
                    ok = ($probe.exit_code -eq 0)
                    reason_code = $probe.reason
                    exit_code = $probe.exit_code
                    output = $text }
    } catch {
        $message = [string]$_
        $code = 'backend_probe_failed'
        if ($message -match '(native_[a-z_]+)') { $code = $Matches[1] }
        $evidence += @{ backend = $candidate; ok = $false; exit_code = -1; reason_code = $code; output = $message }
    }
}

# The CPU profile is always valid: the managed sidecar container runs the
# pinned runtime with GPU devices disabled.
$evidence += @{ backend = 'cpu'; ok = $true; exit_code = 0; output = "Available devices:`n  (none)" }

@{requestedBackend=$Backend; candidates=$evidence} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cache 'probes.json') -Encoding UTF8
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
                 'inference','plan','--host','0.0.0.0','--port',"$Port",'--evidence-b64',$encoded)
. (Join-Path $PSScriptRoot 'workspace.ps1')
$planRaw = Invoke-WorkspaceCompose @composeArgs 2>$null
if ($LASTEXITCODE -ne 0 -or -not $planRaw) {
    Write-Warning 'The inference plan was unavailable; falling back to the validated CPU profile.'
    throw 'inference_plan_unavailable: cannot validate native GPU selection'
}
$plan = ($planRaw -join "`n") | ConvertFrom-Json
if (-not $plan.ok) {
    Write-Warning "The inference plan was invalid; falling back to the validated CPU profile. $($plan.error)"
    $plan = [pscustomobject]@{ ok = $true; backend = 'cpu'; device = $null; fit_target_mib = 192
                               reason = 'inference plan invalid'; rejected = @()
                               server_args = @(); compose = @{ PI_ACCELERATOR = 'cpu'; PI_GPU_DEVICE = 'none'; PI_FIT_TARGET = '192' } }
}

$plan | Add-Member -NotePropertyName schemaVersion -NotePropertyValue 2 -Force
$plan | Add-Member -NotePropertyName requestedBackend -NotePropertyValue $Backend -Force
$plan | Add-Member -NotePropertyName selectedBackend -NotePropertyValue $plan.backend -Force
$plan | Add-Member -NotePropertyName transport -NotePropertyValue $(if ($plan.backend -eq 'cpu') { 'container' } else { 'native-windows' }) -Force
$plan | Add-Member -NotePropertyName rejections -NotePropertyValue @($evidence | Where-Object { -not $_.ok }) -Force
$rejectionCode = $null
if ($plan.backend -eq 'cpu' -and $Backend -ne 'cpu') { $rejectionCode = @($evidence | Where-Object { -not $_.ok } | Select-Object -First 1)[0].reason_code }
$plan | Add-Member -NotePropertyName rejection_code -NotePropertyValue $rejectionCode -Force
$plan | Add-Member -NotePropertyName primaryManifestSha256 -NotePropertyValue $manifestDigest -Force
$plan | Add-Member -NotePropertyName nativeCudaManifestSha256 -NotePropertyValue (Get-WorkspaceValue 'PI_NATIVE_CUDA_MANIFEST_SHA256') -Force

if ($plan.backend -eq 'cpu') {
    # No native service is started: the managed CPU sidecar container serves
    # the pinned runtime with GPU devices disabled.
    Write-Output "Selected inference backend: cpu (managed sidecar container)"
    if ($Backend -ne 'cpu') { Write-Warning ('GPU unavailable: ' + (($plan.rejections | ForEach-Object { $_.reason_code + ': ' + $_.output }) -join '; ')) }
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

# Provision verified offline weights after the selected device has passed its probe.
Get-VerifiedFile $modelSpec.model_filename (Join-Path $cache $modelSpec.model_filename) $modelSpec.model_sha256
if ($modelSpec.projector_filename) {
    Get-VerifiedFile $modelSpec.projector_filename (Join-Path $cache $modelSpec.projector_filename) $modelSpec.projector_sha256
}

$runtimeDir = $runtimeDirs[$backend]
$server = Get-ChildItem -LiteralPath $runtimeDir -Filter llama-server.exe -Recurse | Select-Object -First 1
if (-not $server) { throw "The pinned $backend runtime is not available in $runtimeDir" }

function Test-NativeServingPath {
    $routeArgs = @('--model', $modelSpec.model_alias, '--port', "$Port")
    if (Get-Command Get-PrivateWindowsBridgeAddresses -ErrorAction SilentlyContinue) {
        $addresses = @(Get-PrivateWindowsBridgeAddresses)
        foreach ($address in $addresses) { $routeArgs += @('--host-ip', $address) }
    }
    $raw = Invoke-WorkspaceCompose --env-file deployment.env -f compose.yaml -f compose.windows-gpu.yaml `
        run --rm --no-deps -T production inference native-route @routeArgs 2>$null
    $routeExit = $LASTEXITCODE
    $result = $null
    try { $result = ($raw -join "`n") | ConvertFrom-Json } catch { }
    if ($result) {
        $result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $cache 'route-probe.json') -Encoding UTF8
    }
    if ($routeExit -ne 0 -or -not $result.ok -or $result.endpoint -cnotmatch "^http://[\d.]+:${Port}$") {
        $reason = 'probe_unavailable'
        if ($result.code -cmatch '^[a-z_]+$') { $reason = $result.code }
        $codes = @($result.attempts | ForEach-Object { $_.code } | Where-Object { $_ -cmatch '^[a-z_0-9]+$' })
        throw "native_embedding_smoke_failed: $reason $($codes -join ', '); check container-to-host networking and firewall policy"
    }
    $plan | Add-Member -NotePropertyName endpoint -NotePropertyValue $result.endpoint -Force
    $plan | Add-Member -NotePropertyName embeddingSmoke -NotePropertyValue @{ok=$true;dimension=768;medianMs=$result.median_ms;route=$result.route} -Force
}

# An already-running matching service can be reused, but never kill a process by port.
$localModelsUrl = "http://127.0.0.1:${Port}/v1/models"
$models = $null
try {
    $models = Invoke-RestMethod -Uri $localModelsUrl -Headers @{Authorization="Bearer $token"} -TimeoutSec 3 -MaximumRedirection 0
} catch { }
if ($models) {
    $identityPath = Join-Path $cache 'runtime-identity.json'
    if (-not (Test-Path -LiteralPath $identityPath)) { throw 'native_server_conflict: stop the prior accelerator explicitly before reusing an unowned endpoint' }
    $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
    $owned = Get-Process -Id $identity.pid -ErrorAction SilentlyContinue
    if (-not $owned -or $owned.Path -ne $server.FullName -or $identity.backend -ne $backend -or $identity.device -ne $device -or
        $identity.startedUtc -ne $owned.StartTime.ToUniversalTime().ToString('o') -or
        ($identity.port -and $identity.port -ne $Port)) {
        throw 'native_server_conflict: stop the previous accelerator before switching runtime or device'
    }
    if ($models.data.id -notcontains $modelSpec.model_alias) { throw 'Stop the previous accelerator with stop.ps1 before switching models.' }
    Test-NativeServingPath
    Write-Output "Selected inference backend: $backend (device $device; an instance is already running)"
    $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cache 'plan.json') -Encoding UTF8
    exit 0
}
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw 'native_server_conflict: the requested port is already in use; select another port or stop the existing server'
    }
}
$identityPath = Join-Path $cache 'runtime-identity.json'
if (Test-Path -LiteralPath $identityPath) {
    $identity = Get-Content -LiteralPath $identityPath -Raw | ConvertFrom-Json
    $prior = Get-Process -Id $identity.pid -ErrorAction SilentlyContinue
    if ($prior -and $prior.StartTime.ToUniversalTime().ToString('o') -eq $identity.startedUtc) {
        throw 'native_server_conflict: stop the kit-owned native runtime before changing its port'
    }
}

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
$arguments = @($serverArgs | ForEach-Object { ConvertTo-NativeArgument $_ })
$previousNativePath = $env:PATH
try {
    $env:PATH = $server.DirectoryName + ';' + $env:SystemRoot + '\System32;' + $env:SystemRoot
    $process = Start-Process -FilePath $server.FullName -ArgumentList $arguments -WorkingDirectory $server.DirectoryName -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $cache 'runtime.log') -RedirectStandardError (Join-Path $cache 'runtime-error.log')
} finally { $env:PATH = $previousNativePath }
$nativeReady = $false
try {
    [IO.File]::WriteAllText((Join-Path $cache 'runtime.pid'), [string]$process.Id)
    @{pid=$process.Id;executable=$server.FullName;backend=$backend;device=$device;port=$Port;startedUtc=$process.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cache 'runtime-identity.json') -Encoding UTF8

    [IO.File]::WriteAllText((Join-Path $cache 'backend.txt'), $backend)
    [IO.File]::WriteAllText((Join-Path $cache 'device.txt'), $device)
    $ready = $false
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if ($process.HasExited) {
            $failureCode = 'native_server_exit'
            $errorLog = Join-Path $cache 'runtime-error.log'
            if ((Test-Path -LiteralPath $errorLog) -and ((Get-Content -LiteralPath $errorLog -Tail 100) -match 'out of memory|failed to allocate|insufficient.*memory')) { $failureCode = 'model_not_fit' }
            throw "${failureCode}: inspect private accelerator/runtime-error.log; model did not become ready"
        }
        try {
            $models = Invoke-RestMethod -Uri $localModelsUrl -Headers @{Authorization="Bearer $token"} -TimeoutSec 2 -MaximumRedirection 0
            if ($models.data.id -contains $modelSpec.model_alias) { $ready = $true; break }
        } catch { }
        Start-Sleep -Seconds 2
    }
    if ($process.HasExited -or -not $ready) { Stop-OwnedNativeRuntime $cache; throw 'native_server_not_ready: model did not load within the bounded timeout' }
    try { Test-NativeServingPath } catch { Stop-OwnedNativeRuntime $cache; throw }
    Write-Output "Selected inference backend: $backend (device $device, fit target $($plan.fit_target_mib) MiB)"
    $plan | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cache 'plan.json') -Encoding UTF8

    $nativeReady = $true
} finally {
    # Only this invocation's child may be cleaned up on partial startup.
    if (-not $nativeReady -and -not $process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
}
