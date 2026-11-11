# Export public trusted roots only; never personal certificates/private keys.
$ErrorActionPreference = 'Stop'
$destination = Join-Path $PSScriptRoot 'host-trust'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$seen = @{}
$builder = New-Object Text.StringBuilder
foreach ($store in @('Cert:\LocalMachine\Root','Cert:\CurrentUser\Root')) {
    foreach ($certificate in Get-ChildItem -Path $store) {
        if ($seen.ContainsKey($certificate.Thumbprint)) { continue }
        $seen[$certificate.Thumbprint] = $true
        [void]$builder.AppendLine('-----BEGIN CERTIFICATE-----')
        [void]$builder.AppendLine([Convert]::ToBase64String($certificate.RawData, [Base64FormattingOptions]::InsertLineBreaks))
        [void]$builder.AppendLine('-----END CERTIFICATE-----')
    }
}
if ($seen.Count -eq 0) { throw 'No public trusted root certificates found' }
$temporary = Join-Path $destination ([IO.Path]::GetRandomFileName())
try {
    [IO.File]::WriteAllText($temporary, $builder.ToString(), [Text.Encoding]::ASCII)
    Move-Item -Force -LiteralPath $temporary -Destination (Join-Path $destination 'host-ca-bundle.pem')
} finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
Write-Output "Collected $($seen.Count) public CA certificates. Docker registry trust is configured separately in the engine."
