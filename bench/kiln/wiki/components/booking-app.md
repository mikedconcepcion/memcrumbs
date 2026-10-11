---
title: Booking web app
summary: The public Flask-style booking site for classes and studio time - routes, models, reminders, and where the code lives
verified: 2026-10-03
tags: [booking, web, component]
sources: [repo/booking/app.py, repo/booking/models.py, repo/booking/reminders.py, repo/booking/db.py]
aliases: [website, booking site, reservation app]
---

# Booking web app

Version 3.4.1 as of 2026-10-03. Runs as the `BookingWeb` task on [[web-srv]], port 8080 behind the edge proxy.

## Code map
- `repo/booking/app.py` - routes: `/classes`, `/book`, `/pay`, `/cancel`, `/healthz`.
- `repo/booking/models.py` - dataclasses `Booking`, `Customer`, `ClassSession`.
- `repo/booking/db.py` - SQLite connection helper, WAL mode ([[2026-05-05-sqlite-wal-mode]]).
- `repo/booking/payments.py` - card charges, see [[payments]].
- `repo/booking/refunds.py` - refund logic, see [[issue-refund]].
- `repo/booking/reminders.py` - builds reminder emails; run by `ReminderMailer` every 15 minutes.
- `repo/booking/config.py` - loads `repo/config/booking.toml`.

## Behaviour notes
- A seat is held for 10 minutes while the customer pays; `StaleHoldSweeper` releases expired holds.
- All reminder times are computed in UTC and rendered in studio local time ([[2026-06-08-reminders-wrong-timezone]]).
- Database: `bookings.db`, schema in `repo/db/bookings.sql`.

Deploy with [[deploy-booking]]; undo with [[rollback-booking]].
