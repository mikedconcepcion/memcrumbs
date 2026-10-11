"""Core tests (stdlib unittest): python -m unittest discover -s tests"""
import tempfile
import textwrap
import unittest
from pathlib import Path

from memcrumbs import indexer, markdown, plugins
from memcrumbs.lint import lint
from memcrumbs.outline import outline_text
from memcrumbs.project import Project
from memcrumbs.query import split_filters
from memcrumbs.store import Store, fts_query


class MarkdownTest(unittest.TestCase):
    PAGE = textwrap.dedent("""\
        ---
        title: Svc
        summary: a service
        tags: [a, b]
        sources:
          - x.py
        ---
        # Svc
        intro
        ## Deploy
        step [[other]]
        ```
        ## not a heading
        ```
        ### Sub
        detail
        ## Rollback
        swap
        """)

    def test_frontmatter_and_sections(self):
        meta, body, n = markdown.frontmatter(self.PAGE)
        self.assertEqual(meta["tags"], ["a", "b"])
        self.assertEqual(meta["sources"], ["x.py"])
        self.assertEqual(n, 7)
        lines = body.splitlines()
        self.assertEqual([h for _, _, h in markdown.headings(lines)], ["Svc", "Deploy", "Sub", "Rollback"])
        a, b = markdown.section_span(lines, "deploy")
        self.assertIn("detail", "\n".join(lines[a:b]))          # subsections included
        self.assertNotIn("swap", "\n".join(lines[a:b]))
        self.assertEqual(markdown.links(body), ["other"])

    def test_generated_block(self):
        t = markdown.replace_generated("hand\n", "x", "one")
        t = markdown.replace_generated(t, "x", "two")
        self.assertIn("hand", t)
        self.assertIn("two", t)
        self.assertNotIn("one", t)
        self.assertTrue(markdown.replace_generated("", "x", "one").startswith(markdown.GEN_START % "x"))


class OutlineTest(unittest.TestCase):
    def test_python(self):
        src = 'MAX = 1\n\ndef f(a, b=2):\n    """Doc."""\n    return a\n\nclass C(B):\n    def m(self):\n        pass\n'
        s = {x["qual"]: x for x in outline_text("a.py", src)}
        self.assertEqual((s["f"]["line"], s["f"]["end"], s["f"]["doc"]), (3, 5, "Doc."))
        self.assertEqual(s["C.m"]["kind"], "method")
        self.assertEqual(s["MAX"]["kind"], "const")

    def test_mql(self):
        src = ('input double BatchSize = 0.01;   // base size\n#define MAX 6\n'
               'struct S\n{\n  int a;\n};\nint OnInit()\n{\n   if(x) { y(); }\n   return 0;\n}\n')
        s = {x["name"]: x for x in outline_text("ea.mq5", src)}
        self.assertEqual(s["BatchSize"]["kind"], "input")
        self.assertEqual(s["BatchSize"]["doc"], "base size")
        self.assertEqual((s["OnInit"]["line"], s["OnInit"]["end"]), (7, 11))
        self.assertEqual(s["S"]["kind"], "struct")

    def test_powershell(self):
        s = outline_text("x.ps1", "function Fix($n) {\n  if ($n) { 'a' }\n}\n")
        self.assertEqual((s[0]["name"], s[0]["end"]), ("Fix", 3))


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text('def load_config(path):\n    """Read config."""\n', encoding="utf-8")
        (root / "src" / ".env").write_text("A=1\n", encoding="utf-8")
        (root / "src" / "keys.pem.py").write_text("def k():\n    pass\n", encoding="utf-8")
        proj = root / "proj"
        (proj / "wiki" / "decisions").mkdir(parents=True)
        (proj / "memcrumbs.toml").write_text('name = "t"\nrepos = ["../src"]\n[security]\nnever_index = ["keys.*"]\n',
                                             encoding="utf-8")
        (proj / "wiki" / "api.md").write_text(
            "---\ntitle: API\nsummary: the api\nverified: 2026-01-01\n---\n# API\n## Rollback\nswap app.prev\n",
            encoding="utf-8")
        (proj / "wiki" / "decisions" / "cache.md").write_text(
            "---\ntitle: Add a cache\nsummary: tried a cache\nverified: 2026-01-01\nstatus: rejected\n---\n# Cache\n"
            "## Verdict\nrollback was slower\n", encoding="utf-8")
        (proj / "wiki" / "bad.md").write_text("# Bad\npass" + "word=Sup3r" + "Secret!\n[[missing]]\n", encoding="utf-8")
        self.project = Project(proj / "memcrumbs.toml")
        self.api = plugins.load(self.project)
        self.store = Store(self.project.index_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_refresh_search_symbols_lint(self):
        stats = indexer.refresh(self.project, self.api, self.store, force=True)
        self.assertEqual(stats["wiki"], 3)
        self.assertEqual(stats["code"], 1)                                       # .env and keys.* never indexed
        self.assertEqual(indexer.refresh(self.project, self.api, self.store, force=True)["code"], 1)  # forced
        self.assertEqual(indexer.refresh(self.project, self.api, self.store)["wiki"], 0)              # incremental
        hits = self.store.search("rollback")
        self.assertEqual((hits[0]["kind"], hits[0]["section"]), ("wiki", "Rollback"))
        dec = self.store.search("rollback", kinds=["decision"])
        self.assertEqual((dec[0]["kind"], dec[0]["status"]), ("decision", "rejected"))
        self.assertEqual(len(self.store.search("rollback", kinds=["wiki"])), 3)  # "wiki" covers every wiki kind
        self.assertEqual(self.store.symbols("load_config")[0][4], 1)
        body = " ".join(r[0] for r in self.store.db.execute("SELECT body FROM docs"))
        self.assertNotIn("Sup3rSecret", body)                    # redacted before indexing
        found = {(lvl, msg.split(":")[0]) for lvl, _, msg in lint(self.project)}
        self.assertIn(("E", "secret-like value"), found)
        self.assertIn(("W", "frontmatter missing"), found)
        self.assertIn(("W", "broken link [[missing]]"), found)

    def test_superseded_ranks_below_current(self):
        wiki = self.project.wiki
        (wiki / "old.md").write_text("---\ntitle: Backup\nsummary: backup\nverified: 2026-01-01\nstatus: superseded\n"
                                     "superseded_by: new\n---\n# Backup procedure\nnightly backup copy\n", encoding="utf-8")
        (wiki / "new.md").write_text("---\ntitle: Backup v2\nsummary: backup\nverified: 2026-01-01\n---\n"
                                     "# Backup procedure\nnightly backup copy to the vault\n", encoding="utf-8")
        indexer.refresh(self.project, self.api, self.store, force=True)
        paths = [Path(h["path"]).stem for h in self.store.search("nightly backup procedure")]
        self.assertLess(paths.index("new"), paths.index("old"))

    def test_inline_filters(self):
        indexer.refresh(self.project, self.api, self.store, force=True)
        self.assertEqual([h["title"] for h in self.store.search("kind:decision status:rejected")], ["Add a cache"])
        self.assertEqual({h["kind"] for h in self.store.search("rollback status:rejected")}, {"decision"})
        self.assertTrue(all("api.md" in h["path"] for h in self.store.search("rollback path:api")))
        self.assertEqual(split_filters("x kind:a,b in:src y"), ("x y", {"kind": ["a", "b"], "path": ["src"]}))

    def test_fts_query_quotes_terms(self):
        self.assertEqual(fts_query('app_cfg.json "a b" pre*'), '"app_cfg.json" AND "a b" AND "pre"*')
        self.assertEqual(fts_query("how do I roll back the api?"), '"roll" AND "back" AND "api"')


if __name__ == "__main__":
    unittest.main()
