"""The index is a disposable cache: versioned, rebuilt on mismatch or damage, identical after a rebuild, and safe
with ten processes reading and refreshing at once."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from memcrumbs import indexer, plugins, project as proj
from memcrumbs.store import SCHEMA_VERSION, Store
from test_cli import ProjectCase, run

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ["deploy", "restart service", "config", "load_config", "rollback api", "backup", "worker", "queue retry"]


def make_corpus(projects, n_pages=40, n_code=40):
    wiki = projects / "c" / "wiki"
    (wiki / "runbooks").mkdir(parents=True)
    repo = projects.parent / "crepo"
    repo.mkdir()
    (projects / "c" / "memcrumbs.toml").write_text('name = "c"\nrepos = ["../../crepo"]\n', encoding="utf-8")
    words = "deploy restart service config rollback api backup worker queue retry cache disk".split()
    for i in range(n_pages):
        a, b = words[i % len(words)], words[(i * 7) % len(words)]
        (wiki / ("runbooks" if i % 3 == 0 else ".") / ("page%02d.md" % i)).write_text(
            "---\ntitle: Page %d %s\nsummary: about %s and %s\nverified: 2026-10-01\n---\n# Page %d\n## %s\n"
            "Steps for %s then %s.\n## Notes\nmore %s text\n" % (i, a, a, b, i, a.title(), a, b, b), encoding="utf-8")
    for i in range(n_code):
        (repo / ("mod%02d.py" % i)).write_text('"""Module %d."""\n\ndef load_config_%d(path):\n    """Load %s."""\n\n'
                                               'class Worker%d:\n    def retry(self):\n        pass\n'
                                               % (i, i, words[i % len(words)], i), encoding="utf-8")


def results(store):
    return [[(h["path"], h["loc"], round(h["score"], 9)) for h in store.search(q)] for q in QUERIES]


class IndexLifecycle(ProjectCase):
    def setUp(self):
        super().setUp()
        make_corpus(self.projects)
        self.p = proj.resolve("c")
        self.api = plugins.load(self.p)

    def test_delete_and_rebuild_gives_identical_results(self):
        st = Store(self.p.index_path)
        indexer.refresh(self.p, self.api, st, force=True)
        (self.p.wiki / "page01.md").write_text("---\ntitle: Changed\n---\n# Changed\nrollback now\n", encoding="utf-8")
        indexer.refresh(self.p, self.api, st)                               # incremental history differs …
        first = results(st)
        st.close()
        for suffix in ("", "-wal", "-shm"):
            f = Path(str(self.p.index_path) + suffix)
            if f.exists():
                f.unlink()
        st = Store(self.p.index_path)
        indexer.refresh(self.p, self.api, st, force=True)
        self.assertEqual(results(st), first)                                # … the answers do not
        st.close()

    def test_schema_mismatch_rebuilds(self):
        self.p.data.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.p.index_path))
        db.executescript("CREATE TABLE files(path TEXT PRIMARY KEY, source TEXT, mtime REAL); PRAGMA user_version = 1;")
        db.close()
        st = Store(self.p.index_path)
        self.assertEqual(st.db.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
        self.assertGreater(indexer.refresh(self.p, self.api, st)["wiki"], 0)
        st.close()

    def test_broken_index_is_rebuilt_by_commands(self):
        self.p.data.mkdir(parents=True, exist_ok=True)
        self.p.index_path.write_bytes(b"garbage" * 500)
        code, out = run(["-p", "c", "find", "rollback"])
        self.assertEqual(code, 0)
        self.assertIn("page", out)

    def test_locked_refresh_answers_from_the_last_index(self):
        run(["-p", "c", "index"])
        (self.p.wiki / "page02.md").write_text("# New\nzanzibar\n", encoding="utf-8")
        db = sqlite3.connect(str(self.p.index_path), timeout=0, isolation_level=None)
        db.execute("BEGIN IMMEDIATE")
        try:
            code, out = run(["-p", "c", "find", "rollback"])
            self.assertEqual(code, 0)
            self.assertIn("another memcrumbs process is writing", out)
        finally:
            db.execute("ROLLBACK")
            db.close()
        code, out = run(["-p", "c", "find", "zanzibar"])                    # caught up once the lock is gone
        self.assertIn("page02", out)


class Concurrency(unittest.TestCase):
    def test_ten_processes_read_and_refresh(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            projects = Path(d) / "projects"
            make_corpus(projects, 60, 120)
            env = dict(os.environ, MEMCRUMBS_PROJECTS=str(projects), PYTHONPATH=str(ROOT))
            env.pop("MEMCRUMBS_PROJECT", None)
            code = ("import sys\nfrom memcrumbs import cli\nfor i in range(%d):\n"
                    "    try:\n        cli.main(sys.argv[1:])\n    except SystemExit as e:\n"
                    "        if e.code: raise\n")
            procs = []
            for i in range(10):
                argv = ["-p", "c", "index", "--full"] if i % 2 else ["-p", "c", "find", QUERIES[i % len(QUERIES)]]
                procs.append(subprocess.Popen([sys.executable, "-c", code % 4] + argv, env=env, cwd=d,
                                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True))
            errors = [(p.args[-3:], p.communicate(timeout=300)[1]) for p in procs]
            for args, err in errors:
                self.assertEqual(err.strip(), "", args)
            self.assertTrue(all(p.returncode == 0 for p in procs), [p.returncode for p in procs])
            db = sqlite3.connect(str(projects / "c" / ".memcrumbs" / "index.db"))
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            n = db.execute("SELECT count(*) FROM files").fetchone()[0]
            db.close()
            self.assertEqual(n, 180)


if __name__ == "__main__":
    unittest.main()
