"""How the project's skills are used: `memcrumbs skills`.

A skill leaves a note when it is used: `memcrumbs log "<outcome>" --skill NAME` writes a dated journal line and says
so in the terminal (skills that memcrumbs scaffolds end with that step). With transcripts on, Claude Code's
sessions also give every use: the Skill tool's calls and the slash commands typed (names only, never arguments).
Uses are counted from the transcripts when they are on, else from the notes; the notes give the last outcome.

`memcrumbs skills` lists the repo's skills (`.claude/skills/*`), the user's (`~/.claude/skills/*`) and any other
name seen used: uses in the last 30 days, the last use, the last note. `--page` keeps that table in the wiki page
`skills.md`, inside generated markers; once the page exists the daily scan refreshes it. A skill nobody uses shows
0, which is the hint to drop it."""
import datetime as dt
import re
from pathlib import Path

from memcrumbs import markdown, transcripts, writeset
from memcrumbs.cmd_write import skill_name
from memcrumbs.util import clip, read_doc, read_text

DAYS = 30
NOTE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) \d\d:\d\d skill ([a-z0-9:_-]+): (.*?)(?:\s+#[\w-]+)*\s*$")
BLOCK = "skills"
WIRED = ("memcrumbs", "memcrumbs-review")       # memcrumbs' own skills: loaded as needed, never "drop it"
PAGE = ("---\ntitle: Skills\nsummary: the project's skills, how often each is used and its last outcome\n"
        "tags: [skills]\n---\n# Skills\n\nKept by `memcrumbs skills --page` and refreshed by the daily scan; write "
        "your own notes outside the generated block.\n\n")


def known(project):
    """{name: 'repo' | 'user'}: skills with a SKILL.md in the repo or in the user's Claude Code folder."""
    out = {}
    for where, root in [("user", Path.home() / ".claude" / "skills")] + [
            ("repo", Path(r) / ".claude" / "skills") for r in project.repos]:
        if root.is_dir():
            for f in root.glob("*/SKILL.md"):
                out[f.parent.name.lower()] = where
    return out


def notes(project, since):
    """[(day, name, outcome)] of the skill notes in the journal since `since` (an ISO day)."""
    out = []
    folder = project.wiki / "journal"
    for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        if f.stem < since[:7]:
            continue
        for ln in read_text(f).splitlines():
            m = NOTE.match(ln.strip())
            if m and m.group(1) >= since:
                out.append((m.group(1), m.group(2), m.group(3)))
    return out


def uses(project, days=DAYS, today=None, events=None):
    """{name: [ISO days of its uses]}, oldest first."""
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=days)).isoformat()
    evs = transcripts.events(project, days) if events is None else events
    names, out = known(project), {}
    if evs:
        for day, _sess, kind, val in evs:
            if day >= since and (kind == "skill" or (kind == "slash" and skill_name(val) in names)):
                out.setdefault(skill_name(val), []).append(day)
    else:
        for day, name, _ in notes(project, since):
            out.setdefault(name, []).append(day)
    return {k: sorted(v) for k, v in out.items()}


def table(project, days=DAYS, today=None, events=None):
    today = today or dt.date.today()
    since = (today - dt.timedelta(days=days)).isoformat()
    used, where = uses(project, days, today, events), known(project)
    last_note = {}
    for day, name, said in notes(project, since):
        last_note[name] = (day, said)
    rows = []                                   # the user's own skills only where this project used them
    for name in sorted({n for n, w in where.items() if w == "repo"} | set(used) | set(last_note)):
        days_used = used.get(name, [])
        rows.append(dict(name=name, where=where.get(name, "seen"), uses=len(days_used),
                         last=(days_used[-1] if days_used else (last_note.get(name) or (None,))[0]),
                         note=clip(last_note[name][1], 90) if name in last_note else ""))
    rows.sort(key=lambda r: (-r["uses"], r["name"]))
    return rows


def _lines(rows, days):
    out = ["| Skill | Where | Uses (%d days) | Last | Last note |" % days, "|---|---|---|---|---|"]
    out += ["| %s | %s | %d | %s | %s |" % (r["name"], r["where"], r["uses"], r["last"] or "—",
                                          r["note"].replace("|", "/") or "—") for r in rows]
    return out


def write_page(project, rows, days=DAYS, create=False):
    """Refresh the generated block in wiki/skills.md (creating the page only when asked). True when written."""
    p = project.wiki / "skills.md"
    if not p.exists() and not create:
        return False
    text, info = read_doc(p) if p.exists() else (PAGE, (b"", "utf-8"))
    new = markdown.replace_generated(text, BLOCK, "\n".join(_lines(rows, days)))
    if p.exists() and new == text:
        return False
    writeset.write_text(project, p, new, info)
    return True


def command(out, project, page=False, days=DAYS):
    rows = table(project, days)
    out.list_key = "skills"
    out.set(skills=rows, days=days)
    if page:
        wrote = write_page(project, rows, days, create=True)
        out("%s %s" % ("wrote" if wrote else "unchanged:", project.rel(project.wiki / "skills.md")))
    if not rows:
        out("no skills yet: none in .claude/skills and none used in %d days" % days)
        return
    for r in rows:
        out("%-28s %-4s %3d use%s · last %s%s" % (clip(r["name"], 28), r["where"], r["uses"], " " if r["uses"] == 1
                                                 else "s", r["last"] or "—", " · " + r["note"] if r["note"] else ""))
    unused = [r["name"] for r in rows if r["where"] == "repo" and not r["uses"] and r["name"] not in WIRED]
    if unused:
        out("unused in %d days: %s (drop them, or say when they are for)" % (days, ", ".join(unused)))


def maybe_refresh(project):
    """The daily scan: refresh skills.md when it exists. It never fails the command."""
    try:
        if (project.wiki / "skills.md").exists():
            write_page(project, table(project))
    except Exception:
        pass
