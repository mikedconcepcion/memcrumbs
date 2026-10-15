"""The public bench (bench/kiln, invented): recall gate, planted secrets never leak, the injection is flagged,
reference plugins stay small and work."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memcrumbs import bench, cli, plugins, project as proj
from memcrumbs.output import Out
from memcrumbs.store import Store

BENCH = Path(__file__).resolve().parents[1] / "bench"
MIN_RECALL3 = 0.90                      # CI fails below this


def run(argv):
    out = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        try:
            cli.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, out.getvalue()


class BenchCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.root = Path(cls.tmp.name) / "projects"
        shutil.copytree(BENCH / "kiln", cls.root / "kiln", ignore=shutil.ignore_patterns(".memcrumbs"))
        cls.env = mock.patch.dict(os.environ, {"MEMCRUMBS_PROJECTS": str(cls.root)})
        cls.env.start()
        os.environ.pop("MEMCRUMBS_PROJECT", None)
        run(["-p", "kiln", "index", "--full"])
        cls.project = proj.resolve("kiln")

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.tmp.cleanup()


class RecallGate(BenchCase):
    def recall(self, name):
        st = Store(self.project.index_path)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                out = Out("bench", None, self.project.redact)
                bench.report(out, self.project, st, BENCH / name)
            return out.data["total"]
        finally:
            st.close()

    def test_recall_at_3_on_the_public_bench(self):
        total = self.recall("questions.toml")
        self.assertGreaterEqual(total["recall_at_3"], MIN_RECALL3, total)
        self.assertLessEqual(total["tokens_p95"], 600, total)          # find stays in the 300-600 token band

    def test_error_text_recorded_and_new(self):
        st = Store(self.project.index_path)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                out = Out("bench", None, self.project.redact)
                bench.report(out, self.project, st, BENCH / "errors.toml")
        finally:
            st.close()
        self.assertEqual(out.data["total"]["recall_at_1"], 1.0, out.data["total"])
        new = out.data["unrecorded"]
        self.assertEqual((new["n"], new["labelled"]), (4, 4))            # a new failure is never dressed as a match

    def test_holdout_is_reported(self):
        total = self.recall("holdout.toml")                            # written after tuning; tracked, not tuned
        self.assertGreaterEqual(total["recall_at_3"], 0.80, total)


class Leaks(BenchCase):
    def planted(self):
        items = json.loads((BENCH / "kiln" / "planted.json").read_text(encoding="utf-8"))
        return ["".join(x["fragments"]) for x in items]

    def test_planted_secrets_never_come_out(self):
        secrets = self.planted()
        self.assertEqual(len(secrets), 6)
        outputs = []
        for page in self.project.wiki_pages():
            outputs.append(run(["-p", "kiln", "page", str(page), "--full"])[1])
        for q in ("password", "api key", "token", "smtp", "secret", "alert webhook", "payment key", "disk full",
                  "config booking", "test payments fixture"):
            outputs.append(run(["-p", "kiln", "find", q, "-n", "20"])[1])
            outputs.append(run(["-p", "kiln", "find", q, "--json"])[1])
        repo = self.root / "kiln" / "repo"
        for f in list(repo.rglob("*.py")) + list(repo.rglob("*.ps1")):
            outputs.append(run(["-p", "kiln", "outline", str(f)])[1])
            for line in run(["-p", "kiln", "outline", str(f), "--json"])[1:]:
                outputs.append(line)
        for name in ("send_alert", "Send-Alert", "charge", "load", "refund"):
            outputs.append(run(["-p", "kiln", "sym", name, "--body"])[1])
        outputs += [run(["-p", "kiln", "status"])[1], run(["-p", "kiln", "check", "--full"])[1],
                    run(["-p", "kiln", "log", "rotated smtp " + "pass" + "word=" + secrets[0]])[1]]
        blob = "\n".join(outputs)
        index = (self.project.index_path).read_bytes()
        written = "".join(p.read_text(encoding="utf-8", errors="replace")
                          for p in (self.project.wiki / "journal").glob("*.md"))
        for s in secrets:
            with self.subTest(secret=s[:3] + "…"):
                self.assertNotIn(s, blob)
                self.assertNotIn(s.encode("utf-8"), index)
                self.assertNotIn(s, written)

    def test_injection_is_flagged(self):
        code, out = run(["-p", "kiln", "check"])
        self.assertIn("instruction-like text", out)
        self.assertIn("profire-controller-manual", out)
        code, out = run(["-p", "kiln", "page", "profire-controller-manual"])
        self.assertIn("⚠ instruction-like text", out)
        code, out = run(["-p", "kiln", "find", "controller manual safety interlock"])
        self.assertIn("⚠INSTRUCTION-LIKE TEXT", out)


class ReferencePlugins(BenchCase):
    def test_small_enough(self):
        for name, limit in (("kiln_outline.py", 100), ("tasks.py", 150)):
            n = len((BENCH / "kiln" / "plugins" / name).read_text(encoding="utf-8").splitlines())
            self.assertLess(n, limit, name)

    def test_they_work(self):
        api = plugins.load(self.project)
        self.assertEqual(api.errors, [])
        code, out = run(["-p", "kiln", "outline", str(self.root / "kiln" / "repo" / "profiles" / "cone6_glaze.kiln")])
        self.assertIn("profile cone6_glaze", out)
        code, out = run(["-p", "kiln", "check"])
        self.assertIn("DoorAlarmRelay", out)                       # the 72-hour trap, turned into a check
        code, out = run(["-p", "kiln", "status"])
        self.assertIn("Live tasks", out)
        code, out = run(["-p", "kiln", "tasks-page"])
        self.assertEqual(code, 0, out)
        page = (self.project.wiki / "systems" / "scheduled-tasks.md").read_text(encoding="utf-8")
        self.assertIn("<!-- memcrumbs:gen tasks -->", page)
        self.assertIn("| KilnScheduler |", page)
        original = (BENCH / "kiln" / "wiki" / "systems" / "scheduled-tasks.md").read_text(encoding="utf-8")
        self.assertTrue(page.startswith(original))                   # hand text above the block untouched


if __name__ == "__main__":
    unittest.main()
