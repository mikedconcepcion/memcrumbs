# CLI reference (v1)

`memcrumbs` (alias `memcrumb`). The project comes from `-p NAME`, `$MEMCRUMBS_PROJECT`, or the current
directory (inside a project folder or one of its `repos`); with a single project configured, that one.
`-p` may come before or after the subcommand.

Options every command accepts: `--json` (one JSON object instead of text), `--full` (lift the output cap;
for `index`, re-parse every file). Text output is capped: `find` at about 600 tokens, every other command at
about 2,000; a cut output ends with `… cut N more lines … Next: <command>`. Tokens are estimated as chars/4.

## Read

| Command | What it prints |
|---|---|
| `find <words…> [-k KINDS] [-n N] [--explain]` | Ranked hits: `[kind] title › section — path:line · label` plus a snippet, then the exact command to read the top hit. When a top-3 hit's matching line links elsewhere ("… without a
restart: [[live-tuning]]"), the linked page is shown under it as `→ see <page> — path:line` (rank unchanged). Inline filters: `kind:decision`, `status:rejected`, `path:booking` (`in:` = `path:`); filters alone list matching pages; with `status:` alone, pages whose own status matches come first, then
the table rows and sections that carry it, each with `path:line`. `--explain` first shows how the query was read: each term, how many docs contain it, its synonyms (and whether they are damped), the intent (code first, runbooks first) |
| `page <name> [section]` | Page header (title, path, trust label, summary, verified, status, tags), then the page, or a table of contents with line numbers if it is long, or one section with its subsections |
| `outline <file\|dir> [--kinds K] [--grep W] [--depth N]` | Symbols with `Lstart-end`; a folder lists files with line and symbol counts. Needs no project |
| `sym <name> [--in PATH] [--body] [-n N]` | Where a symbol is defined (exact, then prefix, then substring); `--body` prints the first match's source |
| `about <file>` | What the wiki records about a file: the decisions (with their verdicts), incidents, gotchas, rules and pages that cite it in `sources:` or in their text, verdicts first, at most 5 lines (`--full` for all). A bare file name matches every citation of that name. Code hits in `find` and the end of `outline` carry one line, `cited by: 1 decision (REJECTED), 1 incident`, when decisions, incidents, gotchas or rules cite the file |
| `fact [key]` | A current value from the facts registry (`wiki/facts.md`), with its source and age, in one line: `booking_version = 3.4.1 — bound to repo/booking/__init__.py · v3d · wiki/facts.md:14`. A key is matched exactly, else by its words or `about` phrases; no key lists them all |
| `status [--hook]` | The session header (below). `--hook`: never fails, always exits 0 |
| `stats [--usage]` | Index counts; `--usage`: output size (p50/p95/max tokens), truncation rate and p95 latency per command |
| `check [--baseline] [--all] [--strict] [--dupes]` | Wiki lint + plugin checks: `E` secrets · `W` frontmatter, length, broken links, bad status, injection-like text, broken generated blocks, plugin load errors, a page that states a registered fact with another current value, an unknown `{{fact:key}}`, a fact binding that fails or disagrees with the table · `I` stale (`verified` too old, or `sources:` changed since), an incident with no symptom, a rejected or parked decision with no evidence, a runbook without preconditions / a verify step / a rollback, a page that replaces another without saying so. `--baseline` records today's warnings and curation steps, and later runs list only new ones (errors are never baselined); `--all` lists the known ones too; `--strict` exits 1 on new warnings as well; `--dupes` adds near-duplicate pages |
| `bench [QUESTIONS.toml] [--min-recall3 X] [-k N]` | recall@1/@3, MRR, tokens per answer, latency, per category and for paraphrases; recall@3 also counting `→ see` pointers; lists misses. Default file: the project's `wiki/bench.toml` |
| `plan [next]` | The wiki refresh plan: pages that need an agent (stale, sources changed, unverified, secrets, injection, broken links …) with priority and est. tokens. `next`: the next approved page for the agent, with the exact `git log` command for each changed source; stops at the budget |
| `update [--check] [--no-wire] [-p NAME]` | Asks PyPI for the newest release; if it is newer, upgrades with the tool that installed memcrumbs (pip, pipx or uv), then, running the new code, re-indexes each project (or only `-p NAME`) and refreshes the block, skill and allow rules `wire` installed in each repo. `--check` only reports; `--no-wire` skips the refresh. A source checkout is never upgraded. After an upgrade by hand (`pip install --upgrade`, `git pull`), it runs the same index and wire steps once: `wire` records the version that applied the wiring, and the header and `doctor` say when an upgrade is not finished. After every pip run it checks, in a new process, that memcrumbs starts; if pip left it uninstalled, it reinstalls the version that was running (and says so, or prints the one command that fixes it). pip's own `ERROR:` line is shown, its whole output is kept in the first project's `.memcrumbs/update.log` (redacted), and on Windows a permission failure is retried once. On Windows it first renames its launchers within their folder, so pip never has to move the running `memcrumbs.exe` (the old copy is deleted by the next `update`). The only command that uses the network |
| `doctor [--share]` | Install, config (unknown or deprecated keys), wiki, `secrets.deny`, plugins, index, the wired hook *run for real* (exit 0, ms, tokens), usage, private bench, plan. `--share`: content-free JSON (versions, counts, timings, pass/fail) |
| `scan [PATH]` | Secret scan of a folder, a file, an sdist or a wheel. Needs no project |

Kinds for `-k` / `kind:`: `wiki` (all wiki kinds), `runbook`, `decision`, `incident`, `journal`, `doc`,
`research`, `memory`, `legacy`, `code`, `bug`, `log`, plus any kind a plugin source emits.

**Trust labels** on hits: `v12d` verified 12 days ago · `m3d` file modified 3 days ago (no `verified`) ·
`STALE` older than `[check] stale_days`, or (in `page`) its `sources:` changed since it was verified ·
`SUPERSEDED→page` · `REJECTED`, `PARKED`, `DRAFT` · `⚠INSTRUCTION-LIKE TEXT`.

**The header** (`status`): a title line with index counts (or `index unavailable … may be stale` when the index
is locked or broken — the header reads the wiki files, not the index), a look-up line, then the configured
sections in order under one token cap: `rules` (rules.md `## Top`), `map` (index.md `## Map`), `gotchas`
(gotchas.md `## Top`), `plan` (one line, only while the owner has approved refresh work), `journal` (last
lines), plugin sections. Each section names its source file and age.
A section over budget ends with `… N more (header budget): memcrumbs page X`; none is dropped.

## Write (one deliberate command each; only inside the write set)

| Command | Effect |
|---|---|
| `log <text…> [--tag T]` | Appends `- YYYY-MM-DD HH:MM text #tag` to `wiki/journal/YYYY-MM.md` |
| `decision <title> --status accepted\|rejected\|parked\|superseded [--why W] [--tag T] [--considered "A; B"] [--evidence E] [--revisit-if R]` | New page `wiki/decisions/YYYY-MM-DD-slug.md` with Question / Options considered / What we tried / Evidence / Verdict / Why / Revisit if |
| `incident <title> [--symptom S] [--cause C] [--fix F] [--guard G] [--lucky L] [--tag T]` | New page `wiki/incidents/YYYY-MM-DD-slug.md` with Symptom / What happened / Root cause / Fix / Guard (+ Where we got lucky). `--symptom` is what someone sees first, in their words; it is stored as `symptom:` and searched with the title, so a repeat is found by what it looks like |
| `verify <page> [--date YYYY-MM-DD]` | Sets `verified:` (after you re-checked the facts); touches only that line |
| `suggest [--kind K]` · `suggest show\|apply\|undo\|dismiss ID` | Offers with evidence, each with an id, a one-line why, counts and dates, the action and a risk: `dupes` (supersede one of two near-duplicate pages), `link` (pages that cite the same files but do not link), `split` (a page too big for one lookup; the agent does it), `guard` (a gotcha or rule that forbids a command becomes a permission `ask` rule with every word of the command; `apply ID --deny` makes it a refusal, on the owner's choice, for a line that is neither conditional nor limited to certain files or hosts), `unguard` (its line is gone: take the rule out), `gap` (lookups the wiki could not answer become a draft page), `memory` (an auto-memory note the wiki already holds becomes a pointer: its MEMORY.md line and its body, keeping the lines the page lacks), `skill` (task flows and pipelines: the same 3–6 steps in the same order in 3 tasks on 2 days, or in 6 tasks, a task being the work between two of your messages and a pipeline one with no edits between its steps; repeated command sequences; repeated status queries; or a runbook agents keep re-reading. Each becomes a scaffolded `.claude/skills/NAME/SKILL.md`; `--name`, `--owner-only`, `--agent-may-use`; live or destructive ones default to owner-only. The transcript kinds need `[suggest] transcripts = true`), `rule` (a rule restated on two or more pages joins rules.md). `show` prints the dry-run patch as a diff; `apply ID` (or `apply --kind K` for all of a kind) writes it with backups, `--outside-wiki` when it writes outside the wiki, `--allow-destructive` when destructive; `undo ID` restores every byte if nothing changed since; `dismiss ID [--for 14d\|--never]` (it comes back after the period only if still true). The cheap kinds, the transcript kinds among them, are re-scanned at most once a day after `check`, `index`, `dashboard`, `doctor` and the write commands; the header then pings "N new suggestions", and the agent lists them only on the owner's word |
| `rule <text…>` | Adds a standing rule to `rules.md` `## Top`; it reaches the session header after the owner's review. If it lands past the header's line cap (`[status] rules`, 8), it says so: move it up for it to show. The skill tells the agent to offer it when the owner corrects how it works |
| `review [--approve all\|kept\|ID,…] [--kept]` | What waits for the owner: rule and gotcha lines added since the last review (they stay out of the session header until approved), and pages that an agent wrote (`written_by: agent`) no human has reviewed. `--approve` marks them reviewed. At a terminal the owner types a code. Inside Claude Code it runs only as `memcrumbs [-p NAME] review --approve IDS`, the form `wire`'s ask rule names, so Claude Code asks the owner first (the memcrumbs-review skill); any other agent shell is refused. The header lines present when review arrived were kept; `--kept` lists them once. The list also names quarantined pages |
| `quarantine <page>` · `quarantine --lift <page>` | Keeps a page on disk but out of the index and the header (`quarantined: true`); `--lift` puts it back: the owner's decision, like `review --approve`. Git is the rollback |
| `supersede <page> [--by <page>]` | Sets `status: superseded` (+ `superseded_by:`), and `supersedes:` on the new page, so the link runs both ways; the old page then ranks below current ones |
| `secret-add` | Reads a secret without echo; appends only its hash to `secrets.deny` |
| `bench --add "<question>" --expect <page or file> [--category C]` | Appends a question to `wiki/bench.toml` (redacted): run it when a lookup missed |
| `plan --approve <pages>\|top:N\|all [--budget N]` · `plan --budget N` · `plan --clear` | The owner approves pages and an est. token budget (state in the index folder); `verify <page>` marks an approved page done and charges its estimate |

## Setup

| Command | Effect |
|---|---|
| `init [name] [--repo PATH…] [--title T] [--yes] [--no-wire]` | The first wiring's yes also turns on skill offers from repeated work (`[suggest] transcripts`, unless the config already sets it; `init --remove` turns them off again). Sets up the repo you are in (its git root; outside git, the folder you are in; or `--repo`) in one run: creates `<projects_dir>/<name>/` (name: the repo folder's, made unique; title: the README's first heading) with `memcrumbs.toml`, `wiki/{index,gotchas,rules}.md` and `secrets.deny`; configures the code, the repo's own markdown (top-level `*.md`, `docs/`) and skips generated folders it finds (a virtual environment, `target/`, `vendor/` …); drafts the map from the repo (README, languages, folders, test command, CI); indexes; wires Claude Code with `--allow` after one yes (`--yes` gives it ahead; with no terminal it lists the changes and stops); runs `doctor`. At most 8 lines. Run again, it repairs and upgrades (index, wiring refreshed to this version) and says when nothing changed. Outside git, `init` sets up the folder you are in, but refuses a drive root, your home folder, a folder holding the projects folder, or one with more than 20,000 files (use `--repo PATH` for those); `init NAME` there creates a wiki without a repo |
| `init --remove [name] [--delete-wiki] [--yes]` | Takes the wiring out of every repo the project wired, byte for byte, and keeps the wiki. `--delete-wiki` also deletes the project folder: asked in a terminal, `--yes` otherwise |
| `index [--full]` | Refreshes the index (the wiki is also checked on every command; other sources at most every 60 s) |
| `wire [--repo P] [--target claude,agents] [--apply] [--remove] [--user-skill] [--allow]` | Dry run unless `--apply`. `--allow` adds allow rules for the read-only lookups (`find page outline sym status about fact`, with and without `-p NAME`, for the Bash and PowerShell tools) so they run without an approval prompt; write commands keep asking. `claude`: CLAUDE.md generated block, `.claude/settings.json` SessionStart hook and ask rules for the owner's decisions (`review --approve`, `quarantine --lift`, `suggest apply`/`undo`, `plan --approve`, `init --remove`, with and without `-p NAME`: Claude Code asks the owner before each, in every permission mode, and inside Claude Code memcrumbs runs them only in that form), the skills `.claude/skills/memcrumbs/SKILL.md` and `memcrumbs-review/SKILL.md` (`--user-skill`: `~/.claude/skills`). `agents`: AGENTS.md generated block. `--remove` takes out exactly what `wire` added — each file comes back byte for byte |
| `template` | Prints the page skeleton |
| `dashboard [--open]` | Writes `<project>/.memcrumbs/dashboard.html`: one static, self-contained page (no server, no network, no external scripts). An overview (trust score and trend, what needs you, freshness, header make-up, most-read pages, lookups per day), then tabs for the wiki itself (every page, redacted, rendered with clickable `[[links]]`), the refresh control (pick pages, set a budget, copy the approve command), pages, a knowledge map of `[[links]]`, decisions and incidents, agent usage and checks. The file holds the wiki's text, so share it as you would the wiki. Keeps one content-free line per day in `.memcrumbs/history.jsonl` for the trends |

## Exit codes

`0` success · `1` findings (`check` errors, `scan` hits, `bench` below `--min-recall3`) or an error with a
message on stderr · `2` usage error. `status --hook` always exits `0`.

## JSON

Every command accepts `--json` and prints one object with `"cmd"` and the command's data (`hits`, `symbols`,
`sections`, `findings`, `usage`, `total` …). A capped JSON output drops items from its main list and adds
`"truncated": true` and `"next"`. A command that refuses once it has started (a bad `--date`, for example) still prints its
object, with an `"error"` string, and exits non-zero. Strings in JSON pass the same redaction as text.

## Stability

From 1.0 the CLI (commands, flags, exit codes, JSON keys), the config schema ([config.md](config.md)) and the
plugin API ([plugins.md](plugins.md)) follow semver: nothing is removed or changes meaning within a major
version; a deprecated form keeps working, with a warning from `check`, for at least one minor release before
it is removed in the next major. Text output is for agents and humans and may be reworded; scripts should use
`--json`. The index format is a cache, not an interface: it is rebuilt when its schema version changes.
