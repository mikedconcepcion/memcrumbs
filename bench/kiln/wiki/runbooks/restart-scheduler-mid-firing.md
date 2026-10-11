---
title: Restart kiln scheduler safely mid-firing
summary: Procedure to restart the KilnScheduler daemon while a kiln is firing without interrupting the firing
verified: 2026-09-27
tags: [runbook, scheduler, kiln]
sources: [repo/ops/Restart-KilnScheduler.ps1, repo/scheduler/service.py]
aliases: [bounce scheduler, restart daemon during firing]
---

# Restart kiln scheduler safely mid-firing

The controller runs the loaded program by itself, so a firing survives a daemon restart as long as the
new daemon starts in adopt mode and does not reload a program.

1. Check status: `Invoke-RestMethod http://localhost:7410/status` over SSH. Note `firing_active` and the segment.
2. If a firing is active and within 10 minutes of a hold start or end, wait until the segment is stable.
3. Run `Restart-KilnScheduler.ps1 -Adopt`. It stops the task, waits 5 seconds, starts it with `--adopt`.
4. Confirm the status shows `"adopted": true` and the same profile and segment.
5. Compare the last logged temperature in `firings.db` with the controller display; difference should be under 5 C.
6. Journal it with `#restart`. Never use `Stop-Process` or restart studio-srv itself during a firing.

Background: [[kiln-scheduler]], [[2026-03-14-72h-task-limit-kills-scheduler]].
