# EmberOps helper module. Save as UTF-8 WITHOUT BOM (a BOM broke ReminderMailer once).

function New-DaemonTask {
    <#
    .SYNOPSIS
    Register a long-running task with NO execution time limit.
    The Windows default limit is 72 hours and silently kills daemons.
    #>
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$ScriptPath,
        [string]$Arguments = ''
    )
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -File `"$ScriptPath`" $Arguments"
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
}

function Test-ScriptHasBom {
    param([Parameter(Mandatory)][string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    return ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
}

function Write-OpsLog {
    param([Parameter(Mandatory)][string]$Message, [string]$Tag = 'info')
    $line = '{0:yyyy-MM-dd HH:mm:ss} #{1} {2}' -f (Get-Date), $Tag, $Message
    Add-Content -Path 'D:\emberline\logs\ops.log' -Value $line
}

function Invoke-HealthUrl {
    param([Parameter(Mandatory)][string]$Url, [int]$TimeoutSec = 10)
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec $TimeoutSec -UseBasicParsing
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

Export-ModuleMember -Function New-DaemonTask, Test-ScriptHasBom, Write-OpsLog, Invoke-HealthUrl
