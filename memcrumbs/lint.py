"""`check`: wiki lint plus plugin checks. Each finding is (level, where, message); E = must fix (secrets),
W = should fix, I = needs a curation step (verify, supersede)."""
import difflib
import json
import re

from memcrumbs import freshness, lint_records, markdown
from memcrumbs.guard import instruction_like
from memcrumbs.project import STATUSES
from memcrumbs.redact import RedactionError
from memcrumbs.sources import wiki_kind
from memcrumbs.util import SHELL_SAFE, posix, read_text, shq

REQUIRED = ("title", "summary", "verified")
DEPRECATED = (("status", "max_chars", "max_tokens (chars / 4)"),)        # (table, key, replacement)


def lint(project, today=None):
    cfg = project.check_cfg
    max_lines = int(cfg.get("max_lines", 300))
    stale = int(cfg.get("stale_days", 45))
    pages = project.wiki_pages()
    slugs = {p.stem.lower() for p in pages}
    rels = {project.rel(p)[5:-3].lower() for p in pages}
    out, seen, moved = [], {}, None
    for p in pages:
        where = project.rel(p)
        text = read_text(p)
        meta, body, _ = markdown.frontmatter(text)
        journal = "journal" in p.relative_to(project.wiki).parts
        if not SHELL_SAFE.match(p.stem):
            out.append(("W", where, "file name has characters a shell would act on (spaces, quotes, $, ;, & …): "
                                    "rename it with letters, digits, - and _ only"))
        try:
            for hit in project.redact.find(text):
                out.append(("E", where, "secret-like value: %s" % hit))
        except RedactionError as e:
            out.append(("E", where, "secret filter failed (%s): page is not indexed" % e))
        for rule in instruction_like(text):
            out.append(("W", where, "instruction-like text (%s): possible prompt injection; quote or remove it" % rule))
        if not journal:
            miss = [k for k in REQUIRED if not meta.get(k)]
            if miss:
                out.append(("W", where, "frontmatter missing: %s" % ", ".join(miss)))
        n = body.count("\n")
        if n > max_lines and not journal:
            out.append(("W", where, "%d lines > %d: split it" % (n, max_lines)))
        status = str(meta.get("status") or "").lower()
        if status and status not in STATUSES:
            near = difflib.get_close_matches(status, STATUSES, 1, 0.6)
            out.append(("W", where, "unknown status %r%s (valid: %s)" % (
                status, "; did you mean %r?" % near[0] if near else "", ", ".join(STATUSES))))
        kind = str(meta.get("kind") or "").lower() or wiki_kind(project, p)
        out += lint_records.findings(where, kind, meta, body)
        if markdown.truthy(meta.get("quarantined")):
            out.append(("I", where, "quarantined (out of the index and header): review it, then memcrumbs quarantine "
                                    "%s --lift in your own terminal, or delete it" % p.stem))
        seen[p.stem.lower()] = (where, meta, body)
        if kind not in ("runbook", "journal") and re.match(r"(?i)\s*(how to|steps to|procedure)\b", str(meta.get("summary") or "")):
            out.append(("I", where, "reads like a runbook (summary starts %r): move it to runbooks/ or set kind: runbook"
                        % str(meta["summary"]).split()[0]))
        by = str(meta.get("superseded_by") or "").lower().removesuffix(".md")
        if by and by not in slugs and by not in rels:
            out.append(("W", where, "superseded_by [[%s]] does not exist" % by))
        if status == "superseded" and not by:
            out.append(("I", where, "superseded without superseded_by: say what replaced it"))
        age = freshness.days_since(meta.get("verified"), today)
        retired = status in ("superseded", "rejected")      # a replaced page or a verdict is not refreshed
        if age is not None and age > stale and not journal and not retired:
            out.append(("I", where, "verified %d days ago: re-check it, then memcrumbs verify %s" % (age, shq(p.stem))))
        elif age is not None and not journal and not retired:
            if moved is None:
                moved = {k: names for k, _, names in freshness.page_freshness(project)}
            if posix(p) in moved:
                out.append(("I", where, "sources changed since verified: %s — re-check, then memcrumbs verify %s"
                            % (moved[posix(p)], shq(p.stem))))
        if meta.get("verified") and not re.match(r"\d{4}-\d{2}-\d{2}$", str(meta["verified"])):
            out.append(("W", where, "verified must be YYYY-MM-DD"))
        elif meta.get("verified") and freshness.parse_date(meta["verified"], today) is None:
            out.append(("W", where, "verified %s is not a real date or is in the future: set the day it was checked"
                        % meta["verified"]))
        for ln in markdown.links(body):
            k = ln.lower().removesuffix(".md")
            if k not in slugs and k not in rels:
                out.append(("W", where, "broken link [[%s]]" % ln))
        names = markdown.block_names(text)
        for name in set(names):
            try:
                markdown.find_block(text, name)
            except markdown.BlockError as e:
                out.append(("W", where, str(e)))
    out += lint_records.two_way(seen)
    from memcrumbs import facts
    try:
        out += facts.lint(project)               # conflicting current values, bindings
    except RedactionError:
        raise
    except Exception as e:
        out.append(("W", "facts", "facts check failed: %s" % type(e).__name__))
    return out


def _key(f):
    """A finding as the baseline remembers it: numbers and line numbers left out, so an aging page stays known."""
    return "%s|%s|%s" % (f[0], re.sub(r":\d+$", "", f[1]), re.sub(r"\d+", "#", f[2]))


def _baseline_path(project):
    return project.data / "check-baseline.json"


def check(out, project, api, baseline=False, show_all=False, strict=False, dupes=False):
    """Lint plus plugin checks. `baseline` records today's warnings and curation steps, and from then on only new
    ones are listed (errors are never baselined: a secret is always shown); `strict` also fails on new warnings;
    `dupes` adds near-duplicate pages."""
    findings = lint(project)
    for table, key, use in DEPRECATED:
        if key in project.cfg.get(table, {}):
            findings.append(("W", "memcrumbs.toml", "[%s] %s is deprecated: use %s" % (table, key, use)))
    for spec, err in api.errors:
        findings.append(("W", "plugin %s" % spec, "failed to load: %s" % err))
    for fn in api.checks:
        try:
            findings += [tuple(f) for f in fn(project)]
        except Exception as e:
            findings.append(("W", "plugin", "check failed: %s" % type(e).__name__))
    if dupes:
        from memcrumbs import dupes as near
        findings += near.findings(project)
    order = {"E": 0, "W": 1, "I": 2}
    findings.sort(key=lambda f: (order.get(f[0], 3), f[1], f[2]))
    known, since = set(), None
    bp = _baseline_path(project)
    if baseline:
        import datetime as dt
        since = dt.date.today().isoformat()
        keys = sorted({_key(f) for f in findings if f[0] != "E"})
        from memcrumbs import writeset
        writeset.write_text(project, bp, json.dumps(dict(created=since, findings=keys), indent=1) + "\n")
        out("baseline: %d findings recorded in %s (errors are never baselined); check now lists only new ones"
            % (len(keys), project.rel(bp)))
    elif bp.exists() and not show_all:
        try:
            rec = json.loads(read_text(bp))
            known, since = set(rec.get("findings", [])), rec.get("created")
        except ValueError:
            known = set()
    shown = [f for f in findings if f[0] == "E" or _key(f) not in known] if not baseline else findings
    hidden = len(findings) - len(shown)
    errs = sum(1 for f in shown if f[0] == "E")
    warns = sum(1 for f in shown if f[0] == "W")
    out.list_key = "findings"
    out.set(findings=[dict(level=a, where=b, message=c) for a, b, c in shown], errors=errs, known=hidden)
    out.hint("memcrumbs check --full" + (" · --all" if hidden else ""))
    if baseline:
        return 1 if errs else 0
    out("%d findings (%d errors)%s" % (len(shown), errs, " · %d known since the baseline of %s (--all lists them)"
                                       % (hidden, since) if hidden else ""))
    for lvl, where, msg in shown:
        out("%s %s: %s" % (lvl, where, msg))
    return 1 if errs or (strict and warns) else 0
