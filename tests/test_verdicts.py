"""One-hop pointers, real verdict shapes, and honest output right after an upgrade."""
import json
import sqlite3

from memcrumbs import project as proj
from memcrumbs.verdicts import row_status, row_verdicts, section_verdict, verdict_columns
from memcrumbs.markdown import headings
from test_cli import ProjectCase, run


class Pointers(ProjectCase):
    def test_a_pointer_line_shows_the_linked_page(self):
        w = self.wiki
        (w / "restart-service.md").write_text(
            "---\ntitle: Restart the service\nsummary: s\nverified: 2099-01-01\n---\n# Restart the service\n"
            "1. stop the service\n2. start it\nChanging the gain setting without a restart: [[live-tuning]]\n",
            encoding="utf-8")
        (w / "live-tuning.md").write_text(
            "---\ntitle: Live tuning\nsummary: s\nverified: 2099-01-01\n---\n# Live tuning\n"
            "Edit the gain value in the running config; it is reloaded every minute.\n", encoding="utf-8")
        for i in range(6):                                            # crowd the shown hits with other pages
            (w / ("svc%d.md" % i)).write_text("# Service %d\nrestart the service, then check the setting\n" % i,
                                              encoding="utf-8")
        run(["-p", "t", "index"])
        hits = json.loads(run(["-p", "t", "find", "change the setting without restarting the service", "-n", "2",
                               "--json"])[1])["hits"]
        see = [h["see"] for h in hits if h.get("see")]
        self.assertTrue(see and see[0]["path"] == "wiki/live-tuning.md", hits)
        self.assertIn("→ see Live tuning", run(["-p", "t", "find", "change the setting without restarting the service",
                                                "-n", "2"])[1])


class ClausePointers(ProjectCase):
    def test_the_link_whose_clause_holds_the_words_wins(self):
        w = self.wiki
        (w / "ops.md").write_text("# Ops\n## See also\nBackground on the gain loop: [[gain-loop]]. Changing the gain "
                                  "setting without a restart: [[live-tuning]]. Remote access: [[vpn]], [[ssh]]\n",
                                  encoding="utf-8")
        for slug, text in (("gain-loop", "# Gain loop\nhow the gain loop settles\n"), ("live-tuning", "# Live tuning\nx\n"),
                           ("vpn", "# VPN\nx\n"), ("ssh", "# SSH\nx\n")):
            (w / (slug + ".md")).write_text(text, encoding="utf-8")
        run(["-p", "t", "index"])
        hits = json.loads(run(["-p", "t", "find", "change the gain setting without restarting", "-n", "3", "--json"])[1])["hits"]
        sees = [h["see"]["path"] for h in hits if h.get("see")]
        self.assertIn("wiki/live-tuning.md", sees)
        self.assertNotIn("wiki/vpn.md", sees)


class VerdictShapes(ProjectCase):
    TABLE = ["| Study | Verdict | Notes |", "|---|---|---|",
             "| s1 | REJECTED: slower than baseline | we rejected the first idea |",
             "| s2 | ADOPTED as default | |", "| s3 | PARKED 10-02: needs data | |", "| s4 | NOT ADOPTED: noisy | |",
             "| s5 | **rejected** | |", "| s6 | rejection pending review | |"]

    def test_cells_that_start_with_a_verdict(self):
        cols = verdict_columns(self.TABLE[0])
        self.assertEqual(cols, [1])
        got = [row_verdicts(r, cols) for r in self.TABLE[2:]]
        self.assertEqual(got, [{"rejected"}, {"accepted"}, {"parked"}, {"rejected"}, {"rejected"}, set()])
        self.assertEqual(row_verdicts("| x | we rejected it | y |", cols), set())   # prose in a verdict column
        self.assertEqual(row_status(self.TABLE[:2] + self.TABLE[2:3] + self.TABLE[5:6]), "rejected")

    def test_versions_scopes_and_reversals(self):
        cols = verdict_columns("| Study | Verdict |")
        for cell, want in (("ADOPTED v1.3.18 (fleet)", {"accepted"}), ("ADOPTED fleet-wide since March", {"accepted"}),
                           ("ADOPTED without backtest", {"accepted"}), ("ADOPTED v1.2, then REVERSED", set()),
                           ("adopted by the team later", set()), ("REJECTED twice", {"rejected"})):
            with self.subTest(cell):
                self.assertEqual(row_verdicts("| s | %s |" % cell, cols), want)

    def test_verdict_sections(self):
        lines = ["# Study", "text", "## Verdict", "", "**Rejected** after three weeks: too slow.", "## Notes", "x"]
        self.assertEqual(section_verdict(lines, headings(lines)), "rejected")
        lines[4] = "Not adopted; see notes."
        self.assertEqual(section_verdict(lines, headings(lines)), "rejected")
        lines[4] = "We found the cache helped."
        self.assertEqual(section_verdict(lines, headings(lines)), "")

    def test_status_filter_finds_them(self):
        body = "\n".join(["# Studies"] + self.TABLE + [""] * 3 + ["| s%d | ADOPTED | |" % i for i in range(7, 12)])
        (self.wiki / "studies.md").write_text("---\ntitle: Studies\nsummary: s\nverified: 2099-01-01\n---\n" + body,
                                              encoding="utf-8")
        (self.wiki / "cache-study.md").write_text("# Cache study\n## Verdict\nRejected: no gain.\n", encoding="utf-8")
        run(["-p", "t", "index"])
        hits = json.loads(run(["-p", "t", "find", "status:rejected", "-n", "20", "--json"])[1])["hits"]
        self.assertIn("wiki/cache-study.md", [h["path"] for h in hits])
        rows = [h for h in hits if h["path"] == "wiki/studies.md"]               # rows, not just pages
        self.assertTrue(rows and all(h["status"] == "rejected" for h in rows))
        self.assertTrue(any("s1" in h["snippet"] for h in rows))
        self.assertLess([h["path"] for h in hits].index("wiki/cache-study.md"),  # pages first
                        [h["path"] for h in hits].index("wiki/studies.md"))
        hits = json.loads(run(["-p", "t", "find", "slower baseline status:rejected", "--json"])[1])["hits"]
        self.assertEqual(hits[0]["path"], "wiki/studies.md")


class Upgrade(ProjectCase):
    def test_header_and_doctor_after_a_schema_upgrade(self):
        p = proj.resolve("t")
        p.data.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(p.index_path))
        db.executescript("CREATE TABLE files(path TEXT PRIMARY KEY, source TEXT, mtime REAL); PRAGMA user_version = 1;")
        db.close()
        out = run(["-p", "t", "status", "--hook"])[1]
        self.assertIn("index builds on the first lookup", out)
        self.assertNotIn("0 docs", out)
        (self.wiki / "bench.toml").write_text('[[q]]\nq = "map"\nexpect = ["wiki/index.md"]\n', encoding="utf-8")
        doc = run(["-p", "t", "doctor"])[1]
        self.assertIn("needs a build", doc)
        self.assertIn("bench          skipped", doc)
        run(["-p", "t", "find", "map"])
        self.assertNotIn("builds on the first lookup", run(["-p", "t", "status"])[1])
