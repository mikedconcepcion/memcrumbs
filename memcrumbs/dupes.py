"""Near-duplicate pages: pairs whose title, summary and aliases say nearly the same thing, by TF-IDF cosine
over their words. Deterministic, no model; `check --dupes` lists them as a curation step (supersede one, or merge),
which feeds the planned curation loop."""
import math
import re
from collections import Counter

from memcrumbs import markdown
from memcrumbs.query import STOPWORDS
from memcrumbs.util import read_text

THRESHOLD = 0.6
BODY = 0.5                  # share of word runs two bodies must have in common before a supersede is offered
SERIES = re.compile(r"(?i)\b(\d{4}([-/.]\d{1,2}){0,2}|\d+(\.\d+)*|v\d+(\.\d+)*|q[1-4]|"
                    r"jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(tember)?|oct(ober)?|"
                    r"nov(ember)?|dec(ember)?|week|month|quarter|part)\b")


def _words(text):
    return [w.rstrip("s") if len(w) > 4 else w for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) > 2 and w not in STOPWORDS]


def pairs(project, threshold=THRESHOLD):
    """[(page a, page b, similarity)] for current, non-journal pages, most similar first."""
    docs = []
    for p in project.wiki_pages():
        if "journal" in p.relative_to(project.wiki).parts:
            continue
        meta = markdown.frontmatter(read_text(p))[0]
        if str(meta.get("status") or "").lower() in ("superseded", "rejected"):
            continue
        aliases = meta.get("aliases") or []
        text = " ".join([str(meta.get("title") or p.stem), str(meta.get("summary") or "")] +
                        [str(a) for a in (aliases if isinstance(aliases, list) else [aliases])])
        words = Counter(_words(text))
        if words:
            docs.append((project.rel(p), words, str(meta.get("title") or p.stem), p))
    n = len(docs)
    df = Counter(w for _, c, _, _ in docs for w in c)
    vecs = []
    for rel, c, _, _ in docs:
        v = {w: (1 + math.log(tf)) * math.log((n + 1) / (df[w] + 0.5)) for w, tf in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append((rel, {w: x / norm for w, x in v.items()}))
    by_word = {}
    for i, (_, v) in enumerate(vecs):
        for w in v:
            by_word.setdefault(w, []).append(i)
    out, seen = [], set()
    for i, (rel, v) in enumerate(vecs):            # only pages that share a word are compared
        for j in sorted({j for w in v for j in by_word[w] if j > i}):
            if (i, j) in seen:
                continue
            seen.add((i, j))
            other = vecs[j][1]
            sim = sum(x * other.get(w, 0.0) for w, x in v.items())
            if sim < threshold or series(docs[i][2], docs[j][2]):
                continue                          # monthly logs, versions, parts: a series, not duplicates
            if body_overlap(docs[i][3], docs[j][3]) < BODY:
                continue                          # the titles agree, the contents do not
            out.append((rel, vecs[j][0], round(sim, 2)))
    return sorted(out, key=lambda t: -t[2])


def series(a, b):
    """Titles that differ only by a date, a number, a version or a month are one series."""
    norm = (lambda t: " ".join(SERIES.sub("#", t.lower()).split()))
    return a.lower() != b.lower() and norm(a) == norm(b)


def _shingles(path, n=5):
    words = re.findall(r"[a-z0-9]+", markdown.frontmatter(read_text(path))[1].lower())
    return {" ".join(words[i:i + n]) for i in range(max(len(words) - n + 1, 1))} if words else set()


def body_overlap(a, b):
    """Jaccard of the two bodies' 5-word runs (0 when either is empty)."""
    sa, sb = _shingles(a), _shingles(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def findings(project, threshold=THRESHOLD):
    return [("I", a, "near-duplicate of %s (similarity %.2f): supersede one, or merge them" % (b, s))
            for a, b, s in pairs(project, threshold)]
