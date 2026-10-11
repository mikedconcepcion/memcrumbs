"""Refresh plan, dashboard, doctor and the private bench: the human controls what agents spend tokens on."""
import json
import os

from memcrumbs import project as proj
from test_cli import ProjectCase, run


class PlanCase(ProjectCase):
    def setUp(self):
        super().setUp()
        os.environ["MEMCRUMBS_NO_BROWSER"] = "1"
        w = self.wiki
        (w / "gotchas.md").write_text("---\ntitle: Gotchas\nsummary: traps\nverified: 2020-01-01\n---\n# G\n## Top\n- x\n",
                                      encoding="utf-8")
        (w / "old.md").write_text("---\ntitle: Old runbook\nsummary: s\nverified: 2020-01-01\n---\n# Old\nsteps\n",
                                  encoding="utf-8")
        (w / "fresh.md").write_text("---\ntitle: Fresh\nsummary: s\nverified: 2099-01-01\n---\n# Fresh\nok\n", encoding="utf-8")
        (w / "nodate.md").write_text("# No date\ntext\n", encoding="utf-8")
        run(["-p", "t", "index"])


class PlanTest(PlanCase):
    def test_candidates_and_budgeted_flow(self):
        code, out = run(["-p", "t", "plan", "--json"])
        items = json.loads(out)["items"]
        pages = [c["page"] for c in items]
        self.assertNotIn("fresh", pages)
        self.assertEqual(pages[0], "gotchas")                       # header pages first
        self.assertIn("stale", items[0]["reasons"])
        self.assertIn("unverified", next(c for c in items if c["page"] == "nodate")["reasons"])
        self.assertNotIn("Wiki refresh approved", run(["-p", "t", "status"])[1])   # nothing approved: no nudge
        cost = {c["page"]: c["tokens"] for c in items}
        run(["-p", "t", "plan", "--approve", "gotchas,old", "--budget", str(cost["gotchas"] + cost["old"] - 1)])
        self.assertIn("Wiki refresh approved by the user: 2 page(s) left", run(["-p", "t", "status"])[1])
        code, out = run(["-p", "t", "plan", "next"])
        self.assertIn("refresh wiki/gotchas.md", out)
        self.assertIn("refresh plan: gotchas done", run(["-p", "t", "verify", "gotchas"])[1])
        code, out = run(["-p", "t", "plan", "next"])
        self.assertIn("budget reached", out)                         # the second page does not fit
        run(["-p", "t", "plan", "--budget", "100000"])
        self.assertIn("refresh wiki/old.md", run(["-p", "t", "plan", "next"])[1])
        run(["-p", "t", "verify", "old"])
        self.assertIn("no approved pages left", run(["-p", "t", "plan", "next"])[1])
        self.assertNotIn("Wiki refresh approved", run(["-p", "t", "status"])[1])

    def test_retired_pages_are_never_refresh_candidates(self):
        src = self.repo / "app.py"
        (self.wiki / "replaced.md").write_text("---\ntitle: Replaced\nsummary: s\nverified: 2020-01-01\nstatus: superseded\n"
                                               "superseded_by: old\nsources: [%s]\n---\n# R\n" % src.as_posix(),
                                               encoding="utf-8")
        pages = [c["page"] for c in json.loads(run(["-p", "t", "plan", "--json"])[1])["items"]]
        self.assertNotIn("replaced", pages)

    def test_unknown_page_is_refused(self):
        self.assertEqual(run(["-p", "t", "plan", "--approve", "nope"])[0], 1)


class DashboardTest(PlanCase):
    def test_static_page_is_safe(self):
        secret = "pass" + "word=" + "Rt5!" + "kQm9Zx"
        (self.wiki / "evil.md").write_text("---\ntitle: </script><script>alert(1)</script>\nsummary: %s\n---\n# E\nkey: %s\n" % (secret, secret),
                                           encoding="utf-8")
        code, out = run(["-p", "t", "dashboard"])
        self.assertEqual(code, 0, out)
        page = (proj.resolve("t").data / "dashboard.html").read_text(encoding="utf-8")
        self.assertNotIn("Rt5!", page)
        self.assertNotIn("</script><script>alert", page)              # data cannot close its <script> block
        self.assertNotIn("http://", page.replace("http://www.w3.org", ""))   # no external resources
        self.assertEqual(page.count("<script"), 2)
        blob = page.split('type="application/json">', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<", blob)
        data = json.loads(blob)
        self.assertIn("</script><script>alert(1)</script>", [p["title"] for p in data["pages"]])   # shown as text
        self.assertIn("gotchas", [c["page"] for c in data["plan"]["items"]])

    def test_overview_data_and_content_free_history(self):
        (self.wiki / "linker.md").write_text("---\ntitle: Linker page\nsummary: s\nverified: 2099-01-01\n---\n# L\n"
                                             "See [[old]], [[Fresh]] and [[missing-page]].\n", encoding="utf-8")
        for _ in range(2):                                          # twice on one day: one history line
            self.assertEqual(run(["-p", "t", "dashboard"])[0], 0)
        data = json.loads((proj.resolve("t").data / "dashboard.html").read_text(encoding="utf-8")
                          .split('type="application/json">', 1)[1].split("</script>", 1)[0])
        linker = next(p for p in data["pages"] if p["page"] == "linker")
        self.assertEqual(linker["links"], ["fresh", "old"])           # existing pages only, any case
        self.assertEqual(len(data["wiki"]), len(data["pages"]))       # the reader's text, in page order
        self.assertIn("See [[old]]", data["wiki"][data["pages"].index(linker)])
        self.assertEqual(len(data["daily"]), 30)
        self.assertTrue(data["header"]["sections"])
        self.assertEqual(data["trust"], round(100 * (len(data["pages"]) - len(data["plan"]["items"])) / len(data["pages"])))
        history = (proj.resolve("t").data / "history.jsonl").read_text(encoding="utf-8")
        self.assertEqual(len(history.splitlines()), 1)
        for private in ("Linker", "Old runbook", "gotchas", "wiki/"):
            self.assertNotIn(private, history)


class DoctorTest(PlanCase):
    def test_report_and_shareable_shape(self):
        code, out = run(["-p", "t", "doctor"])
        self.assertIn("index", out)
        self.assertIn("refresh plan", out)
        code, out = run(["-p", "t", "doctor", "--share"])
        shape = json.loads(out)
        self.assertIn("results", shape)
        for private in (str(self.repo), self.tmp.name, "Old runbook"):
            self.assertNotIn(private.replace("\\", "/"), out.replace("\\\\", "/").replace("\\", "/"))


class PrivateBenchTest(PlanCase):
    def test_add_then_measure(self):
        code, out = run(["-p", "t", "bench", "--add", "how do I run the old steps?", "--expect", "old"])
        self.assertEqual(code, 0, out)
        run(["-p", "t", "bench", "--add", "where is main defined", "--expect", str(self.repo / "app.py")])
        text = (self.wiki / "bench.toml").read_text(encoding="utf-8")
        self.assertIn('expect = ["wiki/old.md"]', text)
        code, out = run(["-p", "t", "bench", "--json"])
        self.assertEqual(json.loads(out)["total"]["n"], 2)
        self.assertEqual(run(["-p", "t", "bench", "--add", "q", "--expect", "missing-page"])[0], 1)
