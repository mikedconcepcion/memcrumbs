"""Routine skills, scheduled on the owner's word.

- **Spotting a routine** (`cadence`): a skill of the repo used on at least 4 days at a steady interval (every day,
  every weekday, every week or every N days) is offered for scheduling: suggest kind `schedule`. Uses come from
  `skill_use`. A skill that pushes, publishes, deploys or touches live systems, or that only the owner may start
  (`disable-model-invocation: true`), is never offered and never scheduled: it would run with nobody watching.
- **The owner decides, and how.** `memcrumbs schedule add NAME --every daily|weekdays|weekly[:mon]|Nd --at HH:MM`
  creates the entry in the operating system's scheduler (Task Scheduler on Windows, cron elsewhere); `--print` only
  prints the command, for the owner to run by hand. Claude Code asks the owner before `add` and `remove` (ask
  rules from `wire`). `memcrumbs schedule remove NAME` deletes the entry.
- **What runs** is `memcrumbs schedule run NAME`. A skill with its own script (`run.py`, `run.ps1`, `run.sh` or
  `run.cmd` in its folder) runs that script and spends no tokens. Otherwise each run is a headless Claude Code
  session (`claude -p`), which spends tokens every time: `add` needs `--agent` to accept that.
- **Every run leaves its note** (`memcrumbs skills` counts it). A failed run shows in the header until the owner
  looks (`memcrumbs schedule`).

memcrumbs itself runs nothing in the background: the operating system's scheduler starts each run. The record of
what was scheduled is `schedules.json` in the project folder (not the index cache), so `remove` can always find it."""
import datetime as dt
import json
import re
import shlex
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

from memcrumbs import markdown, writeset
from memcrumbs.util import read_text

MIN_USES = 4
SCRIPTS = ("run.py", "run.ps1", "run.sh", "run.cmd")
EVERY = re.compile(r"^(daily|weekdays|weekly(?::(mon|tue|wed|thu|fri|sat|sun))?|([2-9]|[1-2]\d|30)d)$")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
AT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TIMEOUT = 3600


def cadence(days, today=None):
    """The `--every` value a steady run of use days shows ('daily', 'weekdays', 'weekly:mon', '3d'), or None. The
    last use must be recent: a routine that stopped is not offered."""
    today = today or dt.date.today()
    ds = sorted({dt.date.fromisoformat(d) for d in days})
    if len(ds) < MIN_USES:
        return None
    gaps = [(b - a).days for a, b in zip(ds, ds[1:])]
    m = statistics.median(gaps)
    if (today - ds[-1]).days > 2 * max(m, 1) + 1:
        return None
    if all(d.weekday() < 5 for d in ds) and max(gaps) <= 3 and m == 1 and 3 in gaps:
        return "weekdays"                                    # every working day, the weekend off
    if any(abs(g - m) > max(1, round(0.25 * m)) for g in gaps):
        return None
    n = round(m)
    if n == 1:
        return "daily"
    if n == 7:
        return "weekly:" + DAYS[statistics.mode(d.weekday() for d in ds)]
    return "%dd" % n if 2 <= n <= 30 else None


def describe(every):
    if every == "daily":
        return "every day"
    if every == "weekdays":
        return "every weekday"
    if every.startswith("weekly"):
        return "every week" + (" on " + every.split(":")[1].capitalize() if ":" in every else "")
    return "every %s days" % every[:-1]


def _skill_dir(project, name):
    for r in project.repos:
        d = Path(r) / ".claude" / "skills" / name
        if (d / "SKILL.md").is_file():
            return d
    return None


def live(skill_dir):
    """A skill that only the owner may start, or whose name or description says it pushes, publishes, deploys or
    touches live systems."""
    from memcrumbs.suggest_skill import LIVE, LIVE_WORDS
    meta = markdown.frontmatter(read_text(skill_dir / "SKILL.md"))[0]
    said = "%s %s" % (skill_dir.name, meta.get("description") or "")
    return markdown.truthy(meta.get("disable-model-invocation")) or bool(LIVE.search(said) or LIVE_WORDS.search(said))


def _script(skill_dir):
    return next((skill_dir / s for s in SCRIPTS if (skill_dir / s).is_file()), None)


def _path(project):
    return project.dir / "schedules.json"


def load(project):
    try:
        data = json.loads(read_text(_path(project)))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(project, data):
    p = _path(project)
    writeset.write_text(project, p, json.dumps(data, indent=1, sort_keys=True) + "\n", extra=[p])


def _entry(project, name):
    return "memcrumbs-%s-%s" % (project.name, name)


def _runner(project, name):
    return [sys.executable, "-m", "memcrumbs", "-p", project.name, "schedule", "run", name]


def os_add(project, name, every, at):
    """(argv to run, or None for cron, and the text to show). Windows: schtasks; elsewhere: one crontab line."""
    hour, minute = at.split(":")
    if sys.platform == "win32":
        when = (["/SC", "DAILY"] if every == "daily" else
                ["/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI"] if every == "weekdays" else
                ["/SC", "WEEKLY", "/D", (every.split(":")[1] if ":" in every else "mon").upper()]
                if every.startswith("weekly") else ["/SC", "DAILY", "/MO", every[:-1]])
        tr = subprocess.list2cmdline(_runner(project, name))
        argv = ["schtasks", "/Create", "/TN", "memcrumbs\\" + _entry(project, name), "/TR", tr] + when + [
            "/ST", at, "/F"]
        return argv, subprocess.list2cmdline(argv)
    dow = {"daily": "*", "weekdays": "1-5"}.get(every)
    if dow is None and every.startswith("weekly"):
        dow = str((DAYS.index(every.split(":")[1]) + 1) % 7) if ":" in every else "1"
    dom = "*/%s" % every[:-1] if every.endswith("d") else "*"
    line = "%d %d %s * %s %s  # %s" % (int(minute), int(hour), dom, dow or "*",
                                       " ".join(shlex.quote(a) for a in _runner(project, name)), _entry(project, name))
    return None, line


def _crontab(edit):
    """Rewrite the user's crontab through `crontab -`: edit(lines) -> lines."""
    got = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    lines = got.stdout.splitlines() if got.returncode == 0 else []
    new = edit(lines)
    done = subprocess.run(["crontab", "-"], input="\n".join(new) + ("\n" if new else ""), capture_output=True, text=True)
    if done.returncode:
        raise SystemExit("memcrumbs: crontab refused the change: %s" % (done.stderr.strip() or done.returncode))


def add(out, project, name, every=None, at="09:00", agent=False, print_only=False):
    d = _skill_dir(project, name)
    if d is None:
        raise SystemExit("memcrumbs: no skill %s in the repo's .claude/skills" % name)
    if live(d):
        raise SystemExit("memcrumbs: %s pushes, publishes, deploys or is owner-only: it is never scheduled, since it "
                         "would run with nobody watching" % name)
    if every is None:
        from memcrumbs import skill_use
        every = cadence(skill_use.uses(project).get(name, []))
        if every is None:
            raise SystemExit("memcrumbs: no steady routine seen for %s; say when: --every daily|weekdays|weekly[:mon]|Nd"
                             % name)
    if not EVERY.match(every) or not AT.match(at):
        raise SystemExit("memcrumbs: --every daily|weekdays|weekly[:mon]|Nd (2-30) and --at HH:MM")
    script = _script(d)
    if script is None and not agent:
        raise SystemExit("memcrumbs: %s has no run script (%s), so each run would be a Claude Code session that "
                         "spends tokens every time. Add --agent to accept that, or add a script to the skill's folder"
                         % (name, ", ".join(SCRIPTS)))
    argv, shown = os_add(project, name, every, at)
    how = "script %s" % script.name if script else "a Claude Code session (spends tokens on every run)"
    out.set(skill=name, every=every, at=at, runs=how, command=shown)
    if print_only:
        out("to schedule %s (%s at %s; runs %s), run:" % (name, describe(every), at, how))
        out("  " + shown if argv else "  crontab -e, and add the line:\n  " + shown)
        return
    if argv:
        done = subprocess.run(argv, capture_output=True, text=True)
        if done.returncode:
            raise SystemExit("memcrumbs: the scheduler refused: %s" % (done.stderr.strip() or done.stdout.strip()))
    else:
        tag = "# " + _entry(project, name)
        _crontab(lambda lines: [ln for ln in lines if not ln.endswith(tag)] + [shown])
    data = load(project)
    data[name] = dict(every=every, at=at, how="script" if script else "agent", entry=_entry(project, name),
                      system="schtasks" if argv else "cron", added=dt.date.today().isoformat())
    _save(project, data)
    out("scheduled %s: %s at %s, runs %s. Remove: memcrumbs schedule remove %s" % (name, describe(every), at, how, name))


def remove(out, project, name):
    data = load(project)
    rec = data.get(name)
    if rec is None:
        raise SystemExit("memcrumbs: %s is not scheduled by memcrumbs (memcrumbs schedule lists them)" % name)
    if rec.get("system") == "schtasks":
        done = subprocess.run(["schtasks", "/Delete", "/TN", "memcrumbs\\" + rec["entry"], "/F"],
                              capture_output=True, text=True)
        if done.returncode and "cannot find" not in (done.stderr + done.stdout).lower():
            raise SystemExit("memcrumbs: the scheduler refused: %s" % (done.stderr.strip() or done.stdout.strip()))
    else:
        tag = "# " + rec["entry"]
        _crontab(lambda lines: [ln for ln in lines if not ln.endswith(tag)])
    del data[name]
    _save(project, data)
    out("removed the schedule of %s" % name)


def run(out, project, name):
    """What the scheduler starts: the skill's script, or a headless Claude Code session; the outcome is recorded
    and leaves the skill's note."""
    from memcrumbs import cmd_write
    d = _skill_dir(project, name)
    rec = load(project).get(name, {})
    cwd = project.repos[0] if project.repos else project.dir
    script = _script(d) if d else None
    if d is None:
        argv = None
    elif script is not None:
        argv = ([sys.executable, str(script)] if script.suffix == ".py" else
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
                if script.suffix == ".ps1" else ["sh", str(script)] if script.suffix == ".sh" else
                ["cmd", "/c", str(script)])
    elif rec.get("how") == "agent" and shutil.which("claude"):
        argv = [shutil.which("claude"), "-p", "Use the %s skill. When it is done, leave its one-line note as the skill "
                                              "says." % name]
    else:
        argv = None
    try:
        code = subprocess.run(argv, cwd=str(cwd), timeout=TIMEOUT).returncode if argv else 127
    except (OSError, subprocess.TimeoutExpired):
        code = 124
    data = load(project)
    if name in data:
        data[name]["last"] = dict(at=dt.datetime.now().isoformat(timespec="minutes"), ok=code == 0, code=code,
                                  seen=code == 0)
        _save(project, data)
    cmd_write.log(out, project, "scheduled run %s (exit %d)" % ("ok" if code == 0 else "failed", code), skill=name)
    return 0 if code == 0 else 1


def show(out, project):
    data = load(project)
    out.list_key = "schedules"
    out.set(schedules=data)
    if not data:
        out("nothing scheduled by memcrumbs")
        return
    for name, rec in sorted(data.items()):
        last = rec.get("last") or {}
        out("%s: %s at %s, %s%s" % (name, describe(rec["every"]), rec["at"], "script" if rec["how"] == "script"
                                    else "Claude Code session (tokens)", " · last %s %s" % (
                                        last["at"], "ok" if last.get("ok") else "FAILED (exit %s)" % last.get("code"))
                                    if last else " · not run yet"))
    unseen = [r["last"] for r in data.values() if r.get("last") and not r["last"].get("seen")]
    for last in unseen:
        last["seen"] = True                             # the owner looked: the header stops saying it
    if unseen:
        _save(project, data)


def header_line(project):
    """One line while a scheduled run failed and nobody has looked."""
    try:
        failed = [(n, r["last"]) for n, r in load(project).items()
                  if r.get("last") and not r["last"].get("ok") and not r["last"].get("seen")]
    except (AttributeError, KeyError, TypeError):
        return ""
    if not failed:
        return ""
    return "scheduled run failed: %s — memcrumbs schedule" % ", ".join(
        "%s on %s (exit %s)" % (n, last["at"][:10], last.get("code")) for n, last in failed[:3])


def _offers(project, cheap_only=False):
    from memcrumbs import skill_use
    from memcrumbs.suggest import Suggestion
    have, out = load(project), []
    for name, days in skill_use.uses(project).items():
        d = _skill_dir(project, name)
        if d is None or name in have or live(d):
            continue
        every = cadence(days)
        if every is None:
            continue
        script = _script(d)
        out.append(Suggestion(
            "schedule", "schedule|" + name, "the skill %s is routine: used on %d days, %s (last %s)" % (
                name, len(set(days)), describe(every), days[-1]),
            "schedule it %s, if the owner wants (the operating system's scheduler runs it; memcrumbs runs nothing in "
            "the background)" % describe(every),
            ["runs: %s" % ("its script %s, no tokens" % script.name if script else
                           "a Claude Code session on every run, which spends tokens"),
             "remove at any time: memcrumbs schedule remove %s" % name],
            risk="writes-outside-wiki", score=len(days),
            agent="on the owner's yes: memcrumbs schedule add %s --every %s%s (or --print, for the owner to run it by "
                  "hand)" % (name, every, "" if script else " --agent")))
    return out


SUGGESTERS = {"schedule": _offers}

