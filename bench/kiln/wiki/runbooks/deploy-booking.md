---
title: Deploy booking app
summary: Numbered steps to ship a new booking app release to web-srv, with the owner approval gate and post-deploy checks
verified: 2026-10-03
tags: [runbook, deploy, booking]
sources: [repo/ops/Deploy-Booking.ps1, repo/ops/Test-Health.ps1]
aliases: [release booking, ship website, publish new version]
---

# Deploy booking app

Needs explicit owner approval every time ([[rules]]).

1. On dev-ws run the tests: `python -m unittest discover -s repo/booking/tests`.
2. Ask the owner for approval and note the version number (for example 3.4.1).
3. Build the zip: `Compress-Archive repo/booking dist/booking-<version>.zip`.
4. Copy it to web-srv: `scp dist/booking-<version>.zip web-srv:D:/emberline/booking/incoming/`.
5. Run the one-shot script: `ssh web-srv powershell -File Deploy-Booking.ps1 -Version <version>`.
   It unpacks into `releases\<version>`, repoints the `current` junction and restarts `BookingWeb`.
6. Run `Test-Health.ps1 -Target web`; expect `/healthz` to answer 200 within 30 seconds.
7. Open one class page and one test booking page by hand.
8. Add a line to the month journal, e.g. `deployed booking 3.4.1 to web-srv #deploy` ([[2026-10]]).

If anything fails, go straight to [[rollback-booking]]. System details: [[web-srv]].
