---
title: Kiln k2 overfired because of a typo in a profile
summary: A cone 6 glaze profile with target 1322 instead of 1222 took kiln k2 100 degrees too hot and ruined a full load
verified: 2026-09-20
tags: [incident, kiln, profiles, money]
sources: [repo/scheduler/validator.py, repo/profiles/cone6_glaze.kiln]
aliases: [overfire, kiln too hot, melted load]
---

# Kiln k2 overfired

## What happened
On 2026-05-19 a glaze firing on k2 was edited by hand and the last ramp read `ramp 150/h to 1322;`. The kiln reached
1322 C before the operator noticed. Load lost: about 480 in glazed work, shelves partly glazed to the kiln floor.

## Root cause
The controller hard limit is 1285 but the temperature limit check lived only in the old loader path. The new
`profile_loader` skipped the check when the target was written as a plain number inside a segment.

## Fix
`validator.check_limits()` now rejects any `ramp ... to X` where X is above `MAX_TEMP` (error E104), and the
loader calls it on every segment and macro expansion. The profile was corrected to 1222.

## Prevention
Every profile change needs owner sign-off ([[rules]]). Run `--check` ([[kiln-language]]). Trap number 5 in [[gotchas]].
