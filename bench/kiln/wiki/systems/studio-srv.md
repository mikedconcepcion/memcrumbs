---
title: studio-srv
summary: Windows server in the studio that runs the kiln scheduler, the kiln controller links and the firing and inventory databases
verified: 2026-09-30
tags: [systems, studio-srv, kiln]
sources: [repo/ops/Register-Tasks.ps1, repo/scheduler/service.py, repo/db/firings.sql]
aliases: [studio server, kiln server]
---

# studio-srv

Windows Server in the studio room. Reachable only on the private network, SSH on port 22, no jumpbox
(removed in January 2026, see [[network-ports-2025]] for the old layout).

## What runs here
- `KilnScheduler` - the scheduler daemon, status API on port 7410. See [[kiln-scheduler]].
- `KilnTelemetryPoll` - every minute, writes temperatures to firings.db.
- `GlazeInventorySync` - daily 01:10, updates inventory.db.
- `NightlyBackup` (studio side) - 02:45, see [[backup-system]].
- `FiringLogRotate`, `SchedulerWatchdog`, `DoorAlarmRelay`. Full list: [[scheduled-tasks]].

## Data
- `D:\emberline\data\firings.db` - firings, segments, controller readings.
- `D:\emberline\data\inventory.db` - glazes, clay stock, supplier orders.
- Kiln controllers: k1 on COM3, k2 on COM4, k3 over TCP host `k3-ctl` port 502.

## Health check
Run `repo/ops/Test-Health.ps1 -Target studio` over SSH. It queries `http://localhost:7410/status` and
expects `"ok": true`. If a firing is active it also prints the active profile name.
