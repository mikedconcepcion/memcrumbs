# Plugins and packs (API v1)

Core, packs and project plugins:

| Layer | Where | Use it when |
|---|---|---|
| Core | `memcrumbs/` | every project needs it; standard library only |
| Pack | `memcrumbs.packs.NAME`, or a separate distribution exposing the entry-point group `memcrumbs.packs` | several kinds of project need it |
| Project plugin | `<project>/plugins/*.py` | one project needs it |

List them in `memcrumbs.toml`: `plugins = ["mypack", "plugins/myapp.py", "mypkg.memcrumbs_pack"]`. A bare
name is looked up as `memcrumbs.packs.NAME`, then as an entry point named NAME. A plugin that fails to load
never stops a command: `status` shows one line about it, `check` reports it, and `doctor` fails with the fix.
Its documents stay in the index, no longer refreshed, until it loads again; once it is out of `plugins`, they
leave the index. `index` names the count either way.

## The API

A plugin module defines `register(api)`. `api.version == 1`. `api.project` is the project (`name`, `dir`,
`wiki`, `repos`, `cfg` — the parsed TOML, so a plugin reads its own `[section]`, `path(p)`, `rel(p)`,
`redact`, `blocked(path)`).

| Call | Contract |
|---|---|
| `api.add_source(name, fn)` | `fn(project)` yields `(path, stamp, loader)`. `stamp` is any change marker (compared as a string; use `memcrumbs.util.stamp(os.stat(path))`). `loader()` returns `(docs, symbols)` and runs only when the stamp changed. `docs` are `memcrumbs.sources.Doc(kind, path, loc, title, section, body, tags="", verified="", status="", flags="")`. **Pass every text through `project.redact`**; if it raises, let it — the file is then not indexed. Non-wiki sources refresh at most every 60 s (or on `index`) |
| `api.add_check(fn)` | `fn(project)` returns `[(level, where, message)]`, level `E` / `W` / `I`. Exceptions become a `W` finding |
| `api.add_section(name, fn, title=None)` | A header section: `fn(project)` returns lines. Shown where `[status] sections` names it, or in the `"plugins"` slot. Counted in the header budget like any section |
| `api.add_status(fn)` | v0.1 form of `add_section` (untitled lines in the `"plugins"` slot) |
| `api.add_command(name, setup, run, help="")` | A subcommand: `setup(argparse_subparser)`, `run(project, args)`. It gets `--json`, `--full` and `-p` like the built-ins |
| `api.add_suggester(kind, fn)` | A `memcrumbs suggest` kind. `fn(project, cheap_only=False)` returns `memcrumbs.suggest.Suggestion(kind, key, why, action, evidence=[], risk="safe", changes=[(path, new_text)], agent="", score=0, cheap=True)`. `key` names the subject (the id derives from it); `evidence` is counts and dates, never raw text; `changes` is the patch (`None` deletes a file), applied with backups so `suggest undo` restores every byte; `risk` is `safe`, `writes-outside-wiki` (needs `--outside-wiki`) or `destructive` (needs `--allow-destructive`). `cheap=False` keeps it out of the daily scan |
| `api.add_outliner(exts, fn)` | `fn(text)` returns symbols: dicts with `name, qual, kind, line, end, sig, doc, depth` (1-based lines). Files with these extensions join the code index |
| `api.write_generated(page, name, body)` | The safe writer: replaces generated block NAME in wiki page `page` (wiki-relative; created if missing), redacted; nothing outside the markers changes and nothing outside the wiki can be written |
| `api.redact(text)` | The project's redactor |
| `api.errors` | `[(spec, error)]` for plugins that failed to load |

Rules for plugins: no network or model calls in the core path; write only through `write_generated` (or
`memcrumbs.writeset`, which enforces the write set); keep outputs small.

## Reference plugins

The public bench project carries two (both tested in `tests/test_bench.py`):

- [`bench/kiln/plugins/kiln_outline.py`](../bench/kiln/plugins/kiln_outline.py) — an outliner for a niche brace
  language with no language server, in about 60 lines (uses `memcrumbs.outline.braces.block_end`).
- [`bench/kiln/plugins/tasks.py`](../bench/kiln/plugins/tasks.py) — live state: a source that indexes an
  exported scheduled-task inventory, a check that turns the "72-hour execution limit kills daemons" gotcha into
  a finding, a header section, and a command that writes a generated table into a wiki page; about 115 lines.

## Shipping a pack

```toml
# pyproject.toml of your pack
[project.entry-points."memcrumbs.packs"]
myhosts = "memcrumbs_myhosts"            # a module with register(api)
```

Then `plugins = ["myhosts"]`. A pack may have dependencies of its own; the core never will. Promote a project
plugin to a pack once it can be described without private nouns.

## Stability

`register(api)` and every call above are frozen from 1.0 under semver: arguments are only ever added with
defaults, and a deprecated call keeps working for at least one minor release. `Doc` gains fields only with
defaults.
