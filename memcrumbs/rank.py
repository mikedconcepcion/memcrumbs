"""Ranking signals on top of FTS5 BM25, combined in store.search:

- coverage:  the IDF-weighted share of the query's terms a doc matches, so the doc holding the rare, telling
             word beats one that matches only common words;
- damping:   in a long question, a term's synonyms count SYNONYM_WEIGHT of the term itself (BM25 and coverage),
             so an expansion ("restart" → reboot, bounce) cannot outrank the words the user typed. Short queries
             keep full synonyms: there they carry the paraphrases (public bench: damping them cost recall@3),
             and so does a typed word the index never uses (its synonyms are then the only match).
A rare-pair proximity bonus for long questions was tried and dropped: no gain on either public bench."""
import math
import re
import sqlite3

SCAN_DF = 50_000                 # coverage: fetch a term's whole doclist up to this many docs
SYNONYM_WEIGHT = 0.5
LONG_QUESTION = 5                # damping applies from this many content terms up


def _df(db, expr):
    return db.execute("SELECT count(*) FROM docs WHERE docs MATCH ?", (expr,)).fetchone()[0]


def _hits(db, expr, wanted, inlist, df):
    if df <= SCAN_DF:                # one pass over the term's matches, intersected here, is far cheaper
        return wanted.intersection(r for (r,) in db.execute("SELECT rowid FROM docs WHERE docs MATCH ?", (expr,)))
    return {r for (r,) in db.execute(              # FTS5 checks an IN list one rowid at a time: huge doclists only
        "SELECT rowid FROM docs WHERE docs MATCH ? AND rowid IN (%s)" % inlist, (expr,))}


def is_long(pairs):
    return len(pairs) >= LONG_QUESTION


def effective_pairs(db, pairs):
    """Where the typed word occurs nowhere in the index, its synonyms are the only match and count in full:
    damping applies only to words the corpus actually uses."""
    out = []
    for expanded, plain in pairs:
        try:
            missing = plain != expanded and not _df(db, plain)
        except sqlite3.OperationalError:
            missing = False
        out.append((expanded, expanded if missing else plain))
    return out


def coverage(db, pairs, ids, ndocs):
    """({rowid: share of the query's information it matches}, known): `known` is the share of that information the
    corpus holds at all. A term no doc has is left out of the ranking share (it cannot tell docs apart) but counts
    as missing for whether the query was answered. pairs: [(expanded, plain)]."""
    dfs = {}
    syn_weight = SYNONYM_WEIGHT if is_long(pairs) else 1.0
    if len(pairs) < 2 or not ids:
        return {}, 1.0
    n, wanted = ndocs + 1, set(ids)
    inlist = ",".join(str(int(i)) for i in ids)
    weight, got, absent = {}, {}, 0.0
    for expanded, plain in pairs:
        try:
            df = _df(db, expanded)
            if not df:
                absent += math.log(1 + n)                  # as distinctive as a word can be: in no doc
                continue
            dfs[plain] = _df(db, plain) if plain != expanded else df
            weight[expanded] = w = math.log(1 + n / df)
            every = _hits(db, expanded, wanted, inlist, df)
            own = _hits(db, plain, wanted, inlist, dfs[plain]) if plain != expanded else every
            for rid in every:
                got[rid] = got.get(rid, 0.0) + w * (1.0 if rid in own else syn_weight)
        except sqlite3.OperationalError:
            continue
    total = sum(weight.values()) or 1.0
    return {rid: w / total for rid, w in got.items()}, (total / (total + absent) if weight else 0.0)


LINK_TOP = 3                     # follow [[links]] from this many top hits
POINTER_WORDS = 2                # distinct query words a link's own clause needs before it is shown
LINK_BOOST = 1.0                 # bounded boost for the linked page; 1.5 and 3.0 measured no gain, so rank is unchanged
_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


_CLAUSE_END = re.compile(r"[.;!?|]\s|\s[\u2014\u2013-]\s")


def clause_links(body, words):
    """[(slug, distinct query words in its own clause)] for every [[link]]: the clause is the text between the
    previous link (or the last sentence break) and the link. "Background on X: [[a]]. Live-tuning without a
    restart: [[b]]" gives [[b]] the words of "Live-tuning without a restart" only."""
    keys = sorted({w[:max(4, len(w) - 3)] for w in words if len(w) >= 3})
    out = []
    for ln in body.splitlines():
        prev = 0
        for m in _LINK.finditer(ln):
            clause = ln[prev:m.start()]
            breaks = list(_CLAUSE_END.finditer(clause))
            clause = clause[breaks[-1].end():] if breaks else clause
            out.append((m.group(1), sum(1 for k in keys if k in clause.lower())))
            prev = m.end()
    return out


def _page_entry(db, path):
    """The first doc of a page (its title), found through the file's rowid range: a target the query did not match."""
    r = db.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
    if not r:
        return None
    from memcrumbs.store import ROWID_BITS
    row = db.execute("SELECT loc, title FROM docs WHERE rowid >= ? AND rowid < ? ORDER BY rowid LIMIT 1",
                     (r[0] << ROWID_BITS, (r[0] + 1) << ROWID_BITS)).fetchone()
    return dict(path=path, loc=row[0], title=row[1], section="", score=0.0) if row else None


def follow_links(db, hits, stems, words=()):
    """One hop from the top hits: a page their matched chunk links to ([[slug]]) whose own clause holds
    POINTER_WORDS or more distinct query words ("<topic> without a restart: [[page]]") is shown under the hit
    (hit["see"]). If LINK_BOOST > 1, a linked page the query matched is also lifted, never above the hit that
    points to it. `hits` are sorted best first and still carry rowids; `stems` maps a page slug to its path."""
    best = {}
    for h in hits:
        best.setdefault(h["path"], h)
    pointers, top = [], []
    for h in hits:
        if h["path"] not in top:
            top.append(h["path"])
            pointers.append(h)
        if len(top) >= LINK_TOP:
            break
    for h in pointers:
        row = db.execute("SELECT body FROM docs WHERE rowid=?", (h["rowid"],)).fetchone()
        links = [(slug, n) for slug, n in clause_links(row[0] if row else "", words) if n >= POINTER_WORDS]
        # most query words in the clause first; on a tie, a page the query did not already reach
        links.sort(key=lambda x: (-x[1], stems.get(x[0].strip().lower().removesuffix(".md")) in best))
        for slug, n in links:
            path = stems.get(slug.strip().lower().removesuffix(".md"))
            if not path or path == h["path"] or path in top:
                continue
            target = best.get(path) or _page_entry(db, path)
            if not target:
                continue
            h.setdefault("see", target)
            if LINK_BOOST > 1.0 and path in best:
                target["score"] = max(target["score"] * LINK_BOOST, h["score"] + 1e-9)   # scores < 0: max = worse
            break


def damp(plain_scores, hits):
    """BM25 with synonyms, pulled toward BM25 without them: plain + w·(expanded − plain). Scores are negative
    (lower is better); a doc that only a synonym found keeps w of its score."""
    for h in hits:
        p = plain_scores.get(h["rowid"], 0.0)
        h["score"] = p + SYNONYM_WEIGHT * (h["score"] - p)

