# Writing good crumbs

A crumb is the one fact an agent needs to act correctly, with its source and its age. Write pages so that a
search for the question lands on the page, the hit's snippet already says the answer, and the page says when it
was last true.

## Pages

- **One topic per page**, under about 300 lines. Split by what people ask about, not by how the code is laid
  out: "deploy the booking app" and "roll back the booking app" are two runbooks.
- **Frontmatter is the index card**: `title` and `summary` carry the most search weight, so say what the page is
  *for* ("How to roll back a bad booking deploy in under a minute"), not just its subject.
- **`aliases:`** for the other words people use: a page about the kiln may need `aliases: [furnace, oven]`.
  Real synonyms only; stuffing keywords makes every search worse. Project-wide synonyms go in
  `[search] synonyms`.
- **`verified:`** is the day you checked the facts against the real system, not the day you edited the page.
  Re-check, then `memcrumbs verify <page>`.
- **`sources:`** lists the files (and ticket or incident ids) the facts come from. When a listed file changes
  after `verified`, `page` and `check` mark the page stale.
- A how-to that lives outside `runbooks/` gets `kind: runbook`, so "how do I …" questions find it first.
- Headings are retrieval units. A hit points at `page.md:LINE › Heading`, so make headings say what is under
  them ("Rollback", "Where the key lives"), and keep each section self-contained.
- Never write a secret value. Write *where* it lives ("the provider key is in the web-srv credential store
  under `payments/provider`").

## The always-loaded pages

They cost tokens in every session, so each line must earn its place.

- `rules.md` `## Top`: standing human rules and approvals, one line each ("Ask the owner before deploying to
  web-srv").
- `index.md` `## Map`: what is where, on one screen.
- `gotchas.md` `## Top`: the traps that are cheap to state and expensive to rediscover, most expensive first,
  one line each, linking the detail page (`[[2026-03-14-72h-task-limit]]`).

## Verdicts in research logs

Experiment logs are where negative knowledge lives, so make the verdict machine-readable:
- One page per experiment with `status: rejected` is best.
- In a long log, end each experiment's heading with the verdict ("## Read-through cache — REJECTED"), or add a
  `Verdict: rejected` line under it.
- In a verdict table, give the verdict its own column (headed Verdict, Status or Outcome) and start each cell
  with the verdict: "REJECTED: slower than baseline", "ADOPTED as default". Rows are indexed in small groups
  that share one verdict, so a row's hit carries its status and `find "<idea>" status:rejected` finds it.
- In a write-up, a `## Verdict` section that starts with the verdict word works too.
- When one page answers another page's question, say so in the words people use, right before the link:
  "Changing the gain without a restart: [[live-tuning]]". A lookup that lands there shows the linked page
  under the hit. Each link counts only the clause just before it, so a "see also" line can hold several links.

## Current values: write them once

A value that changes (a live version, a port, a host) belongs in one place, `wiki/facts.md`:

```
| key | value | about | source | verified |
|---|---|---|---|---|
| booking_version | 3.4.1 | booking app version | repo/booking/__init__.py | 2026-10-08 |
```

- Elsewhere, write `{{fact:booking_version}}`: `memcrumbs page` prints today's value. In a code span it stays as
  written, to show the syntax.
- Bind a key to its source in memcrumbs.toml (`[facts.bind.KEY] from = … pattern = …`), and the value is read
  from the file on every lookup.
- `memcrumbs fact booking_version` answers in one line. Facts are also `[fact]` hits in `find`.
- Write `about` the way people ask, not only the formal name: "live booking version; booking app version;
  version in production". A question about "the live version" finds the fact only if a phrase like that is
  there.
- `check` flags a page that states a registered subject with another current value, for example "the booking
  app version is 3.3.0". Dated lines, past-tense lines and History sections are history and are left alone,
  and so are journals, incidents, decisions and retired pages. The check covers values with digits (versions,
  ports, counts).

## Decisions and incidents

- Record rejected ideas with the numbers behind them: `memcrumbs decision "Move bookings to Postgres" --status
  rejected --why "…" --considered "Postgres; SQLite WAL" --evidence "p95 write 40 ms vs 12 ms (load test,
  2026-02-08)" --revisit-if "more than one writer"`. Agents search decisions before proposing something
  (`find "postgres" kind:decision`); a `REJECTED` hit saves a day, and the evidence keeps the verdict
  answerable. `check` asks for evidence on a rejected or parked decision.
- After something breaks: `memcrumbs incident "Double charge on retry" --symptom "a customer sees two charges"
  --cause "…" --fix "…" --guard "…"`. The symptom is what the next person sees first; it is searched with the
  title, so "I pressed X and nothing happened" finds the cause. Add a one-line gotcha if it can happen again.
- Runbooks have Preconditions, steps, a Verify step and a Rollback (or "Rollback: none (irreversible)"). Set
  `tested:` when you last ran the steps, and `destructive: true` when they cannot be undone: hits then say
  `DESTRUCTIVE`.
- When a page is replaced, do not delete it: `memcrumbs supersede old-page --by new-page`. It stays searchable,
  ranks below the current page, and every hit says `SUPERSEDED→new-page`; the new page gets `supersedes:`.
- Before editing an unfamiliar or risky file, `memcrumbs about <file>` lists what the wiki records about it:
  decisions with their verdicts, incidents, gotchas. Hits whose cited files changed after the page was verified
  say `SRC-CHANGED 3d`: check them before trusting the page.

## Review what agents wrote

Agents write most of a wiki, so the owner's review has to be cheap:
- `decision` and `incident` stamp `written_by: agent|human`. An agent-written page that no human has reviewed
  says `UNREVIEWED` on its hits.
- New lines in the rules' and gotchas' `## Top` reach the session header only after review, because the header
  speaks to every session. One header line says how many wait.
- `memcrumbs review` lists everything that waits as one digest. Approve it in your own terminal
  (`--approve all` or ids); inside an agent shell approval is refused. A human's `verify` also counts as a
  review.
- A page that looks planted: `memcrumbs quarantine <page>`. It stays on disk, out of the index and the header,
  until `--lift`.

## Suggestions

`memcrumbs suggest` offers upkeep it can detect without a model:
- near-duplicate pages;
- pages that cite the same files but never link;
- pages too big for one lookup;
- a gotcha that forbids a command, which becomes a permission deny rule;
- questions the wiki keeps failing to answer, which become a draft page;
- an auto-memory note the wiki already holds, which becomes a pointer, so each fact lives in one store;
- repeated work (a multi-step command sequence, a status query, a runbook read again and again), which becomes a
  private skill. memcrumbs writes only the skeleton; the agent writes the steps after the owner's yes;
- a rule restated on several pages, which joins `rules.md`.

Each offer shows its evidence and a patch. Nothing is applied without the owner's yes, and `suggest undo` puts
every byte back. Two sources are opt-in and stay on the machine: `[suggest] transcripts = true` (what agents ran
and read) and `[suggest] query_log = true` (lookups that found no wiki page).

## The journal

`memcrumbs log "deployed booking 3.4.1 to web-srv" --tag deploy` — dated one-liners of what happened. The last
few appear in the header. Write once per event, at the end of a task, not after every step.

## Keep it true

`memcrumbs check` after editing pages: secrets (`E`), missing frontmatter, broken `[[links]]`, oversized pages,
injection-like text (`W`), and pages that need re-verifying (`I`). Pasted vendor docs and tickets are the usual
source of injection attempts: quote them, don't paste them raw.
