# Read-only diagnostics. Host HTTPS is not proof of Docker daemon registry trust.
param([string]$Image)
# Expected cache/context probe failures must remain diagnostics even when the
# caller enables native-command errors. This setting is scoped to this script.
$ErrorActionPreference = 'Continue'
if (-not $Image) { return }
$context = (& docker context show 2>$null | Out-String).Trim()
Write-Host "Registry preflight: Docker context=$context"
& docker image inspect $Image *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Required asset image is cached; no registry HTTPS probe needed.'
    return
}
$registry = $Image.Split('/')[0]
if ($registry -notmatch '^[a-zA-Z0-9.-]+(:[0-9]+)?$') { return }
Write-Host 'Container host-trust bundles do not configure Docker Engine registry trust.'
try {
    # A registry's unauthenticated 401 also proves a successful host TLS exchange.
    Invoke-WebRequest -UseBasicParsing -Uri "https://$registry/v2/" -TimeoutSec 15 -ErrorAction Stop | Out-Null
} catch {
    if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 401) {
        Write-Warning 'Host registry HTTPS probe failed. Check proxy/CA policy; engine pull must also validate TLS.'
    }
}
Write-Host 'Docker Desktop Linux engine: configure approved Windows root CA trust, then restart Desktop as required by policy.'
Write-Host 'Rancher Desktop/WSL: configure the selected VM/engine trust separately; Windows host trust alone is insufficient.'
Write-Host 'Linux rootful: /etc/docker/certs.d/<registry>/ca.crt; rootless: $XDG_CONFIG_HOME/docker/certs.d/<registry>/ca.crt (default ~/.config/docker/certs.d).'
Write-Host 'See https://docs.docker.com/engine/security/certificates/ . No trust settings were changed; the actual pull remains authoritative.'
