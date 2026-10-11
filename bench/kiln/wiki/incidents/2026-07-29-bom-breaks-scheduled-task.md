---
title: BOM in a PowerShell script silently broke a scheduled task
summary: A script saved with a byte-order mark made ReminderMailer exit instantly and send nothing for two days
symptom: no reminder emails; the task finishes in 0 seconds with result 0x1 but runs fine by hand
verified: 2026-09-01
tags: [incident, powershell, scheduled-tasks]
sources: [repo/ops/EmberOps.psm1, repo/ops/Register-Tasks.ps1]
aliases: [utf8 bom, task exits immediately, script encoding]
---

# BOM in a PowerShell script broke a scheduled task

## What happened
On 2026-07-29 no reminder emails were sent. Task history showed `ReminderMailer` finishing in 0 seconds with
result 0x1. The script ran fine by hand in an interactive session.

## Root cause
An editor saved `Send-Reminders.ps1` as UTF-8 with BOM. The task action invoked it through `powershell -Command`,
where the BOM character was parsed as part of the first token and the first line failed with no log.

## Fix
Re-saved without BOM. `Register-Tasks.ps1` now runs scripts with `-File` and `Test-Health.ps1` has a `-CheckBom` switch
that reads the first three bytes of every script.

## Prevention
Save all .ps1 files as UTF-8 without BOM; see [[scheduled-tasks]] and trap number 3 in [[gotchas]].
