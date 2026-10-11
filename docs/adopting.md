# Setting up memcrumbs in a project

Written so that you, or your coding agent, can follow it step by step. Steps marked **(ask the owner)** change
the machine or the project's agent setup: an agent should get explicit approval first.

Your wiki, config, plugins and question set are yours. They live in your projects folder
(`~/.memcrumbs/projects` by default), never in the memcrumbs package.

## 1. Install (ask the owner)

```
pip install git+https://github.com/mikedconcepcion/memcrumbs
memcrumbs --version
```

Python 3.11 or newer, nothing else. To keep wikis in a private git repo, point `projects_dir` at it in
`~/.memcrumbs/config.toml` (or set `MEMCRUMBS_PROJECTS`).

## 2. Create the project

```
memcrumbs init <project> --repo <path to the code> --title "<Readable name>"
memcrumbs -p <project> doctor
```

`init` writes `memcrumbs.toml`, an empty `secrets.deny` and a starter wiki: `rules.md`, `index.md` (the map) and
`gotchas.md`. The journal starts with your first `memcrumbs log`.
`doctor` checks the install, the config, the index and, later, the session hook. Fix every `FAIL`, read every
`WARN`, and run it again after each step below.

## 3. Write the first pages

- **`wiki/rules.md`, section `## Top`:** the standing rules and approval gates, one line each ("Ask the owner
  before deploying to production"). The session header shows them first, every time.
- **`wiki/index.md`, section `## Map`:** where things are, one line per area, linking pages with `[[name]]`.
- **`wiki/gotchas.md`, section `## Top`:** the traps that already bit you, worst first.

How to write pages that are found and stay true: [writing-crumbs.md](writing-crumbs.md).

## 4. Configure what to index

In `memcrumbs.toml` ([reference](config.md)):

- `repos` and `[code]`: the code to outline (Python, PowerShell, MQL and Markdown are built in; plugins add more).
- `[[docs]]`: other markdown trees, such as research notes or an old notes folder (`kind = "legacy"` ranks lowest).
- `[security] secret_keys`: key-name patterns your configs use for credentials (for example `["cfg*key"]`).
  Any key ending in password, secret, token or apikey is already covered.
- `[security] never_index`: files that hold credentials, added to the built-in list (`.env*`, keys, …).
- `[search] synonyms`: the words your team uses for the same thing (`[["kiln", "furnace"]]`).

```
memcrumbs -p <project> index
memcrumbs -p <project> check        # fix every E (a secret) first
```

## 5. Connect it to the agent (ask the owner)

```
memcrumbs -p <project> wire --repo <repo> --allow           # dry run: shows what it would change
memcrumbs -p <project> wire --repo <repo> --apply --allow
memcrumbs -p <project> doctor                               # the hook runs: exit 0, time, size
```

`wire` adds a block to the repo's `CLAUDE.md`, a SessionStart hook that prints the header, and the memcrumbs
skill. `--allow` lets the read-only lookups (`find`, `page`, `outline`, `sym`, `status`, `about`, `fact`) run
without a permission prompt; without it every lookup asks. `--target agents` writes an `AGENTS.md` block for
other agents. `wire --remove --apply` takes it all out again, byte for byte.

## 6. Check that lookups work

Write down 20–40 questions from real recent work, each with the page or file that answers it:

```
memcrumbs -p <project> bench --add "why did the nightly task stop after three days?" --expect task-time-limit
memcrumbs -p <project> bench          # recall@1/@3, tokens per answer, and the misses
```

Aim for recall@3 of 0.85 or more. A miss usually means a page needs a better `summary`, headings or
`aliases`. The file is `wiki/bench.toml` and stays in your project.

## 7. Day to day

- **Record as you go:** `memcrumbs log` for events, `decision` and `incident` for those, `rule` when the owner
  corrects how the agent works. Agent-written rules and gotchas reach the header after the owner runs
  `memcrumbs review`.
- **Keep it current on a budget:** re-indexing is automatic and free; rewriting stale pages costs tokens. The
  owner opens `memcrumbs dashboard --open` (or runs `memcrumbs plan`), picks pages and a budget, and the agent
  works through `memcrumbs plan next` until the budget is used.
- **Take the offers that help:** `memcrumbs suggest` lists merges, missing pages, guards and skills, with the
  evidence. `suggest apply ID` writes one after the owner's yes, and `suggest undo ID` reverses it.
- **Weekly:** `check`, `bench`, and `stats --usage` (output size per command).

## Upgrading

```
pip install --upgrade git+https://github.com/mikedconcepcion/memcrumbs
memcrumbs -p <project> index                                  # a new index schema rebuilds here, once
memcrumbs -p <project> wire --repo <repo> --apply --allow     # refreshes the block, the skill and the allow rules
memcrumbs -p <project> doctor
```

The wiki is plain markdown and an upgrade never rewrites it. To roll back, run
`memcrumbs -p <project> wire --remove --apply` and reinstall the previous version.

## Something wrong?

Run `memcrumbs -p <project> doctor --share` and attach its output to a
[bug report](https://github.com/mikedconcepcion/memcrumbs/issues/new/choose). It holds versions, counts,
timings and pass/fail only: no paths, names or page text.
