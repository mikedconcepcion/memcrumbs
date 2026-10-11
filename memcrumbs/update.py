"""`memcrumbs update`: upgrade memcrumbs and redo what an upgrade needs, in one command.

memcrumbs makes no network calls of its own, with two exceptions the user chooses:
- `memcrumbs update` (and `update --check`) asks PyPI for the newest release, when you run it;
- `[update] notify = true` in a project's memcrumbs.toml lets the daily scan (which runs after slow commands such as
  `check` or `index`, never during a lookup or the session header) ask PyPI at most once a day. The session header
  then shows one line while a newer release exists.

An upgrade uses the tool that installed memcrumbs (pip, pipx or uv). Then, in a new process that runs the new code,
it re-indexes each project and refreshes, in each repo, the CLAUDE.md or AGENTS.md block, the skill and the allow
rules that `wire` installed there (only those; `--no-wire` skips it, and `wire --remove` still undoes it byte for
byte). An editable install or a development build is never upgraded. A failed install is checked, and undone
when it left memcrumbs uninstalled (`update_install`).

After an upgrade made by hand (`pip install --upgrade memcrumbs`, or `git pull` in a checkout), `memcrumbs update`
runs those same steps once: `wire` records the version that applied the wiring, and an older record means the
steps are still due. The header and `doctor` say so until they have run."""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from memcrumbs import __version__, update_install, writeset

INDEX = "https://pypi.org/pypi/memcrumbs/json"
CHANGELOG = "https://github.com/mikedconcepcion/memcrumbs/blob/main/CHANGELOG.md"
TIMEOUT, NOTIFY_TIMEOUT, DAY = 8, 3, 86400
_V = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(\.dev|a|b|rc)(\d+))?$")


def parse(v):
    """'0.2.1' -> (0, 2, 1, 4, 0). A pre-release sorts before its release: .dev < a < b < rc < final."""
    m = _V.match(str(v or "").strip())
    if not m:
        return None
    rank = {".dev": 0, "a": 1, "b": 2, "rc": 3, None: 4}[m.group(4)]
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), rank, int(m.group(5) or 0)


def newer(latest, current=__version__):
    a, b = parse(latest), parse(current)
    return bool(a and b and a > b)


def latest_release(timeout=TIMEOUT):
    """The newest release on PyPI. Raises OSError or ValueError (offline, a proxy, PyPI down, a bad answer)."""
    req = urllib.request.Request(INDEX, headers={"User-Agent": "memcrumbs/%s (update check)" % __version__,
                                                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        version = str(json.load(r)["info"]["version"])
    if not parse(version):
        raise ValueError("unexpected version %r" % version)
    return version


def installer():
    """(how this memcrumbs was installed, the command that upgrades it, or None when it must not be upgraded)."""
    import memcrumbs
    here = Path(memcrumbs.__file__).resolve().as_posix().lower()
    if "site-packages" not in here and "dist-packages" not in here:
        return "source checkout", None                  # editable or run from a clone: upgrade with git
    prefix = Path(sys.prefix).as_posix().lower()
    if "/pipx/" in prefix and shutil.which("pipx"):
        return "pipx", ["pipx", "upgrade", "memcrumbs"]
    if "/uv/tools/" in prefix and shutil.which("uv"):
        return "uv", ["uv", "tool", "upgrade", "memcrumbs"]
    return "pip", [sys.executable, "-m", "pip", "install", "--upgrade", "--disable-pip-version-check", "memcrumbs"]


# ---- the opt-in notice

def notify_on(project):
    from memcrumbs.markdown import truthy
    return truthy((project.cfg.get("update") or {}).get("notify"))


def _stored(project):
    try:
        return json.loads((project.data / "update.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def maybe_check(project):
    """With `[update] notify = true`: ask PyPI at most once a day, after a slow command. Never fails the command."""
    if not notify_on(project) or os.environ.get("MEMCRUMBS_NO_USAGE"):
        return
    st = _stored(project)
    if time.time() - float(st.get("checked") or 0) < DAY:
        return
    try:
        latest = latest_release(NOTIFY_TIMEOUT)
    except Exception:
        latest = st.get("latest")                       # offline: keep what was known, try again tomorrow
    try:
        writeset.write_text(project, project.data / "update.json", json.dumps({"checked": time.time(),
                                                                               "latest": latest}) + "\n")
    except OSError:
        pass


def header_line(project):
    """One line while a newer release is known (from the stored check; nothing is fetched here), or while an upgrade
    made by hand still has its steps to run."""
    done = unfinished(project)
    if done:
        return "memcrumbs was upgraded to %s; the wiring is from %s: run memcrumbs update to finish (index, wire)" % (
            __version__, done)
    if not notify_on(project):
        return ""
    latest = _stored(project).get("latest")
    return "memcrumbs %s is available (you have %s): memcrumbs update" % (latest, __version__) if newer(latest) else ""


def unfinished(project, thorough=False):
    """The version that last applied this project's wiring, when it is older than this one: an upgrade made by hand
    (pip, git) whose index and wire steps have not run. None when there is nothing to finish. The quick form reads
    one small file (the header uses it); `thorough` also looks in the repos for wiring the record does not list."""
    from memcrumbs.wire import _state
    st, _ = _state(project)
    if not st or not newer(__version__, st.get("version") or "0.0.0"):
        return None
    if st.get("created") or st.get("allow") or (thorough and wired(project)):
        return st.get("version") or "an earlier version"
    return None


# ---- after the upgrade: the steps an upgrade needs

def wired(project):
    """[(repo, targets, allow, user_skill)] for the repos `wire` installed into: found from its record and from
    the blocks, hook and allow rules it wrote."""
    from memcrumbs import claude_settings as cs, markdown
    from memcrumbs.util import read_text
    from memcrumbs.wire import BLOCKS, _state
    st, _ = _state(project)
    candidates = {Path(r) for r in project.repos}
    for f in (st or {}).get("created", []) + list(((st or {}).get("allow") or {}).keys()):
        p = Path(f)
        candidates.add(p.parent.parent if p.parent.name == ".claude" else
                       p.parents[3] if p.name == "SKILL.md" and len(p.parents) > 3 else p.parent)
    out, ours = [], set(cs.allow_rules(project))
    for repo in sorted(c for c in candidates if c.is_dir()):
        targets = []
        for target, (fname, block, _) in BLOCKS.items():
            f = repo / fname
            try:
                if f.exists() and markdown.find_block(read_text(f), block):
                    targets.append(target)
            except (OSError, ValueError):
                continue
        settings, allow = repo / ".claude" / "settings.json", False
        try:
            data = json.loads(read_text(settings)) if settings.exists() else {}
            allow = bool(ours & set(((data.get("permissions") or {}).get("allow")) or []))
            hooked = cs.has_hook(data)
        except (OSError, ValueError, AttributeError):
            hooked = False
        if targets or hooked:
            user_skill = not (repo / ".claude" / "skills" / "memcrumbs" / "SKILL.md").exists() and \
                (Path.home() / ".claude" / "skills" / "memcrumbs" / "SKILL.md").exists()
            out.append((repo, targets or ["claude"], allow, user_skill))
    return out


def _run(argv, timeout=900):
    """Run `python -m memcrumbs ARGS` in a new process, so the upgraded code does the work."""
    r = subprocess.run([sys.executable, "-m", "memcrumbs"] + argv, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout)
    tail = (r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or [""])[-1]
    return r.returncode, tail


def after_upgrade(out, projects, rewire=True):
    for project in projects:
        code, tail = _run(["-p", project.name, "index"])
        out("  %s: index %s" % (project.name, "ok" if code == 0 else "FAILED: " + tail))
        if not rewire:
            continue
        for repo, targets, allow, user_skill in wired(project):
            argv = ["-p", project.name, "wire", "--repo", str(repo), "--target", ",".join(targets), "--apply"]
            argv += (["--allow"] if allow else []) + (["--user-skill"] if user_skill else [])
            code, tail = _run(argv)
            out("  %s: wire %s · %s" % (project.name, repo.name, tail if code == 0 else "FAILED: " + tail))


def finish(out, projects, args):
    """Run the after-upgrade steps where an upgrade made by hand left them undone. Needs no network."""
    todo = [p for p in projects if unfinished(p, thorough=True)]
    out.set(finished=[p.name for p in todo])
    if todo:
        out("finishing the upgrade to %s: index and wire in %s" % (__version__, ", ".join(p.name for p in todo)))
        after_upgrade(out, todo, rewire=not args.no_wire)
    return todo


def command(out, args, projects):
    try:
        latest = latest_release()
    except (OSError, ValueError) as e:
        if not args.check:
            finish(out, projects, args)
        raise SystemExit("memcrumbs: could not reach PyPI (%s); try again later, or upgrade by hand: "
                         "pip install --upgrade memcrumbs, then memcrumbs update" % type(e).__name__)
    how, cmd = installer()
    out.set(current=__version__, latest=latest, newer=newer(latest), installer=how)
    if not newer(latest):
        dev = parse(__version__) and parse(__version__)[3] < 4
        out("memcrumbs %s is %s (newest release: %s)" % (__version__, "a development build" if dev else "up to date",
                                                        latest))
        if not args.check:
            finish(out, projects, args)
        elif any(unfinished(p, thorough=True) for p in projects):
            out("the upgrade to %s is not finished (index, wire): memcrumbs update" % __version__)
        return 0
    out("memcrumbs %s is available (you have %s). What changed: %s" % (latest, __version__, CHANGELOG))
    if args.check:
        out.hint("memcrumbs update")
        return 0
    if cmd is None:
        raise SystemExit("memcrumbs: this memcrumbs runs from a %s; upgrade it with git, then run "
                         "memcrumbs update to finish (index, wire)" % how)
    out("upgrading with %s …" % how)
    version = update_install.install(out, how, cmd, latest, projects[0] if projects else None)
    out("installed: memcrumbs %s (checked: it starts)" % version)
    after_upgrade(out, projects, rewire=not args.no_wire)
    out("done. Each project: memcrumbs doctor")
    return 0
