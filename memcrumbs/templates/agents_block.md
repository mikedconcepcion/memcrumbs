# Project knowledge: memcrumbs wiki "{name}"

At the start of a session run `memcrumbs -p {name} status` and follow its Rules section.
Before reading or searching files, look it up (results are small and capped, with path:line, age and status):
- `memcrumbs -p {name} find "<2-4 distinctive words>"` — wiki, runbooks, decisions, incidents, docs, code symbols
- `memcrumbs -p {name} find "<error text, pasted whole>"` — tried as the exact text first; "not recorded" means the failure is new
- `memcrumbs -p {name} page <name> [section]` — one page or one section · `memcrumbs -p {name} outline <file>` — symbols + line ranges
- `memcrumbs -p {name} sym <name> [--body]` — where a function is defined · `memcrumbs -p {name} log "<note>"` — dated journal line

Hits marked STALE or SUPERSEDED are not current fact; REJECTED decisions record ideas that were tried and failed.
Keep it true: update the wiki page once at the end of a task (`{wiki}`), then `memcrumbs -p {name} check`.
Never write secret values — write where they live.
