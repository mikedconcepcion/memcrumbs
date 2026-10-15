"""A skill used on a steady cadence is offered for scheduling; the owner decides; the operating system's scheduler
runs it; every run leaves its note, and a failed one shows in the header until the owner looks."""
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from memcrumbs import project as proj, schedule
from test_cli import ProjectCase, run

TODAY = dt.date(2026, 10, 15)                         # a Thursday


def days(*offsets):
    return [(TODAY - dt.timedelta(days=k)).isoformat() for k in offsets]


def skill(repo, name, description="x", script=None):
    d = repo / ".claude" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: %s\ndescription: %s\n---\n# %s\n" % (name, description, name),
                                encoding="utf-8")
    if script:
        (d / "run.py").write_text(script, encoding="utf-8")
    return d


class Cadence(ProjectCase):
    def test_steady_routines_and_what_is_not_one(self):
        c = (lambda ds: schedule.cadence(ds, TODAY))
        self.assertEqual(c(days(0, 1, 2, 3, 4)), "daily")
        weekdays = [d for d in days(*range(0, 15)) if dt.date.fromisoformat(d).weekday() < 5]
        self.assertEqual(c(weekdays), "weekdays")
        self.assertEqual(c(days(0, 7, 14, 21)), "weekly:thu")
        self.assertEqual(c(days(1, 4, 7, 10, 13)), "3d")
        self.assertIsNone(c(days(0, 1, 5, 6, 14)))                  # irregular
        self.assertIsNone(c(days(20, 21, 22, 23, 24)))              # it stopped
        self.assertIsNone(c(days(0, 1, 2)))                         # too few


class Schedules(ProjectCase):
    def setUp(self):
        super().setUp()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.patch = mock.patch.object(Path, "home", return_value=self.home)
        self.patch.start()
        journal = self.wiki / "journal"
        journal.mkdir()
        today = dt.date.today()
        lines = []
        for k in range(5):                                          # five days in a row, the notes the skills left
            day = (today - dt.timedelta(days=k)).isoformat()
            lines += ["- %s 09:00 skill nightly-report: report sent #skill" % day,
                      "- %s 09:05 skill deploy-site: deployed #skill" % day]
        (journal / ("%s.md" % today.strftime("%Y-%m"))).write_text("\n".join(lines) + "\n", encoding="utf-8")
        skill(self.repo, "nightly-report", "summarise the night's bookings")
        skill(self.repo, "deploy-site", "ship the site")

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_a_routine_is_offered_but_a_live_skill_never(self):
        found = json.loads(run(["-p", "t", "suggest", "--kind", "schedule", "--json"])[1])["suggestions"]
        self.assertEqual([s["why"].split(" is routine")[0] for s in found], ["the skill nightly-report"])
        shown = run(["-p", "t", "suggest", "show", found[0]["id"]])[1]
        self.assertIn("memcrumbs schedule add nightly-report --every daily --agent", shown)
        self.assertIn("spends tokens", shown)
        self.assertEqual(run(["-p", "t", "schedule", "add", "deploy-site", "--every", "daily"])[0], 1)

    def test_the_owner_decides_how_and_remove_takes_it_out(self):
        code, out = run(["-p", "t", "schedule", "add", "nightly-report"])
        self.assertEqual(code, 1)
        self.assertIn("spends tokens every time", out + self._err(["-p", "t", "schedule", "add", "nightly-report"]))
        out = run(["-p", "t", "schedule", "add", "nightly-report", "--agent", "--print", "--at", "07:30"])[1]
        self.assertIn("every day at 07:30", out)
        self.assertEqual(schedule.load(proj.resolve("t")), {})        # printed only: nothing recorded
        calls = []

        def fake(argv, **kw):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(schedule.sys, "platform", "win32"), mock.patch.object(schedule.subprocess, "run", fake):
            out = run(["-p", "t", "schedule", "add", "nightly-report", "--agent"])[1]
            self.assertIn("scheduled nightly-report: every day at 09:00", out)
            self.assertEqual(calls[0][:5], ["schtasks", "/Create", "/TN", "memcrumbs\\memcrumbs-t-nightly-report", "/TR"])
            self.assertIn("schedule run nightly-report", calls[0][5])
            self.assertEqual(calls[0][6:], ["/SC", "DAILY", "/ST", "09:00", "/F"])
            self.assertIn("nightly-report", schedule.load(proj.resolve("t")))
            self.assertEqual(json.loads(run(["-p", "t", "suggest", "--kind", "schedule", "--json"])[1])["suggestions"],
                             [])                                     # scheduled: no longer offered
            run(["-p", "t", "schedule", "remove", "nightly-report"])
            self.assertEqual(calls[-1], ["schtasks", "/Delete", "/TN", "memcrumbs\\memcrumbs-t-nightly-report", "/F"])
        self.assertEqual(schedule.load(proj.resolve("t")), {})

    def test_cron_gets_one_marked_line_and_loses_exactly_it(self):
        tab = ["0 5 * * * backup.sh"]

        def fake(argv, input=None, **kw):
            if argv == ["crontab", "-l"]:
                return subprocess.CompletedProcess(argv, 0, "\n".join(tab) + "\n", "")
            tab[:] = input.splitlines()
            return subprocess.CompletedProcess(argv, 0, "", "")
        with mock.patch.object(schedule.sys, "platform", "linux"), mock.patch.object(schedule.subprocess, "run", fake):
            run(["-p", "t", "schedule", "add", "nightly-report", "--agent", "--every", "weekly:mon", "--at", "06:15"])
            self.assertEqual(tab[0], "0 5 * * * backup.sh")
            self.assertTrue(tab[1].startswith("15 6 * * 1 "), tab)
            self.assertTrue(tab[1].endswith("schedule run nightly-report  # memcrumbs-t-nightly-report"), tab)
            run(["-p", "t", "schedule", "remove", "nightly-report"])
        self.assertEqual(tab, ["0 5 * * * backup.sh"])

    def test_a_run_leaves_its_note_and_a_failure_shows_until_the_owner_looks(self):
        skill(self.repo, "nightly-report", "summarise the night's bookings", script="import sys\nsys.exit(3)\n")
        with mock.patch.object(schedule.sys, "platform", "win32"), mock.patch.object(
                schedule.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", "")):
            run(["-p", "t", "schedule", "add", "nightly-report"])     # a script: no --agent needed
        self.assertEqual(run(["-p", "t", "schedule", "run", "nightly-report"])[0], 1)
        self.assertIn("scheduled run failed: nightly-report on", run(["-p", "t", "status"])[1])
        self.assertIn("skill nightly-report: scheduled run failed (exit 3)",
                      next((self.wiki / "journal").glob("*.md")).read_text(encoding="utf-8"))
        self.assertIn("FAILED (exit 3)", run(["-p", "t", "schedule"])[1])
        self.assertNotIn("scheduled run failed: ", run(["-p", "t", "status"])[1])   # the owner looked

    def test_add_and_remove_are_the_owners_decision_in_claude_code(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), mock.patch.object(sys, "argv", ["python", "-m"]):
            code, _ = run(["-p", "t", "schedule", "add", "nightly-report", "--agent", "--print"])
        self.assertEqual(code, 1)                                     # no ask rule names this form: refused

    def _err(self, argv):
        import contextlib
        import io
        from memcrumbs import cli
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            try:
                cli.main(argv)
            except SystemExit as e:
                return str(e.code)
        return err.getvalue()
