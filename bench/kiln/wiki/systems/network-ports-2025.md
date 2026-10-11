---
title: Network and ports (2025 layout)
summary: Old list of hosts, ports and the SSH jumpbox as of late 2025
verified: 2025-11-03
tags: [systems, network, ports]
sources: [legacy/notes.md]
---

# Network and ports (2025 layout)

Written when the servers were reached through a jumpbox.

- Jumpbox: host `jump-gw`, SSH on port 2222, then hop to the servers.
- Booking app: port 5000 (plain http, no proxy).
- Chat bot: port 8000.
- Kiln scheduler status API: port 7400; telemetry broadcast on UDP port 7411.
- Label printer on `print-srv`, raw port 9100.
- Backups copied at 03:00 to `\studio-srv\share\backups`.
- Controllers: k1 on COM3, k2 on COM4.
- Monitoring dashboard: host `mon-srv`, port 3000.
- Time sync: both servers pointed at host `time-srv` (NTP, UDP 123).

Everything is flat on one private subnet, with no firewall rules besides the jumpbox.
