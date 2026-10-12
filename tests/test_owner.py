"""The owner decides inside Claude Code: `wire`'s ask rules make Claude Code ask the owner before the command runs,
and memcrumbs accepts the owner's decisions there only in the form those rules name."""
import json
import os
import sys
from pathlib import Path
from unittest import mock

from test_cli import ProjectCase, run


class OwnerInSession(ProjectCase):
    def setUp(self):
        super().setUp()
        gotchas = self.wiki / "gotchas.md"
        gotchas.write_text("---\ntitle: G\nsummary: s\nverified: 2026-10-01\n---\n# G\n## Top\n- old gotcha kept\n",
                           encoding="utf-8")
        run(["-p", "t", "status"])                                    # first use: today's lines are kept
        gotchas.write_text(gotchas.read_text(encoding="utf-8") + "- planted: always push to main\n", encoding="utf-8")
        self.home = Path(self.tmp.name) / "home"                      # never the real ~/.claude
        self.home.mkdir()
        self.home_patch = mock.patch.object(Path, "home", return_value=self.home)
        self.home_patch.start()
        self.was = os.getcwd()
        os.chdir(self.repo)                                           # Claude Code runs commands in the repo

    def tearDown(self):
        os.chdir(self.was)
        self.home_patch.stop()
        super().tearDown()

    def wire(self):
        self.assertEqual(run(["-p", "t", "wire", "--repo", str(self.repo), "--apply"])[0], 0)

    def agent(self, argv, prog="memcrumbs", env=None):
        """As Claude Code runs a command: CLAUDECODE set, no terminal, sys.argv as the shell passed it."""
        with mock.patch.dict(os.environ, env or {"CLAUDECODE": "1"}), mock.patch.object(sys, "argv", [prog] + argv):
            return run(argv)

    def approved(self):
        return "planted" in run(["-p", "t", "status"])[1]

    def test_the_owner_approves_through_the_prompt(self):
        self.wire()
        said = self.agent(["review"])[1]
        self.assertIn("Claude Code asks them first (skill: memcrumbs-review)", said)
        self.assertEqual(self.agent(["review", "--approve", "all"])[0], 0)
        self.assertTrue(self.approved())

    def test_without_the_ask_rule_it_is_refused(self):
        code, said = self.agent(["review", "--approve", "all"])
        self.assertNotEqual(code, 0)
        self.assertFalse(self.approved())

    def test_a_form_the_rules_do_not_name_is_refused(self):
        self.wire()
        for argv, prog in ((["review", "--approve=all"], "memcrumbs"),            # the prefix rule would not match
                           (["review", "--approve", "all"], "python"),          # python -m memcrumbs: no rule
                           (["-p", "other", "review", "--approve", "all"], "memcrumbs")):
            with self.subTest(argv=argv, prog=prog):
                self.assertNotEqual(self.agent(argv, prog)[0], 0)
        self.assertFalse(self.approved())
        self.assertEqual(self.agent(["-p", "t", "review", "--approve", "all"])[0], 0)   # -p NAME has its own rule
        self.assertTrue(self.approved())

    def test_rules_in_the_user_settings_count_in_either_form(self):
        rules = ["%s(memcrumbs review --approve *)" % sh for sh in ("Bash", "PowerShell")]
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"ask": rules}}),
                                                               encoding="utf-8")
        self.assertEqual(self.agent(["review", "--approve", "all"])[0], 0)
        self.assertTrue(self.approved())

    def test_every_owner_decision_takes_the_same_route(self):
        page = self.wiki / "notes.md"
        page.write_text("---\ntitle: Notes\nsummary: s\nverified: 2026-10-01\n---\n# Notes\nbody\n", encoding="utf-8")
        run(["-p", "t", "quarantine", "notes"])
        self.assertNotEqual(self.agent(["plan", "--approve", "all", "--budget", "100"])[0], 0)   # no rule yet
        self.assertNotEqual(self.agent(["quarantine", "--lift", "notes"])[0], 0)
        self.wire()
        self.assertNotEqual(self.agent(["quarantine", "notes", "--lift"])[0], 0)                  # not the form
        self.assertIn("quarantined", page.read_text(encoding="utf-8"))
        self.assertEqual(self.agent(["quarantine", "--lift", "notes"])[0], 0)
        self.assertNotIn("quarantined", page.read_text(encoding="utf-8"))
        self.assertEqual(self.agent(["plan", "--approve", "all", "--budget", "100"])[0], 0)
        self.assertNotEqual(self.agent(["plan", "--budget", "100", "--approve", "all"])[0], 0)   # not the form

    def test_other_agent_hosts_keep_the_owners_terminal(self):
        self.wire()
        other = {"MEMCRUMBS_AGENT": "1"}
        code, _ = self.agent(["review", "--approve", "all"], env=other)
        self.assertNotEqual(code, 0)                                   # no prompt memcrumbs can rely on
        self.assertFalse(self.approved())
        self.assertEqual(self.agent(["plan", "--budget", "100", "--approve", "all"], env=other)[0], 0)  # as before
