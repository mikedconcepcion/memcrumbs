# Changelog

What changed for users, newest first. Versions follow [semver](https://semver.org/) from 1.0; before 1.0 the
command line and config may still change, and every such change is listed here.

## [0.3.0] — 2026-10-11

### Added

- **`memcrumbs update`** upgrades to the newest release in one step. It uses the tool that installed memcrumbs
  (pip, pipx or uv), then re-indexes your projects and refreshes the block, skill and allow rules `wire` put in your
  repos. `update --check` only says whether a newer release exists.
- **An opt-in update notice:** with `[update] notify = true`, memcrumbs checks PyPI at most once a day, after slow
  commands such as `check` or `index`, and the session header says when a newer release is out.

### Changed

- Install from PyPI: `pip install memcrumbs`.
- The PyPI page links to the website, the source, the issues and this changelog, and its links work.
- The only network use is updating: `memcrumbs update` when you run it, and the daily check if you turn it on.

## [0.2.0] — 2026-10-11, the first public release

### Find and trust what the wiki knows

- **`find`** returns a few ranked hits with `path:line`, the age of each (`v12d`) and its status (`STALE`,
  `SUPERSEDED→page`, `REJECTED`, `SRC-CHANGED 3d` when the code a page cites changed after it was checked).
  Questions in plain words work: question words are dropped, a small thesaurus and your own synonyms bridge
  vocabulary, and identifiers match by their parts. Inline filters: `kind:decision status:rejected path:booking`.
- **`about <file>`** lists what the wiki says about a file before an agent edits it: decisions and their
  verdicts, incidents, gotchas, runbooks. Code hits carry the same line.
- **`fact <key>`** answers current values (versions, ports, hosts) from one table, optionally read from the
  source file every time; `{{fact:key}}` in a page prints today's value, and `check` flags pages that state an
  old one.
- **`outline` and `sym --body`** show functions and classes with line ranges, so an agent reads 40 lines, not the
  whole file. Python, PowerShell, MQL and Markdown are built in.

### Record what happened

- **`decision`** (with the options considered, the evidence and when to revisit), **`incident`** (keyed on the
  symptom someone will see next time), **`log`** for the journal, **`rule`** for a standing rule.
- **`verify`** and **`supersede`** keep pages current; superseded pages rank below current ones.
- **`check`** lints the wiki: secrets, broken links, stale pages, conflicting facts, runbooks without
  preconditions, verify and rollback steps, and instruction-like text. `--baseline` lets an old wiki start
  clean.

### Let memcrumbs notice things, and decide yourself

- **`suggest`** offers, with evidence: near-duplicate pages, pages to split or link, questions the wiki could not
  answer (opt-in local log), gotchas that can become permission prompts, repeated command sequences that could
  become a skill (opt-in reading of local session transcripts), and auto-memory notes the wiki already holds.
  `suggest apply ID` writes one after your yes; `suggest undo ID` restores every byte.
- **Review of agent-written knowledge:** pages an agent wrote say `UNREVIEWED` until a human checks them, and
  new rules and gotchas reach the session header after `memcrumbs review`.

### Stay in control

- **A session header** under a hard token cap (default 1,000): rules first, then the map, top gotchas and recent
  journal lines.
- **`plan` and `dashboard`**: see which pages need a refresh and what it would cost in tokens, approve pages and a
  budget, and the agent works through exactly that.
- **`doctor`** checks the install, config, index and the wired hook; `doctor --share` gives a summary you can
  paste into a bug report safely.
- **`wire`** connects a repo to Claude Code (a CLAUDE.md block, a session hook, a skill, optional allow rules for
  read-only lookups) or other agents (`--target agents`), and `wire --remove` undoes it byte for byte.

### Safe by default

- Secrets are redacted from everything indexed, printed or written, and redaction fails closed. `secret-add`
  stores only a hash of a value you want blocked. `.env` files, keys and credential files are never indexed.
- memcrumbs writes only inside the project's wiki, its index folder and the files `wire` names.
- `scan` checks a folder, an sdist or a wheel for secret-like values before you publish.
- Standard library only: no model calls, no network, no background service, no per-tool-call hooks.

### Speed (generated 10k-file repo)

Full index in about 10 s on a desktop (5 s on Linux CI), incremental refresh 0.1 s, and `find` in about
25–100 ms depending on the machine.

## [0.1.0]

First version: wiki and SQLite FTS5 index, outliners (Python, PowerShell, MQL, Markdown), `find`, `page`,
`outline`, `sym`, `log`, `check`, `scan`, `status` and `wire`.
