# Register the Emberline scheduled tasks for one role. Run on the target server.
param(
    [Parameter(Mandatory)][ValidateSet('studio', 'web')][string]$Role
)
Import-Module D:\emberline\ops\EmberOps.psm1 -Force

function Register-TimedTask {
    param([string]$Name, [string]$Script, $Trigger)
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -File `"$Script`""
    # Short jobs get a one-hour cap; daemons use New-DaemonTask (unlimited).
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger -Settings $settings -Force | Out-Null
}

if ($Role -eq 'studio') {
    # ExecutionTimeLimit is set to zero inside New-DaemonTask: the 72-hour default killed KilnScheduler.
    New-DaemonTask -Name 'KilnScheduler' -ScriptPath 'D:\emberline\scheduler\run-scheduler.ps1'
    New-DaemonTask -Name 'DoorAlarmRelay' -ScriptPath 'D:\emberline\scheduler\door-alarm.ps1'
    Register-TimedTask 'SchedulerWatchdog' 'D:\emberline\ops\Test-Health.ps1' (New-ScheduledTaskTrigger -Once -At 00:00 -RepetitionInterval (New-TimeSpan -Minutes 5))
    Register-TimedTask 'KilnTelemetryPoll' 'D:\emberline\scheduler\poll.ps1' (New-ScheduledTaskTrigger -Once -At 00:00 -RepetitionInterval (New-TimeSpan -Minutes 1))
    Register-TimedTask 'GlazeInventorySync' 'D:\emberline\jobs\inventory.ps1' (New-ScheduledTaskTrigger -Daily -At 01:10)
    Register-TimedTask 'NightlyBackup' 'D:\emberline\ops\Backup-Databases.ps1' (New-ScheduledTaskTrigger -Daily -At 02:45)
    Register-TimedTask 'FiringLogRotate' 'D:\emberline\ops\logrotate.ps1' (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 04:00)
}
else {
    New-DaemonTask -Name 'BookingWeb' -ScriptPath 'D:\emberline\booking\current\run.ps1'
    New-DaemonTask -Name 'ChatBot' -ScriptPath 'D:\emberline\chatbot\run.ps1'
    Register-TimedTask 'NightlyBackup' 'D:\emberline\ops\Backup-Databases.ps1' (New-ScheduledTaskTrigger -Daily -At 02:30)
    Register-TimedTask 'InvoiceSync' 'D:\emberline\jobs\invoices.ps1' (New-ScheduledTaskTrigger -Daily -At 03:10)
    Register-TimedTask 'BackupVerify' 'D:\emberline\ops\Test-Health.ps1' (New-ScheduledTaskTrigger -Daily -At 03:30)
    Register-TimedTask 'PaymentReconcile' 'D:\emberline\jobs\reconcile.ps1' (New-ScheduledTaskTrigger -Daily -At 06:00)
    Register-TimedTask 'LogPrune' 'D:\emberline\ops\logprune.ps1' (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 03:00)
}
Write-OpsLog -Message "registered tasks for role $Role" -Tag 'register'
