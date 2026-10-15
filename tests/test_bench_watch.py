"""`check` runs the project's own bench and explains every new miss: a buried answer or a stale expectation."""
import json
import os
import time

from memcrumbs import bench_watch, project as proj
from test_cli import ProjectCase, run


def page(wiki, name, title, summary, body):
    (wiki / name).write_text("---\ntitle: %s\nsummary: %s\nverified: 2026-10-01\n---\n# %s\n%s\n" % (
        title, summary, title, body), encoding="utf-8")


class BenchWatch(ProjectCase):
    def setUp(self):
        super().setUp()
        page(self.wiki, "overview.md", "Studio overview", "what runs where in the studio",
             "The kiln controller restarts at night. Bookings live on the web server.")
        (self.wiki / "bench.toml").write_text('[[q]]\nid = "real-001"\nq = "when does the kiln controller restart"\n'
                                              'expect = ["wiki/overview.md"]\n', encoding="utf-8")

    def check(self):
        code, text = run(["-p", "t", "check", "--json"])            # once: each run records the ranks it saw
        return code, text, [f for f in json.loads(text)["findings"] if f["where"] == "wiki/bench.toml"]

    def test_a_new_page_that_takes_first_place_is_explained(self):
        code, _, found = self.check()
        self.assertEqual((code, found), (0, []))                     # the first run records the ranks
        time.sleep(0.05)
        page(self.wiki, "kiln-controller-restart.md", "Kiln controller restart",
             "when and why the kiln controller restarts each night",
             "The kiln controller restarts at 02:00 every night; the kiln controller restart clears its fault latch. "
             "Kiln controller restart: logged in the controller journal.")
        for name in ("a", "b", "c"):                                 # pages that push the old answer out of the top 3
            page(self.wiki, "kiln-%s.md" % name, "Kiln controller restart notes %s" % name,
                 "kiln controller restart notes", "When does the kiln controller restart? Notes %s." % name)
        code, text, found = self.check()
        self.assertEqual(code, 0, text)                              # an info finding never fails the write
        self.assertEqual(len(found), 1, found)
        msg = found[0]["message"]
        self.assertEqual(found[0]["level"], "I")
        self.assertIn("new miss real-001 'when does the kiln controller restart'", msg)
        self.assertIn("written since the last check", msg)
        self.assertIn("memcrumbs supersede overview --by", msg)
        self.assertIn("memcrumbs bench --expect-add real-001", msg)
        new = msg.rsplit(" ", 1)[1]
        out = run(["-p", "t", "bench", "--expect-add", "real-001", new])[1]
        self.assertIn("now also expects wiki/", out)
        self.assertIn('expect = ["wiki/overview.md", "wiki/', (self.wiki / "bench.toml").read_text(encoding="utf-8"))
        self.assertEqual(self.check()[2], [])                        # fixed: no miss left to explain
        self.assertIn("already expects", run(["-p", "t", "bench", "--expect-add", "real-001", new])[1])

    def test_no_bench_no_run_and_a_bad_file_is_a_warning(self):
        os.remove(self.wiki / "bench.toml")
        self.assertEqual(bench_watch.findings(proj.resolve("t"), None), [])
        (self.wiki / "bench.toml").write_text('[[q]]\nid = "x"\n', encoding="utf-8")
        self.assertEqual(self.check()[2][0]["level"], "W")
        self.assertEqual(run(["-p", "t", "bench", "--expect-add", "nope", "overview"])[0], 1)
