# Day 0 on a public repo: httpx

What `memcrumbs init` alone gives on a real repository, before anyone writes a wiki page: the repo's own docs and
code symbols, searched with questions written blind.

- **Repository:** [encode/httpx](https://github.com/encode/httpx) at commit `b5addb64` (2026-02-23).
- **Questions:** three sets of 32, each written by a separate agent that read only the httpx repository and never
  saw how memcrumbs searches: 12 how-to, 10 code location, 5 behaviour and 5 history questions, each with the file
  (and sometimes the section) that answers it.
  - `questions-r1.toml`: the first look. Its misses were read, so it is indicative only.
  - `questions-dev.toml`: the set the search was tuned on.
  - `questions-holdout.toml`: not opened until the final run, and run once. This is the number to quote.
- **Results:** `*.json`, before (0.5.0) and after (0.5.1) each change.

| Holdout, 32 questions | 0.5.0 | 0.5.1 |
|---|---|---|
| answer in the top 3 (recall@3) | 0.625 | 0.750 |
| answer first (recall@1) | 0.312 | 0.438 |
| code questions, recall@3 | 0.60 | 0.90 |
| tokens per `find` answer (characters ÷ 4) | 586 | 377 |

## Run it yourself

```bash
git clone https://github.com/encode/httpx && git -C httpx checkout b5addb64
pip install memcrumbs
python scripts/day0.py httpx bench/httpx/questions-holdout.toml
```

`day0.py` runs `init --no-wire` with a temporary projects folder (the repo is not touched), then `memcrumbs bench`
with the questions, and reads each answering file whole for the comparison.
