"""Structured capture and curation, one deliberate command each:
`decision` and `incident` capture a page with a status; `verify` bumps `verified:` after a re-check;
`supersede` marks a page replaced. Edits touch only the named frontmatter lines."""
import datetime as dt
import re

from memcrumbs import markdown, writeset
from memcrumbs.util import read_doc

DECISION_STATUSES = ("accepted", "rejected", "parked", "superseded")


def slugify(title, n=60):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:n].rstrip("-") or "untitled"


def _yaml(v):
    v = " ".join(str(v).split())
    return '"%s"' % v.replace('"', "'") if re.search(r"[:#\[\]{}]|^[-?!&*@`]", v) else v


def _new_page(out, project, folder, title, meta, sections):
    today = dt.date.today().isoformat()
    red = project.redact
    base = project.wiki / folder / ("%s-%s" % (today, slugify(title)))
    from memcrumbs import review
    meta = dict(meta, written_by=review.writer())          # provenance: an agent shell sets CLAUDECODE
    fm = ["---", "title: %s" % _yaml(red(title))]
    fm += ["%s: %s" % (key, v if key in ("tags", "sources") else _yaml(red(v))) for key, v in meta.items()]
    fm += ["verified: %s" % today, "---", "# %s" % red(title), ""]
    for head, body in sections:
        fm += ["## %s" % head, red(body).strip() or "(fill in)", ""]
    f, k = base.with_suffix(".md"), 2
    while True:                                  # exclusive create: two same-titled records never overwrite
        try:
            writeset.create_new(project, f, "\n".join(fm))
            break
        except FileExistsError:
            f, k = base.with_name("%s-%d.md" % (base.name, k)), k + 1
    out.set(path=project.rel(f))
    out("wrote %s — fill in the sections, add sources:, then memcrumbs check" % project.rel(f))
    return f


def decision(out, project, title, status, why="", tags=(), considered="", evidence="", revisit_if=""):
    """A decision record in the MADR shape: the options considered, the evidence behind the verdict (the
    numbers and where they came from) and what would reopen it."""
    if status not in DECISION_STATUSES:
        raise SystemExit("status must be one of: %s" % ", ".join(DECISION_STATUSES))
    meta = {"summary": "%s: %s" % (status, why or title), "status": status,
            "tags": "[%s]" % ", ".join(["decision"] + list(tags)), "sources": "[]"}
    options = "\n".join("- " + o.strip() for o in considered.split(";") if o.strip())
    return _new_page(out, project, "decisions", title, meta, [
        ("Question", ""), ("Options considered", options), ("What we tried", ""), ("Evidence", evidence),
        ("Verdict", "%s. %s" % (status.capitalize(), why)), ("Why", why), ("Revisit if", revisit_if)])


def incident(out, project, title, cause="", fix="", tags=(), symptom="", guard="", lucky=""):
    """An incident keyed on its symptom: what someone about to repeat it sees first is indexed with the
    title, so "I pressed X and nothing happened" finds the cause; the guard is what stops a repeat."""
    meta = {"summary": "%s%s" % (title, (" — fixed: " + fix) if fix else "")}
    if symptom:
        meta["symptom"] = symptom
    meta.update({"tags": "[%s]" % ", ".join(["incident"] + list(tags)), "sources": "[]"})
    sections = [("Symptom", symptom), ("What happened", ""), ("Root cause", cause), ("Fix", fix), ("Guard", guard)]
    return _new_page(out, project, "incidents", title, meta, sections + ([("Where we got lucky", lucky)] if lucky else []))


def exact_page(project, name):
    """A write needs one unambiguous page: a wiki-relative path, or a file name that only one page has."""
    rel = name[5:] if name.startswith("wiki/") else name
    cand = project.wiki / (rel if rel.endswith(".md") else rel + ".md")
    if cand.exists():
        return cand
    hits = [p for p in project.wiki_pages() if p.stem.lower() == name.lower().removesuffix(".md")]
    if len(hits) == 1:
        return hits[0]
    raise SystemExit("memcrumbs: %s page %r%s" % ("ambiguous" if hits else "no", name,
                                                 (": " + ", ".join(project.rel(h) for h in hits)) if hits else ""))


def _edit_frontmatter(out, project, name, updates, verb):
    p = exact_page(project, name)
    text, info = read_doc(p)
    new = markdown.set_frontmatter(text, updates)
    if new != text:
        writeset.write_text(project, p, new, info)
    out.set(path=project.rel(p), updates={k: v for k, v in updates.items() if v is not None})
    out("%s %s (%s)" % (verb, project.rel(p), ", ".join("%s: %s" % kv for kv in updates.items() if kv[1] is not None)))


def supersede(out, project, name, by=None):
    updates = {"status": "superseded"}
    if by:
        updates["superseded_by"] = exact_page(project, by).stem      # the replacement must exist
    _edit_frontmatter(out, project, name, updates, "superseded")
    if by:                                    # the link runs both ways: the new page names what it replaces
        new = exact_page(project, by)
        meta = markdown.frontmatter(read_doc(new)[0])[0]
        old = exact_page(project, name).stem
        if not meta.get("supersedes"):
            _edit_frontmatter(out, project, by, {"supersedes": old}, "linked")
        elif old not in (meta["supersedes"] if isinstance(meta["supersedes"], list) else [meta["supersedes"]]):
            out("note: %s already says supersedes: %s — add %s there by hand" % (new.stem, meta["supersedes"], old))


def verify(out, project, name, date=None):
    date = date or dt.date.today().isoformat()
    from memcrumbs import freshness, review
    if freshness.parse_date(date) is None:
        raise SystemExit("memcrumbs: --date %s is not a real YYYY-MM-DD date, or is in the future" % date)
    updates = {"verified": date}
    meta = markdown.frontmatter(read_doc(exact_page(project, name))[0])[0]
    if review.writer() == "human" and review.interactive() and review.unreviewed_page(meta):
        updates["reviewed"] = date                      # a human re-checked an agent-written page
    _edit_frontmatter(out, project, name, updates, "verified")
    from memcrumbs import plan
    if plan.mark_done(project, exact_page(project, name).stem):
        out("refresh plan: %s done (memcrumbs plan next for the next page)" % name)
