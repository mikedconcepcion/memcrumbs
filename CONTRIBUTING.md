# Contributing to memcrumbs

Thanks for helping. Bug reports, ideas, docs and code are all welcome.

## Reporting a bug

[Open an issue](https://github.com/mikedconcepcion/memcrumbs/issues/new/choose) with the **Bug report**
template and include:

- what you ran and what you expected;
- what happened instead (the error text, or the output that looked wrong);
- the output of `memcrumbs doctor --share`. It holds versions, counts, timings and pass/fail per check, and
  never your paths, page names, page text or secrets.

Please describe your project in generic words ("a decision page whose verdict is in a table cell"). Never paste
real page text, hostnames, account names or anything from `secrets.deny`.

**Security problems** (a secret that got through redaction, a write outside the write set) go through a
private report, as described in [SECURITY.md](SECURITY.md), not a public issue.

## Suggesting a feature

Use the **Feature request** template. The most useful requests say what you were trying to do and where
memcrumbs got in the way, more than how to build it.

## Contributing code or docs

```bash
git clone https://github.com/mikedconcepcion/memcrumbs && cd memcrumbs
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
python -m unittest discover -s tests              # the whole suite, about a minute
memcrumbs scan .                                  # no secret-like values in the tree
```

Before you open a pull request:

- **Standard library only.** No new dependencies. memcrumbs makes no model calls, needs no network, runs no
  background service and installs no per-tool-call hooks; changes must keep it that way.
- **Tests:** add or update a test for what you changed, and make the whole suite pass. CI runs it on Linux,
  macOS and Windows with Python 3.11–3.13.
- **Invented examples only.** Test data, docs and examples use made-up projects (like `bench/kiln`), never real
  hosts, accounts, keys or another project's content.
- **Small modules:** aim for 200–400 lines per file; 800 is the hard limit (a test checks it).
- **Outputs stay capped**, and anything printed or written goes through the redaction filter.
- **Lookup quality:** if you change ranking or indexing, run the benchmark before and after and put both numbers
  in the pull request:

  ```bash
  MEMCRUMBS_PROJECTS=bench memcrumbs -p kiln index --full
  MEMCRUMBS_PROJECTS=bench memcrumbs -p kiln bench bench/questions.toml
  MEMCRUMBS_PROJECTS=bench memcrumbs -p kiln bench bench/holdout2.toml
  ```

  CI fails below recall@3 0.90. Please don't tune against `bench/holdout2.toml`: it is the held-out set.
- **Speed:** `python scripts/perf.py --files 10000` checks the speed targets on a generated 10k-file repo.
- **User-facing changes** get a line in [CHANGELOG.md](CHANGELOG.md) under "Unreleased".

### Adding support for a language or a data source

Most extensions don't need a change to the core: a plugin can add a source, a check, a header section, a
command or an outliner in a few dozen lines. See [docs/plugins.md](docs/plugins.md). A generally useful
outliner (Go, TypeScript, C#, …) is a welcome pull request.

## Code of conduct

Be kind and assume good intent. Critique code and ideas, not people. Maintainers may remove comments or block
accounts that harass others.
