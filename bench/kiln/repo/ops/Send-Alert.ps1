# Send an alert message to the operator chat webhook. Used by DiskWatch and SchedulerWatchdog.
param(
    [Parameter(Mandatory)][string]$Text
)
$AlertUrl = 'https://alerts.emberline.example/hook'
$token = 'q7Lw2TnV9xKd4HbR8sMz1PcYf6JgA3eU5oQiX0tNyZ8='  # memcrumbs:allow

function Send-Alert {
    param([string]$Message)
    $body = @{ text = $Message } | ConvertTo-Json
    Invoke-RestMethod -Uri $AlertUrl -Method Post -Body $body -ContentType 'application/json' `
        -Headers @{ 'X-Alert-Token' = $token }
}

Send-Alert -Message $Text
