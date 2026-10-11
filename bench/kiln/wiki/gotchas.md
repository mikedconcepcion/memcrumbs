---
title: Gotchas
summary: Ranked list of traps that already cost us time or money, each with a detail page
verified: 2026-10-07
tags: [gotchas, ops]
sources: [repo/ops/Register-Tasks.ps1, repo/scheduler/validator.py]
aliases: [pitfalls, traps, known problems]
---

# Gotchas

## Top
1. The Windows task runner's default 72-hour execution time limit silently kills long-running daemons such as KilnScheduler; always register them with an unlimited limit. [[2026-03-14-72h-task-limit-kills-scheduler]]
2. Restarting KilnScheduler while a kiln is firing drops its hold on the controller; follow the safe procedure. [[restart-scheduler-mid-firing]]
3. A byte-order mark at the top of a .ps1 file makes the scheduled task exit instantly with no log. [[2026-07-29-bom-breaks-scheduled-task]]
4. Copying a live .db file while a service writes gives a locked or torn backup; use the online backup API. [[2026-07-11-bookings-db-locked-by-backup]]
5. A typo in a profile target temperature can overfire a kiln if the limit check is skipped. [[2026-05-19-kiln-overfire-profile-typo]]
6. Retrying a card charge without the same idempotency key double-charges the customer. [[2026-04-02-double-charge-on-retry]]
7. Reminder times were built from naive local time while the server runs UTC. [[2026-06-08-reminders-wrong-timezone]]
8. The chat bot caches prices; a price change is invisible until the cache is refreshed. [[2026-09-02-chatbot-stale-prices]]
9. Logs fill D: on web-srv quickly if log rotation is off. [[2026-08-16-disk-full-web-srv]]
10. The TLS certificate renewal task must be checked after every proxy change. [[2026-09-23-cert-expiry-booking-outage]]
11. Old network notes list wrong ports; trust the newer pages. [[network-ports-2025]]

## More
- Inventory sync can create duplicate glaze rows if run twice in a row. [[2026-09-14-inventory-sync-duplicate-glazes]]
- Auto-retry of payments was rejected for good reason. [[2026-04-20-auto-retry-failed-payments]]
- Task inventory and schedules: [[scheduled-tasks]].
