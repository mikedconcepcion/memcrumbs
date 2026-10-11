---
title: Backup system
summary: Current nightly database backup using the SQLite online backup API with 14-day retention and a copy to the other server
verified: 2026-10-01
tags: [systems, backup, sqlite]
sources: [repo/jobs/nightly_backup.py, repo/ops/Backup-Databases.ps1, repo/ops/Register-Tasks.ps1]
aliases: [database backup, nightly backup, db snapshots]
---

# Backup system

Replaces [[backup-procedure-2025]] since 2026-07-12.

## How it works
- `NightlyBackup` runs on web-srv at 02:30 and on studio-srv at 02:45 (see [[scheduled-tasks]]).
- It calls `repo/jobs/nightly_backup.py`, which uses the sqlite3 module online backup call. Services keep running and no long lock is held.
- Output: `D:\emberline\backups\<db>-<YYYYMMDD>.db`, then an integrity check (`PRAGMA integrity_check`).
- Each server copies its newest files to the other server under `D:\emberline\backups\remote\`.
- Retention: 14 days locally, 30 days on the remote side. `BackupVerify` (03:30) alerts if no file from today exists.

## Restoring
See [[restore-db-from-backup]]. The reason for the change: [[2026-07-11-bookings-db-locked-by-backup]].
