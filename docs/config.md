# Configuration (schema v1)

## Where projects live

Project folders hold private wikis, so they live outside any package or public repo:
`$MEMCRUMBS_PROJECTS`, else `projects_dir` in `~/.memcrumbs/config.toml`, else `~/.memcrumbs/projects`.
Each project is `<projects_dir>/<name>/memcrumbs.toml` plus its `wiki/`, an index folder `.memcrumbs/`
(a disposable cache) and `secrets.deny` (keep both out of git).

## memcrumbs.toml

Relative paths resolve against the project folder.

```toml
name = "myapp"                          # default: the folder name
title = "My App"
wiki = "wiki"
repos = ["/code/myapp"]                 # code roots: the code index and cwd -> project resolution
plugins = ["mypack", "plugins/myapp.py", "some.module"]   # pack name, project file, or module

[code]                                  # code index (the `code` source)
roots = []                              # default: repos
include = []                            # default: every extension with an outliner
exclude = ["**/cache/**", "**/node_modules/**"]

[[docs]]                                # extra markdown trees, indexed as-is (repeatable)
name = "repo-docs"
root = "/code/myapp"
include = ["**/*.md"]
exclude = []
kind = "doc"                            # doc | research | memory | legacy (legacy ranks lowest)

[security]
never_index = ["*.ini"]                 # added to the built-in list; no "/" = file name, with "/" = path
secret_keys = ["cfg*key"]               # extra key names (globs, lower case, separators removed) whose values are secrets

[search]
synonyms = [["kiln", "furnace"], ["booking", "reservation"]]   # added to the built-in thesaurus
thesaurus_remove = ["kill"]             # take words out of the built-in groups (your domain keeps them apart)
thesaurus = true                        # false: only your own synonyms

[facts]                                 # the facts registry: one current value per key
page = "facts"                          # wiki/facts.md: a table | key | value | about | source | verified |

[facts.bind.live_version]               # optional: read this key's value from a file on every lookup
from = "repo/VERSION"                   # relative to the project folder, the wiki or a repo
pattern = '^(\S+)'                     # the first group (or the whole match) is the value

[suggest]                               # opt-in, local only
transcripts = false                     # read ~/.claude/projects/<repo>/*.jsonl: command shapes, files read and edited,
                                        # lookups, where your messages fall; skill offers from task flows and pipelines
                                        # (`init` turns it on with the wiring, after your yes)
query_log = false                       # log the text of lookups the wiki could not answer (.memcrumbs/gaps.jsonl)
gap_cover = 0.4                         # a wiki hit answers a lookup when it holds this share of the query's information

[update]                                # opt-in
notify = false                          # check PyPI once a day (after slow commands); the header says when a newer
                                        # release is out. `memcrumbs update` works either way

[review]                                # agent-written knowledge
gate_header = true                      # rule/gotcha lines reach the header after the owner's review

[check]
max_lines = 300                         # W when a page is longer
stale_days = 45                         # I (and STALE on hits) when `verified` is older

[status]                                # the session header
sections = ["rules", "map", "gotchas", "plan", "journal", "plugins"]   # order; plugin sections by name, or "plugins" for the rest
max_tokens = 1000                       # whole header, estimated as chars/4; hard ceiling 1500
rules = 8                               # bullets of rules.md "## Top"
map_lines = 30                          # lines of index.md "## Map"
gotchas = 12                            # bullets of gotchas.md "## Top"
journal = 3                             # last journal lines
# "style" in sections adds 4 working rules (answer first, no re-reads, outline big files, no guessing), ≈ 60 tokens;
# off by default (style_rules = [...] replaces them)
```

Built-in `never_index`: `.env`, `.env.*`, `*.env`, `.envrc`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`,
`*.keystore`, `*.kdbx`, `*.ppk`, `*.ovpn`, `*.tfstate`, `*.tfstate.*`, `*.tfvars`, `id_rsa*`, `id_dsa*`,
`id_ecdsa*`, `id_ed25519*`, `.netrc`, `_netrc`, `.pgpass`, `.npmrc`, `.pypirc`, `.git-credentials`,
`.htpasswd`, `credentials`, `credentials.*`, `*credentials*.json`, `client_secret*.json`, `secrets.*`,
`*.secrets`, `*.secret`, `secrets.deny`, `**/.ssh/**`, `**/.aws/**`, `**/.gnupg/**`, `**/.docker/config.json`,
`**/.kube/config`. Dot-folders are never walked.

## Page frontmatter

A YAML subset: `key: value`, `key: [a, b]`, and `key:` followed by indented `- item` lines.

| Key | Meaning |
|---|---|
| `title`, `summary` | Shown in hits and `page`; weighted high in search |
| `verified` | `YYYY-MM-DD` the facts were last checked against the real system |
| `tags`, `aliases` | Searchable words (aliases: other names people use for this topic) |
| `sources` | Files (or ids, URLs) the facts come from; files changed after `verified` make the page stale |
| `status` | `current`, `draft`, `accepted`, `rejected`, `parked`, `superseded` |
| `superseded_by` | The page that replaced this one |
| `symptom` | Incidents: what someone sees first, in their words. Searched with the title and shown on the page's hit |
| `evidence` | Decisions: the numbers behind a verdict (or an Evidence section) |
| `tested` | Runbooks: the day the steps were last run (YYYY-MM-DD), apart from `verified` (the day they were read against the system) |
| `destructive` | `true` on a procedure that cannot be undone: hits and `page` say `DESTRUCTIVE` |
| `supersedes` | The page (or pages) this one replaces; `supersede --by` writes it |
| `written_by` | `agent` or `human`, stamped by `decision` and `incident`. An agent-written page without `reviewed:` says `UNREVIEWED` on hits |
| `reviewed` | The day a human reviewed it (`review --approve`, or `verify` run outside an agent shell) |
| `quarantined` | `true`: the page stays on disk but out of the index and the header (`memcrumbs quarantine`) |
| `caused_by` · `affects` | Optional typed relations, shown in `page`; ranking does not use them |
| `kind` | Overrides the folder-based kind: `wiki`, `runbook`, `decision`, `incident`, `journal`, `doc`, `research`, `memory`, `legacy` (a how-to that lives in `research/` sets `kind: runbook`) |

Without a `status:` line, a status is also read from how research write-ups state it. This works in wiki pages
and in `[[docs]]` trees:
- a title or heading ending in "— REJECTED" or "(parked)";
- a `Verdict: accepted` line;
- a `## Verdict` (or Outcome, Decision, Result) section whose first line starts with a verdict word.

Tables:
- A table longer than 8 rows, or any table that states verdicts, is indexed in groups of up to 5 rows that
  repeat the header and never mix verdicts.
- A cell that is exactly a verdict word counts, in any column.
- In a column headed Verdict, Status, Outcome, Decision or Result, a cell that *starts* with a verdict word also
  counts when the word is followed by `:`, `(`, a dash, `as`, a date or the end of the cell: "REJECTED: slower",
  "ADOPTED as default", "PARKED 10-02: …".
- In those columns an ALL-CAPS verdict word counts whatever follows it: "ADOPTED v1.3.18 (…)", "ADOPTED
  fleet-wide".
- A cell that says the decision was reversed, reverted or rolled back gets no label.
- "NOT ADOPTED" counts as rejected.
- Verdicts are labels and `status:` filters only; they never change rank.

## Generated blocks

Text between a line `<!-- memcrumbs:gen NAME -->` and a line `<!-- memcrumbs:end -->` is machine-written.
Generators replace only that span; every byte outside it stays as it was. A block without its end marker, or
with another block starting inside it, is refused rather than guessed at.
