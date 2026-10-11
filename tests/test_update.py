"""`memcrumbs update`: version order, the PyPI check, the upgrade path, the opt-in notice, and no network otherwise."""
import contextlib
import io
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from memcrumbs import __version__, cli, project as proj, update, update_install, wire
from memcrumbs.output import Out
from test_cli import ProjectCase, run

REAL_RUN = subprocess.run
PIP = ["python", "-m", "pip", "install", "--upgrade", "memcrumbs"]


def pypi(version):
    return mock.patch.object(urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(
        {"info": {"version": version}}).encode()))


def no_network():
    return mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("network used"))


def recorder(calls, version="9.9.9"):
    """A fake subprocess.run: records the upgrade and the memcrumbs runs; git calls (project resolution) pass."""
    def fake(argv, **kw):
        if argv and argv[0] == "git":
            return REAL_RUN(argv, **kw)
        calls.append(list(argv))
        out = "memcrumbs %s\n" % version if "--version" in argv else "ok\n"
        return SimpleNamespace(returncode=0, stdout=out, stderr="")
    return fake


class Versions(ProjectCase):
    def test_order(self):
        order = ["0.2.0.dev8", "0.2.0", "0.2.1", "0.3.0a1", "0.3.0rc2", "0.3.0", "1.0.0"]
        self.assertEqual(sorted(order, key=update.parse), order)
        self.assertTrue(update.newer("0.2.1", "0.2.0"))
        self.assertFalse(update.newer("0.2.0", "0.2.0"))
        self.assertFalse(update.newer("not-a-version", "0.2.0"))

    def test_the_pypi_answer(self):
        with pypi("0.4.2"):
            self.assertEqual(update.latest_release(), "0.4.2")
        with pypi("<html>"), self.assertRaises(ValueError):
            update.latest_release()


class Command(ProjectCase):
    def test_check_says_what_is_newer(self):
        with pypi("9.9.9"):
            code, out = run(["update", "--check", "--json"])
        data = json.loads(out)
        self.assertEqual((data["latest"], data["newer"]), ("9.9.9", True))
        with pypi("0.0.1"):
            self.assertIn("newest release: 0.0.1", run(["update", "--check"])[1])

    def test_offline_is_a_clear_message(self):
        with mock.patch.object(urllib.request, "urlopen", side_effect=OSError("offline")):
            code, out = run(["update"])
        self.assertEqual(code, 1)

    def test_a_source_checkout_is_never_upgraded(self):
        calls = []
        with pypi("9.9.9"), mock.patch.object(update, "installer", return_value=("source checkout", None)), \
                mock.patch.object(update.subprocess, "run", side_effect=recorder(calls)):
            code, _ = run(["update"])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])

    def test_upgrade_then_index_and_refresh_what_wire_installed(self):
        p = proj.resolve("t")
        with mock.patch("sys.stdout", new=io.StringIO()):
            o = Out("wire", p)
            wire.wire(o, p, self.repo, apply=True, allow=True)
            o.close()
        self.assertEqual([(r.name, t, a) for r, t, a, _ in update.wired(p)], [(self.repo.name, ["claude"], True)])
        calls = []
        with pypi("9.9.9"), mock.patch.object(update, "installer", return_value=("pip", PIP)), \
                mock.patch.object(update.subprocess, "run", side_effect=recorder(calls)):
            code, out = run(["update"])
        self.assertEqual(code, 0, out)
        self.assertEqual(calls[0], PIP)                                                 # the upgrade first
        tails = [c[3:] for c in calls[1:]]                                               # then the new code runs
        self.assertIn(["--version"], tails)
        self.assertIn(["-p", "t", "index"], tails)
        rewire = [t for t in tails if "wire" in t]                                       # the repo as resolved: on
        self.assertEqual(len(rewire), 1, tails)                                          # macOS /var is /private/var,
        self.assertEqual(Path(rewire[0][4]).resolve(), self.repo.resolve())              # on Windows 8.3 names expand
        self.assertEqual(rewire[0][:4] + rewire[0][5:],
                         ["-p", "t", "wire", "--repo", "--target", "claude", "--apply", "--allow"])
        calls.clear()
        with pypi("9.9.9"), mock.patch.object(update, "installer", return_value=("pip", PIP)), \
                mock.patch.object(update.subprocess, "run", side_effect=recorder(calls)):
            run(["update", "--no-wire"])
        self.assertTrue(calls)
        self.assertFalse(any("wire" in c for c in calls))


class Finish(ProjectCase):
    """An upgrade made by hand (pip, git) has not run index and wire: `update` runs them once."""

    def wired_by(self, version):
        p = proj.resolve("t")
        with mock.patch("sys.stdout", new=io.StringIO()):
            o = Out("wire", p)
            wire.wire(o, p, self.repo, apply=True, allow=True)
            o.close()
        record = p.data / "wire.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data.pop("version")
        record.write_text(json.dumps(dict(data, **({"version": version} if version else {}))), encoding="utf-8")

    def update(self, argv=("update",), offline=False):
        calls = []
        net = mock.patch.object(urllib.request, "urlopen", side_effect=OSError("offline")) if offline else \
            pypi(update.__version__)
        with net, mock.patch.object(update.subprocess, "run", side_effect=recorder(calls)):
            code, out = run(list(argv))
        return code, out, [c[3:] for c in calls]

    def test_a_hand_upgrade_is_finished_once(self):
        self.wired_by(None)                                     # 0.2.0 wired it and kept no version
        self.assertIn("run memcrumbs update to finish (index, wire)", run(["-p", "t", "status"])[1])
        self.assertIn("the wiring is from an earlier version", run(["-p", "t", "doctor"])[1])
        _, out, calls = self.update(["update", "--check"])
        self.assertIn("is not finished (index, wire): memcrumbs update", out)
        self.assertEqual(calls, [])                             # --check only says so
        code, out, calls = self.update()
        self.assertEqual(code, 0, out)
        self.assertIn("finishing the upgrade to %s" % update.__version__, out)
        self.assertIn(["-p", "t", "index"], calls)
        self.assertEqual([c[2] for c in calls if len(c) > 2 and c[2] == "wire"], ["wire"])
        self.wired_by(update.__version__)                       # what that new wire run records
        _, out, calls = self.update()
        self.assertEqual(calls, [])                             # nothing left: nothing runs
        self.assertNotIn("to finish", run(["-p", "t", "status"])[1])

    def test_offline_still_finishes(self):
        self.wired_by("0.2.0")
        code, out, calls = self.update(offline=True)
        self.assertEqual(code, 1)                               # PyPI was not reached: said
        self.assertIn(["-p", "t", "index"], calls)              # but the local steps ran

    def test_a_newer_record_is_not_a_downgrade_to_finish(self):
        self.wired_by("99.0.0")
        self.assertIsNone(update.unfinished(proj.resolve("t"), thorough=True))


class SafeInstall(ProjectCase):
    """A failed pip run never leaves memcrumbs uninstalled without saying so, and says only what was checked."""
    DENIED = ("ERROR: Could not install packages due to an OSError: [WinError 5] Access is denied: "
              "'C:\\venv\\Lib\\site-packages\\memcrumbs\\cli.py'\n"
              "Consider using the `--user` option or check the permissions.\n")

    def update(self, pip=(1,), starts=(None,), restore=0, windows=False, launchers=(), seen=None):
        """pip's exit codes in turn; what `--version` reports in turn (None: memcrumbs does not start). An install
        that succeeds writes new `launchers`; `seen` collects what pip found in their folder when it ran."""
        calls, pips, versions = [], list(pip), list(starts)

        def pip_ran(code):
            if seen is not None and launchers:
                seen.append(sorted(f.name for f in launchers[0].parent.iterdir()))
            for f in launchers if code == 0 else ():
                f.write_bytes(b"new launcher")

        def fake(argv, **kw):
            if argv and argv[0] == "git":
                return REAL_RUN(argv, **kw)
            calls.append(list(argv))
            if "--version" in argv:
                v = versions.pop(0) if len(versions) > 1 else versions[0]
                return SimpleNamespace(returncode=0 if v else 1, stdout="memcrumbs %s\n" % v if v else "",
                                       stderr="" if v else "ModuleNotFoundError: No module named 'memcrumbs'\n")
            if any(a.startswith("memcrumbs==") for a in argv):
                pip_ran(restore)
                return SimpleNamespace(returncode=restore, stdout="",
                                       stderr="ERROR: No matching distribution\n" if restore else "")
            if argv[1:3] == ["-m", "memcrumbs"]:
                return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
            code = pips.pop(0) if len(pips) > 1 else pips[0]
            pip_ran(code)
            return SimpleNamespace(returncode=code, stdout="", stderr=self.DENIED if code else "")
        out, said, code = io.StringIO(), "", 0
        with pypi("9.9.9"), mock.patch.object(update, "installer", return_value=("pip", PIP)), \
                mock.patch.object(update.subprocess, "run", side_effect=fake), \
                mock.patch.object(update_install, "windows", return_value=windows), \
                mock.patch.object(update_install, "launchers", return_value=list(launchers)), \
                mock.patch.object(update_install.time, "sleep"), contextlib.redirect_stdout(out):
            try:
                cli.main(["update"])
            except SystemExit as e:
                code, said = (1 if e.code else 0), (e.code if isinstance(e.code, str) else "")
        return code, out.getvalue() + said, calls

    def test_left_uninstalled_the_running_version_is_put_back(self):
        code, said, calls = self.update(starts=(None, __version__))
        self.assertEqual(code, 1)
        self.assertIn("pip failed: ERROR: Could not install packages due to an OSError: [WinError 5] Access is denied",
                      said)                                       # pip's error, not its closing hint
        self.assertIn("pip had left memcrumbs uninstalled. memcrumbs %s was reinstalled and starts (checked)"
                      % __version__, said)
        self.assertNotIn("Nothing else was changed", said)
        self.assertIn([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                       "memcrumbs==" + __version__], calls)
        log = proj.resolve("t").data / "update.log"
        self.assertIn("Consider using the `--user` option", log.read_text(encoding="utf-8"))   # pip's whole output
        self.assertIn("pip's output: %s" % log.as_posix(), said)

    def test_when_nothing_can_be_put_back_it_says_so_plainly(self):
        code, said, _ = self.update(starts=(None,), restore=1)
        self.assertEqual(code, 1)
        self.assertIn("memcrumbs is NOT installed now: the session hook in every wired repo fails until you run: "
                      '"%s" -m pip install --upgrade memcrumbs' % sys.executable, said)

    def test_a_failure_that_left_the_old_version_is_said_as_checked(self):
        code, said, calls = self.update(starts=(__version__,))
        self.assertEqual(code, 1)
        self.assertIn("memcrumbs %s is still installed and starts (checked)" % __version__, said)
        self.assertFalse(any(a.startswith("memcrumbs==") for c in calls for a in c))     # nothing to put back

    def test_windows_retries_a_permission_failure_once(self):
        code, said, calls = self.update(pip=(1, 0), starts=("9.9.9",), windows=True)
        self.assertEqual(code, 0, said)
        self.assertEqual(calls.count(PIP), 2)
        self.assertIn("pip failed (ERROR: Could not install packages", said)
        self.assertIn("trying once more in", said)
        self.assertIn("installed: memcrumbs 9.9.9 (checked: it starts)", said)
        _, _, calls = self.update(pip=(1,), starts=(__version__,), windows=False)
        self.assertEqual(calls.count(PIP), 1)                     # elsewhere: no retry

    def scripts(self, *leftovers):
        """A Scripts folder with memcrumbs' two launchers, and copies an earlier update left."""
        folder = Path(self.tmp.name) / "Scripts"
        folder.mkdir()
        for name in ("memcrumbs.exe", "memcrumb.exe") + leftovers:
            (folder / name).write_bytes(b"old launcher")
        (folder / "other.exe").write_bytes(b"not ours")
        return folder, [folder / "memcrumbs.exe", folder / "memcrumb.exe"]

    def test_windows_moves_the_launchers_out_of_pips_way(self):
        folder, launchers = self.scripts("memcrumbs.exe.old-1")
        seen = []
        code, said, _ = self.update(pip=(0,), starts=("9.9.9",), windows=True, launchers=launchers, seen=seen)
        self.assertEqual(code, 0, said)
        self.assertEqual(len(seen), 1)
        self.assertFalse({"memcrumbs.exe", "memcrumb.exe"} & set(seen[0]))     # nothing for pip to move
        self.assertNotIn("memcrumbs.exe.old-1", seen[0])                       # an earlier copy is deleted first
        self.assertEqual(sorted(f.name for f in folder.iterdir()), ["memcrumb.exe", "memcrumbs.exe", "other.exe"])
        self.assertEqual(launchers[0].read_bytes(), b"new launcher")

    def test_a_launcher_pip_did_not_write_goes_back(self):
        folder, launchers = self.scripts()
        code, said, _ = self.update(pip=(1,), starts=(__version__,), windows=True, launchers=launchers)
        self.assertEqual(code, 1)
        self.assertIn("still installed and starts (checked)", said)
        self.assertEqual(sorted(f.name for f in folder.iterdir()), ["memcrumb.exe", "memcrumbs.exe", "other.exe"])
        self.assertEqual(launchers[0].read_bytes(), b"old launcher")           # the same file, renamed back

    def test_the_launchers_come_from_the_install_record(self):
        site = Path(self.tmp.name) / "venv" / "Lib" / "site-packages"
        info = site / ("memcrumbs-%s.dist-info" % __version__)
        info.mkdir(parents=True)
        (info / "RECORD").write_text("memcrumbs/__init__.py,sha256=x,1\n../../Scripts/memcrumbs.exe,sha256=x,1\n"
                                     "../../Scripts/memcrumb.exe,sha256=x,1\n", encoding="utf-8")
        scripts = site.parent.parent / "Scripts"
        scripts.mkdir()
        (scripts / "memcrumbs.exe").write_bytes(b"launcher")                  # memcrumb.exe is gone already
        self.assertEqual(update_install.launchers(site), [(scripts / "memcrumbs.exe").resolve()])
        self.assertEqual(update_install.launchers(Path(self.tmp.name) / "elsewhere"), [])

    def test_doctor_names_the_folders_a_failed_upgrade_left(self):
        site = Path(self.tmp.name) / "site-packages"
        (site / "~emcrumbs").mkdir(parents=True)
        (site / "~emcrumbs-0.4.0.dist-info").mkdir()
        (site / "memcrumbs").mkdir()
        with mock.patch.object(update_install.sysconfig, "get_paths", return_value={"purelib": str(site)}):
            said = run(["-p", "t", "doctor"])[1]
            shared = run(["-p", "t", "doctor", "--share"])[1]
        self.assertIn("a failed upgrade left ~emcrumbs, ~emcrumbs-0.4.0.dist-info in %s" % site.as_posix(), said)
        self.assertIn('"pip_stash": 2', shared)
        self.assertNotIn("~emcrumbs", shared)                                  # shape only: no names, no paths
        self.assertNotIn(site.name, shared)

    def test_elsewhere_the_launchers_stay_put(self):
        folder, launchers = self.scripts()
        seen = []
        self.update(pip=(0,), starts=("9.9.9",), windows=False, launchers=launchers, seen=seen)
        self.assertIn("memcrumbs.exe", seen[0])


class Notice(ProjectCase):
    def opt_in(self):
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[update]\nnotify = true\n", encoding="utf-8")

    def test_opted_in_the_header_shows_one_line(self):
        self.opt_in()
        with pypi("9.9.9"):
            run(["-p", "t", "check"])                       # a slow command: the daily check runs after it
        with no_network() as net:                           # the header and doctor only read what was stored
            self.assertIn("memcrumbs 9.9.9 is available", run(["-p", "t", "status"])[1])
            self.assertIn("memcrumbs 9.9.9 is available", run(["-p", "t", "doctor"])[1])
            run(["-p", "t", "check"])                       # checked today: no second call
        self.assertEqual(net.call_count, 0)

    def test_not_opted_in_nothing_touches_the_network(self):
        with no_network() as net:
            for argv in (["-p", "t", "check"], ["-p", "t", "status"], ["-p", "t", "find", "map"],
                         ["-p", "t", "doctor"], ["-p", "t", "index"]):
                run(argv)
            self.assertNotIn("is available", run(["-p", "t", "status"])[1])
        self.assertEqual(net.call_count, 0)
