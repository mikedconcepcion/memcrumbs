"""CLI regression tests: run `main()` in-process, the way the shell and the SessionStart hook do."""
import contextlib
import io
import json
import os
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memcrumbs import cli, project as proj, wire
from memcrumbs.output import Out


def run(argv):
    """Run the CLI; return (exit code, stdout)."""
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            cli.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, out.getvalue()


class ProjectCase(unittest.TestCase):
    """A temp projects_dir with project `t` whose repo is `repo/`."""

    def setUp(self):
        # sqlite handles stay open until GC, which Windows refuses to delete: tolerate cleanup errors
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        (self.repo / "app.py").write_text('def main():\n    """Entry point."""\n    pass\n', encoding="utf-8")
        self.projects = root / "projects"
        self.wiki = self.projects / "t" / "wiki"
        self.wiki.mkdir(parents=True)
        (self.projects / "t" / "memcrumbs.toml").write_text('name = "t"\nrepos = ["../../repo"]\n', encoding="utf-8")
        (self.wiki / "index.md").write_text("# T\n## Map\n- the map line\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if not k.startswith("MEMCRUMBS_") and k != "CLAUDECODE"}   # a human
        env["MEMCRUMBS_PROJECTS"] = str(self.projects)
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class CliTest(ProjectCase):
    def test_project_flag_before_or_after_subcommand(self):
        for argv in (["-p", "t", "status"], ["status", "--hook", "-p", "t"]):
            code, out = run(argv)
            self.assertEqual(code, 0, argv)
            self.assertIn("the map line", out)

    def test_wire_writes_a_hook_that_runs_and_is_idempotent(self):
        (self.repo / "CLAUDE.md").write_text("# Repo\nhand notes\n", encoding="utf-8")
        project = proj.resolve("t")
        for _ in range(2):
            with contextlib.redirect_stdout(io.StringIO()):
                out = Out("wire", project)
                wire.wire(out, project, self.repo, apply=True)
                out.close()
        claude = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("hand notes", claude)
        self.assertEqual(claude.count("<!-- memcrumbs:gen claude -->"), 1)
        settings = json.loads((self.repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
        hooks = [h["command"] for e in settings["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertEqual(len(hooks), 1)
        argv = shlex.split(hooks[0])
        self.assertEqual(argv[0], "memcrumbs")
        code, out = run(argv[1:])                      # exactly what Claude Code will execute
        self.assertEqual(code, 0)
        self.assertIn("the map line", out)

    def test_scan_needs_no_project(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["MEMCRUMBS_PROJECTS"] = str(Path(d) / "none")       # no projects configured at all
            target = Path(d) / "src"
            target.mkdir()
            (target / "ok.txt").write_text("password: changed yesterday\n", encoding="utf-8")
            self.assertEqual(run(["scan", str(target)])[0], 0)
            (target / "leak.txt").write_text("pass" + "word=" + "Zx9kq!Lm2\n", encoding="utf-8")
            code, out = run(["scan", str(target)])
            self.assertEqual(code, 1)
            self.assertIn("leak.txt", out)
            self.assertNotIn("Zx9kq", out)
            self.assertEqual(run(["-p", "nope", "scan", str(target)])[0], 1)   # a named project must exist

    def test_json_outputs_for_read_commands(self):
        run(["-p", "t", "index"])
        for argv, key in ((["find", "map"], "hits"), (["page", "index"], "path"), (["sym", "main"], "symbols"),
                          (["outline", str(self.repo / "app.py")], "symbols"), (["status"], "sections"),
                          (["stats", "--usage"], "usage"), (["check"], "findings")):
            code, out = run(["-p", "t"] + argv + ["--json"])
            with self.subTest(argv):
                self.assertEqual(json.loads(out)[key] is not None, True)

    def test_hook_never_fails(self):
        os.environ["MEMCRUMBS_PROJECTS"] = str(Path(self.tmp.name) / "missing")
        code, out = run(["-p", "t", "status", "--hook"])
        self.assertEqual(code, 0)
        self.assertIn("memcrumbs", out)

    def test_curation_commands(self):
        code, out = run(["-p", "t", "decision", "Move to Postgres", "--status", "rejected", "--why", "locks"])
        self.assertEqual(code, 0, out)
        page = next((self.wiki / "decisions").glob("*-move-to-postgres.md"))
        self.assertIn("status: rejected", page.read_text(encoding="utf-8"))
        run(["-p", "t", "incident", "Disk full", "--cause", "logs", "--fix", "rotation"])
        self.assertTrue(next((self.wiki / "incidents").glob("*-disk-full.md")))
        (self.wiki / "old.md").write_text("---\ntitle: Old\nverified: 2025-01-01\n---\n# Old\n", encoding="utf-8")
        self.assertEqual(run(["-p", "t", "supersede", "old", "--by", "index"])[0], 0)
        self.assertEqual(run(["-p", "t", "verify", "old", "--date", "2026-10-01"])[0], 0)
        text = (self.wiki / "old.md").read_text(encoding="utf-8")
        self.assertEqual(text, "---\ntitle: Old\nverified: 2026-10-01\nstatus: superseded\nsuperseded_by: index\n---\n# Old\n")
        code, out = run(["-p", "t", "find", "old"])
        self.assertIn("SUPERSEDED→index", out)


class WorktreeTest(ProjectCase):
    def test_find_from_a_linked_worktree(self):
        import shutil
        import subprocess
        if not shutil.which("git"):
            self.skipTest("no git")
        g = ["git", "-C", str(self.repo), "-c", "user.email=t@example.com", "-c", "user.name=t"]
        (self.repo / "sub").mkdir()
        (self.repo / "sub" / "x.py").write_text("X = 1\n", encoding="utf-8")
        for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "x"]):
            subprocess.run(g + cmd, check=True, capture_output=True)
        wt = Path(self.tmp.name) / "elsewhere" / "wt"
        subprocess.run(g + ["worktree", "add", "-q", str(wt)], check=True, capture_output=True)
        self.assertEqual(proj.resolve(cwd=wt / "sub").name, "t")
        (self.projects / "u").mkdir()                                   # two projects: the cwd must decide
        (self.projects / "u" / "memcrumbs.toml").write_text('name = "u"\n', encoding="utf-8")
        self.assertEqual(proj.resolve(cwd=wt / "sub").name, "t")
        with self.assertRaises(SystemExit):
            proj.resolve(cwd=Path(self.tmp.name))


class ProjectsDirTest(unittest.TestCase):
    def test_default_and_user_config(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "MEMCRUMBS_PROJECTS"},
                                clear=True), \
                mock.patch.object(proj, "USER_DIR", Path(d)):
            self.assertEqual(proj.projects_dir(), Path(d) / "projects")            # never the package folder
            (Path(d) / "config.toml").write_text('projects_dir = "/srv/wikis"\n', encoding="utf-8")
            self.assertEqual(proj.projects_dir(), Path("/srv/wikis"))
            os.environ["MEMCRUMBS_PROJECTS"] = str(Path(d) / "env")
            self.assertEqual(proj.projects_dir(), Path(d) / "env")


if __name__ == "__main__":
    unittest.main()
