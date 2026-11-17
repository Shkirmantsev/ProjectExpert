# Shared fixture/software acceptance for both asset validation and promotion.
# Physical NVIDIA/Intel GPU inference is a separate hardware acceptance gate.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'test_deployment_launchers.ps1')
& (Join-Path $PSScriptRoot '../tests/windows_deployment_runtime.ps1')
& (Join-Path $PSScriptRoot '../tests/windows_offline_assets.ps1')
& (Join-Path $PSScriptRoot '../tests/windows_container_cuda.ps1')
& (Join-Path $PSScriptRoot '../tests/windows_native_cuda.ps1')
& (Join-Path $PSScriptRoot '../tests/windows_native_routing.ps1')
$global:LASTEXITCODE = 0
