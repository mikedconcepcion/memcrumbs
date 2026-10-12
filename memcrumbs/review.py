"""Provenance and review for agent-written knowledge.

- **Stamps.** The capture commands write `written_by: agent|human`. A shell inside Claude Code sets CLAUDECODE=1
  (MEMCRUMBS_AGENT=1 does the same for other hosts). Hits on an agent-written page that no human has reviewed
  say UNREVIEWED.
- **Header.** The standing sections (rules, top gotchas) show only reviewed lines. The lines present when review
  arrives are kept, and lines added later wait; one header line says how many (`[review] gate_header = false`
  turns this off).
- **`memcrumbs review`** lists what waits as one digest. `review --approve all|ID,…` marks it reviewed. A human
  types a code at a terminal. Inside Claude Code it runs only in the form `wire`'s ask rules name, so Claude Code
  asks the owner first and their answer is the approval (the memcrumbs-review skill); any other agent shell is
  refused, so an agent cannot approve its own text.
- **`memcrumbs quarantine <page>`** keeps a page on disk but out of the index and the header. Git is the
  rollback."""
import datetime as dt
import hashlib
import json
import os
import secrets
import sys

from memcrumbs import markdown, writeset
from memcrumbs.util import read_doc, read_text, split_lines

AGENT_ENV = ("CLAUDECODE", "MEMCRUMBS_AGENT")
GATED = (("rules", "rules.md", "Top"), ("gotchas", "gotchas.md", "Top"))


def writer():
    """'agent' when CLAUDECODE is set at all (even empty) or MEMCRUMBS_AGENT is true; else 'human'."""
    if "CLAUDECODE" in os.environ:
        return "agent"
    v = os.environ.get("MEMCRUMBS_AGENT")
    return "agent" if v is not None and v.strip().lower() not in ("", "0", "false", "no") else "human"


def interactive():
    try:
        return bool(sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty())
    except (AttributeError, ValueError):
        return False


def confirm(what, project=None, cmd=None):
    """A human at a terminal types a code. An agent's shell has no terminal (and its environment says so), so an
    agent cannot approve its own text by clearing a variable. Inside Claude Code, the owner's answer to the prompt
    an ask rule forces is the approval: `cmd` (an OWNER entry) must run in the form that rule names."""
    from memcrumbs import claude_settings as cs
    if writer() == "agent" and cmd and cs.in_claude_code():
        why = cs.owner_form(project, cmd)
        if why is None:
            return
        raise SystemExit("memcrumbs: %s needs the owner: %s; or the owner runs it in their own terminal" % (what, why))
    if writer() == "agent" or not interactive():
        raise SystemExit("memcrumbs: %s needs a human: run it in your own terminal, not through the agent" % what)
    code = "%04d" % secrets.randbelow(10000)
    try:
        got = input("type %s to %s: " % (code, what))
    except EOFError:
        got = ""
    if got.strip() != code:
        raise SystemExit("memcrumbs: not confirmed; nothing changed")


def line_id(line):
    return hashlib.sha256(" ".join(line.split()).encode("utf-8")).hexdigest()[:10]


def _path(project):
    """Kept in the wiki (versioned with it), not in the index folder: a cache that is deleted or not cloned must
    not approve anything."""
    return project.wiki / ".review.json"


def standing(project):
    """[(section, line)] of the gated header sections, every line (not cut to the header's count)."""
    out = []
    for name, fname, heading in GATED:
        p = project.wiki / fname
        if p.exists():
            meta, body, _ = markdown.frontmatter(read_text(p))
            if markdown.truthy(meta.get("quarantined")):
                continue
            lines = split_lines(body)
            span = markdown.section_span(lines, heading)
            out += [(name, ln) for ln in (lines[span[0] + 1: span[1]] if span else lines) if ln.strip()]
    return out


def state(project):
    """The reviewed line ids. On first adoption (no state anywhere) today's lines are kept (grandfathered); a state
    file that cannot be read fails closed: nothing counts as reviewed until the owner reviews again."""
    p, legacy = _path(project), project.data / "reviewed.json"
    if not p.exists() and legacy.exists():                  # 0.2.0.dev4 kept it in the index folder
        try:
            writeset.write_text(project, p, read_text(legacy))
        except OSError:
            pass
    if not p.exists():
        keep = sorted({line_id(ln) for _, ln in standing(project)})
        st = dict(lines=keep, kept=keep, since=dt.date.today().isoformat(), kept_shown=False)
        try:
            writeset.write_text(project, p, json.dumps(st, indent=1) + "\n")
        except OSError:
            pass
        return st
    try:
        st = json.loads(read_text(p))
    except (OSError, ValueError):
        st = None
    ok = isinstance(st, dict) and isinstance(st.get("lines"), list) and all(isinstance(x, str) for x in st["lines"])
    return st if ok else dict(lines=[], kept=[], kept_shown=True, broken=True)


def gating(project):
    return bool(project.cfg.get("review", {}).get("gate_header", True))


def gate(project, name, lines):
    """(the reviewed lines, how many wait) for a header section; other sections pass through."""
    if name not in {g[0] for g in GATED} or not gating(project):
        return lines, 0
    ok = set(state(project)["lines"])
    keep = [ln for ln in lines if line_id(ln) in ok]
    return keep, len(lines) - len(keep)


def unreviewed_page(meta):
    return str(meta.get("written_by") or "").lower() == "agent" and not meta.get("reviewed")


def digest(project):
    """Everything that waits: new header lines, then agent-written pages no human reviewed."""
    st, items = state(project), []
    ok = set(st["lines"])
    for name, ln in standing(project):
        if line_id(ln) not in ok and gating(project):
            items.append(dict(id=line_id(ln), what="line", where="%s.md" % name, text=ln.strip()))
    for p in project.wiki_pages():
        meta = markdown.frontmatter(read_text(p))[0]
        if unreviewed_page(meta):
            srcs = meta.get("sources") or []
            items.append(dict(id=p.stem, what="page", where=project.rel(p), text=str(meta.get("title") or p.stem),
                              summary=str(meta.get("summary") or ""),
                              sources=", ".join(map(str, srcs if isinstance(srcs, list) else [srcs]))))
    kept = [] if st.get("kept_shown") else [ln.strip() for _, ln in standing(project) if line_id(ln) in set(st.get("kept", []))]
    return items, kept


def quarantined(project):
    return sorted(p.stem for p in project.wiki_pages()
                  if markdown.truthy(markdown.frontmatter(read_text(p))[0].get("quarantined")))


def approve(project, ids):
    """Mark items reviewed: 'all', or ids from the digest ('kept' marks the kept lines as seen). The owner only."""
    confirm("approve these reviews", project, ("review", "--approve"))
    items, _ = digest(project)
    want = {i.strip() for i in ids.split(",") if i.strip()}
    pick = [it for it in items if "all" in want or it["id"] in want]
    st = state(project)
    st.pop("broken", None)
    st["lines"] = sorted(set(st["lines"]) | {it["id"] for it in pick if it["what"] == "line"})
    if "all" in want or "kept" in want:
        st["kept_shown"] = True
    writeset.write_text(project, _path(project), json.dumps(st, indent=1) + "\n")
    today = dt.date.today().isoformat()
    for it in pick:
        if it["what"] == "page":
            p = project.wiki / it["where"][5:] if it["where"].startswith("wiki/") else project.wiki / it["where"]
            text, info = read_doc(p)
            writeset.write_text(project, p, markdown.set_frontmatter(text, {"reviewed": today}), info)
    return pick


def command(out, project, approve_ids=None, show_kept=False):
    out.list_key = "items"
    if approve_ids:
        done = approve(project, approve_ids)
        out.set(approved=[it["id"] for it in done])
        out("reviewed %d item(s)%s" % (len(done), "; the kept lines are marked seen" if "kept" in approve_ids
                                       or "all" in approve_ids else ""))
        return 0
    items, kept = digest(project)
    held = quarantined(project)
    out.set(items=items, kept=kept if show_kept else len(kept), quarantined=held)
    if held:
        out("quarantined (out of the index and the header until the owner lifts it): %s — memcrumbs quarantine "
            "--lift NAME" % ", ".join(held))
    if not items and not kept:
        out("nothing waits for review")
        return 0
    from memcrumbs import claude_settings as cs
    if cs.in_claude_code():
        out("%d item(s) wait for review: show each in full to the owner; on their word, memcrumbs review --approve "
            "all (or ID,…), and Claude Code asks them first (skill: memcrumbs-review)" % len(items))
    else:
        out("%d item(s) wait for review — approve in your own terminal: memcrumbs review --approve all (or ID,…)"
            % len(items))
    for it in items:
        if it["what"] == "line":
            out("[%s] %s: %s" % (it["id"], it["where"], it["text"]))
        else:
            out("[%s] %s — %s%s%s" % (it["id"], it["where"], it["text"], " — " + it["summary"] if it["summary"] else "",
                                      " (sources: %s)" % it["sources"] if it["sources"] else ""))
    if kept:
        if show_kept:
            out("kept at the upgrade (written before review existed), shown once:")
            for ln in kept:
                out("  " + ln)
        else:
            out("%d header line(s) were kept at the upgrade without review: memcrumbs review --kept, then "
                "--approve kept" % len(kept))
    return 0


def quarantine(out, project, name, lift=False):
    """Keep a page on disk but out of the index and the header (`--lift` puts it back; humans only)."""
    from memcrumbs.curate import exact_page
    if lift:
        confirm("lift the quarantine", project, ("quarantine", "--lift"))
    p = exact_page(project, name)
    text, info = read_doc(p)
    new = markdown.set_frontmatter(text, {"quarantined": None if lift else "true"})
    if new != text:
        writeset.write_text(project, p, new, info)
    out.set(path=project.rel(p), quarantined=not lift)
    out("%s %s" % ("lifted the quarantine of" if lift else "quarantined (kept on disk, out of the index and header):",
                   project.rel(p)))
