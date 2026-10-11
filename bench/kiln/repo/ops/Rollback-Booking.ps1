# Roll the booking app back to the previous (or a named) release on web-srv.
param(
    [string]$Version,
    [switch]$List
)
Import-Module D:\emberline\ops\EmberOps.psm1 -Force
$root = 'D:\emberline\booking'
$releases = Get-ChildItem (Join-Path $root 'releases') -Directory | Sort-Object LastWriteTime -Descending

if ($List) { $releases | Select-Object -First 3 Name, LastWriteTime; return }

if ($Version) { $target = Join-Path $root "releases\$Version" }
else { $target = Get-Content (Join-Path $root 'previous.txt') }

if (-not (Test-Path $target)) { throw "release not found: $target" }
Stop-ScheduledTask -TaskName 'BookingWeb' -ErrorAction SilentlyContinue
cmd /c rmdir (Join-Path $root 'current')
New-Item -ItemType Junction -Path (Join-Path $root 'current') -Target $target | Out-Null
Start-ScheduledTask -TaskName 'BookingWeb'
Start-Sleep -Seconds 10
if (Invoke-HealthUrl 'http://127.0.0.1:8080/healthz') { Write-OpsLog -Message "rolled back to $target" -Tag 'rollback' }
else { throw 'healthz still failing after rollback' }
