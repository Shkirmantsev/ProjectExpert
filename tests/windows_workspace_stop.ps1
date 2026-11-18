# Execute the real launcher ordering; the helper process is the controlled boundary.
$ErrorActionPreference = 'Stop'
$previousMode = $env:PI_WORKSPACE_MODE
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pi-stop-' + [Guid]::NewGuid())
try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    Copy-Item (Join-Path $PSScriptRoot '../distribution/deployment/workspace.ps1') $temporary
    [IO.File]::WriteAllText((Join-Path $temporary 'deployment.env'), 'PI_WORKSPACE_MODE=volume')
    $env:PI_WORKSPACE_MODE = 'volume'
    . (Join-Path $temporary 'workspace.ps1')
    $script:stopCalls = New-Object System.Collections.Generic.List[string]
    $script:failAction = ''
    function Invoke-WorkspaceAgent([string]$Action) {
        $script:stopCalls.Add($Action)
        if ($Action -eq $script:failAction) { throw ('fixture failure: ' + $Action) }
    }
    Initialize-Workspace @('down')
    if (($script:stopCalls -join ',') -ne 'stop') { throw 'Normal shutdown waited for a new backup' }
    $script:stopCalls.Clear()
    Initialize-Workspace @('down','backup')
    if (($script:stopCalls -join ',') -ne 'stop,backup') { throw 'Backup ran before quiescence' }
    $script:stopCalls.Clear(); $script:failAction = 'stop'
    $failed = $false
    try { Initialize-Workspace @('down','backup') } catch { $failed = $true }
    if (-not $failed -or ($script:stopCalls -join ',') -ne 'stop') { throw 'Pending stop incorrectly allowed backup/shutdown' }
    $script:stopCalls.Clear(); $script:failAction = 'backup'
    $failed = $false
    try { Initialize-Workspace @('down','backup') } catch { $failed = $true }
    if (-not $failed) { throw 'Required backup failure was swallowed' }
    Write-Output 'PASS: actual managed stop-first ordering, optional backup and failure propagation'
} finally {
    $env:PI_WORKSPACE_MODE = $previousMode
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
$global:LASTEXITCODE = 0
