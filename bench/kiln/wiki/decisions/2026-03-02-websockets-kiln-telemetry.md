---
title: Use websockets for live kiln telemetry
summary: Experiment streaming kiln temperatures to the operator dashboard over websockets instead of polling; rejected
verified: 2026-09-09
tags: [decision, telemetry, kiln]
status: rejected
sources: [repo/scheduler/service.py, repo/scheduler/firing_log.py]
aliases: [push updates, streaming temperatures, live graph]
---

# Use websockets for live kiln telemetry

## Question
Can the dashboard get kiln temperatures by push (websockets) so the graph updates every second?

## What we tried
- Added a websocket endpoint to the scheduler status server for two weeks on a branch.
- Compared with the existing one-minute `KilnTelemetryPoll` plus a dashboard page that polls `/status` every 5 seconds.

## Verdict
Rejected on 2026-03-02.

## Why
Kilns change temperature by 1 or 2 degrees per minute, so a one-second graph shows nothing new. The websocket server added
a dependency and a reconnect bug that froze the dashboard. The event loop also competed with the controller driver
for the serial port. See [[kiln-scheduler]].
