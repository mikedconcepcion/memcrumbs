---
title: Gotchas (do-not-repeat)
summary: ranked traps; the Top section is printed at every session start
verified: 2026-10-10
tags: [gotchas]
---
# Gotchas

## Top
- Restart the API with the service manager, never by killing the PID — the supervisor flaps. [[api]]
- Config is read once at start: a config change needs a restart. [[api]]

## More
- (one line each, newest first within a group)
