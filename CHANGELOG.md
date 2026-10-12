# Changelog

What changed for users, newest first. Versions follow [semver](https://semver.org/) from 1.0; before 1.0 the
command line and config may still change, and every such change is listed here.

## [0.5.0] — 2026-10-12

### Added

- **Approve in the Claude Code session: `/memcrumbs-review`.** You no longer open a second terminal to approve the
  rules and gotchas the agent drafted.
  - The new memcrumbs-review skill shows you each item in full, asks, then runs the approval.
  - Claude Code asks you before the approval runs, in every permission mode, and that answer is the approval.
  - It also takes you through suggestions, quarantined pages and the refresh budget.
- **`wire` and `init` add ask rules for your decisions:** `review --approve`, `quarantine --lift`, `suggest apply`
  and `undo`, `plan --approve`, `init --remove`.
  - Inside Claude Code, memcrumbs runs these only in the form the rules name (`memcrumbs review --approve …`), so
    the prompt cannot be skipped by writing them another way.
  - Other agent shells are still refused, and at a terminal you still type the code.
- **The secret check runs by itself.** `check` runs once a day after a slow command, and the session header names
  any page that holds secret-like text (never the text).
- **Skill offers from the work you repeat.** memcrumbs finds task flows and pipelines in Claude Code's
  transcripts: the same steps in the same order in 3 tasks on 2 days, or in 6 tasks.
  - Steps are named by what they run (`build.py`, `unittest discover`, `git tag`, `npm run build`).
  - A pipeline (no edits between its steps) could be a script; a task flow becomes a skill's checklist.
  - The check runs once a day by itself. The header pings with a count, and the agent lists the offers only when
    you say so, since listing costs tokens.
  - `init`'s wiring question now also asks to turn this on: the transcripts are read locally, and
    `init --remove` turns it off again.

### Changed

- `quarantine --lift` is written `memcrumbs quarantine --lift <page>`. `memcrumbs review` also lists quarantined
  pages.

### Fixed

- The map that `init` drafts no longer lists pip's `*.egg-info` folders, and they are left out of the index like a
  virtual environment.

## [0.4.2] — 2026-10-12

### Fixed

- **On Windows, `memcrumbs update` works through the `memcrumbs` command when Python's Scripts folder and %TEMP%
  are on different drives**, for example a Python folder that is a junction to another drive. pip could not move
  the running launcher across drives, so every upgrade failed there.
  - `update` now renames its launchers within their folder before pip runs, so pip has nothing to move.
  - The launcher that is still running stays as `memcrumbs.exe.old-…` until the next `update` deletes it.
  - **Upgrading from 0.4.1 or older on Windows:** run `python -m memcrumbs update` once.
- **`doctor` names the `~emcrumbs` folders a failed upgrade left in site-packages.** pip warns "Ignoring invalid
  distribution" until they are deleted.
- **Loading a pack by entry point no longer holds the `memcrumbs` launcher open.**

## [0.4.1] — 2026-10-11

### Fixed

- **`memcrumbs update` never leaves memcrumbs uninstalled without saying so.** pip can fail halfway, for example
  when another process holds a file open, and fail to put the old version back. After any pip run, `update` now
  checks in a new process that memcrumbs starts:
  - if pip left it uninstalled, `update` reinstalls the version you had and checks again;
  - if that fails too, it says plainly that memcrumbs is not installed and prints the one command that fixes it;
  - it no longer says "Nothing else was changed" without checking.
- **pip's own error is shown** (the file it could not replace), not its closing hint. pip's full output is kept in
  the project's `.memcrumbs/update.log`, redacted.
- **On Windows, a permission failure is retried once** after 5 seconds: antivirus and indexers hold new files
  briefly.

## [0.4.0] — 2026-10-11

### Added

- **One-command setup:** `cd your-repo && memcrumbs init`. It names the project after the repo and writes a starter
  wiki whose map is drafted from the repo (its README, languages, folders, test command and CI). It indexes the
  code and the repo's own markdown, skipping generated folders such as a virtual environment. It asks once before
  wiring Claude Code (`--yes` answers ahead), then runs `doctor`, all in at most 8 lines. Running it again
  repairs and upgrades, and says when nothing changed. `memcrumbs init --remove` takes the wiring out byte for
  byte and keeps the wiki (`--delete-wiki` deletes it too). `memcrumbs init NAME` outside a repo still makes a wiki
  on its own.
- **A first-run step:** a new wiki's header says rules and gotchas are empty, and the skill tells the agent to
  draft them from CLAUDE.md, the README and the code. The drafts wait for your `memcrumbs review`.

### Changed

- **`memcrumbs update` finishes an upgrade made by hand** (`pip install --upgrade`, `git pull`): it re-indexes and
  refreshes the wiring once, and a second run changes nothing. The header and `doctor` say when an upgrade is not
  finished.
- **A new wiki starts clean:** `rules.md` and `gotchas.md` start empty (no placeholder lines), and the header
  skips a section with nothing in it.
- **A plugin that does not load:**
  - `doctor` says how to keep it (copy it into the project's `plugins/` folder) or take it out;
  - its documents stay in the index, no longer refreshed, and `index` says how many;
  - once it is out of `plugins`, they leave the index.
- **Runbook skill offers are owner-only in more cases:** also when the runbook's summary, tags or aliases say live
  or production, or a step in its code runs on a remote host or deploys.
- **`suggest`:** `split` is offered only for a page with sections to split; a long table is already returned row by
  row.

### Fixed

- `wire` no longer calls its own skill "different from this version" when only the line endings differ, as on
  every Windows checkout with git's `autocrlf`. Such a skill is now refreshed and removed like any other.

### Upgrading from 0.2.0

0.2.0 has no `update` command: run `pip install --upgrade memcrumbs`, then `memcrumbs update` once to finish.

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
