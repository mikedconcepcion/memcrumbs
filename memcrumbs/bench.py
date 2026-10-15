"""`memcrumbs bench QUESTIONS.toml`: recall@1 / recall@3 / MRR, tokens per answer and latency, against any
project (public or private) with no code changes.

    [[q]]
    id = "rb-01"
    q = "how do I roll back a bad deploy?"
    expect = ["wiki/runbooks/rollback.md"]      # path suffixes; any one in the top k counts
    category = "runbook"                        # optional; results are also broken down by category

A hit matches an expected path when its file path ends with it (`wiki/x.md`, `repo/app.py`); `path#Section`
also requires the hit's section to contain that text. Tokens are the `find` output's chars/4 (estimate).

Error text that nothing records is asked with `new = true` and no `expect`: the right answer says so ("not
recorded", or no hits). Those questions are reported apart and stay out of recall."""
import io
import json
import re
import time
import tomllib
from contextlib import redirect_stdout
from pathlib import Path

from memcrumbs import cmd_read, writeset
from memcrumbs.output import Out, est_tokens
from memcrumbs.util import posix, read_doc


def load(path):
    with open(path, "rb") as f:
        qs = tomllib.load(f).get("q", [])
    for i, q in enumerate(qs):
        if not q.get("q") or not (q.get("expect") or q.get("new")):
            raise SystemExit("bench: question %d needs q and expect (or new = true)" % (i + 1))
        q.setdefault("expect", [])
        q.setdefault("id", "q%d" % (i + 1))
    return qs


def _match(hit, expect):
    path = "/" + posix(hit["path"]).lstrip("/")
    for e in expect:
        target, _, section = e.partition("#")
        if path.lower().endswith("/" + target.strip("/").lower()) and \
                (not section or section.lower() in (hit.get("section") or "").lower()):
            return True
    return False


def run(project, store, questions, k=8):
    rows = []
    for q in questions:
        t0 = time.perf_counter()
        hits = cmd_read.lookup(store, q["q"], q.get("kinds"), k)[0]
        ms = (time.perf_counter() - t0) * 1000
        buf = io.StringIO()
        with redirect_stdout(buf):                                 # the exact text an agent would read
            out = Out("find", None, project.redact)
            cmd_read.find(out, project, store, q["q"], q.get("kinds"), k, track=False)
            out.close()
        rank = next((i + 1 for i, h in enumerate(hits) if _match(h, q["expect"])), None)
        followed = next((i + 1 for i, h in enumerate(hits) if _match(h, q["expect"]) or
                         (h.get("see") and _match(h["see"], q["expect"]))), None)
        rows.append(dict(id=q["id"], q=q["q"], expect=q["expect"], category=q.get("category", ""),
                         paraphrase=bool(q.get("paraphrase")), rank=rank, followed=followed, ms=round(ms, 1), tokens=est_tokens(len(buf.getvalue())),
                         top3=[project.rel(h["path"]) for h in hits[:3]]))
        if q.get("new"):
            text = buf.getvalue()
            rows[-1].update(new=True, labelled=cmd_read.NOT_RECORDED in text or "no hits for" in text)
    return rows


def _agg(rows):
    n = len(rows) or 1
    ms, toks = sorted(r["ms"] for r in rows), sorted(r["tokens"] for r in rows)
    pct = (lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))] if xs else 0)
    return dict(n=len(rows), recall_at_1=round(sum(1 for r in rows if r["rank"] == 1) / n, 3),
                recall_at_3=round(sum(1 for r in rows if r["rank"] and r["rank"] <= 3) / n, 3),
                recall_at_3_with_pointers=round(sum(1 for r in rows if r.get("followed") and r["followed"] <= 3) / n, 3),
                mrr=round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3),
                tokens_mean=round(sum(toks) / n), tokens_p95=pct(toks, 0.95),
                ms_mean=round(sum(ms) / n, 1), ms_p95=pct(ms, 0.95))


def default_path(project):
    """The project's own bench, grown from real use with `memcrumbs bench --add` (kept with the wiki)."""
    return project.wiki / "bench.toml"


def _target(project, e):
    """A page name or a file, as the path an `expect` holds."""
    from memcrumbs.curate import exact_page
    try:
        return project.rel(exact_page(project, e))
    except SystemExit:
        p = Path(e).expanduser().resolve()
        if not p.exists():
            raise SystemExit("memcrumbs: no page or file %r" % e)
        try:
            return posix(p.relative_to(project.dir))
        except ValueError:
            return posix(p)


def expect_add(out, project, qid, page):
    """Add a page to one question's `expect` (a newer page that answers it better): a one-line edit."""
    path = default_path(project)
    target = _target(project, page)
    text = read_doc(path)[0] if path.exists() else ""
    blocks = re.split(r"(?m)^(?=\[\[q\]\])", text)
    for i, b in enumerate(blocks):
        if not re.search(r'(?m)^id\s*=\s*"%s"\s*$' % re.escape(qid), b):
            continue
        m = re.search(r"(?m)^(expect\s*=\s*\[)(.*)\](.*)$", b)
        if not m:
            raise SystemExit("memcrumbs: %s has no one-line expect in %s; edit it by hand" % (qid, project.rel(path)))
        if json.dumps(target) in m.group(2):
            out("%s already expects %s" % (qid, target))
            return
        items = m.group(2).strip()
        blocks[i] = b[:m.start()] + "%s%s%s]%s" % (m.group(1), items + ", " if items else "", json.dumps(target),
                                                   m.group(3)) + b[m.end():]
        writeset.write_text(project, path, "".join(blocks), read_doc(path)[1])
        out.set(id=qid, expect_added=target)
        out("%s now also expects %s (%s)" % (qid, target, project.rel(path)))
        return
    raise SystemExit("memcrumbs: no question %s in %s" % (qid, project.rel(path)))


def add(out, project, question, expects, category=""):
    """Record a question the wiki should answer, with the file(s) that do. Run it when a lookup missed."""
    if not expects:
        raise SystemExit("memcrumbs: --add needs --expect <page or file>")
    targets = [_target(project, e) for e in expects]
    path = default_path(project)
    head = "" if path.exists() else ("# Questions this wiki must answer (memcrumbs bench). Added with "
                                      "`memcrumbs bench --add`.\n")
    n = len(load(path)) + 1 if path.exists() else 1
    entry = '%s\n[[q]]\nid = "real-%03d"\nq = %s\nexpect = [%s]\n%s' % (
        head, n, json.dumps(project.redact(question), ensure_ascii=False), ", ".join(json.dumps(t) for t in targets),
        ("category = %s\n" % json.dumps(category)) if category else "")
    writeset.append_text(project, path, entry)
    out.set(path=project.rel(path), id="real-%03d" % n, expect=targets)
    out("added real-%03d to %s (%d questions) — memcrumbs bench to measure" % (n, project.rel(path), n))


def report(out, project, store, path, min_recall3=None, k=8):
    path = path or default_path(project)
    if not Path(path).exists():
        raise SystemExit("memcrumbs: no questions at %s — record real ones with: memcrumbs bench --add \"<question>\" "
                         "--expect <page>" % posix(path))
    rows = run(project, store, load(path), k)
    new = [r for r in rows if r.get("new")]
    rows = [r for r in rows if not r.get("new")]
    total = _agg(rows)
    cats = {c: _agg([r for r in rows if r["category"] == c]) for c in sorted({r["category"] for r in rows if r["category"]})}
    para = _agg([r for r in rows if r["paraphrase"]])
    misses = [r for r in rows if not r["rank"] or r["rank"] > 3]
    out.list_key = "questions"
    out.set(project=project.name, questions_file=posix(path), total=total, by_category=cats, paraphrase=para,
            questions=rows + new, unrecorded=dict(n=len(new), labelled=sum(1 for r in new if r["labelled"])))
    out.hint("memcrumbs bench %s --json --full" % posix(path))
    out("bench %s · %d questions · recall@1 %.3f · recall@3 %.3f · MRR %.3f" % (
        project.name, total["n"], total["recall_at_1"], total["recall_at_3"], total["mrr"]))
    out("recall@3 counting '→ see' pointers under a hit: %.3f" % total["recall_at_3_with_pointers"])
    out("tokens/answer mean %d p95 %d (est.) · search latency mean %.1f ms p95 %.1f ms" % (
        total["tokens_mean"], total["tokens_p95"], total["ms_mean"], total["ms_p95"]))
    if para["n"]:
        out("paraphrased questions: %d · recall@3 %.3f" % (para["n"], para["recall_at_3"]))
    for c, a in cats.items():
        out("  %-12s n=%-3d r@1 %.2f  r@3 %.2f" % (c, a["n"], a["recall_at_1"], a["recall_at_3"]))
    for r in misses:
        out("miss %s (rank %s): %s → %s" % (r["id"], r["rank"] or "-", r["q"], ", ".join(r["top3"]) or "no hits"))
    if new:
        out("unrecorded error text: %d · said so: %d" % (len(new), sum(1 for r in new if r["labelled"])))
    for r in new:
        if not r["labelled"]:
            out("unlabelled %s: %s → %s" % (r["id"], r["q"], ", ".join(r["top3"]) or "no hits"))
    if min_recall3 is not None and total["recall_at_3"] < min_recall3:
        out("FAIL: recall@3 %.3f < %.3f" % (total["recall_at_3"], min_recall3))
        return 1
    return 0
