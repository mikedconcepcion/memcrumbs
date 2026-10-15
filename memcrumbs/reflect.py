"""How the work goes, counted across the user's projects: `memcrumbs reflect` (opt-in, machine-wide).

Counts only, no text: per project, the days since the last commit and the commits of the last four weeks against
the four before, whether there are tests, CI and release tags, the wiki's open and decided decisions, and from
Claude Code's transcripts the tokens, sessions and tool calls of the last four weeks. A project opts out with
`[reference] reflect = false` in its memcrumbs.toml. Nothing is counted until the owner turned the reflection on
(`memcrumbs reference reflect on`, or the question after `init`).

memcrumbs makes no model call. The daily scan refreshes the counts at most once a week; the header then says a
reflection is ready (at most every 30 days), and the agent reads it only on the owner's word, since reading it
costs tokens. The reading is the user's own session: next to the user's development reference, it says where the
numbers and the stated principles disagree. The counts are shown to the user; they never become instructions for
the agent, which would copy bad habits too."""
import datetime as dt
import json
import subprocess
import time
from pathlib import Path

from memcrumbs import markdown, project as proj, transcripts
from memcrumbs.util import read_text

WEEKS = 4
REFRESH_DAYS = 7
READ_DAYS = 30
OPEN = ("draft", "proposed", "parked", "open")
DECIDED = ("accepted", "rejected", "superseded")


def _path():
    return proj.projects_dir() / ".memcrumbs-reflect.json"


def enabled():
    from memcrumbs import reference
    return bool(reference.load().get("reflect"))


def _git(repo, *args):
    try:
        r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def project_counts(p, now=None):
    now = now or time.time()
    days = WEEKS * 7
    row = dict(name=p.name)
    repo = Path(p.repos[0]) if p.repos else None
    last = _git(repo, "log", "-1", "--format=%ct") if repo else None
    if last:
        row["days_since_commit"] = int((now - int(last)) // 86400)
        row["commits"] = int(_git(repo, "rev-list", "--count", "--since=%d.days" % days, "HEAD") or 0)
        row["commits_before"] = int(_git(repo, "rev-list", "--count", "--since=%d.days" % (2 * days),
                                         "--until=%d.days" % days, "HEAD") or 0)
        row["tags"] = len((_git(repo, "tag", "--list") or "").split())
    if repo:
        row["tests"] = any((repo / d).is_dir() for d in ("tests", "test", "spec", "__tests__"))
        row["ci"] = (repo / ".github" / "workflows").is_dir() or (repo / ".gitlab-ci.yml").exists()
    opened = decided = 0
    folder = p.wiki / "decisions"
    for f in folder.glob("*.md") if folder.is_dir() else []:
        status = str(markdown.frontmatter(read_text(f))[0].get("status") or "").lower()
        opened += status in OPEN or not status
        decided += status in DECIDED
    row.update(decisions_open=opened, decisions_decided=decided)
    evs = transcripts.events(p, days, opted=True)
    if evs:
        tin = tout = cached = 0
        for _, _, kind, val in evs:
            if kind == "tokens":
                a, b, c = (val.split(",") + ["0", "0"])[:3]
                tin, tout, cached = tin + int(a or 0), tout + int(b or 0), cached + int(c or 0)
        row.update(tokens_in=tin, tokens_out=tout, tokens_cached=cached, sessions=len({s for _, s, _, _ in evs}),
                   tool_calls=sum(1 for e in evs if e[2] in ("cmd", "read", "edit", "skill")))
    row["stage"] = _stage(row)
    return row


def _stage(row):
    d = row.get("days_since_commit")
    if d is None:
        return "no git"
    return "active" if d <= 14 else "quiet" if d <= 60 else "stale"


def flags_of(rows):
    """What the counts show, for the reminder: many quiet unfinished projects; most projects with tests and no
    release tag (a release may live elsewhere: another repo, a package index, a deploy, so this is a hint)."""
    out, real = [], [r for r in rows if r["stage"] != "no git"]
    if real and sum(1 for r in real if r["stage"] != "active") * 2 >= len(real) and len(real) >= 2:
        out.append("unfinished")
    if real and sum(1 for r in real if r.get("tests") and not r.get("tags")) * 2 > len(real):
        out.append("unreleased")
    return out


def summary(now=None):
    rows = [project_counts(p, now) for p in proj.all_projects()
            if (p.cfg.get("reference") or {}).get("reflect", True) is not False]
    data = dict(at=dt.date.today().isoformat(), projects=rows, flags=flags_of(rows))
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)
    return data


def stored():
    try:
        data = json.loads(read_text(_path()))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def flags():
    return stored().get("flags", []) if enabled() else []


def maybe_refresh():
    """The daily scan: refresh the counts at most once a week, only when the owner turned the reflection on."""
    try:
        if not enabled():
            return
        at = stored().get("at")
        if not at or (dt.date.today() - dt.date.fromisoformat(at)).days >= REFRESH_DAYS:
            summary()
    except Exception:
        pass


def _tok(n):
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%dk" % (n // 1000) if n >= 1000 else str(n)


def line(r):
    bits = [r["name"] + ": " + r["stage"]]
    if "commits" in r:
        bits.append("%d commits in %d weeks (%d the %d before), last %dd ago" % (
            r["commits"], WEEKS, r["commits_before"], WEEKS, r["days_since_commit"]))
    if "tests" in r:
        bits.append(", ".join(x for x in ("tests" if r["tests"] else "no tests", "CI" if r.get("ci") else "no CI",
                                         "%d release tags" % r["tags"] if r.get("tags") else "no release tags")))
    if r["decisions_open"] or r["decisions_decided"]:
        bits.append("decisions %d open / %d decided" % (r["decisions_open"], r["decisions_decided"]))
    if "tokens_in" in r:
        bits.append("%s tokens in%s, %s out, %d sessions, %d tool calls" % (
            _tok(r["tokens_in"]), " (+%s cache reads)" % _tok(r["tokens_cached"]) if r.get("tokens_cached") else "",
            _tok(r["tokens_out"]), r["sessions"], r["tool_calls"]))
    return " · ".join(bits)


def command(out):
    from memcrumbs import reference
    if not enabled():
        raise SystemExit("memcrumbs: the reflection is off; the owner turns it on with: memcrumbs reference reflect on")
    data = summary()
    rows = data["projects"]
    out.list_key = "projects"
    out.set(**data)
    out("how the work goes, last %d weeks (counts only, %d projects):" % (WEEKS, len(rows)))
    for r in rows:
        out("- " + line(r))
    stages = {s: sum(1 for r in rows if r["stage"] == s) for s in ("active", "quiet", "stale", "no git")}
    out("stages: %s" % ", ".join("%d %s" % (n, s) for s, n in stages.items() if n))
    if data["flags"]:
        out("the counts show: %s" % ", ".join({"unfinished": "many projects quiet or stale",
                                               "unreleased": "most projects with tests have no release tag"}[f]
                                              for f in data["flags"]))
    st = reference.load()
    if st.get("folder"):
        out("read these next to the development reference (%s): where do the numbers and the stated principles "
            "disagree, and what is one thing to change?" % st["folder"])
    st["reflected"] = dt.date.today().isoformat()
    reference.save(st)


def header_line(today=None):
    """One line when a reflection is ready and none was read in 30 days."""
    today = today or dt.date.today()
    try:
        if not enabled() or not stored().get("at"):
            return ""
        from memcrumbs import reference
        last = reference.load().get("reflected")
        if last and (today - dt.date.fromisoformat(last)).days < READ_DAYS:
            return ""
        return ("a reflection on how the work goes is ready: memcrumbs reflect (reading it costs tokens: tell the "
                "owner; run it only on their word)")
    except Exception:
        return ""
