"""Freshness on hits, reverse lookup, single-sourced
facts, symptoms, decision evidence, runbook shape, two-way supersede, near-duplicates, the check baseline."""
import json
import os
import time

from memcrumbs import project as proj, wire
from test_cli import ProjectCase, run


def page(wiki, rel, text):
    p = wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


class FreshnessAndCitations(ProjectCase):
    def setUp(self):
        super().setUp()
        src = self.repo / "app.py"
        old = time.time() - 30 * 86400
        page(self.wiki, "components/app.md", "---\ntitle: App service\nsummary: s\nverified: 2020-01-02\n"
                                             "sources: [%s]\n---\n# App\nThe app service entry point.\n" % src.as_posix())
        page(self.wiki, "components/calm.md", "---\ntitle: Calm service\nsummary: s\nverified: 2099-01-01\n"
                                              "sources: [%s]\n---\n# Calm\nThe calm service.\n" % src.as_posix())
        page(self.wiki, "decisions/2026-01-01-rewrite.md", "---\ntitle: Rewrite the entry point\nsummary: s\n"
             "verified: 2026-01-01\n---\n# Rewrite\n\n| Option | Verdict |\n|---|---|\n"
             "| Async rewrite of app.py | REJECTED |\n")
        os.utime(self.repo / "app.py", (old, old))
        run(["-p", "t", "index"])

    def test_hits_carry_source_changes_computed_at_index_time(self):
        out = run(["-p", "t", "find", "service"])[1]
        app = next(ln for ln in out.splitlines() if "components/app.md" in ln)
        calm = next(ln for ln in out.splitlines() if "components/calm.md" in ln)
        self.assertIn("SRC-CHANGED 30d", app)                  # app.py changed after 2020-01-02
        self.assertNotIn("SRC-CHANGED", calm)                  # verified after the change

    def test_about_lists_verdicts_first_and_code_hits_say_cited_by(self):
        code, out = run(["-p", "t", "about", str(self.repo / "app.py")])
        self.assertEqual(code, 0, out)
        lines = out.splitlines()
        self.assertIn("cited by 1 decision (REJECTED)", lines[0])
        self.assertIn("decisions/2026-01-01-rewrite.md", lines[1])
        self.assertIn("REJECTED", lines[1])
        self.assertIn("app.md", out)
        hits = run(["-p", "t", "find", "main entry point", "-k", "code"])[1]
        self.assertIn("cited by: 1 decision (REJECTED) · memcrumbs about app.py", hits)
        tail = run(["outline", str(self.repo / "app.py"), "-p", "t"])[1]
        self.assertIn("cited by: 1 decision (REJECTED)", tail)
        data = json.loads(run(["-p", "t", "about", "app.py", "--json"])[1])
        self.assertEqual(data["cited_by"][0]["status"], "rejected")


class Facts(ProjectCase):
    def setUp(self):
        super().setUp()
        (self.repo / "VERSION").write_text("2.4.0\n", encoding="utf-8")
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '\n[facts.bind.live_version]\nfrom = "../../repo/VERSION"\n'
                       "pattern = '^(\\S+)'\n", encoding="utf-8")
        page(self.wiki, "facts.md", "---\ntitle: Facts\nsummary: current values\nverified: 2026-10-01\n---\n# Facts\n\n"
             "| key | value | about | source | verified |\n|---|---|---|---|---|\n"
             "| live_version | 2.3.9 | live version | repo/VERSION | 2026-10-01 |\n"
             "| web_port | 8080 | web port | config | 2026-10-01 |\n")
        page(self.wiki, "ops.md", "---\ntitle: Ops\nsummary: s\nverified: 2026-10-01\n---\n# Ops\n"
             "The live version is 2.3.1 on the server.\nThe web port: 9090.\nDeploys show {{fact:live_version}}.\n"
             "On 2026-01-05 the live version was 1.9.0.\n## History\nThe web port was 7070 in the old layout.\n")

    def test_lookup_binding_conflicts_and_substitution(self):
        out = run(["-p", "t", "fact", "live_version"])[1]
        self.assertIn("live_version = 2.4.0", out)                        # the binding wins
        self.assertIn("the table says 2.3.9: update it", out)
        self.assertIn("web_port = 8080", run(["-p", "t", "fact", "web port"])[1])
        check = run(["-p", "t", "check"])[1]
        self.assertIn("states live_version = 2.3.1", check)
        self.assertIn("states web_port = 9090", check)
        self.assertNotIn("1.9.0", check)                                  # dated line
        self.assertNotIn("7070", check)                                   # history section
        self.assertIn("the table says 2.3.9", check)
        self.assertIn("Deploys show 2.4.0", run(["-p", "t", "page", "ops"])[1])
        hit = run(["-p", "t", "find", "current live version"])[1].splitlines()[0]
        self.assertTrue(hit.startswith("[fact] live_version"), hit)

    def test_a_binding_never_reads_a_never_index_file(self):
        (self.repo / ".env").write_text("TOKEN_VERSION=9.9.9\n", encoding="utf-8")
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '\n[facts.bind.web_port]\nfrom = "../../repo/.env"\n'
                       "pattern = '=(\\S+)'\n", encoding="utf-8")
        out = run(["-p", "t", "fact", "web_port"])[1]
        self.assertIn("web_port = 8080", out)                                   # the table value, not the file's
        self.assertIn("never_index", out)
        self.assertNotIn("9.9.9", out)

    def test_unknown_key_and_code_spans(self):
        page(self.wiki, "x.md", "---\ntitle: X\nsummary: s\nverified: 2026-10-01\n---\n# X\nuse {{fact:nope}}; "
             "syntax `{{fact:shown_as_code}}`\n")
        check = run(["-p", "t", "check"])[1]
        self.assertIn("unknown fact {{fact:nope}}", check)
        self.assertNotIn("shown_as_code", check)
        self.assertIn("`{{fact:shown_as_code}}`", run(["-p", "t", "page", "x"])[1])


class Records(ProjectCase):
    def test_symptom_evidence_runbook_supersede(self):
        run(["-p", "t", "incident", "Mailer stopped", "--symptom", "no reminder emails, task ends in 0 seconds",
             "--cause", "BOM", "--fix", "save without BOM", "--guard", "check rejects BOM"])
        inc = next((self.wiki / "incidents").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("symptom: no reminder emails, task ends in 0 seconds", inc)
        self.assertIn("## Guard", inc)
        hit = run(["-p", "t", "find", "task ends in 0 seconds"])[1].splitlines()[0]
        self.assertIn("symptom:", hit)
        run(["-p", "t", "decision", "Use queue", "--status", "rejected", "--why", "slower",
             "--considered", "queue; cron", "--evidence", "p95 40 ms vs 12 ms (bench run)", "--revisit-if", "load x10"])
        dec = next((self.wiki / "decisions").glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("## Options considered\n- queue\n- cron", dec)
        self.assertIn("## Revisit if\nload x10", dec)
        page(self.wiki, "decisions/2026-01-01-bare.md", "---\ntitle: Bare\nsummary: s\nverified: 2026-01-01\n"
             "status: parked\n---\n# Bare\nnothing\n")
        page(self.wiki, "incidents/2026-01-01-old.md", "---\ntitle: Old\nsummary: s\nverified: 2026-01-01\n---\n# O\n")
        page(self.wiki, "runbooks/wipe.md", "---\ntitle: Wipe the cache\nsummary: s\nverified: 2026-01-01\n"
             "destructive: true\ntested: soon\n---\n# Wipe\n## Steps\n1. delete it\n")
        page(self.wiki, "runbooks/good.md", "---\ntitle: Good\nsummary: s\nverified: 2026-01-01\n---\n# G\n"
             "## Preconditions\nx\n## Steps\ny\n## Verify\nz\nRollback: none (irreversible)\n")
        check = run(["-p", "t", "check"])[1]
        self.assertIn("2026-01-01-bare.md: parked without evidence", check)
        self.assertNotIn("use-queue.md: rejected without evidence", check)
        self.assertIn("2026-01-01-old.md: no symptom", check)
        self.assertIn("wipe.md: runbook without preconditions, a verify step, a rollback", check)
        self.assertIn("wipe.md: tested must be YYYY-MM-DD", check)
        self.assertNotIn("good.md: runbook", check)
        self.assertIn("DESTRUCTIVE", run(["-p", "t", "find", "wipe the cache"])[1].splitlines()[0])
        self.assertIn("DESTRUCTIVE", run(["-p", "t", "page", "wipe"])[1].splitlines()[0])
        page(self.wiki, "old-way.md", "---\ntitle: Old way\nsummary: s\nverified: 2026-01-01\n---\n# Old\n")
        page(self.wiki, "new-way.md", "---\ntitle: New way\nsummary: s\nverified: 2026-01-01\n---\n# New\n")
        page(self.wiki, "lone.md", "---\ntitle: Lone\nsummary: s\nverified: 2026-01-01\nstatus: superseded\n"
             "superseded_by: new-way\n---\n# L\n")
        self.assertIn("new-way.md: replaces [[lone]]", run(["-p", "t", "check"])[1])
        run(["-p", "t", "supersede", "old-way", "--by", "new-way"])
        self.assertIn("supersedes: old-way", (self.wiki / "new-way.md").read_text(encoding="utf-8"))

    def test_near_duplicates_and_the_baseline(self):
        for name in ("restore-db", "restore-database"):
            page(self.wiki, name + ".md", "---\ntitle: Restore the bookings database from backup\nsummary: restore "
                 "bookings database backup copy nightly snapshot\nverified: 2026-01-01\n---\n# R\n")
        self.assertIn("near-duplicate of", run(["-p", "t", "check", "--dupes"])[1])
        self.assertNotIn("near-duplicate", run(["-p", "t", "check"])[1])
        before = run(["-p", "t", "check"])[1]
        self.assertIn("frontmatter missing", before)                    # index.md has none
        code, out = run(["-p", "t", "check", "--baseline"])
        self.assertIn("baseline:", out)
        after = run(["-p", "t", "check"])[1]
        self.assertNotIn("frontmatter missing", after)
        self.assertIn("known since the baseline", after)
        page(self.wiki, "new.md", "# no frontmatter\n")
        new = run(["-p", "t", "check"])[1]
        self.assertIn("new.md: frontmatter missing", new)
        self.assertEqual(run(["-p", "t", "check", "--strict"])[0], 1)     # a new warning fails strict
        self.assertIn("index.md: frontmatter missing", run(["-p", "t", "check", "--all"])[1])
        secret = "pass" + "word=" + "Zq7!" + "xKm4Rt"
        page(self.wiki, "leak.md", "---\ntitle: L\nsummary: s\nverified: 2026-01-01\n---\n%s\n" % secret)
        run(["-p", "t", "check", "--baseline"])
        self.assertEqual(run(["-p", "t", "check"])[0], 1)                 # errors are never baselined


class SkillProtocol(ProjectCase):
    def test_skill_says_how_to_work_long_and_knows_the_new_commands(self):
        text = (wire.TPL / "skill.md").read_text(encoding="utf-8")
        for s in ("Long or risky work", "memcrumbs about", "memcrumbs fact", "SRC-CHANGED", "DESTRUCTIVE",
                  "--symptom", "{{fact:key}}"):
            self.assertIn(s, text)
        import hashlib
        self.assertNotIn("sha256:" + hashlib.sha256((wire.TPL / "skill.md").read_bytes()).hexdigest(), wire.OLD_SKILLS)
        rules = proj.resolve("t")
        from memcrumbs import claude_settings
        self.assertIn("Bash(memcrumbs about:*)", claude_settings.allow_rules(rules))
