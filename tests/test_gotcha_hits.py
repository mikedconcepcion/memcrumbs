"""A trap that bites again is counted in its gotcha line; at two bites a ## More line is offered for ## Top, and a
Top line that stops biting is flagged after 90 days."""
import datetime as dt
import json
from unittest import mock

from memcrumbs import gotcha_hits, project as proj, review
from memcrumbs.output import Out
from test_cli import ProjectCase, run

GOTCHAS = ("---\ntitle: Gotchas\nsummary: traps\n---\n# Gotchas\n\n## Top\n"
           "- The kiln controller drops serial at 115200 baud: use 9600.\n\n## More\n"
           "- Old backups live on the second shelf drive.\n")


class GotchaHits(ProjectCase):
    def setUp(self):
        super().setUp()
        (self.wiki / "gotchas.md").write_text(GOTCHAS, encoding="utf-8")
        run(["-p", "t", "status"])                                  # first adoption: today's lines are reviewed

    def text(self):
        return (self.wiki / "gotchas.md").read_text(encoding="utf-8")

    def test_a_trap_that_bites_twice_is_offered_for_top_and_waits_for_review(self):
        today = dt.date.today().isoformat()
        out = run(["-p", "t", "gotcha", "--add", "Bash heredocs collapse double backslashes in Windows paths"])[1]
        self.assertIn("added under More (hit 1)", out)
        self.assertIn("- Bash heredocs collapse double backslashes in Windows paths (hit 1, last %s)\n" % today,
                      self.text())
        self.assertEqual(json.loads(run(["-p", "t", "suggest", "--kind", "gotcha", "--json"])[1])["suggestions"], [])
        out = run(["-p", "t", "gotcha", "--hit", "heredoc backslashes"])[1]
        self.assertIn("hit 2 (More)", out)
        self.assertIn("memcrumbs suggest --kind gotcha", out)
        found = json.loads(run(["-p", "t", "suggest", "--kind", "gotcha", "--json"])[1])["suggestions"]
        self.assertEqual(len(found), 1)
        self.assertIn("the fewest hits in 90 days: The kiln controller drops serial", " ".join(found[0]["evidence"]))
        run(["-p", "t", "suggest", "apply", found[0]["id"]])
        top = self.text().split("## More")[0]
        self.assertIn("Bash heredocs collapse", top)                  # moved to Top
        status = run(["-p", "t", "status"])[1]
        self.assertNotIn("Bash heredocs", status)                     # it waits for the owner's review
        self.assertIn("1 new rule/gotcha line", status)
        with mock.patch.object(review, "confirm"):
            run(["-p", "t", "review", "--approve", "all"])
        status = run(["-p", "t", "status"])[1]
        self.assertIn("Bash heredocs collapse double backslashes in Windows paths", status)
        self.assertNotIn("(hit 2", status)                            # the count stays in the page
        run(["-p", "t", "gotcha", "--hit", "kiln controller serial baud"])
        self.assertIn("(hit 1, last", self.text().split("## More")[0])
        status = run(["-p", "t", "status"])[1]
        self.assertIn("The kiln controller drops serial", status)     # a counted line stays reviewed

    def test_words_that_match_nothing_or_two_lines_are_refused(self):
        self.assertEqual(run(["-p", "t", "gotcha", "--hit", "printer toner"])[0], 1)
        (self.wiki / "gotchas.md").write_text(GOTCHAS + "- Old backups live on the third shelf drive.\n",
                                              encoding="utf-8")
        code, _ = run(["-p", "t", "gotcha", "--hit", "old backups shelf drive"])
        self.assertEqual(code, 1)
        self.assertEqual(self.text(), GOTCHAS + "- Old backups live on the third shelf drive.\n")   # unchanged

    def test_a_top_line_that_stops_biting_is_flagged_after_90_days(self):
        p = proj.resolve("t")
        today = dt.date.today()
        self.assertEqual(gotcha_hits.findings(p, today), [])           # counting starts now
        self.assertEqual(gotcha_hits.findings(p, today + dt.timedelta(days=30)), [])
        later = today + dt.timedelta(days=91)
        found = gotcha_hits.findings(p, later)
        self.assertEqual(len(found), 1)
        self.assertIn("no hit in 90 days", found[0][2])
        gotcha_hits.hit(Out("gotcha", None, p.redact), p, "kiln controller serial", today=later)
        self.assertEqual(gotcha_hits.findings(p, later), [])           # it bit: still earning its place

    def test_crlf_pages_stay_crlf(self):
        (self.wiki / "gotchas.md").write_bytes(GOTCHAS.replace("\n", "\r\n").encode())
        run(["-p", "t", "gotcha", "--add", "A new trap with the printer queue"])
        run(["-p", "t", "gotcha", "--hit", "printer queue trap"])
        raw = (self.wiki / "gotchas.md").read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertIn(b"- A new trap with the printer queue (hit 2, last ", raw)
        self.assertIn("A new trap", run(["-p", "t", "gotcha"])[1])
