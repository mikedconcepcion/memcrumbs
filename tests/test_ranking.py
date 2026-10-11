"""Ranking and records: kind override and procedure intent, table chunks, long
questions, thesaurus overrides, verdicts, page size, usage switch, status hint."""
import json
import os
from pathlib import Path

from memcrumbs import markdown, project as proj, rank, synonyms
from memcrumbs.query import term_pairs, wants_procedure
from memcrumbs.verdicts import row_status, row_verdicts, verdict
from test_cli import ProjectCase, run

ROWS = "".join("| exp-%02d | idea %s | %s |\n" % (i, "zebra" if i == 31 else "x%d" % i,
                                                 "REJECTED" if i == 31 else "ADOPTED") for i in range(40))


class FieldR1(ProjectCase):
    def setUp(self):
        super().setUp()
        w = self.wiki
        (w / "research").mkdir()
        (w / "research" / "backtest-howto.md").write_text(
            "---\ntitle: Run a backtest\nsummary: How to run a backtest\nkind: runbook\nverified: 2099-01-01\n---\n"
            "# Run a backtest\n1. run the backtest script\n", encoding="utf-8")
        (w / "verdicts.md").write_text("---\ntitle: Experiment log\nsummary: s\nverified: 2099-01-01\n---\n# Log\n"
                                       "| id | idea | verdict |\n|---|---|---|\n" + ROWS, encoding="utf-8")
        docs = Path(self.tmp.name) / "research-docs"
        docs.mkdir()
        (docs / "cache.md").write_text("# Read-through cache — REJECTED\nmeasured slower\n", encoding="utf-8")
        (self.projects / "t" / "memcrumbs.toml").write_text(
            'name = "t"\nrepos = ["../../repo"]\n[[docs]]\nname = "r"\nroot = "%s"\n' % docs.as_posix(), encoding="utf-8")
        run(["-p", "t", "index"])

    def hits(self, q):
        return json.loads(run(["-p", "t", "find", q, "--json"])[1])["hits"]

    def test_kind_override_and_procedure_intent(self):
        self.assertTrue(wants_procedure("how do I run a backtest?") and not wants_procedure("backtest results"))
        top = self.hits("how do I run a backtest")[0]
        self.assertEqual((top["kind"], top["path"]), ("runbook", "wiki/research/backtest-howto.md"))

    def test_table_rows_are_their_own_hits_with_status(self):
        lines = ("| a | b |\n|---|---|\n" + ROWS).splitlines()
        parts = list(markdown.chunks(lines))
        self.assertTrue(all(p[2][0].startswith("| a") for p in parts))                # header repeated
        self.assertTrue(all(len(p[2]) - 2 <= markdown.TABLE_GROUP for p in parts))
        self.assertTrue(all(len(set().union(*(row_verdicts(r) for r in p[2][2:]))) == 1 for p in parts))
        top = self.hits("zebra idea")[0]
        self.assertEqual((top["status"], top["line"]), ("rejected", 40))              # the row's own line
        self.assertEqual(row_status(["| a |", "|---|", "| x | **Parked** |"]), "parked")

    def test_long_questions_damp_synonyms_only_where_the_word_exists(self):
        pairs = term_pairs("why would we restart the kiln scheduler safely after midnight today", synonyms.TABLE)
        self.assertTrue(rank.is_long(pairs))
        self.assertFalse(rank.is_long(term_pairs("restart kiln", synonyms.TABLE)))
        code, out = run(["-p", "t", "find", "--explain", "restart the whole booking web server safely after midnight"])
        self.assertIn("query read as", out)

    def test_thesaurus_overrides(self):
        t = synonyms.build(remove=["kill"])
        self.assertNotIn("kill", t)
        self.assertNotIn("kill", t["stop"])
        self.assertEqual(synonyms.build([["kiln", "furnace"]], builtin=False), {"kiln": {"furnace"}, "furnace": {"kiln"}})

    def test_verdicts_in_docs_trees(self):
        self.assertEqual(verdict("Exp 12 — REJECTED"), "rejected")
        self.assertEqual(verdict("**Verdict:** parked for now", lines_only=True), "parked")
        hits = self.hits("cache status:rejected")
        self.assertTrue(any(h["path"].endswith("cache.md") for h in hits))

    def test_long_page_prints_toc(self):
        (self.wiki / "wide.md").write_text("---\ntitle: Wide\nsummary: s\n---\n# Wide\n## A\n" + ("word " * 1600) + "\n## B\nb\n",
                                           encoding="utf-8")
        code, out = run(["-p", "t", "page", "wide"])
        self.assertIn("Sections", out)
        self.assertLess(len(out), 2000)

    def test_usage_switch(self):
        p = proj.resolve("t")
        log = p.data / "usage.jsonl"
        before = log.read_text(encoding="utf-8") if log.exists() else ""
        os.environ["MEMCRUMBS_NO_USAGE"] = "1"
        try:
            run(["-p", "t", "find", "zebra"])
        finally:
            del os.environ["MEMCRUMBS_NO_USAGE"]
        self.assertEqual(log.read_text(encoding="utf-8") if log.exists() else "", before)

    def test_unknown_status_suggests(self):
        (self.wiki / "odd.md").write_text("---\ntitle: Odd\nsummary: s\nverified: 2099-01-01\nstatus: rejectd\n---\n# Odd\n",
                                          encoding="utf-8")
        self.assertIn("did you mean 'rejected'", run(["-p", "t", "check"])[1])
