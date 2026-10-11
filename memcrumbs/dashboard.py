"""`memcrumbs dashboard`: one static, self-contained HTML file for the human (a static export, no
always-on service). An overview first (trust score, what needs the human, trends), then the refresh control
(pick pages, set a token budget, copy the approve command), the wiki itself (every page's text, redacted, to
read in place), pages, a knowledge map of `[[links]]`, decisions and incidents, agent usage and checks. The page reads nothing and writes nothing; the approval stays a
deliberate CLI command. Every string in it passed the redactor. Each run also keeps one content-free line per
day (counts and percentages) in <project>/.memcrumbs/history.jsonl, for the trend lines."""
import html
import json
import os
import re
import time
import webbrowser
from pathlib import Path

from memcrumbs import __version__, freshness, header, markdown, plan, synonyms, usage, writeset
from memcrumbs.cmd_write import journal_tail
from memcrumbs.redact import safe
from memcrumbs.sources import wiki_kind
from memcrumbs.store import IndexBroken, Locked, Store
from memcrumbs.util import read_text

TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"
SCRIPTS = [Path(__file__).parent / "templates" / n for n in ("markdown.js", "dashboard.js")]
LINK = re.compile(r"\[\[([^\]|#\n]+)")
HISTORY_DAYS = 180
PAGE_CHARS = 200_000                    # a page past this is left out of the reader (read it with `memcrumbs page`)
WIKI_CHARS = 8_000_000                  # the whole wiki's text in one file stays well under a browser's comfort


def _group(project, path):
    """The wiki folder a page sits in ("" at the top), for the knowledge map's clusters."""
    try:
        parts = Path(path).resolve().relative_to(project.wiki.resolve()).parts
    except ValueError:
        return ""
    return parts[0] if len(parts) > 1 else ""


def _sources(meta):
    v = meta.get("sources") or []
    return [str(x) for x in (v if isinstance(v, list) else [v])][:20]


def _pages(project, counts):
    """(page rows, page texts in the same order). A text is None past PAGE_CHARS or once WIKI_CHARS is used."""
    from memcrumbs import facts
    rows, texts, used, known = [], [], 0, facts.load(project)
    for p in project.wiki_pages():
        meta, body, _ = markdown.frontmatter(read_text(p))
        rel = project.rel(p)
        keep = len(body) <= PAGE_CHARS and used + len(body) <= WIKI_CHARS
        used += len(body) if keep else 0
        texts.append(facts.substitute(project, body, known) if keep else None)
        rows.append(dict(path=rel, page=p.stem, title=str(meta.get("title") or p.stem), kind=wiki_kind(project, p),
                         verified=str(meta.get("verified") or ""), age=freshness.days_since(meta.get("verified")),
                         status=str(meta.get("status") or "").lower(), lines=body.count("\n"), hits=counts.get(rel, 0),
                         summary=str(meta.get("summary") or "")[:200], group=_group(project, p), sources=_sources(meta),
                         links=sorted({m.strip() for m in LINK.findall(body)})))
    names = {r["page"].lower(): r["page"] for r in rows}
    for r in rows:                                   # only links to pages that exist; check reports broken ones
        r["links"] = sorted({names[n.lower()] for n in r["links"] if n.lower() in names} - {r["page"]})
    return rows, texts


def _header_size(project, api):
    """The session header's size, and what each section asks for (est. tokens) before the cap cuts it."""
    cfg = project.cfg.get("status", {})
    secs = header.sections(project, api, cfg)
    text, cut = header.render([], secs, header.budget_tokens(cfg) * 4)
    parts = [dict(name=s["name"], title=s["title"] or s["name"], lines=len(s["lines"]) + s["more"],
                  tokens=(len(s["title"]) + sum(len(x) + 1 for x in s["lines"]) + 3) // 4) for s in secs]
    return dict(tokens=(len(text) + 3) // 4, budget=header.budget_tokens(cfg), cut=cut, sections=parts)


def _bench(project, store):
    from memcrumbs import bench
    path = bench.default_path(project)
    if not path.exists() or store is None:
        return None
    rows = bench.run(project, store, bench.load(path))
    return dict(total=bench._agg(rows), misses=[dict(id=r["id"], q=r["q"], rank=r["rank"]) for r in rows
                                                if not r["rank"] or r["rank"] > 3][:20])


def _review(project):
    from memcrumbs import review
    try:
        items, kept = review.digest(project)
    except Exception:
        return dict(lines=0, pages=0, kept=0)
    return dict(lines=sum(1 for i in items if i["what"] == "line"), pages=sum(1 for i in items if i["what"] == "page"),
                kept=len(kept))


def _suggest(project):
    """Open suggestions from the last scan, by kind (the dashboard runs no scan of its own)."""
    from memcrumbs import suggest
    try:
        st = suggest.load_state(project)
    except Exception:
        return {}
    import datetime
    today = datetime.date.today().isoformat()
    kinds = {}
    for sid, v in st["open"].items():
        if suggest._active(st, sid, today):
            kinds[v.get("kind", "?")] = kinds.get(v.get("kind", "?"), 0) + 1
    return kinds


def collect(project, api):
    from memcrumbs.lint import lint
    findings = lint(project)
    counts = plan.hits(project)
    try:
        store = Store(project.index_path, synonyms.for_project(project))
    except (IndexBroken, Locked):
        store = None
    try:
        kinds, nsym, nfiles = store.counts() if store else ({}, 0, 0)
        age = store.age() if store else None
        bench = _bench(project, store)
    finally:
        if store:
            store.close()
    pages, texts = _pages(project, counts)
    journal, _ = journal_tail(project, 12)
    items = plan.candidates(project, findings)
    attention = {c["path"] for c in items}
    data = dict(
        project=dict(name=project.name, title=project.title, version=__version__,
                     generated=time.strftime("%Y-%m-%d %H:%M"), stale_days=int(project.check_cfg.get("stale_days", 45))),
        index=dict(files=nfiles, docs=sum(kinds.values()), symbols=nsym, kinds=kinds,
                   refreshed_min_ago=round(age / 60) if age is not None else None),
        pages=pages, header=_header_size(project, api),
        check=dict(errors=sum(1 for f in findings if f[0] == "E"), warnings=sum(1 for f in findings if f[0] == "W"),
                   info=sum(1 for f in findings if f[0] == "I"),
                   findings=[dict(level=a, where=b, message=c) for a, b, c in sorted(findings)[:80]]),
        plan=dict(items=items, state=plan.load_state(project)), review=_review(project), suggest=_suggest(project),
        trust=round(100 * sum(1 for p in pages if p["path"] not in attention) / len(pages)) if pages else None,
        wiki=texts, usage=usage.summary(project), daily=usage.daily(project), bench=bench, journal=journal,
        decisions=[p for p in pages if p["kind"] == "decision"], incidents=[p for p in pages if p["kind"] == "incident"])
    return _clean(project.redact, data)


def _clean(redact, v):
    if isinstance(v, str):
        return safe(redact, v)
    if isinstance(v, dict):
        return {k: _clean(redact, x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(redact, x) for x in v]
    return v


def snapshot(data):
    """Today's line for history.jsonl: counts and percentages only, never names or text."""
    find = data["usage"].get("find", {})
    return dict(day=time.strftime("%Y-%m-%d"), pages=len(data["pages"]), trust=data["trust"],
                attention=len(data["plan"]["items"]), errors=data["check"]["errors"],
                warnings=data["check"]["warnings"], header=data["header"]["tokens"],
                recall3=data["bench"]["total"]["recall_at_3"] if data["bench"] else None,
                lookups=sum(d["lookups"] for d in data["daily"]), zero=find.get("zero_results_pct"))


def history(project, snap):
    """Keep one snapshot per day (the latest), the last HISTORY_DAYS days; returns them oldest first."""
    p = project.data / "history.jsonl"
    rows = []
    for ln in read_text(p).splitlines() if p.exists() else []:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("day") and r["day"] != snap["day"]:
            rows.append(r)
    rows = sorted(rows + [snap], key=lambda r: r["day"])[-HISTORY_DAYS:]
    writeset.write_text(project, p, "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    return rows


def render(data):
    # no "<" at all inside the data block: wiki text can then neither close it nor switch the HTML parser's
    # script state (`<!--` + `<script`); < is plain JSON and JSON.parse restores it
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    script = "\n".join(f.read_text(encoding="utf-8") for f in SCRIPTS)
    page = TEMPLATE.read_text(encoding="utf-8").replace("{{SCRIPT}}", script)
    return page.replace("{{TITLE}}", html.escape(data["project"]["title"])).replace("{{DATA}}", blob)


def write(out, project, api, open_it=False):
    data = collect(project, api)
    data["history"] = history(project, snapshot(data))
    path = writeset.write_text(project, project.data / "dashboard.html", render(data))
    st = data["plan"]["state"]
    out.set(path=str(path), pages=len(data["pages"]), candidates=len(data["plan"]["items"]),
            approved=len(st.get("approved", [])), header_tokens=data["header"]["tokens"])
    out("wrote %s — %d pages, %d need attention (≈ %d tokens est. to refresh all), header ≈ %d of %d tokens" % (
        path, len(data["pages"]), len(data["plan"]["items"]), sum(c["tokens"] for c in data["plan"]["items"]),
        data["header"]["tokens"], data["header"]["budget"]))
    if open_it and not os.environ.get("MEMCRUMBS_NO_BROWSER"):
        webbrowser.open(path.as_uri())
    return path

