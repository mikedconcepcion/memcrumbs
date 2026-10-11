---
title: Bookings database locked by the backup copy
summary: Website returned errors for three hours because the old backup copied bookings.db while the service held it
verified: 2026-09-05
tags: [incident, backup, sqlite]
sources: [repo/jobs/nightly_backup.py, repo/booking/db.py]
aliases: [database is locked, backup hang, sqlite locked]
---

# Bookings database locked by the backup copy

## What happened
On 2026-07-11 `BookingWeb` answered 500 with "database is locked" from 03:00 until 06:10. Three customers could not pay.

## Root cause
The [[backup-procedure-2025]] stopped the service but the stop timed out; the copy then raced a writer, and the
stuck `Copy-Item` kept a handle on the file until the morning.

## Fix
Replaced with the online backup in [[backup-system]] (live since 2026-07-12). WAL mode was already accepted in
[[2026-05-05-sqlite-wal-mode]].

## Prevention
Never copy a live .db file; use the backup job. `BackupVerify` checks for a fresh file each morning.
