"""Ranking and records: kind override and procedure intent, table chunks, long
questions, thesaurus overrides, verdicts, page size, usage switch, status hint."""
import json
import os
from pathlib import Path

from memcrumbs import markdown, project as proj, rank, synonyms
from memcrumbs.query import error_phrases, term_pairs, wants_code, wants_procedure, wants_tests
from memcrumbs.sources import split_ident
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


class RepoOnDayZero(ProjectCase):
    """A repo with no wiki page written yet: source over its tests, short paths, and no starter text as answers."""

    def setUp(self):
        super().setUp()
        (self.repo / "app").mkdir()
        (self.repo / "app" / "decoders.py").write_text(
            'class GZipDecoder:\n    """Handle gzip decoding of response bodies."""\n    def decode(self, data):\n'
            '        return data\n', encoding="utf-8")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_decoders.py").write_text(
            "def test_gzip_decoding():\n    pass\n\n\ndef test_gzip_decoding_of_response_bodies():\n    pass\n",
            encoding="utf-8")
        for name in ("rules.md", "gotchas.md"):                  # the starter pages exactly as init writes them
            (self.wiki / name).write_text((Path(proj.__file__).parent / "templates" / name).read_text(
                encoding="utf-8").replace("{title}", "T"), encoding="utf-8")
        run(["-p", "t", "index"])

    def paths(self, q):
        return [h["path"] for h in json.loads(run(["-p", "t", "find", q, "--json"])[1])["hits"]]

    def test_the_source_ranks_above_its_tests_unless_tests_are_asked_for(self):
        self.assertTrue(self.paths("where is gzip decoding of response bodies done")[0].endswith("app/decoders.py"))
        self.assertTrue(self.paths("the tests for gzip decoding")[0].endswith("tests/test_decoders.py"))

    def test_paths_are_short_inside_the_working_folder(self):
        was = os.getcwd()
        os.chdir(self.repo)
        try:
            hits = self.paths("gzip decoding")
        finally:
            os.chdir(was)
        self.assertIn("app/decoders.py", hits)                   # relative to where the agent runs

    def test_starter_text_is_never_an_answer(self):
        self.assertFalse(any("wiki/" in p for p in self.paths("what happens at every session start")))
        rules = self.wiki / "rules.md"
        rules.write_text(rules.read_text(encoding="utf-8").replace("## Top\n", "## Top\n- Ask before every deploy\n"),
                         encoding="utf-8")
        run(["-p", "t", "index"])
        self.assertIn("wiki/rules.md", self.paths("ask before every deploy"))

    def test_question_intents_and_identifier_words(self):
        self.assertTrue(wants_code("where is that header masked?") and not wants_code("where do I set a timeout?"))
        self.assertTrue(wants_tests("which tests cover redirects") and not wants_tests("test my app in unit tests"))
        self.assertIn("gzip", split_ident("GZipDecoder").split())
        self.assertIn("ipv6", split_ident("IPv6Address").split())


class ErrorText(ProjectCase):
    """Pasted error text is tried as an exact phrase first; hits that only share words say so."""

    def setUp(self):
        super().setUp()
        (self.wiki / "outage.md").write_text("---\ntitle: Bookings stopped at night\nsummary: the backup held the "
                                             "database\n---\n# Outage\nThe site answered with \"database is locked\" "
                                             "until the backup copy ended.\n", encoding="utf-8")
        (self.wiki / "locks.md").write_text("---\ntitle: Lock files\nsummary: which tools lock what\n---\n# Locks\n"
                                            "The editor locks the database schema file while it is open; an error "
                                            "there is harmless.\n", encoding="utf-8")
        run(["-p", "t", "index"])

    def find(self, q):
        return run(["-p", "t", "find", q])[1], json.loads(run(["-p", "t", "find", q, "--json"])[1])

    def test_what_is_error_shaped(self):
        self.assertEqual(error_phrases("sqlite3.OperationalError: database is locked"),
                         ["sqlite3.OperationalError: database is locked", "database is locked"])
        for q in ("Task result 0x1 at night", "OSError: [Errno 28] No space left", "HTTP 503 from the proxy"):
            self.assertTrue(error_phrases(q), q)
        for q in ("how do I fix the database lock error", "database locked?", "deploy the web app", "error log",
                  '"database is locked" again'):
            self.assertEqual(error_phrases(q), [], q)                   # a question, no error, too short, quoted

    def test_a_recorded_error_leads_and_a_new_one_says_so(self):
        text, data = self.find("sqlite3.OperationalError: database is locked")
        self.assertTrue(data["exact"])
        self.assertTrue(data["hits"][0]["path"].endswith("outage.md"))
        self.assertNotIn("not recorded", text)
        text, data = self.find("PermissionError: the database is locked by another user")
        self.assertFalse(data["exact"])
        self.assertIn("exact text not recorded; the hits below only share words", text)
        text = self.find("ZeroDivisionError: integer division by zero in the scheduler")[0]
        self.assertIn("the error text is not recorded, so the failure is new", text)
        self.assertNotIn("exact", self.find("how do I fix the database lock error")[1])   # a question: as before
