"""Write set, output caps/redaction/usage log, header budget and fallback."""
import contextlib
import io
import json
import os
import sqlite3
import unittest
from pathlib import Path

from memcrumbs import header, plugins, project as proj, writeset
from memcrumbs.output import Out
from memcrumbs.redact import RedactionError, Redactor
from test_cli import ProjectCase, run


class WriteSetTest(ProjectCase):
    def test_outside_the_write_set_is_refused(self):
        p = proj.resolve("t")
        writeset.write_text(p, p.wiki / "new.md", "ok\n")
        writeset.write_text(p, p.data / "x.json", "{}\n")
        for bad in (self.repo / "app.py", p.dir / "memcrumbs.toml", p.wiki / ".." / "escape.md", Path(self.tmp.name) / "x"):
            with self.subTest(bad=bad), self.assertRaises(writeset.WriteSetError):
                writeset.write_text(p, bad, "no\n")
        self.assertEqual((self.repo / "app.py").read_text(encoding="utf-8")[:10], "def main()")

    def test_symlink_out_of_the_wiki_is_refused(self):
        p = proj.resolve("t")
        link = p.wiki / "link.md"
        try:
            os.symlink(self.repo / "app.py", link)
        except (OSError, NotImplementedError):
            self.skipTest("no symlink privilege")
        with self.assertRaises(writeset.WriteSetError):
            writeset.write_text(p, link, "overwrite\n")

    def test_byte_exact_rewrite(self):
        p = proj.resolve("t")
        f = p.wiki / "bom.md"
        f.write_bytes(b"\xef\xbb\xbf---\r\ntitle: X\r\nverified: 2026-01-01\r\n---\r\nbad \xff byte\r\n")
        self.assertEqual(run(["-p", "t", "verify", "bom", "--date", "2026-10-01"])[0], 0)
        self.assertEqual(f.read_bytes(), b"\xef\xbb\xbf---\r\ntitle: X\r\nverified: 2026-10-01\r\n---\r\nbad \xff byte\r\n")


class FailClosedIndexTest(ProjectCase):
    def test_redaction_failure_keeps_the_file_out_of_the_index(self):
        secret = "pass" + "word=" + "Vb7!" + "qLm3Xz"
        (self.wiki / "leaky.md").write_text("---\ntitle: Leaky\n---\n# Leaky\n%s\nzebra\n" % secret, encoding="utf-8")
        from unittest import mock
        with mock.patch.object(Redactor, "_apply", side_effect=ValueError("boom")):
            code, out = run(["-p", "t", "index"])
        db = sqlite3.connect(str(proj.resolve("t").index_path))
        body = " ".join(r[0] for r in db.execute("SELECT title || ' ' || body FROM docs"))
        db.close()
        self.assertNotIn("Vb7!", body)
        self.assertNotIn("zebra", body)                 # nothing of that file, not just the secret
        self.assertNotIn("Vb7!", out)


class OutputTest(ProjectCase):
    def test_cap_names_the_next_command(self):
        p = proj.resolve("t")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = Out("page", p, cap=200)
            out.hint("memcrumbs page x --full")
            for i in range(50):
                out("line %d" % i)
            out.close()
        text = buf.getvalue()
        self.assertLessEqual(len(text), 200 + 150)
        self.assertIn("Next: memcrumbs page x --full", text)

    def test_json_stays_valid_when_cut(self):
        p = proj.resolve("t")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = Out("find", p, json_mode=True, cap=300, list_key="hits")
            out.set(hits=[{"path": "x%d" % i, "snippet": "y" * 40} for i in range(30)])
            out.close()
        data = json.loads(buf.getvalue())
        self.assertTrue(data["truncated"])
        self.assertLess(len(data["hits"]), 30)

    def test_every_line_is_redacted_and_failures_withhold(self):
        p = proj.resolve("t")
        secret = "pass" + "word=" + "Qz8!" + "kLm2Wx"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = Out("page", p)
            out("a " + secret)
            out.set(text=secret)
            out.close()
        self.assertNotIn("Qz8!", buf.getvalue())

        class Broken(Redactor):
            def __call__(self, text):
                raise RedactionError("boom")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            out = Out("page", p, redact=Broken())
            out(secret)
            out.close()
        self.assertNotIn("Qz8!", buf.getvalue())
        self.assertIn("withheld", buf.getvalue())

    def test_usage_log_has_sizes_not_content(self):
        run(["-p", "t", "index"])
        run(["-p", "t", "find", "zebra-quokka-term"])
        log = (proj.resolve("t").data / "usage.jsonl").read_text(encoding="utf-8")
        self.assertIn('"cmd": "find"', log)
        self.assertNotIn("zebra", log)
        code, out = run(["-p", "t", "stats", "--usage"])
        self.assertIn("find", out)


class DailyCheckTest(ProjectCase):
    def test_secret_like_text_reaches_the_header_without_a_check_run(self):
        bad = self.wiki / "bad.md"
        bad.write_text("# Bad\npass" + "word=Sup3r" + "Secret!\n", encoding="utf-8")       # split: not a secret here
        self.assertNotIn("secret-like", run(["-p", "t", "status"])[1])        # the header never runs the lint
        run(["-p", "t", "index"])                                              # a slow command: the daily check
        head = run(["-p", "t", "status"])[1]
        self.assertIn("check: 1 error (secret-like text) in wiki/bad.md — memcrumbs check", head)
        self.assertNotIn("Sup3r", head)                                        # where, never the text
        bad.write_text("# Bad\nthe password lives in the vault\n", encoding="utf-8")
        run(["-p", "t", "check"])                                              # a check run refreshes it at once
        self.assertNotIn("secret-like", run(["-p", "t", "status"])[1])


class HeaderTest(ProjectCase):
    def setUp(self):
        super().setUp()
        (self.wiki / "rules.md").write_text("# Rules\n## Top\n" + "".join("- rule %d: never do thing %d\n" % (i, i) for i in range(8)),
                                            encoding="utf-8")
        (self.wiki / "gotchas.md").write_text("---\nverified: 2026-10-01\n---\n# G\n## Top\n" +
                                              "".join("- gotcha %d %s\n" % (i, "x" * 150) for i in range(12)), encoding="utf-8")
        (self.wiki / "index.md").write_text("# T\n## Map\n" + "".join("- map line %d %s\n" % (i, "y" * 100) for i in range(30)),
                                            encoding="utf-8")

    def test_hard_cap_and_no_section_silently_dropped(self):
        (self.projects / "t" / "memcrumbs.toml").write_text(
            'name = "t"\nrepos = ["../../repo"]\n[status]\nmax_tokens = 400\n', encoding="utf-8")
        code, out = run(["-p", "t", "status"])
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out), 400 * 4 + 50)
        for title in ("Rules", "Map", "Top gotchas"):
            self.assertIn(title, out)                    # every section keeps at least its title …
        self.assertIn("(header budget): memcrumbs page", out)   # … and says how to see the rest
        self.assertLess(out.index("Rules"), out.index("Map"))

    def test_budget_never_exceeds_the_hard_ceiling(self):
        (self.projects / "t" / "memcrumbs.toml").write_text(
            'name = "t"\n[status]\nmax_tokens = 99999\nmap_lines = 500\ngotchas = 500\n', encoding="utf-8")
        code, out = run(["-p", "t", "status"])
        self.assertLessEqual(len(out), header.HARD_CAP_TOKENS * 4 + 50)

    def test_header_reads_files_when_the_index_is_broken_or_locked(self):
        p = proj.resolve("t")
        p.data.mkdir(parents=True, exist_ok=True)
        p.index_path.write_bytes(b"this is not a database" * 100)
        code, out = run(["-p", "t", "status", "--hook"])
        self.assertEqual(code, 0)
        self.assertIn("index unavailable", out)
        self.assertIn("rule 0", out)
        p.index_path.unlink()
        run(["-p", "t", "index"])
        db = sqlite3.connect(str(p.index_path), timeout=0)
        db.execute("BEGIN EXCLUSIVE")
        try:
            code, out = run(["-p", "t", "status", "--hook"])
            self.assertEqual(code, 0)
            self.assertIn("rule 0", out)
            code, out = run(["-p", "t", "find", "rule"])       # a reader never fails because of a writer
            self.assertEqual(code, 0)
        finally:
            db.rollback()
            db.close()

    def test_external_docs_never_enter_the_header(self):
        docs = Path(self.tmp.name) / "docs"
        docs.mkdir()
        (docs / "notes.md").write_text("# Notes\n## Map\n- EXTERNAL-DOC-LINE\n", encoding="utf-8")
        (self.projects / "t" / "memcrumbs.toml").write_text(
            'name = "t"\n[[docs]]\nname = "d"\nroot = "%s"\n' % docs.as_posix(), encoding="utf-8")
        run(["-p", "t", "index"])
        self.assertNotIn("EXTERNAL-DOC-LINE", run(["-p", "t", "status"])[1])

    def test_plugin_sections_and_failures(self):
        plug = self.projects / "t" / "plugins"
        plug.mkdir()
        (plug / "ok.py").write_text("def register(api):\n    api.add_section('live', lambda p: ['LIVE-LINE'], 'Live')\n",
                                    encoding="utf-8")
        (plug / "bad.py").write_text("raise ImportError('nope')\n", encoding="utf-8")
        (self.projects / "t" / "memcrumbs.toml").write_text(
            'name = "t"\nplugins = ["plugins/ok.py", "plugins/bad.py"]\n[status]\nsections = ["live", "map"]\n',
            encoding="utf-8")
        code, out = run(["-p", "t", "status", "--hook"])
        self.assertEqual(code, 0)
        self.assertIn("LIVE-LINE", out)
        self.assertIn("plugin plugins/bad.py failed to load", out)
        self.assertLess(out.index("LIVE-LINE"), out.index("Map"))
        api = plugins.load(proj.resolve("t"))
        self.assertEqual([e[0] for e in api.errors], ["plugins/bad.py"])


if __name__ == "__main__":
    unittest.main()
