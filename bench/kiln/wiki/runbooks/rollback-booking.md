---
title: Roll back booking app
summary: How to return the website to the previous booking release in under two minutes by repointing the current junction
verified: 2026-10-03
tags: [runbook, rollback, booking]
sources: [repo/ops/Rollback-Booking.ps1, repo/ops/Deploy-Booking.ps1]
aliases: [revert release, undo deploy, previous version]
---

# Roll back booking app

The three newest releases stay in `D:\emberline\booking\releases`.

1. Tell the owner you are rolling back (a rollback does not need approval, but report it).
2. List releases: `ssh web-srv powershell -File Rollback-Booking.ps1 -List`.
3. Roll back to the previous one: `ssh web-srv powershell -File Rollback-Booking.ps1`
   or name a version with `-Version 3.4.0`.
4. The script stops `BookingWeb`, repoints the `current` junction, starts `BookingWeb`.
5. Run `Test-Health.ps1 -Target web` and confirm `/healthz` returns 200.
6. Database schema changes are never rolled back by this script; check `repo/db/bookings.sql` notes first.
7. Journal the rollback with the tag `#rollback`.

Forward procedure: [[deploy-booking]].
