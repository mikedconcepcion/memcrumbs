"""Edge cases: line numbering, junction loops, dates, appends, frontmatter with
mixed newlines, JSON-mode errors, doctor's config schema, wire's reformatted allow list."""
import datetime as dt
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from memcrumbs import claude_settings as cs, freshness, markdown, project as proj, writeset
from memcrumbs.query import clean
from memcrumbs.util import split_lines, walk_stat
from test_cli import ProjectCase, run



class Pure(unittest.TestCase):
    def test_split_lines_counts_newlines_only(self):
        self.assertEqual(split_lines("a\u2028b\x0cc\r\nd\n"), ["a\u2028b\x0cc", "d"])
        self.assertEqual(split_lines(""), [])
        self.assertEqual(split_lines("x"), ["x"])

    def test_control_characters_leave_a_query(self):
        self.assertEqual(clean("disk\x00full\tnow"), "disk full now")

    def test_dates_that_do_not_exist_or_lie_ahead_are_not_fresh(self):
        today = dt.date(2026, 10, 11)
        self.assertIsNone(freshness.parse_date("2026-02-30", today))
        self.assertIsNone(freshness.parse_date("2099-01-01", today))
        self.assertIsNone(freshness.days_since("2099-01-01", today))
        self.assertEqual(freshness.days_since("2026-10-12", today), 0)     # one day of clock skew
        self.assertEqual(freshness.days_since("2026-10-01", today), 10)

    def test_frontmatter_edit_keeps_each_lines_own_newline(self):
        text = "---\r\ntitle: a\nverified: 2020-01-01\r\ntags:\n  - x\n  - y\n---\r\nbody\n"
        new = markdown.set_frontmatter(text, {"verified": "2026-10-11"})
        self.assertEqual(new, text.replace("2020-01-01", "2026-10-11"))
        self.assertEqual(markdown.frontmatter(markdown.set_frontmatter(text, {"tags": ["q"], "new": "v"}))[0],
                         {"title": "a", "verified": "2020-01-01", "tags": ["q"], "new": "v"})

    def test_reformatted_allow_list_still_loses_only_our_rules(self):
        ours = ["Bash(memcrumbs find:*)", "Bash(memcrumbs page:*)"]
        text = '{\n\t"permissions": {\n\t\t"allow": [\n\t\t\t"Bash(git status)",\n\t\t\t"Bash(memcrumbs find:*)",' \
               '\n\t\t\t"Bash(memcrumbs page:*)"\n\t\t]\n\t}\n}\n'
        out = cs.remove_items(text, ("permissions", "allow"), ours)
        self.assertEqual(json.loads(out)["permissions"]["allow"], ["Bash(git status)"])
        self.assertEqual(out, '{\n\t"permissions": {\n\t\t"allow": [\n\t\t\t"Bash(git status)"\n\t\t]\n\t}\n}\n')
        only = cs.remove_items('{"permissions": {"allow": ["Bash(memcrumbs find:*)"]}}', ("permissions", "allow"), ours)
        self.assertEqual(json.loads(only), {"permissions": {"allow": []}})
        self.assertIsNone(cs.remove_items('{"permissions": {"allow": ["x"]}}', ("permissions", "allow"), ours))


class Walk(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "junctions are a Windows feature")
    def test_a_junction_back_to_the_root_is_not_followed(self):
        import _winapi
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "wiki"
            (root / "sub").mkdir(parents=True)
            (root / "sub" / "a.md").write_text("# a\n", encoding="utf-8")
            _winapi.CreateJunction(str(root), str(root / "sub" / "loop"))
            try:
                found = [p.name for p, _, _ in walk_stat(root, ["**/*.md"], [])]
            finally:
                os.rmdir(root / "sub" / "loop")
            self.assertEqual(found, ["a.md"])


class Project(ProjectCase):
    def project(self):
        return proj.resolve("t")

    def test_append_matches_the_file(self):
        p = self.project()
        f = self.wiki / "journal" / "x.md"
        f.parent.mkdir()
        f.write_bytes(b"- one")                                     # no final newline
        writeset.append_text(p, f, "- two\n")
        self.assertEqual(f.read_bytes(), b"- one\n- two\n")
        f.write_bytes(b"- one\r\n")
        writeset.append_text(p, f, "- two\n")
        self.assertEqual(f.read_bytes(), b"- one\r\n- two\r\n")
        f.write_bytes("\ufeff- one\n".encode("utf-16-le"))           # a UTF-16 journal stays UTF-16
        writeset.append_text(p, f, "- two\n")
        self.assertEqual(f.read_bytes().decode("utf-16-le"), "\ufeff- one\n- two\n")

    def test_a_symlinked_wire_target_is_refused(self):
        p = self.project()
        outside = Path(self.tmp.name) / "elsewhere.json"
        outside.write_text("{}", encoding="utf-8")
        link = self.repo / "settings.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("no symlink privilege")
        with self.assertRaises(writeset.WriteSetError):
            writeset.write_text(p, link, "{}", extra=[link])

    def test_a_future_verified_date_is_flagged(self):
        (self.wiki / "decisions").mkdir()
        (self.wiki / "decisions" / "d.md").write_text(
            "---\ntitle: D\nsummary: s\nverified: 2099-01-01\n---\n# D\n", encoding="utf-8")
        code, out = run(["-p", "t", "check", "--all"])
        self.assertIn("not a real date or is in the future", out)

    def test_json_mode_reports_a_refusal_as_an_error_field(self):
        code, out = run(["-p", "t", "verify", "index", "--date", "2026-02-30", "--json"])
        self.assertEqual(code, 1)
        self.assertIn("not a real YYYY-MM-DD date", json.loads(out)["error"])

    def test_doctor_names_unknown_tables_and_counts_malformed_deny_lines(self):
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "[serach]\nsynonyms = []\n", encoding="utf-8")
        (self.projects / "t" / "secrets.deny").write_text("sha256:12:not-a-hash-SECRETISH\n", encoding="utf-8")
        code, out = run(["-p", "t", "doctor"])
        self.assertIn("[serach]", out)
        self.assertIn("1 malformed sha256", out)
        self.assertNotIn("SECRETISH", out)

    def test_two_sources_over_one_file_index_it_once(self):
        (self.repo / "notes.md").write_text("# Notes\n## Kiln\nthe kiln runs hot\n", encoding="utf-8")
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '[[docs]]\nname = "a"\nroot = "../../repo"\n'
                       '[[docs]]\nname = "b"\nroot = "../../repo"\n', encoding="utf-8")
        for _ in range(2):
            code, out = run(["-p", "t", "find", "kiln", "runs", "hot", "--json"])
            self.assertEqual(code, 0)
            hits = [h for h in json.loads(out)["hits"] if h["path"].endswith("notes.md")]
            self.assertEqual(len({(h["path"], h.get("loc")) for h in hits}), len(hits))
            self.assertTrue(hits)


class Grade(ProjectCase):
    """Small behaviours: the header cap, `about` labels, import commits."""

    def test_a_rule_past_the_header_cap_says_so(self):
        (self.wiki / "rules.md").write_text("# Rules\n## Top\n" + "".join("- rule %d\n" % i for i in range(8)),
                                            encoding="utf-8")
        out = run(["-p", "t", "rule", "Never restart the kiln controller during a firing."])[1]
        self.assertIn("line 9 of ## Top and the header shows 8", out)

    def test_about_names_every_group(self):
        from memcrumbs.cites import describe
        hits = [dict(what=w, status=s) for w, s in (("decision", "rejected"), ("memory", ""), ("memory", ""),
                                                    ("legacy", ""), ("journal", ""), ("journal", ""), ("wiki", ""))]
        self.assertEqual(describe(hits), "1 decision (REJECTED), 2 memory notes, 1 legacy note, 2 journal entries, "
                                         "1 page")

    def test_a_bound_fact_counts_for_its_file(self):
        (self.repo / "VERSION").write_text("2.4.1\n", encoding="utf-8")
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '[facts.bind.live_version]\nfrom = "%s"\n'
                       % (self.repo / "VERSION").as_posix(), encoding="utf-8")
        out = run(["-p", "t", "about", str(self.repo / "VERSION")])[1]
        self.assertIn("1 fact", out)
        self.assertIn("live_version", out)

    def test_the_first_import_is_not_a_source_change(self):
        git = lambda *a: subprocess.run(["git", "-C", str(self.repo)] + list(a), capture_output=True, check=True)
        try:
            git("init", "-q")
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("no git")
        git("add", "app.py")
        git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "import")
        page = self.wiki / "app.md"
        page.write_text("---\ntitle: App\nsummary: s\nverified: 2020-01-01\nsources: [%s]\n---\n# App\n"
                        % (self.repo / "app.py").as_posix(), encoding="utf-8")
        freshness._GIT.clear()
        self.assertEqual(freshness.page_freshness(self.project()), [])
        (self.repo / "app.py").write_text("def main():\n    return 2\n", encoding="utf-8")
        git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam", "change")
        freshness._GIT.clear()
        self.assertEqual(len(freshness.page_freshness(self.project())), 1)

    def project(self):
        return proj.resolve("t")


if __name__ == "__main__":
    unittest.main()
