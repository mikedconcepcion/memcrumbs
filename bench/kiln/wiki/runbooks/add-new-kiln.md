---
title: Add a new kiln
summary: Steps to register a new kiln and controller in the scheduler, the profile files and the monitoring
verified: 2026-09-16
tags: [runbook, kiln, scheduler]
sources: [repo/profiles/common.kiln, repo/scheduler/controller.py, repo/scheduler/service.py]
aliases: [install kiln, onboard kiln, new firing chamber]
---

# Add a new kiln

Last done for k3 on 2026-09-16.

1. Connect the controller (serial COM port or TCP host and port) and note the thermocouple type.
2. Add a `kiln kN` block (model, zones, thermocouple) to `repo/profiles/common.kiln` ([[kiln-language]]).
3. Add the kiln to the `[kilns]` table in the scheduler settings on [[studio-srv]].
4. Write a test profile (`tile_fast.kiln` is a good template) targeting at most 300 C.
5. Check it: `python -m scheduler.profile_loader --check repo/profiles/tile_fast.kiln`.
6. With the owner present, run the test profile and watch the controller display.
7. Add the kiln to the seed data of table `kilns` in `repo/db/firings.sql`.
8. Restart the scheduler only when idle, otherwise [[restart-scheduler-mid-firing]].
