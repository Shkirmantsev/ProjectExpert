# Stop containers and only the native accelerator started by this kit.
param([switch]$KeepWorkspaceSupervisor, [switch]$WorkspacePrepared, [switch]$Backup)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'workspace.ps1')
. (Join-Path $PSScriptRoot 'native-process.ps1')
Push-Location $PSScriptRoot
try {
    # The complete service topology is used so every service of the
    # deployment is stopped. Orphans are never removed automatically: an
    # unrelated container in the same project must stay visible.
    # Internal inference fallback retains the workspace process while preserving
    # the previous container/native-runtime cleanup behavior.
    if (-not $KeepWorkspaceSupervisor -and -not $WorkspacePrepared) { if ($Backup) { Initialize-Workspace @('down','backup') } else { Initialize-Workspace @('down') } }
    Invoke-WorkspaceCompose --env-file deployment.env -f compose.yaml -f compose.accelerator.yaml down
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop application containers' }
    $cache = Join-Path $PSScriptRoot 'accelerator'
    Stop-OwnedNativeRuntime $cache
} finally { Pop-Location }
