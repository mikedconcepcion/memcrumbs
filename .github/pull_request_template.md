## What this changes

<!-- One or two sentences: what users get, or what it fixes. Link the issue if there is one. -->

## Checklist

- [ ] `python -m unittest discover -s tests` passes
- [ ] `memcrumbs scan .` finds nothing
- [ ] Tests added or updated for the change
- [ ] Standard library only; no model calls, network or background service
- [ ] Examples and test data are invented, with no real hosts, accounts or project content
- [ ] For ranking or indexing changes: bench numbers before and after (`bench/questions.toml`, `bench/holdout2.toml`)
- [ ] A line in `CHANGELOG.md` under "Unreleased" for user-facing changes
