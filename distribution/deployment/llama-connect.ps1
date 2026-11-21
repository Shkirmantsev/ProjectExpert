# Explicitly adopt a running Windows llama-server. The kit never takes ownership.
param(
    [ValidateRange(1,65535)][int]$Port = $(if ($env:PI_LLAMA_PORT) { $env:PI_LLAMA_PORT } else { 8769 }),
    [ValidateSet('managed-token','token-file','none')][string]$Auth = $(if ($env:PI_NATIVE_LLAMA_AUTH) { $env:PI_NATIVE_LLAMA_AUTH } else { 'managed-token' }),
    [string]$TokenFile = $env:PI_NATIVE_LLAMA_TOKEN_FILE
)
$ErrorActionPreference = 'Stop'
$saved = @{}
foreach ($name in @('PI_NATIVE_LLAMA_CONNECT','PI_LLAMA_PORT','PI_NATIVE_LLAMA_AUTH','PI_NATIVE_LLAMA_TOKEN_FILE')) {
    $saved[$name] = [Environment]::GetEnvironmentVariable($name)
}
try {
    $env:PI_NATIVE_LLAMA_CONNECT = '1'
    $env:PI_LLAMA_PORT = "$Port"
    $env:PI_NATIVE_LLAMA_AUTH = $Auth
    $env:PI_NATIVE_LLAMA_TOKEN_FILE = $TokenFile
    & (Join-Path $PSScriptRoot 'compose.ps1') up -d --wait --wait-timeout 1800
} finally {
    foreach ($name in $saved.Keys) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
}
