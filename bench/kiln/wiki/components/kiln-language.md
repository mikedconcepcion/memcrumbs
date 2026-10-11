---
title: Kiln Schedule Language
summary: Brace-based language for firing profiles in .kiln files - top-level items, grammar, error codes and how to check a file
verified: 2026-09-29
tags: [kiln-language, profiles, component]
sources: [repo/scheduler/kiln_parser.py, repo/scheduler/validator.py, repo/profiles/common.kiln, repo/profiles/cone6_glaze.kiln]
aliases: [KSL, schedule language, profile syntax, firing profile format]
---

# Kiln Schedule Language

Files `*.kiln` in `repo/profiles/`. There is no language server; the only checker is
`python -m scheduler.profile_loader --check <file>`.

## Top-level items
`const NAME = value;`, `include "file.kiln";`, `kiln NAME { ... }`, `macro NAME(args) { ... }`,
`profile NAME (key: value, ...) { ... }`. Line comments start with `//`. One statement per line, braces balanced.

## Inside a profile
`segment NAME { ramp RATE/h to TEMP; hold 30m; }`, `use macro(args);`, `on fault { alarm "text"; abort; }`.

## Files
- `common.kiln` - constants (`MAX_TEMP = 1285`), kiln definitions k1, k2, k3, shared macros such as `slow_cool`.
- `cone6_glaze.kiln` - the cone 6 glaze firing for k2. Others: `cone04_bisque.kiln`, `cone10_reduction.kiln`, `crystalline_glaze.kiln`, `tile_fast.kiln`.

## Rules
- Targets above `MAX_TEMP` fail with E104; see [[2026-05-19-kiln-overfire-profile-typo]].
- Unbalanced braces: E001. Unknown macro: E201. Unknown kiln in a profile header: E202.
- Changing a live profile needs owner approval ([[rules]]). Loader: [[kiln-scheduler]].
