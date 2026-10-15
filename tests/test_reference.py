"""The user's development reference (optional, once per machine) and the reflection on how the work goes."""
import datetime as dt
import json
import os
import subprocess
from pathlib import Path
from unittest import mock

from memcrumbs import project as proj, reference, reflect, setup_repo, transcripts
from test_cli import ProjectCase, run


class Reference(ProjectCase):
    def setUp(self):
        super().setUp()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.patch = mock.patch.object(Path, "home", return_value=self.home)
        self.patch.start()
        self.skill = self.home / ".claude" / "skills" / "dev-reference" / "SKILL.md"

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def init_lines(self):
        was = os.getcwd()
        os.chdir(self.repo)
        try:
            return run(["init", "--no-wire"])[1].strip().splitlines()
        finally:
            os.chdir(was)

    def test_asked_once_after_init_and_never_again_once_answered(self):
        lines = self.init_lines()
        self.assertTrue(lines[-2].startswith("development reference (optional, asked once per machine)"), lines)
        self.assertTrue(lines[-1].startswith("next:"), lines)
        run(["reference", "skip"])
        self.assertFalse(any("development reference" in ln for ln in self.init_lines()))
        self.assertFalse(self.skill.exists())

    def test_a_starter_is_copied_once_and_stays_the_users(self):
        out = run(["reference", "set", "agile"])[1]
        page = self.projects / "_reference" / "agile.md"
        self.assertIn("agile starter copied to", out)
        self.assertIn("Ship working software often", page.read_text(encoding="utf-8"))
        skill = self.skill.read_text(encoding="utf-8")
        self.assertIn("name: dev-reference", skill)
        self.assertIn(page.parent.as_posix(), skill)
        page.write_text("---\ntitle: mine\n---\n- Finish what I start before the next shiny thing.\n", encoding="utf-8")
        self.assertIn("kept at", run(["reference", "set", "agile"])[1])
        self.assertIn("shiny thing", page.read_text(encoding="utf-8"))           # never over an edited copy
        self.assertEqual(proj.all_projects()[0].name, "t")                       # not a project of its own
        run(["reference", "off"])
        self.assertFalse(self.skill.exists())
        self.assertTrue(page.exists())                                           # the folder stays

    def test_your_own_folder(self):
        mine = Path(self.tmp.name) / "my principles"
        mine.mkdir()
        self.assertEqual(run(["reference", "set", str(mine)])[0], 1)            # no markdown: refused
        (mine / "README.md").write_text("# How I work\n- Small steps, always tested.\n", encoding="utf-8")
        (mine / "notes").mkdir()
        (mine / "notes" / "testing.md").write_text("- Every bug gets a test first.\n", encoding="utf-8")
        run(["reference", "set", str(mine)])
        skill = self.skill.read_text(encoding="utf-8")
        self.assertIn("`README.md`, `notes/testing.md`", skill)
        self.assertEqual(reference.principles(mine), ["Small steps, always tested.", "Every bug gets a test first."])
        self.assertIn("reflection: off", run(["reference"])[1])

    def test_the_weekly_reminder_picks_what_the_counts_show(self):
        run(["reference", "set", "software"])
        today = dt.date(2026, 10, 15)
        p = proj.resolve("t")
        first = reference.header_line(p, today)
        self.assertTrue(first.startswith("your reference: "), first)
        self.assertEqual(reference.header_line(p, today + dt.timedelta(days=3)), "")   # once a week at most
        with mock.patch.object(reflect, "flags", return_value=["unfinished"]):
            line = reference.header_line(p, today + dt.timedelta(days=8))
        self.assertIn("(many projects are quiet and unfinished)", line)
        self.assertRegex(line.lower(), r"finish|done|start")
        st = reference.load()
        st["reminded"] = (dt.date.today() - dt.timedelta(days=8)).isoformat()
        reference.save(st)
        self.assertIn("your reference", run(["-p", "t", "status"])[1])           # the session header shows it
        self.assertNotIn("your reference", run(["-p", "t", "status"])[1])        # and not again this week

    def test_the_question_in_a_terminal(self):
        answers = iter(["3", "y"])
        out = setup_repo.Collect()
        with mock.patch("builtins.input", lambda *a: next(answers)), mock.patch("builtins.print"):
            reference.after_init(out, True)
        st = reference.load()
        self.assertEqual((st["answer"], st["starter"], st["reflect"]), ("starter", "agile", True))
        self.assertTrue(self.skill.exists())

    def test_setting_it_is_the_owners_decision_in_claude_code(self):
        import sys
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), mock.patch.object(sys, "argv", ["python"]):
            self.assertEqual(run(["reference", "set", "lean"])[0], 1)
        self.assertFalse(self.skill.exists())


class Reflection(ProjectCase):
    def setUp(self):
        super().setUp()
        self.home = Path(self.tmp.name) / "home"
        self.home.mkdir()
        self.patch = mock.patch.object(Path, "home", return_value=self.home)
        self.patch.start()
        git = ["git", "-C", str(self.repo)]
        subprocess.run(git + ["init", "-q"], check=True, capture_output=True)
        subprocess.run(git + ["-c", "user.name=a", "-c", "user.email=a@example.invalid", "add", "-A"], check=True,
                       capture_output=True)
        subprocess.run(git + ["-c", "user.name=a", "-c", "user.email=a@example.invalid", "commit", "-qm", "one"],
                       check=True, capture_output=True)
        (self.repo / "tests").mkdir()
        (self.wiki / "decisions").mkdir()
        (self.wiki / "decisions" / "a.md").write_text("---\ntitle: A\nstatus: draft\n---\n# A\n", encoding="utf-8")
        (self.wiki / "decisions" / "b.md").write_text("---\ntitle: B\nstatus: accepted\n---\n# B\n", encoding="utf-8")
        at = dt.date.today().isoformat() + "T10:00:00Z"
        folder = self.home / ".claude" / "projects" / transcripts.mangle(self.repo)
        folder.mkdir(parents=True)
        reply = {"type": "assistant", "timestamp": at, "sessionId": "s1", "message": {
            "id": "m1", "role": "assistant", "usage": {"input_tokens": 1500, "output_tokens": 300},
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}}]}}
        (folder / "s.jsonl").write_text(json.dumps(reply) + "\n", encoding="utf-8")

    def tearDown(self):
        self.patch.stop()
        super().tearDown()

    def test_off_until_the_owner_turns_it_on_then_counts_only(self):
        self.assertEqual(run(["reflect"])[0], 1)                               # off: nothing is read
        self.assertEqual(reflect.header_line(), "")
        run(["reference", "set", "lean"])
        run(["reference", "reflect", "on"])
        run(["-p", "t", "check"])                                               # the daily scan counts
        self.assertIn("a reflection on how the work goes is ready", run(["-p", "t", "status"])[1])
        out = run(["reflect"])[1]
        self.assertIn("- t: active · 1 commits in 4 weeks (0 the 4 before), last 0d ago", out)
        self.assertIn("tests, no CI, no release tags", out)
        self.assertIn("decisions 1 open / 1 decided", out)
        self.assertIn("1k tokens in, 300 out, 1 sessions, 1 tool calls", out)
        self.assertIn("pytest", json.dumps(transcripts.events(proj.resolve("t"), opted=True)))
        self.assertNotIn("pytest", out)                                         # counts, never commands
        self.assertNotIn("reflection on how the work goes is ready", run(["-p", "t", "status"])[1])   # read

    def test_a_project_can_opt_out(self):
        run(["reference", "reflect", "on"])
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[reference]\nreflect = false\n", encoding="utf-8")
        self.assertNotIn("- t:", run(["reflect"])[1])
