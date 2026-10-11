"""Upgrading a 0.1.0 deployment: its plugins keep loading, its wiring is updated and removable exactly."""
import contextlib
import io
import json
import subprocess
from pathlib import Path
from unittest import mock

from memcrumbs import plugins, project as proj, wire
from memcrumbs.output import Out
from test_cli import ProjectCase, run

ROOT = Path(__file__).resolve().parents[1]
V01_PLUGIN = '''
import time
from pathlib import Path
from memcrumbs.sources import Doc, md_docs, refresh
from memcrumbs.util import walk, read_text
from memcrumbs.cmd_write import recent_journal, lint

def gen(project):
    for p, rel in walk(project.dir / "notes", ["**/*.txt"]):          # 0.1: 2-tuples, float mtime
        yield p, p.stat().st_mtime, (lambda p=p: ([Doc("doc", str(p), 1, p.name, "", read_text(p), "note")], []))

def register(api):
    api.add_source("notes", gen)
    api.add_status(lambda project: ["journal lines: %d, lint findings: %d" % (len(recent_journal(project)),
                                                                          len(lint(project)))])
'''


def v01_skill():
    try:                                                   # the root commit is v0.1 (its hash changes with a rewrite)
        root = subprocess.run(["git", "-C", str(ROOT), "rev-list", "--max-parents=0", "HEAD"], capture_output=True,
                              check=True, text=True).stdout.split()[-1]
        skill = subprocess.run(["git", "-C", str(ROOT), "show", "%s:memcrumbs/templates/skill.md" % root],
                               capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError, IndexError):
        return None
    import hashlib                                         # only a skill an old version really wrote counts
    return skill if "sha256:" + hashlib.sha256(skill).hexdigest() in wire.OLD_SKILLS else None


class V01Upgrade(ProjectCase):
    def test_a_v01_plugin_still_works(self):
        pdir = self.projects / "t"
        (pdir / "notes").mkdir()
        (pdir / "notes" / "a.txt").write_text("the quokka migration note\n", encoding="utf-8")
        (pdir / "plugins").mkdir()
        (pdir / "plugins" / "old.py").write_text(V01_PLUGIN, encoding="utf-8")
        (pdir / "memcrumbs.toml").write_text('name = "t"\nplugins = ["plugins/old.py"]\n', encoding="utf-8")
        self.assertEqual(plugins.load(proj.resolve("t")).errors, [])
        run(["-p", "t", "index"])
        self.assertIn("quokka", run(["-p", "t", "find", "quokka"])[1])
        self.assertIn("lint findings:", run(["-p", "t", "status"])[1])

    def test_v01_wiring_is_upgraded_and_removed(self):
        skill = v01_skill()
        if skill is None:
            self.skipTest("no v0.1 commit in this history")
        p = proj.resolve("t")
        home = Path(self.tmp.name) / "home"
        user_skill = home / ".claude" / "skills" / "memcrumbs" / "SKILL.md"
        user_skill.parent.mkdir(parents=True)
        user_skill.write_bytes(skill.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))       # 0.1 wrote CRLF on Windows
        before = {"model": "x", "permissions": {"allow": ["Bash(ls)"]}}
        wired = dict(before, hooks={"SessionStart": [{"matcher": "", "hooks": [
            {"type": "command", "command": "memcrumbs -p t status --hook", "timeout": 30}]}]})
        (self.repo / ".claude").mkdir()
        sp = self.repo / ".claude" / "settings.json"
        sp.write_bytes((json.dumps(wired, indent=2) + "\n").replace("\n", "\r\n").encode())
        (self.repo / "CLAUDE.md").write_bytes(b"# Repo\r\nhand notes\r\n\r\n<!-- memcrumbs:gen claude -->\r\n"
                                              b"old block\r\n<!-- memcrumbs:end -->\r\n")

        def go(**kw):
            with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(Path, "home", return_value=home):
                out = Out("wire", p)
                wire.wire(out, p, self.repo, apply=True, user_skill=True, **kw)
                out.close()
        go()
        self.assertEqual(user_skill.read_bytes(), (ROOT / "memcrumbs" / "templates" / "skill.md").read_bytes())
        self.assertNotIn(b"old block", (self.repo / "CLAUDE.md").read_bytes())
        self.assertEqual(sp.read_bytes().count(b"memcrumbs -p t status"), 1)            # not added twice
        go(remove=True)
        self.assertEqual((self.repo / "CLAUDE.md").read_bytes(), b"# Repo\r\nhand notes\r\n")
        self.assertEqual(sp.read_bytes(), (json.dumps(before, indent=2) + "\n").replace("\n", "\r\n").encode())
        self.assertFalse(user_skill.exists())
