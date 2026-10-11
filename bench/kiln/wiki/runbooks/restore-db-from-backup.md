---
title: Restore a database from backup
summary: Steps to bring bookings.db, firings.db or inventory.db back from the newest good nightly backup
verified: 2026-09-12
tags: [runbook, backup, sqlite]
sources: [repo/ops/Backup-Databases.ps1, repo/jobs/nightly_backup.py]
aliases: [recover database, bring back data]
---

# Restore a database from backup

1. Get owner approval; a restore overwrites live data ([[rules]]).
2. Stop the owning service (`BookingWeb` or `KilnScheduler`; never mid-firing, see [[restart-scheduler-mid-firing]]).
3. Pick the file: `D:\emberline\backups\<db>-<YYYYMMDD>.db` locally, or `backups\remote\` from the other server.
4. Verify it with sqlite3: `PRAGMA integrity_check;` must print `ok`.
5. Move the damaged live file to `D:\emberline\data\quarantine\` (do not delete it).
6. Copy the backup to `D:\emberline\data\<db>.db`; delete any `-wal` and `-shm` files next to it.
7. Start the service and run `Test-Health.ps1`.
8. Re-apply bookings made since the backup from the provider dashboard and the journal.

How backups are produced: [[backup-system]].
