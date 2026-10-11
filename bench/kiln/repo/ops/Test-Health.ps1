# One-shot health check for a server. Prints one line per probe and exits non-zero on failure.
param(
    [Parameter(Mandatory)][ValidateSet('studio', 'web')][string]$Target,
    [switch]$CheckBom,
    [switch]$CheckCert
)
Import-Module D:\emberline\ops\EmberOps.psm1 -Force
$failed = 0

function Write-Probe {
    param([string]$Name, [bool]$Ok)
    Write-Output ("{0,-22} {1}" -f $Name, $(if ($Ok) { 'ok' } else { 'FAIL' }))
    if (-not $Ok) { $script:failed++ }
}

if ($Target -eq 'studio') {
    $status = Invoke-RestMethod 'http://localhost:7410/status' -TimeoutSec 10
    Write-Probe 'scheduler status' ([bool]$status.ok)
    if ($status.firing_active) { Write-Output "active firing: $($status.active | ConvertTo-Json -Compress)" }
}
else {
    Write-Probe 'booking healthz' (Invoke-HealthUrl 'http://127.0.0.1:8080/healthz')
    Write-Probe 'chatbot ping' (Invoke-HealthUrl 'http://127.0.0.1:8091/ping')
}
if ($CheckBom) {
    Get-ChildItem 'D:\emberline' -Recurse -Filter '*.ps1' | ForEach-Object {
        if (Test-ScriptHasBom $_.FullName) { Write-Probe "bom: $($_.Name)" $false }
    }
}
if ($CheckCert) {
    $cert = Get-ChildItem Cert:\LocalMachine\My | Sort-Object NotAfter -Descending | Select-Object -First 1
    Write-Probe 'certificate > 20 days' (($cert.NotAfter - (Get-Date)).TotalDays -gt 20)
}
exit $failed
