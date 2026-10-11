# Run the online SQLite backup for this host and copy the newest files to the other server.
param(
    [string]$Peer = 'studio-srv'
)
Import-Module D:\emberline\ops\EmberOps.psm1 -Force

function Get-LocalDatabases {
    Get-ChildItem 'D:\emberline\data' -Filter '*.db' | ForEach-Object { $_.FullName }
}

$dbs = Get-LocalDatabases
& python D:\emberline\jobs\nightly_backup.py @dbs
if ($LASTEXITCODE -ne 0) { throw 'nightly_backup.py failed' }

# Copy only today's finished backups; never touch the live .db files.
$today = Get-Date -Format 'yyyyMMdd'
Get-ChildItem 'D:\emberline\backups' -Filter "*-$today.db" | ForEach-Object {
    scp $_.FullName "${Peer}:D:/emberline/backups/remote/"
}
Write-OpsLog -Message "backup finished for $($dbs.Count) databases" -Tag 'backup'
