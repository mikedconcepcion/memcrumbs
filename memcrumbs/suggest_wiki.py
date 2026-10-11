"""Wiki-only suggesters: near-duplicate pages, pages that cite the same files but never link,
and pages too big to read in one lookup. All are deterministic and write only the wiki."""
import re

from memcrumbs import dupes, freshness, markdown
from memcrumbs.suggest import Suggestion
from memcrumbs.util import read_doc, read_text, split_lines

HEADER_PAGES = {"rules", "index", "gotchas"}
HUB = 6                       # a source cited by more pages than this links nothing in particular
MAX_LINKS = 20
SPLIT_CHARS = 12000           # ≈ 3k tokens: past this a page no longer reads in one lookup


def _pages(project):
    """[(path, meta, body)] for current, non-journal pages."""
    out = []
    for p in project.wiki_pages():
        if "journal" in p.relative_to(project.wiki).parts:
            continue
        meta, body, _ = markdown.frontmatter(read_text(p))
        if str(meta.get("status") or "").lower() in ("superseded", "rejected") or markdown.truthy(meta.get("quarantined")):
            continue
        out.append((p, meta, body))
    return out


def _dupes(project, cheap_only=False):
    pairs = dupes.pairs(project)
    if not pairs:
        return []
    by_rel = {project.rel(p): p for p in project.wiki_pages()}
    out, texts = [], {}

    def doc(p):                                   # each page is read once
        if p not in texts:
            texts[p] = read_doc(p)[0]
        return texts[p]
    for a, b, sim in pairs:
        pa, pb = by_rel.get(a), by_rel.get(b)
        if pa is None or pb is None:
            continue
        ma, mb = (markdown.frontmatter(doc(x))[0] for x in (pa, pb))
        newer_a = (str(ma.get("verified") or ""), pa.stat().st_size) >= (str(mb.get("verified") or ""), pb.stat().st_size)
        keep, old = (pa, pb) if newer_a else (pb, pa)
        old_text, keep_text = doc(old), doc(keep)
        changes = [(old, markdown.set_frontmatter(old_text, {"status": "superseded", "superseded_by": keep.stem}))]
        if not markdown.frontmatter(keep_text)[0].get("supersedes"):
            changes.append((keep, markdown.set_frontmatter(keep_text, {"supersedes": old.stem})))
        out.append(Suggestion(
            "dupes", "%s|%s" % (a, b), "near-duplicate pages %s and %s (similarity %.2f)" % (a, b, sim),
            "supersede %s by %s (it stays searchable, below the current page)" % (project.rel(old), project.rel(keep)),
            ["title, summary and aliases score %.2f (threshold %.2f); the bodies share %.0f%% of their word runs"
             % (sim, dupes.THRESHOLD, 100 * dupes.body_overlap(pa, pb))], risk="review", changes=changes,
            agent="first move anything only %s says into %s, then apply" % (old.stem, keep.stem), score=sim))
    return out


def _links(project, cheap_only=False):
    pages = _pages(project)
    cites, linked = {}, {}
    for p, meta, body in pages:
        if p.stem.lower() in HEADER_PAGES:
            continue
        linked[p] = {x.lower() for x in markdown.links(body)}
        for s in freshness.source_paths(project, meta.get("sources")):
            cites.setdefault(s, []).append(p)
    shared, strength = {}, {}
    for src, ps in cites.items():
        if 1 < len(ps) <= HUB:
            for i, a in enumerate(ps):
                for b in ps[i + 1:]:
                    key = tuple(sorted((a, b)))
                    shared.setdefault(key, []).append(src.name)
                    strength[key] = strength.get(key, 0) + 1.0 / (len(ps) - 1)   # a file only these two cite: 1
    out = []
    for (a, b), names in sorted(shared.items(), key=lambda kv: (-strength[kv[0]], str(kv[0]))):
        if strength[(a, b)] < 1 or b.stem.lower() in linked[a] or a.stem.lower() in linked[b]:
            continue
        why = ", ".join(sorted(set(names))[:3])
        changes = [(x, _add_related(read_doc(x)[0], y.stem, why)) for x, y in ((a, b), (b, a))]
        out.append(Suggestion(
            "link", "%s|%s" % (project.rel(a), project.rel(b)),
            "%s and %s cite the same files (%s) but do not link" % (project.rel(a), project.rel(b), why),
            "add a Related link on each page", ["%d shared source file(s), cited by few other pages" % len(set(names))],
            changes=changes, score=strength[(a, b)]))
        if len(out) >= MAX_LINKS:
            break
    return out


def _add_related(text, stem, why):
    """A '- [[stem]]: also cites …' bullet under '## Related' (added at the end if missing)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    line = "- [[%s]]: also cites %s" % (stem, why)
    m = re.search(r"(?m)^##\s+Related\s*$", text)
    if m:
        end = text.find(nl, m.end())
        return text[:end + len(nl)] + line + nl + text[end + len(nl):] if end >= 0 else text + nl + line + nl
    return text.rstrip("\r\n") + nl + nl + "## Related" + nl + nl + line + nl


def _split(project, cheap_only=False):
    max_lines = int(project.check_cfg.get("max_lines", 300))
    out = []
    for p, meta, body in _pages(project):
        lines = split_lines(body)
        if p.stem.lower() in HEADER_PAGES or (len(lines) <= max_lines and len(body) <= SPLIT_CHARS):
            continue
        heads = markdown.headings(lines)
        hs = [(i, h) for i, lvl, h in heads if lvl == 2]
        if len(hs) < 2:
            hs = [(i, h) for i, lvl, h in heads if lvl == 3]
        if len(hs) < 2:                  # nothing to split by: one long table or list, which lookups return by rows
            continue
        sizes = [(h, (hs[k + 1][0] if k + 1 < len(hs) else len(lines)) - i) for k, (i, h) in enumerate(hs)]
        big = ", ".join("%s (%d lines)" % (h, n) for h, n in sorted(sizes, key=lambda x: -x[1])[:3])
        out.append(Suggestion(
            "split", project.rel(p), "%s is %d lines, ≈ %d tokens: too big for one lookup" % (
                project.rel(p), len(lines), len(body) // 4),
            "split it by its sections into pages, and keep this page as a short index that links them",
            ["%d lines, %d characters; largest sections: %s" % (len(lines), len(body), big)],
            agent="move each large section to its own page (keep `sources:` and aliases with the facts), leave a "
                  "one-line summary and a [[link]] here, then memcrumbs check", score=len(body) / 1000))
    return out


SUGGESTERS = {"dupes": _dupes, "link": _links, "split": _split}
