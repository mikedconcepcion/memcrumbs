---
title: Scheduled tasks and services
summary: Inventory of the 20 Windows scheduled tasks and long-running services on both servers with schedule and kind
verified: 2026-10-04
tags: [systems, scheduled-tasks]
sources: [repo/ops/Register-Tasks.ps1]
aliases: [task scheduler, cron jobs, jobs list]
---

# Scheduled tasks and services

All tasks are registered by `repo/ops/Register-Tasks.ps1`. Long-running ones use an unlimited execution
time limit, because the default is 72 hours ([[2026-03-14-72h-task-limit-kills-scheduler]]).

| Task | Host | Schedule | Kind |
|---|---|---|---|
| KilnScheduler | studio-srv | at startup | daemon |
| SchedulerWatchdog | studio-srv | every 5 min | check |
| KilnTelemetryPoll | studio-srv | every minute | poll |
| DoorAlarmRelay | studio-srv | at startup | daemon |
| FiringLogRotate | studio-srv | Sun 04:00 | maintenance |
| GlazeInventorySync | studio-srv | daily 01:10 | sync |
| NightlyBackup (studio) | studio-srv | daily 02:45 | backup |
| BookingWeb | web-srv | at startup | daemon |
| ChatBot | web-srv | at startup | daemon |
| ChatKnowledgeRefresh | web-srv | daily 04:00 | refresh |
| NightlyBackup | web-srv | daily 02:30 | backup |
| BackupVerify | web-srv | daily 03:30 | check |
| InvoiceSync | web-srv | daily 03:10 | sync |
| ReminderMailer | web-srv | every 15 min | mailer |
| StaleHoldSweeper | web-srv | every 10 min | cleanup |
| PaymentReconcile | web-srv | daily 06:00 | reconcile |
| CertRenewCheck | web-srv | Mon 07:00 | check |
| DiskWatch | web-srv | hourly | check |
| LogPrune | web-srv | Sun 03:00 | maintenance |
| WeeklyDigest | web-srv | Mon 08:00 | mailer |

Scripts must be saved as UTF-8 without BOM ([[2026-07-29-bom-breaks-scheduled-task]]).
Per-host detail: [[studio-srv]], [[web-srv]].
