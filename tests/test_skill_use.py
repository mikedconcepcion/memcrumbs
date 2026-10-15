"""Each use of a skill leaves a short note (a journal line and a terminal line); `memcrumbs skills` counts the uses
from the notes, or from Claude Code's transcripts when they are on."""
import datetime as dt
import json
from pathlib import Path
from unittest import mock

from memcrumbs import project as proj, skill_use, transcripts
from test_cli import ProjectCase, run


def skill(root, name):
    p = root / ".claude" / "skills" / name / "SKILL.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("---\nname: %s\ndescription: x\n---\n# %s\n" % (name, name), encoding="utf-8")


def transcript(folder, lines):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "s.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


class SkillUse(ProjectCase):
    def setUp(self):
        super().setUp()
        self.home = Path(self.tmp.name) / "home"
        skill(self.repo, "test-scan-and-push")
        skill(self.repo, "rotate-key")
        skill(self.home, "my-own-habits")                   # a user skill this project never used

    def skills(self):
        with mock.patch.object(Path, "home", return_value=self.home):
            return run(["-p", "t", "skills"])[1], json.loads(run(["-p", "t", "skills", "--json"])[1])["skills"]

    def test_a_use_leaves_a_note_in_the_journal_and_the_terminal(self):
        out = run(["-p", "t", "log", "tests passed, pushed 3 commits", "--skill", "Test-Scan-And-Push"])[1]
        self.assertIn("skill test-scan-and-push used: tests passed, pushed 3 commits (logged -> wiki/journal/", out)
        journal = next((self.wiki / "journal").glob("*.md")).read_text(encoding="utf-8")
        self.assertRegex(journal, r"- \d{4}-\d\d-\d\d \d\d:\d\d skill test-scan-and-push: tests passed, pushed 3 "
                                  r"commits #skill\n")
        text, rows = self.skills()
        row = next(r for r in rows if r["name"] == "test-scan-and-push")
        self.assertEqual((row["uses"], row["where"], row["note"]), (1, "repo", "tests passed, pushed 3 commits"))
        self.assertIn("unused in 30 days: rotate-key", text)
        self.assertNotIn("my-own-habits", text)                             # not used here: not listed

    def test_transcripts_count_skill_calls_and_slash_commands(self):
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[suggest]\ntranscripts = true\n", encoding="utf-8")
        today = dt.date.today().isoformat()
        at = today + "T10:00:00Z"
        use = {"type": "assistant", "timestamp": at, "sessionId": "s1", "message": {
            "id": "m1", "role": "assistant", "usage": {"input_tokens": 10, "cache_read_input_tokens": 90,
                                                       "output_tokens": 5},
            "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "test-scan-and-push",
                                                                       "args": "secret-ish arguments"}}]}}
        again = dict(use, message=dict(use["message"], content=[{"type": "text", "text": "done"}]))   # same reply
        slash = {"type": "user", "timestamp": at, "sessionId": "s1", "message": {
            "role": "user", "content": "<command-name>/my-own-habits</command-name> please"}}
        builtin = dict(slash, message={"role": "user", "content": "<command-name>/clear</command-name>"})
        transcript(self.home / ".claude" / "projects" / transcripts.mangle(self.repo), [use, again, slash, builtin])
        with mock.patch.object(Path, "home", return_value=self.home):
            evs = transcripts.events(proj.resolve("t"))
        kinds = [(k, v) for _, _, k, v in evs]
        self.assertIn(("skill", "test-scan-and-push"), kinds)
        self.assertIn(("slash", "my-own-habits"), kinds)
        self.assertEqual([v for k, v in kinds if k == "tokens"], ["10,5,90"])  # one reply, counted once
        self.assertNotIn("secret-ish", json.dumps(evs))                      # names only, never arguments
        _, rows = self.skills()
        names = {r["name"]: r["uses"] for r in rows}
        self.assertEqual(names.get("test-scan-and-push"), 1)
        self.assertEqual(names.get("my-own-habits"), 1)                     # used here: listed
        self.assertNotIn("clear", names)                                    # a built-in command is not a skill

    def test_the_page_keeps_its_own_text_and_is_refreshed(self):
        with mock.patch.object(Path, "home", return_value=self.home):
            run(["-p", "t", "skills", "--page"])
            page = self.wiki / "skills.md"
            page.write_text(page.read_text(encoding="utf-8") + "\nMy own note about skills.\n", encoding="utf-8")
            run(["-p", "t", "log", "rotated", "--skill", "rotate-key"])       # a write: the daily scan runs
            text = page.read_text(encoding="utf-8")
        self.assertIn("| rotate-key | repo | 1 |", text)
        self.assertIn("My own note about skills.", text)
        self.assertEqual(text.count("<!-- memcrumbs:gen skills -->"), 1)
        page.unlink()
        self.assertFalse(skill_use.write_page(proj.resolve("t"), [], create=False))   # never made unasked
        self.assertFalse(page.exists())
