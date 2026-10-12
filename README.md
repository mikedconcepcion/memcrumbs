# memcrumbs

**Project memory for Claude Code and other coding agents: a small markdown wiki your agent reads before it
reads your code, and a local index that answers in a few hundred tokens.**

Every new session, a coding agent starts from zero. It greps, it reads whole files, it rediscovers the same
facts, and it repeats mistakes your team already made. Notes kept by hand drift until they contradict the
system, and sometimes they leak a secret.

memcrumbs gives each project a memory that stays small, current and safe.

## Start in five minutes

```bash
pip install memcrumbs
cd /code/myapp && memcrumbs init
```

Three things work from the first session:

- **Rules first, every session.** A short header (under 1,000 tokens) brings your standing rules, the project
  map and the top gotchas, so "never deploy on Friday" is read before anything else. In the first session the
  agent drafts the rules from CLAUDE.md, the README and the code, and you approve them with `/memcrumbs-review`.
- **Answers instead of file dumps.** `memcrumbs find "how do I roll back a bad deploy"` searches your repo's
  docs and code symbols from the start, before you write a single wiki page, and returns a few ranked hits with
  `path:line`, how old each one is and whether it is still current. The agent then opens one section or one
  function, not a 4,000-line file. On httpx, with no wiki page written, the answer was in the top 3 for 75% of
  32 questions written blind (90% of the code questions), at about 380 tokens per answer ([method and data](https://github.com/mikedconcepcion/memcrumbs/tree/main/bench/httpx)).
- **What the wiki says about a file, before an edit.** `memcrumbs about deploy.ps1` lists the decisions,
  incidents and gotchas that cite it. It has more to say as you record them.

That is the whole minimal setup. Everything under [When you need more](#when-you-need-more) is optional.

## What it looks like

```text
$ memcrumbs find "how do I roll back a bad deploy" -n 3
[run ] Roll back booking app — wiki/runbooks/rollback-booking.md:1 · v8d
       …booking [release] in under two minutes by repointing the current junction [Roll back] booking…
[run ] Deploy booking app — wiki/runbooks/deploy-booking.md:1 · v8d
       Numbered steps to [ship] a new booking app [release] to web-srv, with the…
[wiki] Booking web app › Behaviour notes — wiki/components/booking-app.md:23 · v8d
       …[Deploy] with [[deploy-booking]]; [undo] with [[rollback-booking]].
read: memcrumbs page rollback-booking · more: -n 6

$ memcrumbs about repo/ops/EmberOps.psm1
EmberOps.psm1 — cited by 1 decision (ACCEPTED), 2 incidents, 1 runbook
[dec ] Unlimited execution time for daemon tasks — wiki/decisions/2026-08-12-execution-time-limit-zero.md:1 · ACCEPTED
[inc ] BOM in a PowerShell script silently broke a scheduled task — wiki/incidents/2026-07-29-bom-breaks-scheduled-task.md:1
…
```

(From the invented sample project in `bench/kiln`.)

## When you need more

- **It remembers what happened and why.** Decisions (including the ones you rejected), incidents with the
  symptom someone will see next time, runbooks, and a dated journal. Asking "did we ever try Postgres?" finds
  the rejected decision instead of a fresh attempt.
- **It knows when it may be wrong.** Every hit says how long ago it was verified, flags `STALE` pages, and says
  `SRC-CHANGED` when the code a page describes changed after the page was checked.
- **It keeps one current value per fact.** Versions, ports and hosts live in one table, optionally read straight
  from the source file, and `check` flags pages that still state an old value.
- **You approve what the agent writes.** Rules and gotchas an agent adds reach the header only after you
  approve them, in the session with `/memcrumbs-review`; Claude Code asks you before each approval runs.
- **It notices things for you, and asks first.** `memcrumbs suggest` offers near-duplicate pages to merge,
  questions the wiki could not answer, gotchas that can become permission prompts, task flows and pipelines you
  keep repeating that could become a skill, and auto-memory notes the wiki already holds. Once a day the header
  pings with a count; the offers are listed only when you ask. Nothing changes until you say yes, and every
  change can be undone byte for byte.
- **Your secrets stay out.** Everything indexed, printed or written is redacted; `.env` files and keys are never
  indexed; `memcrumbs scan` checks a folder or a package before you publish it.
- **You stay in control of token spend.** Re-indexing is free and local. Rewriting stale pages is agent work, so
  `memcrumbs plan` and the dashboard let you pick the pages and the budget.

Standard library only: no model calls, no background service, no per-tool-call hooks, and no network use except
`memcrumbs update`, when you run it. Your wiki is plain markdown in your own folder.

## Install

```bash
pip install memcrumbs            # Python 3.11+; puts `memcrumbs` on PATH (pipx and uv tool work too)
```

To upgrade later, run `memcrumbs update`: it installs the newest release the same way memcrumbs was installed,
re-indexes your projects and refreshes the agent setup in your repos. After an upgrade by hand
(`pip install --upgrade memcrumbs`), run `memcrumbs update` once to finish it. Add `[update] notify = true` to a
project's config to get a one-line notice in the session header when a new release is out.

Your wikis live outside the package, in `~/.memcrumbs/projects` by default. To keep them somewhere else (for
example a private git repo), set `projects_dir` in `~/.memcrumbs/config.toml` or the `MEMCRUMBS_PROJECTS`
environment variable.

## What `init` does

`init` names the project after the repo, writes a starter wiki with a map drafted from the repo (README,
languages, folders, tests, CI), indexes the code and the repo's markdown, and checks the result. It asks once
before it wires Claude Code (a CLAUDE.md block, a session-start hook, read-only allow rules, a rule that makes
Claude Code ask you before each of your decisions, and two skills).
Running it again repairs and upgrades; `memcrumbs init --remove` takes the wiring out again, byte for byte.

From then on, every Claude Code session in that repo starts with the header, and the agent looks things up with
`memcrumbs find`. In the first session the agent drafts your rules and gotchas from CLAUDE.md, the README and the
code; they reach the header once you approve them. Type `/memcrumbs-review` in Claude Code: the agent shows you
each line, and Claude Code asks you before the approval runs. Inside the repo (or the project
folder) `-p` can be left out. Write the wiki as you go:

```bash
memcrumbs log "rotated the API key" --tag ops                        # a dated journal line
memcrumbs decision "Move bookings to Postgres" --status rejected --why "too much to run for our size"
memcrumbs incident "Nightly task died after 72 h" --symptom "no reports since Tuesday" --cause "task time limit"
memcrumbs check                                                      # lint: secrets, links, stale pages, …
```

To do each step yourself (or have your agent follow them), see the step-by-step setup in
[docs/adopting.md](https://github.com/mikedconcepcion/memcrumbs/blob/main/docs/adopting.md).

## Everyday commands

| Command | What you get |
|---|---|
| `find <words>` | Ranked hits with `path:line`, age and status. Filters: `kind:decision status:rejected path:booking` |
| `page <name> [section]` | A page, or one section of it |
| `outline <file>` · `sym <name> [--body]` | Functions and classes with line ranges · where a symbol is defined |
| `about <file>` · `fact [key]` | What the wiki says about a file · a current value with its source |
| `log` · `decision` · `incident` · `rule` | Write the journal, a decision, an incident, a standing rule |
| `verify <page>` · `supersede <page> --by <new>` | Mark a page re-checked today · replaced by a newer one |
| `suggest` · `suggest apply ID` · `suggest undo ID` | Offers to improve the wiki and the agent setup, applied only on your yes |
| `check` · `scan [path]` | Lint the wiki · secret-scan a folder, an sdist or a wheel |
| `plan` · `dashboard --open` | What needs a refresh and what it would cost · an HTML overview |
| `doctor` · `stats --usage` · `bench` | Health check · output size per command · lookup quality on your own questions |
| `update` · `update --check` | Upgrade to the newest release and refresh what an upgrade needs · only say whether one exists |

Every command takes `--json`. Full reference: [docs/cli.md](https://github.com/mikedconcepcion/memcrumbs/blob/main/docs/cli.md).

## Documentation

- [Setting up a project](https://github.com/mikedconcepcion/memcrumbs/blob/main/docs/adopting.md), step by step
- [Writing good crumbs](https://github.com/mikedconcepcion/memcrumbs/blob/main/docs/writing-crumbs.md): pages, rules, gotchas, decisions, incidents, facts
- [Configuration](https://github.com/mikedconcepcion/memcrumbs/blob/main/docs/config.md) · [Command reference](https://github.com/mikedconcepcion/memcrumbs/blob/main/docs/cli.md)
- [Plugins and packs](https://github.com/mikedconcepcion/memcrumbs/blob/main/docs/plugins.md): add a source, a check, a header section or a language
- [Security](https://github.com/mikedconcepcion/memcrumbs/blob/main/SECURITY.md): what redaction promises and what it does not

## Contributing and reporting bugs

- **Found a bug?** [Open an issue](https://github.com/mikedconcepcion/memcrumbs/issues/new/choose) with the bug
  template. Paste the output of `memcrumbs doctor --share`: it holds versions, counts and timings only, never
  your paths, page text or secrets.
- **An idea or a missing feature?** Use the feature request template. Say what you were trying to do.
- **A security problem?** Please report it privately, as described in [SECURITY.md](https://github.com/mikedconcepcion/memcrumbs/blob/main/SECURITY.md), not in a
  public issue.
- **Want to contribute code or docs?** See [CONTRIBUTING.md](https://github.com/mikedconcepcion/memcrumbs/blob/main/CONTRIBUTING.md): how to run the tests, the few
  rules the code follows, and what a good pull request looks like.

## Status

Alpha: usable day to day, with the command line and config still allowed to change before 1.0. Changes are
listed in [CHANGELOG.md](https://github.com/mikedconcepcion/memcrumbs/blob/main/CHANGELOG.md). License: [Apache-2.0](https://github.com/mikedconcepcion/memcrumbs/blob/main/LICENSE).
