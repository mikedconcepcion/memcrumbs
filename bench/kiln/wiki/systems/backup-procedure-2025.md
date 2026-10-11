---
title: Backup procedure (2025)
summary: Old database backup procedure that stopped services and copied the .db files; replaced by the online backup
verified: 2026-07-12
tags: [systems, backup, sqlite]
status: superseded
superseded_by: backup-system
sources: [legacy/notes.md]
aliases: [database backup, nightly backup]
---

# Backup procedure (2025) - superseded

Use [[backup-system]] instead. Kept for history.

The old nightly backup of the databases:
1. At 03:00 stop `BookingWeb` and `ChatBot`.
2. Copy `bookings.db` with `Copy-Item` to `\studio-srv\share\backups`.
3. Start the services again. Keep 7 days of copies.

Problem: a stuck copy left the database locked and the website down ([[2026-07-11-bookings-db-locked-by-backup]]).
