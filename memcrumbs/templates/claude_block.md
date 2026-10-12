# Project knowledge: memcrumbs wiki "{name}"

Look up project knowledge here first: rules, decisions, incidents, runbooks, how-to in the docs, and anything you
do not know the name of yet (results are small and capped, with path:line, age and status). When you already know
the exact name (a function, class, setting or error text), search for it directly with Grep, or `sym` for a symbol.
- `memcrumbs -p {name} find "<2-4 distinctive words>"` — wiki, runbooks, decisions, incidents, docs, code symbols
- `memcrumbs -p {name} page <name> [section]` — one page or one section · `memcrumbs -p {name} outline <file>` — symbols + line ranges, then Read only that range
- `memcrumbs -p {name} sym <name> [--body]` — where a function is defined · `memcrumbs -p {name} log "<note>"` — dated journal line

Hits marked STALE or SUPERSEDED are not current fact; REJECTED decisions record ideas that were tried and failed.
Keep it true: when a task changes how something works, update that wiki page once at the end
(`{wiki}`, skeleton: `memcrumbs template`), then `memcrumbs -p {name} check`. Never write secret values — say where they live.
Details: skill `memcrumbs`.
