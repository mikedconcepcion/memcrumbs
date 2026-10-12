"""wire / wire --remove: every file comes back byte for byte, and nothing outside the declared files is touched
(write set enforced, `wire --remove` restores files byte for byte)."""
import contextlib
import io
import itertools
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memcrumbs import project as proj, wire
from memcrumbs.output import Out

CLAUDE = {"absent": None, "empty": b"", "plain": b"# Repo\nhand notes\n", "no-newline": b"# Repo\nhand notes",
          "crlf-bom": b"\xef\xbb\xbf# Repo\r\nnotes  \r\n\r\n", "has-other-block":
          b"a\n<!-- memcrumbs:gen other -->\nx\n<!-- memcrumbs:end -->\nb\n"}
SETTINGS = {"absent": None, "empty-object": b"{}\n", "compact": b'{"model":"x"}',
            "pretty": b'{\n  "permissions": {\n    "allow": ["Bash(ls)"]\n  },\n  "env": {"A": "\\u00e9"}\n}\n',
            "hooks-no-sessionstart": b'{\r\n  "hooks": {\r\n    "Stop": []\r\n  }\r\n}\r\n',
            "sessionstart-list": b'{"hooks": {"SessionStart": [{"matcher": "startup", "hooks": []}]}}\n',
            "empty-sessionstart": b'{"hooks": {"SessionStart": []}}\n'}


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class WireRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        projects = root / "projects"
        (projects / "t" / "wiki").mkdir(parents=True)
        (projects / "t" / "memcrumbs.toml").write_text('name = "t"\n', encoding="utf-8")
        self.root = root
        self.env = mock.patch.dict(os.environ, {"MEMCRUMBS_PROJECTS": str(projects)})
        self.env.start()
        self.project = proj.resolve("t")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def run_wire(self, repo, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            out = Out("wire", self.project)
            wire.wire(out, self.project, repo, apply=True, **kw)
            out.close()

    def test_round_trip_is_byte_exact(self):
        for (cname, cbytes), (sname, sbytes), targets, allow in itertools.product(
                CLAUDE.items(), SETTINGS.items(), (("claude",), ("claude", "agents")), (False, True)):
            with self.subTest(claude=cname, settings=sname, targets=targets, allow=allow):
                repo = self.root / ("repo-%s-%s-%d-%d" % (cname, sname, len(targets), allow))
                repo.mkdir()
                (repo / "src.py").write_bytes(b"x = 1\n")
                if cbytes is not None:
                    (repo / "CLAUDE.md").write_bytes(cbytes)
                if sbytes is not None:
                    (repo / ".claude").mkdir()
                    (repo / ".claude" / "settings.json").write_bytes(sbytes)
                before = snapshot(repo)
                self.run_wire(repo, targets=targets, allow=allow)
                wired = snapshot(repo)
                settings = json.loads(wired[".claude/settings.json"])
                hooks = settings["hooks"]["SessionStart"]
                self.assertEqual(sum(h["command"].startswith("memcrumbs ") for e in hooks for h in e["hooks"]), 1)
                rules = (settings.get("permissions") or {}).get("allow") or []
                self.assertEqual("PowerShell(memcrumbs -p t find:*)" in rules, allow)
                self.assertFalse(any(" log" in r or " verify" in r or " wire" in r for r in rules))
                asks = settings["permissions"]["ask"]                         # always: the owner's decisions
                self.assertIn("Bash(memcrumbs review --approve:*)", asks)
                self.assertIn("PowerShell(memcrumbs -p t suggest apply:*)", asks)
                self.assertFalse(set(asks) & set(rules))
                self.assertIn(b"memcrumbs:gen claude", wired["CLAUDE.md"])
                self.assertEqual(set(wired) - set(before) - {"CLAUDE.md", "AGENTS.md", ".claude/settings.json",
                                                             ".claude/skills/memcrumbs/SKILL.md",
                                                             ".claude/skills/memcrumbs-review/SKILL.md"}, set())
                self.run_wire(repo, targets=targets, allow=allow)             # idempotent
                self.assertEqual(snapshot(repo), wired)
                self.run_wire(repo, targets=targets, remove=True)
                self.assertEqual(snapshot(repo), before)
                self.assertEqual(sorted(p.name for p in repo.iterdir()), sorted(
                    {"src.py"} | ({"CLAUDE.md"} if cbytes is not None else set()) | ({".claude"} if sbytes is not None else set())))

    def test_allow_added_later_and_partial_rules(self):
        repo = self.root / "later"
        (repo / ".claude").mkdir(parents=True)
        original = b'{\n  "permissions": {\n    "allow": [\n      "Bash(memcrumbs find:*)",\n      "Bash(ls:*)"\n    ]\n  }\n}\n'
        (repo / ".claude" / "settings.json").write_bytes(original)
        self.run_wire(repo)                                            # hook first, no rules
        self.run_wire(repo, allow=True)                                # rules in a later run; one already there
        rules = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
        self.assertEqual(rules.count("Bash(memcrumbs find:*)"), 1)
        self.assertIn("Bash(ls:*)", rules)
        self.run_wire(repo, remove=True)
        self.assertEqual((repo / ".claude" / "settings.json").read_bytes(), original)

    def test_wiring_from_before_the_ask_rules_is_completed_and_still_removed_exactly(self):
        """A repo wired by a version without the ask rules and the review skill: the next wire adds them, and
        --remove still gives back every file byte for byte."""
        from memcrumbs import claude_settings as cs
        for (sname, sbytes), allow in itertools.product(SETTINGS.items(), (False, True)):
            with self.subTest(settings=sname, allow=allow):
                repo = self.root / ("older-%s-%d" % (sname, allow))
                repo.mkdir()
                if sbytes is not None:
                    (repo / ".claude").mkdir()
                    (repo / ".claude" / "settings.json").write_bytes(sbytes)
                before = snapshot(repo)
                with mock.patch.object(cs, "OWNER", ()), mock.patch.object(wire, "SKILLS", wire.SKILLS[:1]):
                    self.run_wire(repo, allow=allow)                   # as the older version wired it
                older = snapshot(repo)
                self.assertNotIn(".claude/skills/memcrumbs-review/SKILL.md", older)
                self.run_wire(repo, allow=allow)                       # the upgrade's wire adds the rest
                settings = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
                self.assertIn("Bash(memcrumbs review --approve:*)", settings["permissions"]["ask"])
                self.assertIn(".claude/skills/memcrumbs-review/SKILL.md", snapshot(repo))
                self.run_wire(repo, remove=True)
                self.assertEqual(snapshot(repo), before)

    def test_refuses_what_it_cannot_reverse(self):
        repo = self.root / "jsonc"
        (repo / ".claude").mkdir(parents=True)
        bad = b'{\n  // a comment\n  "model": "x"\n}\n'
        (repo / ".claude" / "settings.json").write_bytes(bad)
        with self.assertRaises(SystemExit):
            self.run_wire(repo)
        self.assertEqual((repo / ".claude" / "settings.json").read_bytes(), bad)
        self.assertFalse((repo / "CLAUDE.md").exists())                 # nothing half-applied

    def test_hand_edited_hook_is_not_guessed_away(self):
        repo = self.root / "edited"
        repo.mkdir()
        self.run_wire(repo)
        sp = repo / ".claude" / "settings.json"
        sp.write_text(json.dumps(json.loads(sp.read_text(encoding="utf-8")), indent=4), encoding="utf-8")  # reformatted
        with self.assertRaises(SystemExit):
            self.run_wire(repo, remove=True)

    def test_line_endings_never_make_a_skill_foreign(self):
        """git's autocrlf rewrites the skill on every Windows checkout: the same text is still ours."""
        repo = self.root / "crlf"
        skill = repo / ".claude" / "skills" / "memcrumbs" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        ours = wire.lf((wire.TPL / "skill.md").read_bytes())
        skill.write_bytes(ours.replace(b"\n", b"\r\n"))

        def skill_change():
            return [c["what"] for c in wire.plan(self.project, repo) if c["path"] == skill]
        self.assertEqual(skill_change(), [])                                    # nothing to do
        with mock.patch.object(wire, "OLD_SKILLS", {wire.skill_hash(b"an older skill\n")}):
            skill.write_bytes(b"an older skill\r\n")                            # an older version's text, CRLF
            self.assertEqual(skill_change(), ["update skill (an older memcrumbs version)"])
            self.run_wire(repo)
            self.assertEqual(skill.read_bytes(), ours)
        skill.write_bytes(ours.replace(b"\n", b"\r\n"))
        self.run_wire(repo, remove=True)                                        # still ours to remove
        self.assertFalse(skill.exists())
        state = json.loads((self.project.data / "wire.json").read_text(encoding="utf-8"))
        self.assertEqual(state["version"], wire.__version__)                    # who applied the wiring last

    def test_user_skill_kept_unless_asked(self):
        repo = self.root / "userskill"
        repo.mkdir()
        home = self.root / "home"
        with mock.patch.object(Path, "home", return_value=home):
            self.run_wire(repo, user_skill=True)
            skill = home / ".claude" / "skills" / "memcrumbs" / "SKILL.md"
            self.assertTrue(skill.exists())
            self.run_wire(repo, remove=True)
            self.assertTrue(skill.exists())
            self.run_wire(repo, remove=True, user_skill=True)
            self.assertFalse(skill.exists())


if __name__ == "__main__":
    unittest.main()
