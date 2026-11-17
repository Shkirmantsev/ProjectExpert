# Real process primitives on PowerShell 5.1/7; no GPU, Docker or network.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../distribution/deployment/native-process.ps1')
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pi-probe-' + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $shell = (Get-Process -Id $PID).Path
    $fixture = Join-Path $temporary (([char]0x041F).ToString() + ' probe fixture.ps1')
    [IO.File]::WriteAllText($fixture, 'param([string]$Value) [Console]::Out.WriteLine($Value); [Console]::Error.WriteLine("probe-warning"); exit 23')
    $value = 'space "quoted" trailing\'
    $result = Invoke-PinnedNativeProbe -Executable $shell -Arguments @('-NoProfile','-NonInteractive','-File',$fixture,$value)
    if ($result.exit_code -ne 23 -or $result.stdout.Trim() -ne $value -or $result.stderr -notmatch 'probe-warning') { throw ('Native argv/status/streams lost: ' + ($result | ConvertTo-Json)) }
    [IO.File]::WriteAllText($fixture, '[Console]::Out.WriteLine(("x" * 200000)); [Console]::Error.WriteLine(("y" * 200000)); exit 0')
    $result = Invoke-PinnedNativeProbe -Executable $shell -Arguments @('-NoProfile','-NonInteractive','-File',$fixture)
    if ($result.exit_code -ne 0 -or $result.stdout.Length -lt 200000 -or $result.stderr.Length -lt 200000) { throw 'Concurrent pipe drain failed' }
    [IO.File]::WriteAllText($fixture, '[Console]::Error.WriteLine("stderr-only"); exit 0')
    $result = Invoke-PinnedNativeProbe -Executable $shell -Arguments @('-NoProfile','-NonInteractive','-File',$fixture)
    if ($result.exit_code -ne 0 -or $result.stdout -ne '' -or $result.stderr -notmatch 'stderr-only') { throw 'Immediate stderr-only exit lost' }
    [IO.File]::WriteAllText($fixture, 'Start-Sleep -Seconds 30')
    $result = Invoke-PinnedNativeProbe -Executable $shell -Arguments @('-NoProfile','-NonInteractive','-File',$fixture) -TimeoutMs 100
    if ($result.ok -or $result.reason -ne 'native_probe_timeout') { throw 'Timeout not reported' }
    if (Get-Process -Id $result.pid -ErrorAction SilentlyContinue) { throw 'Owned child leaked' }
    $result = Invoke-PinnedNativeProbe -Executable (Join-Path $temporary 'missing.exe')
    if ($result.ok -or $result.reason -ne 'native_probe_start_failed') { throw 'Launch failure not reported' }
    if ($ErrorActionPreference -ne 'Stop') { throw 'Caller preference changed' }
    Write-Output 'PASS: real probe argv, exit0/23, concurrent streams, timeout cleanup and start failure'
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
$global:LASTEXITCODE = 0
