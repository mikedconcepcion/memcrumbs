---
title: Enable SQLite WAL mode on all databases
summary: Decision to run bookings, firings and inventory databases in write-ahead-log mode with a busy timeout
verified: 2026-09-13
tags: [decision, sqlite]
status: accepted
sources: [repo/booking/db.py, repo/db/bookings.sql]
aliases: [journal mode, concurrent reads]
---

# Enable SQLite WAL mode on all databases

## Question
How do we let the website read while the nightly jobs write, without moving to another database engine?

## What we tried
Default rollback journal versus WAL with `busy_timeout = 5000`. Replayed a day of traffic.

## Verdict
Accepted on 2026-05-05. `repo/booking/db.py` sets `PRAGMA journal_mode=WAL` on every new connection.

## Why
Readers no longer block on the writer; lock errors dropped to zero in the replay. It pairs with the online backup in
[[backup-system]]. Alternative rejected: [[2026-02-10-bookings-to-postgres]].
