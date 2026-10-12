"""The install step of `memcrumbs update`, made safe: it never leaves memcrumbs uninstalled without saying so.

pip can fail halfway (a file held open by antivirus or another process) and fail to put the old package back,
leaving the console script with no package behind it, which breaks the session hook in every wired repo. So after
any pip run, a new process checks that `python -m memcrumbs --version` still starts:

- it works: report the version that is installed;
- it does not: reinstall the version that was running (`memcrumbs==OLD`) and check again;
- that fails too: say plainly that memcrumbs is not installed, with the one command that fixes it.

The message gives pip's own `ERROR:` line (its last line is often only a hint), and pip's full output, redacted, is
kept in the first project's data folder as `update.log`. On Windows a permission failure is retried once after a
short pause. This module is imported before pip runs: once pip has removed the package, nothing can be imported.

On Windows, pip moves the old launchers (`memcrumbs.exe`, `memcrumb.exe`) into %TEMP% before it writes new ones.
When %TEMP% is on another drive than the Scripts folder, that move is a copy and a delete, and Windows refuses to
delete the launcher that is running `update`. So the launchers are first renamed within their own folder, which
Windows allows while one runs, and pip has nothing to move. Afterwards a launcher pip did not write again is renamed
back, and the replaced copies are deleted; the one still running is deleted by the next `update`."""
import csv
import os
import re
import subprocess
import sys
import sysconfig
import time
from pathlib import Path

from memcrumbs import __version__, writeset
from memcrumbs.redact import safe
from memcrumbs.util import clip, posix

RETRY_PAUSE = 5
PERMISSION = re.compile(r"(?i)WinError (5|32)\b|Errno 13|access is denied|permission denied|being used by another "
                        r"process|--user` option")


def windows():
    return sys.platform == "win32"


def run_installer(cmd, timeout=900):
    """(exit code, stdout and stderr) of one installer run; a tool that cannot start is a failure, not a crash."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "ERROR: %s could not run: %s" % (cmd[0], e)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def reason(output):
    """pip's own error line (it names the file or path that failed), not its last line, which is often a hint."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    errors = [ln for ln in lines if ln.startswith("ERROR:")]
    return clip(errors[0] if errors else (lines[-1] if lines else "no output"), 300)


def working():
    """The version `python -m memcrumbs --version` reports in a new process, or None when it does not start."""
    try:
        r = subprocess.run([sys.executable, "-m", "memcrumbs", "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"memcrumbs (\S+)", r.stdout or "")
    return m.group(1) if r.returncode == 0 and m else None


def restore_cmd(how, version):
    spec = "memcrumbs==%s" % version
    return {"pipx": ["pipx", "install", "--force", spec], "uv": ["uv", "tool", "install", "--force", spec]}.get(
        how, [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", spec])


def fix_cmd(how):
    return {"pipx": "pipx install --force memcrumbs", "uv": "uv tool install --force memcrumbs"}.get(
        how, '"%s" -m pip install --upgrade memcrumbs' % sys.executable)


def stash():
    """Folders pip left behind when it could not put the old package back: our names, '~' for the first letter."""
    site = Path(sysconfig.get_paths()["purelib"])
    try:
        return site, sorted(p.name for p in site.iterdir() if p.name.startswith("~") and
                            p.name[1:].lower().startswith("emcrumbs"))
    except OSError:
        return site, []


def _log(project, runs):
    if project is None:
        return ""
    text = "\n\n".join("$ %s\n(exit %d)\n%s" % (" ".join(cmd), code, output) for cmd, code, output in runs)
    path = project.data / "update.log"
    try:
        writeset.write_text(project, path, safe(project.redact, text) + "\n")
    except OSError:
        return ""
    return " pip's output: %s." % posix(path)


def launchers(site=None):
    """memcrumbs' own launchers, as its install record lists them: the files pip replaces in the Scripts folder.

    The record is read directly. importlib.metadata would scan sys.path, and under a launcher sys.path[0] is the
    launcher itself, a zip archive that the scan keeps open: then nothing can rename it."""
    site = Path(site) if site else Path(__file__).resolve().parent.parent
    try:
        with open(site / ("memcrumbs-%s.dist-info" % __version__) / "RECORD", encoding="utf-8", newline="") as f:
            rows = [row[0] for row in csv.reader(f) if row]
    except OSError:
        return []
    found = [(site / row).resolve() for row in rows if row.lower().endswith(".exe")]
    return [p for p in found if p.is_file()]


def aside(paths):
    """Rename each launcher within its folder, after deleting the copies an earlier update left. Returns the moves."""
    moved = []
    for p in paths:
        for old in p.parent.glob(p.name + ".old-*"):
            try:
                old.unlink()
            except OSError:
                pass                                # still running: the next update deletes it
        old = p.with_name("%s.old-%d" % (p.name, os.getpid()))
        try:
            os.replace(p, old)
        except OSError:
            continue
        moved.append((p, old))
    return moved


def settle(moved):
    """A launcher pip did not write again goes back; a replaced copy is deleted, unless it is the one running."""
    for p, old in moved:
        try:
            if p.exists():
                old.unlink()
            else:
                os.replace(old, p)
        except OSError:
            pass


def install(out, how, cmd, latest, project=None):
    """Run the upgrade, then check in a new process that memcrumbs starts. Returns the installed version; raises
    SystemExit, with what was checked, when the upgrade did not happen."""
    moved = aside(launchers()) if how == "pip" and windows() else []
    try:
        return _install(out, how, cmd, latest, project)
    finally:
        settle(moved)


def _install(out, how, cmd, latest, project):
    code, output = run_installer(cmd)
    runs = [(cmd, code, output)]
    if code and windows() and PERMISSION.search(output):
        out("pip failed (%s); trying once more in %d s" % (reason(output), RETRY_PAUSE))
        time.sleep(RETRY_PAUSE)                     # antivirus and indexers hold just-written files briefly
        code, output = run_installer(cmd)
        runs.append((cmd, code, output))
    now = working()
    if code == 0 and now == __version__ != latest:       # pip found nothing newer: its index lags a new release
        raise SystemExit("memcrumbs: pip found nothing newer than %s yet. PyPI can take a few minutes to serve a new "
                         "release (%s); nothing changed: run memcrumbs update again shortly.%s"
                         % (now, latest, _log(project, runs)))
    if code == 0 and now:
        _log(project, runs)
        return now
    why = "pip failed: %s" % reason(output) if code else "pip finished, but memcrumbs does not start"
    if now == latest:                               # an error after the new version was in place: it works
        out("%s; memcrumbs %s is installed and starts (checked)" % (why, now))
        _log(project, runs)
        return now
    if now:
        raise SystemExit("memcrumbs: the upgrade did not happen (%s). memcrumbs %s is still installed and starts "
                         "(checked).%s" % (why, now, _log(project, runs)))
    back = restore_cmd(how, __version__)
    rcode, routput = run_installer(back)
    runs.append((back, rcode, routput))
    again = working()
    where = _log(project, runs)
    site, left = stash()
    leftover = (" pip left %s in %s, its copy of the old files: delete them once memcrumbs starts, or pip warns about "
                "an invalid distribution." % (", ".join(left), posix(site))) if left else ""
    if again:
        raise SystemExit("memcrumbs: the upgrade did not happen (%s), and pip had left memcrumbs uninstalled. "
                         "memcrumbs %s was reinstalled and starts (checked).%s%s" % (why, again, where, leftover))
    raise SystemExit("memcrumbs: the upgrade did not happen (%s), and memcrumbs is NOT installed now: the session "
                     "hook in every wired repo fails until you run: %s%s%s" % (why, fix_cmd(how), where, leftover))
