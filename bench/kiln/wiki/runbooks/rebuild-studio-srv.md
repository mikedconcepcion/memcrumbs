---
title: Rebuild studio-srv from scratch
summary: Ordered steps to reinstall studio-srv, restore its databases and re-register all scheduled tasks
verified: 2026-09-10
tags: [runbook, studio-srv, disaster]
sources: [repo/ops/Register-Tasks.ps1, repo/ops/EmberOps.psm1]
aliases: [reinstall server, disaster recovery]
---

# Rebuild studio-srv from scratch

1. Install Windows Server, join the private network, enable OpenSSH on port 22.
2. Create `D:\emberline\data`, `D:\emberline\backups`, `D:\emberline\logs` and `D:\emberline\scheduler`.
3. Install Python and copy `repo/scheduler` and `repo/jobs` with scp from dev-ws.
4. Copy the newest firings and inventory backups from web-srv `D:\emberline\backups\remote\` ([[restore-db-from-backup]]).
5. Run `Register-Tasks.ps1 -Role studio` (the studio tasks from [[scheduled-tasks]], unlimited time limit for the daemons).
6. Plug in the controllers and confirm COM3, COM4 and the TCP host for k3.
7. Start `KilnScheduler` with `--adopt` only if a kiln is mid-firing; otherwise normally.
8. Run `Test-Health.ps1 -Target studio` and journal the rebuild.

Details of the machine: [[studio-srv]].
