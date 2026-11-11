param([ValidateSet('Install','Uninstall','Supervise')][string]$Action)
$ErrorActionPreference = 'Stop'
$name = 'ProjectExpert workspace ' + ([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($PSScriptRoot))).Replace('/','_').Replace('+','-')
if ($Action -eq 'Install') {
    $command = '-NoProfile -File "' + $PSCommandPath + '" -Action Supervise'
    $task = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $command -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
    Register-ScheduledTask -TaskName $name -Action $task -Trigger $trigger -Description 'Explicit per-user ProjectExpert workspace supervision' | Out-Null
} elseif ($Action -eq 'Uninstall') {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
} elseif ($Action -eq 'Supervise') {
    . (Join-Path $PSScriptRoot 'workspace.ps1')
    if ($workspaceManaged) { Invoke-WorkspaceAgent supervise -Foreground }
} else { throw 'Specify -Action Install, Uninstall or Supervise; registration is opt-in' }
