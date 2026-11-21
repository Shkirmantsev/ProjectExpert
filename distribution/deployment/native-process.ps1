# Short-lived verified native probes. .NET Process owns both asynchronous pipes;
# Start-Process ExitCode caching and PowerShell 5.1 stderr semantics are avoided.
function ConvertTo-NativeArgument([AllowEmptyString()][string]$Value) {
    # Windows CRT argv quoting, including backslashes before quotes/end quotes.
    return '"' + ([regex]::Replace(([regex]::Replace($Value, '(\\*)"', '$1$1\"')), '(\\+)$', '$1$1')) + '"'
}
function Invoke-PinnedNativeProbe {
    param([string]$Executable, [string[]]$Arguments = @('--list-devices'), [int]$TimeoutMs = 15000)
    $process = New-Object System.Diagnostics.Process
    $result = @{ok=$false; exit_code=-1; stdout=''; stderr=''; reason='native_probe_start_failed'; pid=$null}
    try {
        $info = New-Object System.Diagnostics.ProcessStartInfo
        $info.FileName = $Executable
        $info.Arguments = (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
        $info.WorkingDirectory = Split-Path -Parent $Executable
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        # Matching DLLs resolve from the isolated verified executable directory;
        # no unverified CUDA toolkit or user-controlled PATH DLLs are needed.
        $info.EnvironmentVariables['PATH'] = (Split-Path -Parent $Executable) + ';' + $env:SystemRoot + '\System32;' + $env:SystemRoot
        $process.StartInfo = $info
        if (-not $process.Start()) { return [pscustomobject]$result }
        $result.pid = $process.Id
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutMs)) {
            $result.reason = 'native_probe_timeout'
            $process.Kill()
            $process.WaitForExit(5000) | Out-Null
        } else {
            $result.exit_code = [int]$process.ExitCode
            $result.ok = $true
            $result.reason = $(if ($result.exit_code -eq 0) { 'completed' } else { 'native_probe_exit_nonzero' })
        }
        if ($stdout.Wait(5000)) { $result.stdout = $stdout.Result }
        if ($stderr.Wait(5000)) { $result.stderr = $stderr.Result }
    } catch {
        # Do not expose environment values or exception command strings.
        $result.stderr = 'Native process could not be started or collected.'
    } finally {
        if ($result.pid -and -not $process.HasExited) { $process.Kill(); $process.WaitForExit(5000) | Out-Null }
        $process.Dispose()
    }
    return [pscustomobject]$result
}

function Stop-OwnedNativeRuntime([string]$Cache) {
    $pidFile = Join-Path $Cache 'runtime.pid'
    if (-not (Test-Path -LiteralPath $pidFile)) { return }
    $runtimePid = [int](Get-Content -LiteralPath $pidFile)
    $process = Get-Process -Id $runtimePid -ErrorAction SilentlyContinue
    if ($process) {
        $prefix = [IO.Path]::GetFullPath($Cache) + [IO.Path]::DirectorySeparatorChar
        if (-not $process.Path -or -not $process.Path.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or $process.Name -ne 'llama-server') {
            throw 'Saved PID belongs to another process; nothing was stopped.'
        }
        $identityFile = Join-Path $Cache 'runtime-identity.json'
        if (Test-Path -LiteralPath $identityFile) {
            $identity = Get-Content -LiteralPath $identityFile -Raw | ConvertFrom-Json
            if ($identity.pid -ne $process.Id -or $identity.executable -ne $process.Path -or
                $identity.startedUtc -ne $process.StartTime.ToUniversalTime().ToString('o')) {
                throw 'Native process identity changed; nothing was stopped.'
            }
        }
        Stop-Process -Id $runtimePid
    }
    Remove-Item -LiteralPath $pidFile
}
function Get-PrivateWindowsBridgeAddresses {
    if (-not (Get-Command Get-NetIPAddress -ErrorAction SilentlyContinue)) { return }
    Get-NetIPAddress -AddressFamily IPv4 -AddressState Preferred -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -match '^vEthernet \((?:WSL|Docker|Rancher)' -and
            $_.IPAddress -match '^(?:10\.|172\.(?:1[6-9]|2[0-9]|3[01])\.|192\.168\.)' } |
        Select-Object -ExpandProperty IPAddress -Unique -First 8
}
