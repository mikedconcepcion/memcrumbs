---
title: Unlimited execution time for daemon tasks
summary: Decision to register every long-running task with no execution time limit and add a watchdog
verified: 2026-09-17
tags: [decision, scheduled-tasks]
status: accepted
sources: [repo/ops/Register-Tasks.ps1, repo/ops/EmberOps.psm1]
aliases: [no time limit, task settings]
---

# Unlimited execution time for daemon tasks

## Question
After [[2026-03-14-72h-task-limit-kills-scheduler]], how do we keep daemons alive for weeks?

## What we tried
Option A: restart every 60 hours with a trigger. Option B: set the limit to zero (unlimited) and watch health.
Option C: run daemons as true Windows services with a wrapper.

## Verdict
Accepted on 2026-08-12: option B. `New-DaemonTask` in `EmberOps.psm1` is the only way to register a daemon.

## Why
Option A interrupts a firing every few days. Option C adds a wrapper tool we would have to maintain. The watchdog
`SchedulerWatchdog` covers real crashes. See [[scheduled-tasks]].
