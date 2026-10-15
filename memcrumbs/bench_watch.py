"""`check` runs the project's own bench (wiki/bench.toml) when there is one and explains every new miss.

A question the wiki answered at the last check (its expected page in the top 3) and misses now has one of two
causes with opposite fixes:
- a buried answer: the expected page is still right but ranks lower; sharpen its title or summary, or supersede it;
- a stale expectation: a newer page answers better; add it to the question's `expect`.

Each new miss is an info finding with the facts that tell them apart (the expected page's rank, the page now
first, and whether it was written since the last check) and the command for each fix. A write never fails on it.
The last ranks are kept in the project's data folder; only changes are reported."""
import json
import time
from pathlib import Path

from memcrumbs import bench, writeset
from memcrumbs.util import read_text

TOP = 3


def _last_path(project):
    return project.data / "bench-last.json"


def _name(project, rel):
    """A wiki page by its name (what `page` and `supersede` take), anything else by its path."""
    p = Path(rel)
    return p.stem if p.parts[:1] == ("wiki",) else rel


def _ranks(project, api):
    from memcrumbs import indexer
    from memcrumbs.cli import open_store
    store, _ = open_store(project)
    if store is None:
        return None
    try:
        indexer.refresh(project, api, store, wait=5)
        return [r for r in bench.run(project, store, bench.load(bench.default_path(project))) if not r.get("new")]
    finally:
        store.close()


def findings(project, api):
    if not bench.default_path(project).exists():
        return []
    try:
        rows = _ranks(project, api)
    except SystemExit as e:                      # a question file that does not parse
        return [("W", "wiki/bench.toml", str(e))]
    if rows is None:
        return []
    last = _last_path(project)
    try:
        prev = json.loads(read_text(last)) if last.exists() else {}
    except ValueError:
        prev = {}
    was, since = prev.get("ranks", {}), float(prev.get("at") or 0)
    writeset.write_text(project, last, json.dumps(dict(at=time.time(), ranks={r["id"]: r["rank"] or 0 for r in rows}),
                                                  indent=1) + "\n")
    out = []
    for r in rows:
        before = was.get(r["id"])
        if not before or before > TOP or (r["rank"] and r["rank"] <= TOP):
            continue
        out.append(("I", "wiki/bench.toml", explain(project, r, before, since)))
    return out


def explain(project, row, before, since):
    """One line: the facts that tell a buried answer from a stale expectation, and the command for each fix."""
    names = [_name(project, e) for e in row["expect"]]
    where = "rank %d" % row["rank"] if row["rank"] else "not in the top 8"
    if not row["top3"]:
        return "new miss %s %r: no hits now (it was rank %d); check that %s still exists" % (
            row["id"], row["q"], before, " or ".join(names))
    first = row["top3"][0]
    path = project.dir / first
    newer = since and path.exists() and path.stat().st_mtime > since
    new = _name(project, first)
    return ("new miss %s %r: %s is %s (it was rank %d); first now: %s%s. Buried answer: sharpen %s's title or "
            "summary, or memcrumbs supersede %s --by %s. Stale expectation: memcrumbs bench --expect-add %s %s"
            % (row["id"], row["q"], " or ".join(names), where, before, first,
               ", written since the last check" if newer else "", names[0], names[0], new, row["id"], new))
