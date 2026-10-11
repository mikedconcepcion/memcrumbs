---
title: Kiln scheduler
summary: The daemon on studio-srv that loads .kiln profiles, drives the kiln controllers and records every firing
verified: 2026-10-06
tags: [scheduler, kiln, component]
sources: [repo/scheduler/service.py, repo/scheduler/controller.py, repo/scheduler/profile_loader.py, repo/scheduler/firing_log.py]
aliases: [firing scheduler, kiln daemon]
---

# Kiln scheduler

Python daemon registered as the `KilnScheduler` task on [[studio-srv]]; status API on port 7410.

## Code map
- `repo/scheduler/service.py` - `KilnSchedulerService`: main loop, queue of firings, `/status` endpoint, `--adopt` start mode.
- `repo/scheduler/controller.py` - `ControllerDriver`: serial/TCP driver, `send_setpoint`, `read_temp`, `load_program`.
- `repo/scheduler/profile_loader.py` - `load_profile()` reads a `.kiln` file and compiles segments.
- `repo/scheduler/kiln_parser.py` - tokenizer and parser for the language ([[kiln-language]]).
- `repo/scheduler/validator.py` - `check_limits()` rejects any target above `MAX_TEMP` (rule E104).
- `repo/scheduler/firing_log.py` - writes readings to `firings.db`.

## Key facts
- Once a program is loaded, the controller runs it on its own; the scheduler supervises and logs.
- The daemon must never be killed by the task runner: unlimited execution time ([[2026-03-14-72h-task-limit-kills-scheduler]]).
- Safe restart during a firing: [[restart-scheduler-mid-firing]].
- Adding hardware: [[add-new-kiln]].
