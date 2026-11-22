# Read help from Makefile without relying on POSIX tools on Windows.
$ErrorActionPreference = 'Stop'
Write-Output 'Project Intelligence deployment kit -- available commands'
Write-Output ''
foreach ($line in Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Makefile') -Encoding UTF8) {
    if ($line -match '^([A-Za-z0-9][A-Za-z0-9_.-]*):.*##\s*(.+)$') {
        Write-Output ('  make {0,-22} {1}' -f $Matches[1], $Matches[2])
    }
}
Write-Output ''
Write-Output "Startup is explicit: run 'make platform-start'. Optional: LLM=1 (configure), LLM=0 (disable), ALLOW_SKIPPED_SOURCES=1 (local search with file errors)."
