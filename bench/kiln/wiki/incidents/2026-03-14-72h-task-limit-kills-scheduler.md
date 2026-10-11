---
title: KilnScheduler killed after 72 hours by the task runner
summary: The scheduler daemon vanished every third day because the Windows task default execution time limit is 72 hours
symptom: the scheduler status API stops answering every third day and nothing is logged
verified: 2026-09-14
tags: [incident, scheduler, scheduled-tasks]
sources: [repo/ops/Register-Tasks.ps1, repo/ops/Test-Health.ps1]
aliases: [scheduler died after three days, daemon stops silently]
---

# KilnScheduler killed after 72 hours

## What happened
On 2026-03-14 at 06:12 the KilnScheduler status API stopped answering during a bisque firing. The kiln finished
on its own, but nothing was logged for 5 hours. The same thing had happened on 03-11 and was put down to a crash.

## Root cause
The task was registered with default settings. The Windows task runner stops any task that runs longer than
72 hours (ExecutionTimeLimit default). The daemon had been up for exactly 72 hours both times. No error is written.

## Fix
`Register-Tasks.ps1` now sets `-ExecutionTimeLimit ([TimeSpan]::Zero)` for every daemon task and
`SchedulerWatchdog` restarts the task if `/status` fails twice. See [[2026-08-12-execution-time-limit-zero]].

## Prevention
- All long-running tasks are listed as daemons in [[scheduled-tasks]]; new ones must use the helper in `EmberOps.psm1`.
- Gotcha number one in [[gotchas]]. Recovery during a firing: [[restart-scheduler-mid-firing]].
