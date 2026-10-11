---
title: Disk full on web-srv stopped the booking site
summary: The D drive on web-srv filled with logs and a debug dump, the database could not write, and bookings failed
verified: 2026-09-06
tags: [incident, web-srv, disk]
sources: [repo/ops/Test-Health.ps1, repo/ops/Register-Tasks.ps1]
aliases: [no space left, out of disk, logs too big]
---

# Disk full on web-srv

## What happened
On 2026-08-16 around 19:30 new bookings failed with "disk I/O error". D: had 0 bytes free.

## Root cause
Log rotation had never been registered on web-srv (only on studio-srv). A debug flag left on after a payment test
wrote 40 GB of request logs. The dump also held a config echo with a leftover test credential:
- password = "Mv6@jD3zUq" <!-- memcrumbs:allow -->

That credential was for a retired test mailbox and was revoked the same day.

## Fix
Deleted old logs, turned off debug, registered `LogPrune` (Sun 03:00) and `DiskWatch` (hourly alert under 15 percent free).

## Prevention
Task list in [[scheduled-tasks]]. Never dump configuration into logs. Host notes: [[web-srv]].
