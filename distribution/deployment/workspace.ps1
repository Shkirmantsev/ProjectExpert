# Dot source from kit launchers. Read dotenv as text; never Invoke-Expression.
function Get-WorkspaceValue([string]$Name) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ($value) { return $value }
    foreach ($line in Get-Content -LiteralPath (Join-Path $PSScriptRoot 'deployment.env')) {
        if ($line.StartsWith($Name + '=')) { $value = $line.Substring($Name.Length + 1).TrimEnd("`r") }
    }
    if ($value -and $value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) { $value = $value.Substring(1, $value.Length - 2) }
    return $value
}
$workspaceMode = Get-WorkspaceValue 'PI_WORKSPACE_MODE'
if (-not $workspaceMode) { $workspaceMode = 'auto' }
if ($workspaceMode -notin @('auto','bind','volume')) { throw 'PI_WORKSPACE_MODE must be auto, bind or volume' }
$workspaceManaged = $workspaceMode -in @('auto','volume')
if ($workspaceManaged) {
    foreach ($key in @('PI_WORKSPACE_EXCLUDE','PI_WORKSPACE_MAX_FILE_BYTES','PI_RUNTIME_BACKUP','PI_RUNTIME_BACKUP_DIR','PI_RUNTIME_BACKUP_INTERVAL_MINUTES','PI_RUNTIME_BACKUP_INTERVAL_SECONDS','PI_WORKSPACE_DEBOUNCE_MS','PI_WORKSPACE_VERIFY_INTERVAL_SECONDS')) {
        $setting = Get-WorkspaceValue $key
        if ($setting) { [Environment]::SetEnvironmentVariable($key, $setting, 'Process') }
    }
}
function Invoke-WorkspaceAgent([string]$Action, [switch]$Foreground) {
    $binary = Join-Path $PSScriptRoot 'workspace-agent-windows-amd64.exe'
    $checksum = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'workspace-agent-SHA256SUMS') | Where-Object { $_ -match '^([0-9a-fA-F]{64})\s+\*?workspace-agent-windows-amd64\.exe$' } | Select-Object -Last 1
    if (-not $checksum -or (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash -ne ($checksum -split '\s+')[0]) { throw 'Workspace helper checksum mismatch or missing checksum' }
    $repo = Get-WorkspaceValue 'PI_TARGET_REPO'
    if (-not $repo) { $repo = '..' }
    if (-not [IO.Path]::IsPathRooted($repo)) { $repo = Join-Path $PSScriptRoot $repo }
    $repo = (Resolve-Path -LiteralPath $repo).Path
    if ($Action -eq 'supervise' -and -not $Foreground) {
        # Go also acquires a per-kit OS lock, so concurrent launches are safe.
        $quotedRepo = '"' + $repo + '"'
        $quotedKit = '"' + $PSScriptRoot + '"'
        Start-Process -FilePath $binary -ArgumentList @($Action, '--repo', $quotedRepo, '--kit', $quotedKit) -WindowStyle Hidden | Out-Null
    } else {
        & $binary $Action --repo $repo --kit $PSScriptRoot
        if ($LASTEXITCODE -ne 0) { throw "Workspace helper $Action failed" }
    }
}
function Initialize-Workspace([string[]]$Commands) {
    if (-not $workspaceManaged) { return }
    if (($Commands -contains 'up') -or ($Commands -contains 'run') -or ($Commands -contains 'restart')) {
        Invoke-WorkspaceAgent prepare
        Invoke-WorkspaceAgent sync
    }
    if ($Commands -contains 'down') {
        try { Invoke-WorkspaceAgent backup } catch { Write-Warning "Workspace backup failed: $_" }
        Invoke-WorkspaceAgent stop
    } elseif ($Commands -contains 'stop') { Invoke-WorkspaceAgent stop }
    if (($Commands -contains 'up') -or ($Commands -contains 'restart')) { Invoke-WorkspaceAgent supervise }
}
function Invoke-WorkspaceCompose {
    $compose = @($args)
    $dockerArguments = @()
    if ($workspaceManaged) {
        $context = (Invoke-WorkspaceAgent context | Out-String).Trim()
        if (-not $context) { throw 'Missing pinned Docker context' }
        $dockerArguments = @('--context', $context)
        $commands = @('up','run','restart','config','ps','logs','down','stop','start','exec','pull','build','images','top','version','ls','events','pause','unpause','kill','rm','create','cp','port','wait','watch')
        $index = 0
        while ($index -lt $compose.Count -and $compose[$index] -notin $commands) { $index++ }
        $before = @(); $after = @()
        if ($index -gt 0) { $before = @($compose[0..($index-1)]) }
        if ($index -lt $compose.Count) { $after = @($compose[$index..($compose.Count-1)]) }
        $compose = $before + @('--env-file','workspace.env','-f','compose.workspace-volume.yaml') + $after
    }
    if ((Get-WorkspaceValue 'PI_HOST_CA_MODE') -ne 'off' -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'host-trust/host-ca-bundle.pem'))) {
        $index = 0
        $commands = @('up','run','restart','config','ps','logs','down','stop','start','exec','pull','build','images','top','version','ls','events','pause','unpause','kill','rm','create','cp','port','wait','watch')
        while ($index -lt $compose.Count -and $compose[$index] -notin $commands) { $index++ }
        $before = @(); $after = @()
        if ($index -gt 0) { $before = @($compose[0..($index-1)]) }
        if ($index -lt $compose.Count) { $after = @($compose[$index..($compose.Count-1)]) }
        $compose = $before + @('-f','compose.host-trust.yaml') + $after
    }
    # PS 5.1 treats native stderr as an error under Stop; use exit status.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & docker @dockerArguments compose @compose
        $nativeExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    $global:LASTEXITCODE = $nativeExitCode
}
