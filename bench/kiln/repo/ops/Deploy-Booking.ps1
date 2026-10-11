# Deploy a booking release on web-srv. Needs owner approval BEFORE it is run (see wiki rules).
param(
    [Parameter(Mandatory)][string]$Version
)
Import-Module D:\emberline\ops\EmberOps.psm1 -Force
$root = 'D:\emberline\booking'
$zip = Join-Path $root "incoming\booking-$Version.zip"
$release = Join-Path $root "releases\$Version"

function Install-Release {
    param([string]$ZipPath, [string]$Target)
    if (-not (Test-Path $ZipPath)) { throw "missing $ZipPath" }
    Expand-Archive -Path $ZipPath -DestinationPath $Target -Force
}

Install-Release -ZipPath $zip -Target $release
$current = Join-Path $root 'current'
if (Test-Path $current) {
    # Remember the previous release so Rollback-Booking.ps1 can find it.
    (Get-Item $current).Target | Set-Content (Join-Path $root 'previous.txt')
    cmd /c rmdir $current
}
New-Item -ItemType Junction -Path $current -Target $release | Out-Null
Stop-ScheduledTask -TaskName 'BookingWeb' -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName 'BookingWeb'
Start-Sleep -Seconds 10
if (-not (Invoke-HealthUrl 'http://127.0.0.1:8080/healthz')) { throw 'healthz failed after deploy; run Rollback-Booking.ps1' }
Write-OpsLog -Message "deployed booking $Version" -Tag 'deploy'
