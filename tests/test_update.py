"""`memcrumbs update`: version order, the PyPI check, the upgrade path, the opt-in notice, and no network otherwise."""
import io
import json
import subprocess
import urllib.request
from types import SimpleNamespace
from unittest import mock

from memcrumbs import project as proj, update, wire
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
        self.assertIn(["-p", "t", "wire", "--repo", str(self.repo), "--target", "claude", "--apply", "--allow"], tails)
        calls.clear()
        with pypi("9.9.9"), mock.patch.object(update, "installer", return_value=("pip", PIP)), \
                mock.patch.object(update.subprocess, "run", side_effect=recorder(calls)):
            run(["update", "--no-wire"])
        self.assertTrue(calls)
        self.assertFalse(any("wire" in c for c in calls))


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
