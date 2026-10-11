---
title: Emberline wiki index
summary: Start here - map of the Emberline Ceramics operations wiki and where each kind of knowledge lives
verified: 2026-10-08
tags: [index]
sources: [repo/README.md]
---

# Emberline Ceramics operations wiki

Emberline is a small ceramics studio. The owner and the operator run it; several AI coding agents
work on the code in parallel from `dev-ws`. Servers are `studio-srv` and `web-srv`.

## Map
- [[rules]] - standing human rules (owner approval gates). Read before any live action.
- [[gotchas]] - ranked traps that already bit us.
- `systems/` - one page per server and service: [[studio-srv]], [[web-srv]], [[scheduled-tasks]], [[backup-system]].
- `components/` - code-level pages: [[booking-app]], [[kiln-scheduler]], [[chat-bot]], [[payments]], [[kiln-language]].
- `runbooks/` - exact numbered procedures, e.g. [[deploy-booking]], [[restore-db-from-backup]].
- `incidents/` - dated post-mortems (`YYYY-MM-DD-slug`).
- `decisions/` - research and decisions with a verdict; most experiments were rejected.
- `journal/` - one line per action, per month: [[2026-10]].
- `reference/` - pasted vendor material, lowest trust: [[profire-controller-manual]].
- Stale or replaced: [[network-ports-2025]] (stale), [[backup-procedure-2025]] (superseded).
- `legacy/notes.md` (outside the wiki) is raw material and may contradict these pages.

## How to use it
Trust order: code in `repo/`, then verified wiki pages, then journal, then legacy notes.
