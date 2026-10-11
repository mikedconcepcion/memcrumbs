"""`memcrumbs init` inside a repo: one command sets it all up, a second run changes nothing, and `--remove` gives
back every repo file byte for byte."""
import os
import subprocess
from pathlib import Path

from memcrumbs import header, project as proj
from test_cli import ProjectCase, run
from test_wire import snapshot

REPO = {"README.md": "# Kiln App\n\n[![ci](b.svg)](x)\n\nKiln App schedules firing runs for a pottery studio. It talks to "
                     "the kiln over serial.\n\n## Install\n",
        "src/kiln/fire.py": 'def fire(profile):\n    """Start a firing."""\n',
        "tests/test_fire.py": "def test_fire():\n    pass\n",
        "docs/ops.md": "# Ops\n## Restart the controller\npower cycle the quokka board\n",
        "pyproject.toml": "[tool.pytest.ini_options]\n",
        ".github/workflows/ci.yml": "on: push\n",
        "env/pyvenv.cfg": "home = x\n", "env/lib/site.py": "x = 1\n",
        "CLAUDE.md": "# Kiln\r\nhand notes\r\n"}


def files(root):
    return {k: v for k, v in snapshot(root).items() if not k.startswith(".git/")}


class Init(ProjectCase):
    def setUp(self):
        super().setUp()
        self.app = Path(self.tmp.name) / "code" / "Kiln App"
        for rel, text in REPO.items():
            p = self.app / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode())
        subprocess.run(["git", "-C", str(self.app), "init", "-q"], check=True, capture_output=True)
        self.cwd = os.getcwd()
        os.chdir(self.app / "src")                          # anywhere inside the repo

    def tearDown(self):
        os.chdir(self.cwd)
        super().tearDown()

    def test_one_command_then_nothing_to_do_then_removed_byte_for_byte(self):
        before = files(self.app)
        code, out = run(["init"])
        self.assertEqual(code, 0, out)
        lines = out.strip().splitlines()
        self.assertLessEqual(len(lines), 8, out)
        self.assertTrue(lines[0].startswith("created kiln-app: wiki"), out)
        self.assertIn("wire: not applied. Ask the owner, then run memcrumbs init --yes", out)   # no terminal: no yes
        self.assertTrue(lines[-1].startswith("next: memcrumbs init --yes"), out)
        self.assertEqual(files(self.app), before)          # the repo is untouched without the owner's yes
        out = run(["init", "--yes"])[1]
        self.assertIn("already set up: kiln-app", out)
        self.assertIn("wire: wrote CLAUDE.md, .claude/settings.json, .claude/skills/memcrumbs/SKILL.md", out)
        self.assertIn("next: start Claude Code here", out)
        p = proj.resolve("kiln-app")
        wired, wiki = files(self.app), files(p.wiki)
        out = run(["init"])[1]
        self.assertIn("wire: Claude Code is wired and current", out)
        self.assertIn("next: nothing to do", out)
        self.assertEqual((files(self.app), files(p.wiki)), (wired, wiki))      # a second run changes nothing
        out = run(["init", "--remove"])[1]
        self.assertIn("unwired: %s" % self.app.resolve().as_posix(), out)
        self.assertEqual(files(self.app), before)          # every byte back, CRLF and all
        self.assertTrue((p.dir / "memcrumbs.toml").exists())                    # the wiki is kept

    def test_what_it_found_and_the_header_of_a_new_wiki(self):
        run(["init", "--no-wire"])
        p = proj.resolve("kiln-app")
        self.assertEqual(p.title, "Kiln App")
        self.assertIn("env/**", p.cfg["code"]["exclude"])                     # a virtual environment is skipped
        self.assertEqual(p.cfg["docs"][0]["include"], ["*.md", "docs/**/*.md"])
        index = (p.wiki / "index.md").read_text(encoding="utf-8")
        for want in ("- What it is: Kiln App schedules firing runs for a pottery studio.",
                     "- Languages: Python (2 files)", "`src/`", "Tests: `python -m pytest`",
                     "CI: GitHub Actions (ci.yml)"):
            self.assertIn(want, index)
        out = run(["status"])[1]                                               # the cwd finds the project
        self.assertIn(header.NEW_WIKI, out)
        self.assertNotIn("Top gotchas", out)                                   # no bare title over nothing
        self.assertIn("docs/ops.md", run(["find", "quokka board"])[1])        # the repo's own docs are indexed
        self.assertNotIn("site.py", run(["find", "site"])[1])
        self.assertNotIn("broken link", run(["check"])[1])                    # a fresh wiki lints clean
        gotchas = p.wiki / "gotchas.md"
        gotchas.write_text(gotchas.read_text(encoding="utf-8").replace(
            "## Top\n", "## Top\n- The kiln controller drops serial at 115200 baud.\n"), encoding="utf-8")
        self.assertNotIn(header.NEW_WIKI, run(["status"])[1])

    def test_names_are_unique_and_found_again(self):
        (self.projects / "kiln-app").mkdir()                                   # the name is taken
        self.assertIn("created kiln-app-2", run(["init", "--no-wire"])[1])
        self.assertIn("already set up: kiln-app-2", run(["init", "--no-wire"])[1])
        self.assertEqual(run(["init", "other", "--no-wire"])[0], 1)            # one repo, one project

    def test_deleting_the_wiki_needs_the_owners_yes(self):
        run(["init", "--yes"])
        p = proj.resolve("kiln-app")
        self.assertEqual(run(["init", "--remove", "--delete-wiki"])[0], 1)
        self.assertTrue((self.app / ".claude").exists())                      # refused before anything changed
        self.assertEqual(run(["init", "--remove", "--delete-wiki", "--yes"])[0], 0)
        self.assertFalse(p.dir.exists())
        self.assertFalse((self.app / ".claude").exists())

    def test_outside_a_repo_a_name_makes_a_wiki_only(self):
        os.chdir(self.tmp.name)
        self.assertEqual(run(["init"])[0], 1)                                  # no repo, no name: says what to do
        self.assertIn("created", run(["init", "notes"])[1])
        self.assertEqual(proj.resolve("notes").repos, [])
