"""Knowledge gaps → page drafts: lookups the wiki could not answer, clustered by their words, become an offer
to draft a page. Two local, opt-in sources:
- `[suggest] query_log = true`: `find` logs, in the index folder, the redacted text of lookups that no wiki hit
  in the top 3 answers (`unanswered`: it holds under half of the query's information);
- `[suggest] transcripts = true`: a `find` followed by 5 or more file reads and no wiki page read (the agent dug
  the answer out of the code).

A cluster needs 3 or more lookups on 2 or more days, and is dropped once the wiki answers its words. Nothing from
either log enters the wiki: applying writes a bare draft (title and empty sections, `status: draft`,
`written_by: agent`); the agent fills it from what `suggest show` lists, and the owner reviews it."""
import datetime as dt
import json
import os
import re
import time
from collections import Counter

from memcrumbs import transcripts, writeset
from memcrumbs.query import STOPWORDS, split_filters
from memcrumbs.suggest import Suggestion
from memcrumbs.util import posix, read_text

LOG_BYTES, LOG_LINES = 400_000, 2000
ANSWERS = 0.4                     # [suggest] gap_cover: share of a query's information a wiki hit must hold
FOLLOW = 300                      # a wiki `page` read this many seconds after a logged lookup answers it
MIN_HITS, MIN_DAYS, TRAIL = 3, 2, 5
JOIN = 0.34                       # a lookup joins a cluster that shares a third of their words


def enabled(project):
    return bool(project.cfg.get("suggest", {}).get("query_log"))


def unanswered(hits, floor=ANSWERS):
    """One test for `find`'s log and for a cluster: no wiki hit in the top 3 holds `floor` of the query's
    information (distinctive terms weigh more; synonyms count; a word in no doc counts as missing). Any shared word
    used to be enough, so almost nothing was logged. On bench/kiln, 0.4 logs 18 of 113 answered bench questions
    (paraphrases share few words with their page) and 6 of 10 planted off-topic ones; clusters (3 lookups on 2 days)
    and the `page` follow-up below filter the rest."""
    from memcrumbs.store import WIKI_KINDS
    return max((h.get("answers", 1.0) for h in hits[:3] if h["kind"] in WIKI_KINDS), default=0.0) < floor


def floor(project):
    try:
        return float(project.cfg.get("suggest", {}).get("gap_cover", ANSWERS))
    except (TypeError, ValueError):
        return ANSWERS


def read(project):
    """Called by `page` for a wiki page: a mark (time only), so the logged lookup just before it counts as answered."""
    if not enabled(project) or os.environ.get("MEMCRUMBS_NO_USAGE"):
        return
    try:
        writeset.append_text(project, project.data / "gaps.jsonl", json.dumps({"t": round(time.time()), "read": 1}) + "\n")
    except Exception:
        pass


def log(project, q, n):
    """Called by `find` when `unanswered`. Never fails the lookup."""
    if not enabled(project) or os.environ.get("MEMCRUMBS_NO_USAGE"):
        return
    try:
        p = project.data / "gaps.jsonl"
        writeset.append_text(project, p, json.dumps({"t": round(time.time()), "q": project.redact(q)[:200], "n": n}) + "\n")
        if p.stat().st_size > LOG_BYTES:
            writeset.write_text(project, p, "\n".join(read_text(p).splitlines()[-LOG_LINES:]) + "\n")
    except Exception:
        pass


def _words(q):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9_-]*", split_filters(q)[0].lower())
            if len(w) >= 3 and w not in STOPWORDS]


def _stem(w):
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[:-len(suf)]
    return w


def terms(q):
    return {_stem(w) for w in _words(q)}


def label(c, n=3):
    """A cluster's top words as they were asked ("charts staging helm", not the stems "chart stag helm"), most
    frequent first, ties alphabetical, so the list and `show` agree."""
    asked = Counter(w for _, q, _ in c["items"] for w in _words(q))
    top = sorted(c["terms"].items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [max(sorted(w for w in asked if _stem(w) == stem), key=lambda w: asked[w], default=stem)
            for stem, _ in top]


def entries(project, cheap_only=False):
    """[(day, query, files read instead)] from the opted-in sources."""
    out, logged, reads = [], [], []
    p = project.data / "gaps.jsonl"
    if enabled(project) and p.exists():
        for ln in read_text(p).splitlines():
            try:
                r = json.loads(ln)
                if r.get("read"):
                    reads.append(int(r["t"]))
                else:
                    logged.append((int(r["t"]), dt.date.fromtimestamp(r["t"]).isoformat(), str(r["q"])))
            except (ValueError, KeyError, TypeError, OSError, OverflowError, AttributeError):
                continue
    for t, day, q in logged:                               # the agent opened a wiki page right after: answered
        if not any(t <= r <= t + FOLLOW for r in reads):
            out.append((day, q, []))
    if cheap_only:
        return out
    wiki = posix(project.wiki).lower()
    sessions = {}
    for e in transcripts.events(project):
        sessions.setdefault(e[1], []).append(e)
    for evs in sessions.values():
        cur = None
        for day, _, kind, val in evs + [("", "", "end", "")]:
            if kind == "lookup" and not val.startswith("find:"):
                if cur is not None:
                    cur[3] = True                          # `page X` after a find: the wiki answered it
                continue
            if kind in ("lookup", "end"):
                if cur and not cur[3] and len(cur[2]) >= TRAIL:
                    out.append((cur[0], cur[1], cur[2]))
                cur = [day, val[5:], [], False] if kind == "lookup" else None
            elif kind == "read" and cur is not None:
                if val.lower().startswith(wiki):
                    cur[3] = True                          # the agent read a wiki page: the wiki had it
                elif val not in cur[2]:
                    cur[2].append(val)
    return out


def clusters(items):
    """Greedy clusters of lookups by shared words; only those with MIN_HITS lookups on MIN_DAYS days."""
    out = []
    for day, q, files in sorted(items):
        t = terms(q)
        if not t:
            continue
        best, score = None, 0.0
        for c in out:
            top = {w for w, _ in sorted(c["terms"].items(), key=lambda kv: (-kv[1], kv[0]))[:4]}   # ties: by word,
            # not by set order (which Python randomises per process, so the same log could cluster differently)
            s = len(t & top) / len(t | top)
            if s > score:
                best, score = c, s
        if best is not None and score >= JOIN:
            best["terms"].update(t)
            best["items"].append((day, q, files))
        else:
            out.append(dict(terms=Counter(t), items=[(day, q, files)]))
    return [c for c in out if len(c["items"]) >= MIN_HITS and len({d for d, _, _ in c["items"]}) >= MIN_DAYS]


def _answered(project, questions):
    """Does the wiki answer this cluster today? Each logged question is put to `find`'s own test, as asked:
    the cluster is answered when most of them now pass. The label's few words are for naming only."""
    if not project.index_path.exists():
        return False
    from memcrumbs import synonyms
    from memcrumbs.store import Store
    try:
        store = Store(project.index_path, synonyms.for_project(project))
    except Exception:
        return False
    answered, floor_ = 0, floor(project)
    try:
        for q in questions:
            try:
                answered += not unanswered(store.search(q, limit=3), floor_)
            except Exception:
                continue
    finally:
        store.close()
    return bool(questions) and answered * 2 > len(questions)


def draft(title):
    return ("---\ntitle: %s\nsummary: (draft) fill in what this page answers\nstatus: draft\nwritten_by: agent\n"
            "sources: []\ntags: [draft]\n---\n# %s\n\n## What it is\n\n(fill in)\n\n## How it works\n\n(fill in)\n\n"
            "## Sources\n\n(the files this was checked against)\n" % (title, title))


def _gaps(project, cheap_only=False):
    out = []
    for c in clusters(entries(project, cheap_only)):
        words = label(c)
        if _answered(project, list(dict.fromkeys(q for _, q, _ in c["items"]))):
            continue
        import hashlib
        stems = sorted(_stem(w) for w in words)                # the id stays stable when the wording varies
        short = hashlib.sha1(" ".join(stems).encode("utf-8")).hexdigest()[:6]
        title = "Draft %s" % short                       # neutral: no lookup words enter the wiki (§6)
        page = project.wiki / ("draft-%s.md" % short)
        if page.exists():
            continue
        days = sorted({d for d, _, _ in c["items"]})
        files = Counter(f for _, _, fs in c["items"] for f in fs).most_common(5)
        examples = list(dict.fromkeys(q for _, q, _ in c["items"]))[:3]
        evidence = ["%d lookups on %d days (%s … %s)" % (len(c["items"]), len(days), days[0], days[-1]),
                    "asked as: " + " · ".join('"%s"' % q[:60] for q in examples)]
        if files:
            evidence.append("read instead: " + ", ".join("%s (%d×)" % (f.rsplit("/", 1)[-1], n) for f, n in files))
        out.append(Suggestion(
            "gap", " ".join(stems), "%d lookups about \"%s\" found no wiki page" % (len(c["items"]), " ".join(words)),
            "draft %s (status: draft; the agent fills it in, the owner reviews it)" % project.rel(page), evidence,
            changes=[(page, draft(title))],
            agent="fill %s from the files listed above and what the lookups asked: give it a real title (and rename "
                  "the file), set sources: and verified:, drop status: draft, then memcrumbs check" % project.rel(page),
            score=len(c["items"]) * len(days), cheap=not transcripts.enabled(project)))
    return out


SUGGESTERS = {"gap": _gaps}
