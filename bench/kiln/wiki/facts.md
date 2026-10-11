---
title: Current facts
summary: one registry of current values (versions, ports) with their source; pages write {{fact:key}} instead of a copy
verified: 2026-10-08
tags: [facts, registry, versions, ports]
---
# Current facts

Each value lives here once. Bound keys are read from their source file on every lookup (memcrumbs.toml
`[facts.bind]`). In a page, write `{{fact:booking_version}}` and `memcrumbs page` prints today's value.

| key | value | about | source | verified |
|---|---|---|---|---|
| booking_version | 3.4.1 | booking app version; booking site version | repo/booking/__init__.py | 2026-10-08 |
| booking_port | 8080 | booking app port; BookingWeb port | repo/config/booking.toml | 2026-10-08 |
| chatbot_port | 8091 | chat bot port; ChatBot port | wiki/components/chat-bot.md | 2026-10-08 |
