# Restart KilnScheduler. With -Adopt the new daemon re-attaches to a running firing.
param(
    [switch]$Adopt
)
Import-Module D:\emberline\ops\EmberOps.psm1 -Force

$status = Invoke-RestMethod 'http://localhost:7410/status' -TimeoutSec 10
if ($status.firing_active -and -not $Adopt) {
    throw 'A kiln is firing. Re-run with -Adopt after reading the restart-mid-firing runbook.'
}

Stop-ScheduledTask -TaskName 'KilnScheduler'
Start-Sleep -Seconds 5
if ($Adopt) {
    Set-Content -Path 'D:\emberline\scheduler\next-args.txt' -Value '--adopt'
}
Start-ScheduledTask -TaskName 'KilnScheduler'
Start-Sleep -Seconds 8

$after = Invoke-RestMethod 'http://localhost:7410/status' -TimeoutSec 10
Write-Output ($after | ConvertTo-Json -Compress)
Write-OpsLog -Message "restarted KilnScheduler adopt=$Adopt" -Tag 'restart'
