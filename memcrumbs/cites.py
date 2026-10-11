"""Reverse lookup: what the wiki records about a file. At index time every markdown doc's `sources:` and
the file-like tokens in its text become citation rows; `about <path>` lists the pages, decision rows, incidents
and gotchas that cite a file, verdicts first, and code hits and `outline` say "cited by: …" in one line."""
import re
from pathlib import Path

EXT = ("py|pyw|ps1|psm1|psd1|js|mjs|cjs|ts|tsx|jsx|go|rs|cs|java|kt|rb|php|c|h|cpp|hpp|sql|sh|bash|bat|cmd|toml|json|"
       "jsonc|yaml|yml|ini|cfg|conf|env|xml|csv|md|txt|mq5|mqh|mq4|service|timer|tf|kiln")
PATH = re.compile(r"(?<![\w/\\.:@~-])((?:[A-Za-z]:[/\\]|~?/)?(?:\.{1,2}[/\\])*+(?:[\w.~-]+[/\\])*+[\w-][\w.-]*\.(?:%s))"
                  r"(?![\w/\\-])" % EXT, re.I)
CITING = ("decision", "incident", "runbook", "wiki", "journal", "doc", "research", "memory", "legacy", "bug")
ORDER = {"decision": 0, "incident": 1, "runbook": 3, "wiki": 4, "journal": 6}
HEADER_PAGES = {"gotchas": "gotcha", "rules": "rule"}
NAMES = {"wiki": "page", "memory": "memory note", "legacy": "legacy note", "research": "research note",
         "journal": "journal entry", "bug": "bug log entry", "doc": "doc"}       # every group named


def norm(token):
    """A cited path as stored: forward slashes, lower case, no leading ./ or ../ parts."""
    t = token.replace("\\", "/").lower()
    while t.startswith(("./", "../")):
        t = t.split("/", 1)[1]
    return t


def tokens(text):
    return {norm(m) for m in PATH.findall(text or "")}


def rows(path, docs):
    """Citation rows (target basename, token, page path, loc, kind, status, title, section) for one file's docs."""
    out, seen = [], set()
    for d in docs:
        if d.kind not in CITING:
            continue
        for t in tokens(d.body) | tokens(getattr(d, "cites", "")) | tokens(d.section):
            key = (t, d.loc)
            if key not in seen:
                seen.add(key)
                out.append((t.rsplit("/", 1)[-1], t, path, d.loc, d.kind, (d.status or "").lower(), d.title, d.section))
    return out


def _matches(store, project, path):
    """Rows citing `path`: a token with folders must be a suffix of the path; a bare name matches by name."""
    p = Path(path)
    rows = store.db.execute("SELECT token, path, loc, kind, status, title, section FROM cites WHERE target = ?",
                            (p.name.lower(),)).fetchall()
    if not rows:                                   # the usual case on a code hit: no filesystem calls at all
        return []
    if len(p.parts) == 1 and not p.exists():       # a bare file name: every citation of that name
        return [dict(token=r[0], path=r[1], loc=r[2], kind=r[3], status=r[4], title=r[5], section=r[6], exact=True)
                for r in rows]
    forms = {p}
    if p.exists() or p.is_absolute():               # as given and resolved: on macOS /var/… is /private/var/…
        forms = {p.absolute(), p.resolve()}
    rels = {f.as_posix().lower() for f in forms}
    for root in list(getattr(project, "repos", [])) + [getattr(project, "dir", None)]:
        if root is not None:
            for f in forms:
                for r in {Path(root), Path(root).resolve()}:
                    try:
                        rels.add(f.relative_to(r).as_posix().lower())
                    except ValueError:
                        pass
    found = []
    for r in rows:
        token = r[0]
        exact = "/" in token and any(x == token or x.endswith("/" + token) for x in rels)
        if "/" in token and not exact:
            continue
        found.append(dict(token=token, path=r[1], loc=r[2], kind=r[3], status=r[4], title=r[5], section=r[6],
                          exact=exact))
    return found


def _kind(h):
    stem = Path(h["path"]).stem.lower()
    return HEADER_PAGES.get(stem, h["kind"])


def _bound_facts(project, path):
    """Facts whose value is read from this file ([facts.bind.KEY] from = …): the file is their source."""
    binds = (getattr(project, "cfg", {}).get("facts", {}) or {}).get("bind") or {}
    if not binds:
        return []
    from memcrumbs import facts, freshness
    try:
        me = Path(path).resolve()
    except OSError:
        return []
    out = []
    for key, spec in binds.items():
        if any(p.resolve() == me for p in freshness.source_paths(project, [spec.get("from", "")])):
            out.append(dict(token=Path(path).name.lower(), path=str(facts.page_path(project)), loc=1, kind="fact",
                            status="", title="fact %s (bound to this file)" % key, section="", exact=True, what="fact"))
    return out


def about(store, project, path):
    """One entry per citing page (its best location), verdicts and incidents first."""
    best = {}
    for h in _matches(store, project, path):
        cur = best.get(h["path"])
        if cur is None or (bool(h["status"]), h["exact"], -h["loc"]) > (bool(cur["status"]), cur["exact"], -cur["loc"]):
            best[h["path"]] = h
    hits = list(best.values()) + _bound_facts(project, path)
    for h in hits:
        h["what"] = h.get("what") or _kind(h)
    hits.sort(key=lambda h: (0 if h["status"] in ("rejected", "accepted", "parked", "superseded") else 1,
                             {"gotcha": 2, "rule": 2}.get(h["what"], ORDER.get(h["kind"], 5)), not h["exact"], h["path"]))
    return hits


def summary(store, project, path):
    """'1 decision (REJECTED), 1 incident, 1 gotcha' or '' — one line for code hits and outline. Only what changes
    how a file is handled; plain pages that mention it are left to `about`."""
    return describe([h for h in about(store, project, path) if h["what"] in ("decision", "incident", "gotcha", "rule")])


def describe(hits):
    if not hits:
        return ""
    counts = {}
    for h in hits:
        counts.setdefault(h["what"], []).append(h["status"])
    parts, named = [], {}
    for what in sorted(counts, key=lambda w: {"decision": 0, "incident": 1, "gotcha": 2, "rule": 3, "fact": 4}.get(w, 5)):
        name = NAMES.get(what, what.replace("_", " "))
        named.setdefault(name, []).extend(counts[what])
    for name, statuses in named.items():
        st = sorted({s.upper() for s in statuses if s})
        n = len(statuses)
        plural = (name[:-1] + "ies" if name.endswith("y") else name + "s") if n > 1 else name
        parts.append("%d %s%s" % (n, plural, " (%s)" % "/".join(st) if st else ""))
    return ", ".join(parts)
