---
title: Move bookings to Postgres
summary: Research on replacing the SQLite bookings database with Postgres; rejected as needless complexity at our size
verified: 2026-09-11
tags: [decision, database, sqlite]
status: rejected
sources: [repo/booking/db.py, repo/db/bookings.sql]
aliases: [switch database engine, postgresql migration, client-server database]
---

# Move bookings to Postgres

## Question
Should `bookings.db` move from SQLite to a Postgres server on web-srv to avoid file locking problems?

## What we tried
- Ported `bookings.sql` and ran the booking tests against a local Postgres on dev-ws.
- Load test: 40 simultaneous bookings, p95 latency 120 ms on SQLite in WAL mode versus 95 ms on Postgres.
- Estimated extra operations: a new service, new backups, a new credential, a new restore procedure.

## Verdict
Rejected on 2026-02-10. Revisit only if we exceed 5,000 bookings per month.

## Why
Peak load is a handful of writes per minute. The locking trouble was a backup problem, not an engine problem
([[2026-07-11-bookings-db-locked-by-backup]]). One more server process means one more thing to restart. We chose
WAL mode instead: [[2026-05-05-sqlite-wal-mode]].
