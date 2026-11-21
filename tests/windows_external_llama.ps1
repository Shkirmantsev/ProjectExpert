# Run the real connect command with controlled Windows network and Docker boundaries.
$ErrorActionPreference = 'Stop'
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('pi-external-' + [Guid]::NewGuid())
$saved = @{}
foreach ($item in Get-ChildItem Env:) { $saved[$item.Name] = $item.Value }
$global:externalBind = '172.20.0.1'
$global:externalProbe = 0
$global:externalEndpoint = ''
$global:externalAuth = ''
$global:externalTokenMount = ''

function global:Get-NetIPAddress { [pscustomobject]@{ IPAddress='172.20.0.1'; InterfaceAlias='vEthernet (WSL)' } }
function global:Get-NetTCPConnection { [pscustomobject]@{ LocalAddress=$global:externalBind; OwningProcess=12345 } }
function global:docker {
    $global:LASTEXITCODE = 0
    if ($args[0] -eq 'context' -and $args[1] -eq 'show') { 'fixture'; return }
    if ($args[0] -eq 'context' -and $args[1] -eq 'inspect') { 'npipe:////./pipe/docker_engine'; return }
    if ($args -contains 'native-route') {
        $global:externalProbe++
        if ($args -notcontains '--host-only' -or $args -notcontains '9009') { throw 'Unexpected route probe' }
        '{"ok":true,"endpoint":"http://172.20.0.1:9009"}'
        return
    }
    if ($args -contains 'up') {
        $global:externalEndpoint = $env:PI_NATIVE_LLAMA_ENDPOINT
        $global:externalAuth = $env:PI_NATIVE_LLAMA_AUTH
        if ($global:externalAuth -eq 'none' -and $env:PI_NATIVE_LLAMA_PRIVATE -ne '1') { throw 'Missing verified private route' }
        if ($args -contains 'compose.windows-llama-token.yaml') {
            $global:externalTokenMount = $env:PI_NATIVE_LLAMA_TOKEN_FILE
        }
    }
}
try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    Copy-Item (Join-Path $PSScriptRoot '../distribution/deployment/*') $temporary -Recurse
    $env:PI_WORKSPACE_MODE = 'bind'; $env:PI_HOST_CA_MODE = 'off'; $env:PI_EMBEDDING_MODEL = 'gemma'
    $env:PI_ACCELERATOR = 'auto'; $env:DOCKER_HOST = ''; $env:DOCKER_CONTEXT = ''
    $connect = Join-Path $temporary 'llama-connect.ps1'
    & $connect -Port 9009 -Auth none
    if ($global:externalEndpoint -ne 'http://172.20.0.1:9009' -or $global:externalAuth -ne 'none') {
        throw 'The actual Compose command did not use the verified external endpoint'
    }
    $plan = Get-Content -LiteralPath (Join-Path $temporary 'accelerator/plan.json') -Raw | ConvertFrom-Json
    if ($plan.transport -ne 'external-windows' -or $plan.backend -ne 'auto' -or
        (Test-Path (Join-Path $temporary 'accelerator/runtime.pid'))) { throw 'External server must stay externally owned' }
    $global:externalBind = '0.0.0.0'
    $failed = $false
    try { & $connect -Port 9009 -Auth none } catch { $failed = $_ -match 'Wildcard and LAN listeners' }
    if (-not $failed -or $global:externalProbe -ne 1) { throw 'Unsafe tokenless bind reached the container probe' }
    $token = Join-Path $temporary 'private token file'
    [IO.File]::WriteAllText($token, ('x' * 64))
    & $connect -Port 9009 -Auth token-file -TokenFile $token
    if ($global:externalTokenMount -ne $token -or $global:externalAuth -ne 'managed-token' -or $global:externalProbe -ne 2) {
        throw 'External credential was not mounted through the token-file overlay'
    }
    Write-Output 'PASS: external native connect verifies the listener, authentication choice and separate process ownership'
} finally {
    foreach ($item in Get-ChildItem Env:) { if (-not $saved.ContainsKey($item.Name)) { [Environment]::SetEnvironmentVariable($item.Name,$null,'Process') } }
    foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
    Remove-Item Function:docker,Function:Get-NetIPAddress,Function:Get-NetTCPConnection -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
$global:LASTEXITCODE = 0
