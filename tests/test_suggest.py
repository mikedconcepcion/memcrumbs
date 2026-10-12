"""`memcrumbs suggest` and its kinds: duplicates, links, splits (wiki only), guards from gotchas,
knowledge gaps from lookups and transcripts."""
import datetime as dt
import json
import os
import time
from pathlib import Path
from unittest import mock

from memcrumbs import project as proj, suggest, suggest_flow, suggest_guard, suggest_skill, transcripts
from test_cli import ProjectCase, run


def page(wiki, rel, text):
    p = wiki / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def ids(kind):
    return [s["id"] for s in json.loads(run(["-p", "t", "suggest", "--kind", kind, "--json"])[1])["suggestions"]]


class Framework(ProjectCase):
    def setUp(self):
        super().setUp()
        for name, v in (("restore-db", "2026-01-01"), ("restore-database", "2026-03-01")):
            page(self.wiki, name + ".md", "---\ntitle: Restore the bookings database from backup\nsummary: restore "
                 "bookings database backup copy nightly snapshot\nverified: %s\n---\n# R\nsteps\n" % v)

    def test_list_show_apply_undo_dismiss(self):
        self.assertNotIn("new suggestion", run(["-p", "t", "status"])[1])     # the header never scans
        run(["-p", "t", "check"])                                               # the daily scan runs after it
        self.assertIn("1 new suggestion: tell the owner; list them only on their word", run(["-p", "t", "status"])[1])
        out = run(["-p", "t", "suggest"])[1]
        self.assertIn("near-duplicate pages", out)
        self.assertNotIn("new suggestion", run(["-p", "t", "status"])[1])                    # seen now
        sid = ids("dupes")[0]
        shown = run(["-p", "t", "suggest", "show", sid])[1]
        self.assertIn("+status: superseded", shown)
        self.assertIn("supersede wiki/restore-db.md by wiki/restore-database.md", shown)   # the newer one stays
        before = (self.wiki / "restore-db.md").read_bytes()
        run(["-p", "t", "suggest", "apply", sid])
        self.assertIn("superseded_by: restore-database", (self.wiki / "restore-db.md").read_text(encoding="utf-8"))
        self.assertIn("supersedes: restore-db", (self.wiki / "restore-database.md").read_text(encoding="utf-8"))
        run(["-p", "t", "suggest", "undo", sid])
        self.assertEqual((self.wiki / "restore-db.md").read_bytes(), before)               # every byte back
        run(["-p", "t", "suggest", "dismiss", sid, "--for", "14d"])
        self.assertEqual(ids("dupes"), [])
        st = suggest.load_state(proj.resolve("t"))
        st["decided"][sid]["until"] = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        suggest.save_state(proj.resolve("t"), st)
        self.assertEqual(ids("dupes"), [sid])                                               # still true: back
        run(["-p", "t", "suggest", "dismiss", sid, "--never"])
        self.assertEqual(ids("dupes"), [])

    def test_links_splits_and_plugin_kinds(self):
        src = self.repo / "app.py"
        for name in ("alpha", "beta"):
            page(self.wiki, name + ".md", "---\ntitle: %s\nsummary: s\nverified: 2026-01-01\nsources: [%s]\n---\n# %s\n"
                 % (name, src.as_posix(), name))
        sid = ids("link")[0]
        run(["-p", "t", "suggest", "apply", sid])
        self.assertIn("## Related\n\n- [[beta]]: also cites app.py", (self.wiki / "alpha.md").read_text(encoding="utf-8"))
        self.assertEqual(ids("link"), [])
        page(self.wiki, "huge.md", "---\ntitle: Huge\nsummary: s\nverified: 2026-01-01\n---\n# H\n" +
             "".join("## Part %d\n%s\n" % (i, "line\n" * 40) for i in range(10)))
        sid = ids("split")[0]
        out = run(["-p", "t", "suggest", "apply", sid])[1]
        self.assertIn("has no mechanical patch; the agent does it", out)
        from memcrumbs import suggest as sg
        api = mock.Mock(suggesters={"mine": lambda project, cheap_only=False: [
            sg.Suggestion("mine", "k", "a plugin kind", "do it")]})
        found, _ = sg.detect(proj.resolve("t"), api, ["mine"])
        self.assertEqual([s.why for s in found], ["a plugin kind"])


class Guards(ProjectCase):
    def setUp(self):
        super().setUp()
        page(self.wiki, "gotchas.md", "---\ntitle: G\nsummary: s\nverified: 2026-09-01\n---\n# G\n## Top\n"
             "- 2026-09-02: never run `rm -rf` in a hurry; it took the bookings with it.\n")
        self.settings = self.repo / ".claude" / "settings.json"

    def test_prefixes(self):
        cases = {"rm -rf /var/x": "rm -rf", "git push --force origin main": "git push --force",
                 "Remove-Item -Recurse -Force D:/x/*": "Remove-Item -Recurse -Force", "Set-Content": "Set-Content",
                 "config.json": None, "ExecutionTimeLimit": None, "schtasks /Delete /TN x": "schtasks"}
        for span, want in cases.items():
            self.assertEqual(suggest_guard.prefix(span), want, span)

    def test_deny_rule_apply_undo_and_unguard(self):
        sid = ids("guard")[0]
        self.assertNotEqual(run(["-p", "t", "suggest", "apply", sid])[0], 0)                  # needs --outside-wiki
        self.assertFalse(self.settings.exists())
        rules = ["Bash(rm *-rf)", "Bash(rm *-rf *)", "PowerShell(rm *-rf)", "PowerShell(rm *-rf *)"]
        run(["-p", "t", "suggest", "apply", sid, "--outside-wiki"])                          # ask by default
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["permissions"], {"ask": rules})
        self.assertEqual(ids("guard"), [])                                                   # already in place
        run(["-p", "t", "suggest", "undo", sid])
        self.assertFalse(self.settings.exists())                                             # it did not exist
        run(["-p", "t", "suggest", "apply", sid, "--outside-wiki", "--deny"])                # the owner's choice
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["permissions"], {"deny": rules})
        page(self.wiki, "gotchas.md", "---\ntitle: G\nsummary: s\nverified: 2026-09-01\n---\n# G\n## Top\n- other\n")
        un = ids("unguard")
        self.assertEqual(len(un), 1)
        self.assertNotEqual(run(["-p", "t", "suggest", "apply", un[0], "--outside-wiki"])[0], 0)   # loosens a guard:
        from memcrumbs import review                                                        # a human only
        with mock.patch.object(review, "confirm"):
            run(["-p", "t", "suggest", "apply", un[0], "--outside-wiki"])
        self.assertNotIn("rm -rf", self.settings.read_text(encoding="utf-8"))

    def test_the_forbidden_clause_the_matcher_and_ask(self):
        page(self.wiki, "gotchas.md", "---\ntitle: G\nsummary: s\nverified: 2026-09-01\n---\n# G\n## Top\n"
             "- Read configs with `Get-Content -Encoding UTF8`; never `Set-Content -Encoding UTF8` on config files "
             "(it adds a BOM).\n- Never `git push --force` without asking first.\n")
        found = {f[3]: f for f in suggest_guard.forbidden(proj.resolve("t"))}
        self.assertEqual(sorted(found), ["Set-Content -Encoding UTF8", "git push --force"])   # not Get-Content
        self.assertEqual(found["Set-Content -Encoding UTF8"][5], "ask")                     # about config files
        self.assertEqual(found["git push --force"][5], "ask")                               # conditional
        self.assertEqual(suggest_guard.rules("Set-Content -Encoding UTF8"),               # no Bash twin; ends at
                         ["PowerShell(Set-Content *-Encoding UTF8)", "PowerShell(Set-Content *-Encoding UTF8 *)"])
        m = suggest_guard.matches
        self.assertTrue(m("Set-Content -Encoding UTF8", "set-content -path b.json -encoding utf8"))   # -Path first
        self.assertFalse(m("Set-Content -Encoding UTF8", "get-content a.json -encoding utf8"))
        self.assertTrue(m("rm -rf", "rm -rf cache/"))
        for safe in ("set-content x -encoding utf8nobom", "set-content -encoding utf8bom -path x"):     # safe forms
            self.assertFalse(m("Set-Content -Encoding UTF8", safe), safe)
        self.assertTrue(m("Set-Content -Encoding UTF8", "set-content -encoding utf8 -path x"))       # value mid-call
        for safe in ("git push --force-with-lease", "git push --force-with-lease origin main"):
            self.assertFalse(m("git push --force", safe), safe)
        for bad in ("git push --force", "git push origin main --force", "git -c x=y push --force origin"):
            self.assertTrue(m("git push --force", bad), bad)
        self.assertTrue(transcripts.nested('powershell -Command "Set-Content x -Encoding UTF8"'))
        self.assertEqual(transcripts.shapes("Get-Content a | Set-Content -Path b -Encoding UTF8"),
                         ["get-content a", "set-content -path b -encoding utf8"])           # each part of a pipe

    def test_every_word_is_kept_ask_is_the_default_and_hosts_are_a_scope(self):
        page(self.wiki, "gotchas.md", "---\ntitle: G\nsummary: s\nverified: 2026-09-01\n---\n# G\n## Top\n"
             "- Never `docker system prune -a` on the build host.\n- Do not `chmod -R 777` anything.\n"
             "- Never `npm install --force` here.\n")
        found = {f[3]: f[5] for f in suggest_guard.forbidden(proj.resolve("t"))}
        self.assertEqual(found, {"docker system prune -a": "ask", "chmod -R 777": "deny", "npm install --force": "deny"})
        m = suggest_guard.matches
        for harmless in ("docker system df", "docker system info", "docker system prune"):
            self.assertFalse(m("docker system prune -a", harmless), harmless)
        self.assertTrue(m("docker system prune -a", "docker system prune -a -f"))
        for harmless in ("chmod -R 755 x", "chmod -R u+w x", "chmod 777 x"):
            self.assertFalse(m("chmod -R 777", harmless), harmless)
        self.assertTrue(m("chmod -R 777", "chmod -R 777 x"))
        self.assertFalse(m("npm install --force", "npm install"))
        self.assertFalse(m("npm install --force", "npm uninstall --force"))                # not glued to a word
        self.assertFalse(m("git push --force", "git stash push --force"))
        self.assertTrue(m("git push --force", "git -C repo push --force"))                 # options first still count
        offers = {x["why"]: x for x in json.loads(run(["-p", "t", "suggest", "--kind", "guard", "--json"])[1])["suggestions"]}
        self.assertTrue(all(x["action"].startswith("ask before") for x in offers.values()))
        docker = next(x for w, x in offers.items() if "docker" in w)
        self.assertIn("on the build host", docker["action"])
        self.assertIn("`docker … --all`", " ".join(docker["evidence"]))                     # what gets past
        code, out = run(["-p", "t", "suggest", "apply", docker["id"], "--outside-wiki", "--deny"])
        self.assertNotEqual(code, 0)                                                         # a scoped line: no deny
        self.assertFalse(self.settings.exists())

    def test_unguard_takes_out_rules_in_the_dev5_form(self):
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{\n  "permissions": {\n    "deny": [\n      "Bash(rm *-rf*)", "PowerShell(rm *-rf*)",'
                                 '\n      "Bash(git status)"\n    ]\n  }\n}\n', encoding="utf-8")
        (_, new), = suggest_guard._patch(proj.resolve("t"), "rm -rf", "deny", remove=True)
        self.assertEqual(json.loads(new)["permissions"]["deny"], ["Bash(git status)"])

    def test_an_older_wider_rule_from_the_same_line_is_named(self):
        from memcrumbs import suggest_state
        page(self.wiki, "gotchas.md", "---\ntitle: G\nsummary: s\nverified: 2026-09-01\n---\n# G\n## Top\n"
             "- Never `git push --force origin main`.\n")
        self.settings.parent.mkdir(parents=True)
        self.settings.write_text('{"permissions": {"deny": ["Bash(git *push --force*)"]}}\n', encoding="utf-8")
        p = proj.resolve("t")
        st = suggest_state.load_state(p)
        st["applied"]["guard-old123"] = dict(kind="guard", key="gotchas.md|deny|git push --force", at="2026-10-01")
        suggest_state.save_state(p, st)
        offer = json.loads(run(["-p", "t", "suggest", "--kind", "guard", "--json"])[1])["suggestions"][0]
        self.assertIn("older, wider rule from this line is still applied (guard-old123)", " ".join(offer["evidence"]))

    def test_file_scoped_lines_ask_and_say_what_they_touched(self):
        page(self.wiki, "gotchas.md", "---\ntitle: G\nsummary: s\nverified: 2026-09-01\n---\n# G\n## Top\n"
             "- Read with `Get-Content -Raw`; never write JSON files with `Set-Content -Encoding UTF8` (BOM).\n"
             "- Never `rm -rf data/` on the server.\n")
        found = {f[3]: f for f in suggest_guard.forbidden(proj.resolve("t"))}
        self.assertEqual({k: f[5] for k, f in found.items()},
                         {"Set-Content -Encoding UTF8": "ask", "rm -rf data/": "ask"})
        home = Path(self.tmp.name) / "home"
        calls = ["Get-Content a.txt | Set-Content -Path run.log -Encoding UTF8"] * 3 + \
                ["Set-Content -Path x.log -Encoding UTF8NoBOM", "Set-Content -Path c.json -Encoding UTF8"]
        transcript(home / ".claude" / "projects" / transcripts.mangle(self.repo), [(dt.date.today().isoformat(), calls)])
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[suggest]\ntranscripts = true\n", encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=home):
            shown = [x for x in json.loads(run(["-p", "t", "suggest", "--kind", "guard", "--json"])[1])["suggestions"]
                     if "Set-Content" in x["why"]][0]
        evidence = " ".join(shown["evidence"])
        self.assertIn("ran 4 time(s)", evidence)                        # the forbidden form only, not UTF8NoBOM
        self.assertIn("asked on 4", evidence)
        self.assertIn("1 of those named json", evidence)                 # 3 of them wrote a .log
        self.assertIn("cannot see", shown["action"])

    def test_transcripts_rank_guards_by_use(self):
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[suggest]\ntranscripts = true\n", encoding="utf-8")
        home = Path(self.tmp.name) / "home"
        folder = home / ".claude" / "projects" / transcripts.mangle(self.repo)
        folder.mkdir(parents=True)
        today = dt.date.today()
        lines = []
        for k, cmd in enumerate(["cd data && rm -rf cache/", "rm -rf tmp/", "ls"]):
            day = (today - dt.timedelta(days=k)).isoformat()
            lines.append(json.dumps({"timestamp": day + "T10:00:00Z", "sessionId": "s%d" % k, "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}}))
        (folder / "s.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=home):
            out = run(["-p", "t", "suggest", "show", ids("guard")[0]])[1]
        self.assertIn("ran 2 time(s) on 2 day(s)", out)                                       # `cd …&&` skipped


def transcript(folder, sessions):
    """sessions: [(day, [commands])] → one transcript file of Bash tool uses."""
    folder.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"timestamp": day + "T10:00:00Z", "sessionId": "s%d" % k, "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": c}} for c in cmds]}}) for k, (day, cmds) in enumerate(sessions)]
    (folder / "t.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


class MemoryPointers(ProjectCase):
    def setUp(self):
        super().setUp()
        page(self.wiki, "deploy.md", "---\ntitle: Deploy the booking app\nsummary: steps to ship the booking app to the "
             "web server\nverified: 2026-10-01\n---\n# Deploy\nRun the deploy script on the web server, then check the "
             "health endpoint and the version banner.\n")
        run(["-p", "t", "index"])
        self.home = Path(self.tmp.name) / "home"
        self.mem = self.home / ".claude" / "projects" / transcripts.mangle(self.repo) / "memory"
        self.mem.mkdir(parents=True)
        (self.mem / "MEMORY.md").write_text("- [Deploy the booking app](deploy_notes.md) — how we ship the booking app "
                                            "to the web server\n- [Unrelated](other.md) — something else entirely\n",
                                            encoding="utf-8")
        (self.mem / "deploy_notes.md").write_text("---\nname: deploy\ndescription: how we ship the booking app\n---\n"
                                                  "Run the deploy script on the web server, then check the health "
                                                  "endpoint and the version banner.\n", encoding="utf-8")
        (self.mem / "other.md").write_text("---\nname: other\n---\nbananas and pears\n", encoding="utf-8")

    def test_a_duplicate_note_becomes_a_pointer(self):
        with mock.patch.object(Path, "home", return_value=self.home):
            found = ids("memory")
            self.assertEqual(len(found), 1)
            self.assertNotEqual(run(["-p", "t", "suggest", "apply", found[0]])[0], 0)       # outside the wiki
            before = (self.mem / "MEMORY.md").read_bytes()
            run(["-p", "t", "suggest", "apply", found[0], "--outside-wiki"])
            index = (self.mem / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("- [Deploy the booking app](deploy_notes.md) → memcrumbs page deploy", index)
            self.assertIn("- [Unrelated](other.md) — something else entirely", index)
            note = (self.mem / "deploy_notes.md").read_text(encoding="utf-8")
            self.assertIn("now lives in the wiki: `memcrumbs page deploy`", note)
            self.assertNotIn("Not in the wiki yet", note)                                   # a real duplicate
            self.assertNotIn("health endpoint", note)
            run(["-p", "t", "suggest", "undo", found[0]])
            self.assertEqual((self.mem / "MEMORY.md").read_bytes(), before)

    def test_index_line_words_keep_the_wording_and_figures_wait(self):
        index = self.mem / "MEMORY.md"
        index.write_text("- [Deploy the booking app](deploy_notes.md) — how we ship the booking app, carefully and "
                         "quietly\n", encoding="utf-8")                                        # ordinary words
        with mock.patch.object(Path, "home", return_value=self.home):
            found = json.loads(run(["-p", "t", "suggest", "--kind", "memory", "--json"])[1])["suggestions"]
            self.assertEqual(len(found), 1)
            self.assertIn("keeps its wording", found[0]["action"])
            self.assertNotIn("tokens less", found[0]["action"])                              # no tiny claims
            run(["-p", "t", "suggest", "apply", found[0]["id"], "--outside-wiki"])
            self.assertIn("— how we ship the booking app, carefully and quietly → memcrumbs page deploy",
                          index.read_text(encoding="utf-8"))
            run(["-p", "t", "suggest", "undo", found[0]["id"]])
            for fact in ("on port 8443", "paused until spring"):                            # a figure, a state
                index.write_text("- [Deploy the booking app](deploy_notes.md) — how we ship it, %s\n" % fact,
                                 encoding="utf-8")
                self.assertEqual(ids("memory"), [], fact)
                self.assertEqual(len(ids("migrate")), 1, fact)

    def test_a_note_the_wiki_does_not_fully_hold_is_migrated_first(self):
        note = self.mem / "deploy_notes.md"
        note.write_text(note.read_text(encoding="utf-8") + "The release notes go to the operator by mail.\n",
                        encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=self.home):
            self.assertEqual(ids("memory"), [])                                              # not a duplicate
            found = json.loads(run(["-p", "t", "suggest", "--kind", "migrate", "--json"])[1])["suggestions"]
            self.assertEqual(len(found), 1)
            self.assertIn("1 of 2 content lines are in the page", found[0]["evidence"][0])
            self.assertFalse(found[0]["patch"])                                              # the agent moves lines
            note.write_text(note.read_text(encoding="utf-8").replace("The release notes go to the operator by mail.\n",
                                                                     ""), encoding="utf-8")
            (self.mem / "MEMORY.md").write_text("- [Deploy the booking app](deploy_notes.md) — booking app on port "
                                                "9090\n", encoding="utf-8")
            self.assertEqual(ids("memory"), [])                                              # 9090 is not in the page
            mig = json.loads(run(["-p", "t", "suggest", "--kind", "migrate", "--json"])[1])["suggestions"]
            self.assertIn("9090", " ".join(mig[0]["evidence"]))


    def test_links_out_of_the_memory_folder_are_never_followed(self):
        outside = self.mem.parent / "escape.md"
        outside.write_text("Run the deploy script on the web server, then check the health endpoint.\n", encoding="utf-8")
        (self.mem / "MEMORY.md").write_text("- [Deploy the booking app](../escape.md) — how we ship the booking app\n",
                                            encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=self.home):
            self.assertEqual(ids("memory"), [])

    def test_a_patch_that_fails_half_way_is_rolled_back(self):
        from memcrumbs import writeset
        with mock.patch.object(Path, "home", return_value=self.home):
            sid = ids("memory")[0]
            index_before = (self.mem / "MEMORY.md").read_bytes()
            real, calls = writeset.write_text, []

            def flaky(project, path, text, info=(b"", "utf-8"), extra=()):
                calls.append(path)
                if len(calls) == 2:                                  # the second file of the patch fails
                    raise OSError("disk full")
                return real(project, path, text, info, extra)
            with mock.patch.object(writeset, "write_text", side_effect=flaky):
                self.assertNotEqual(run(["-p", "t", "suggest", "apply", sid, "--outside-wiki"])[0], 0)
            self.assertEqual((self.mem / "MEMORY.md").read_bytes(), index_before)  # the first write was undone
            self.assertNotIn(sid, suggest.load_state(proj.resolve("t"))["applied"])
            self.assertEqual(ids("memory"), [sid])                                # still offered


def task_transcript(folder, tasks):
    """tasks: [(day, [commands, or EDIT])] → one transcript in which each task opens with a message from the user."""
    folder.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, (day, steps) in enumerate(tasks):
        at, sess = "%sT10:%02d:00Z" % (day, k % 60), "s-" + day
        lines.append(json.dumps({"type": "user", "timestamp": at, "sessionId": sess,
                                 "message": {"role": "user", "content": "the next task"}}))
        uses = [{"type": "tool_use", "name": "Edit", "input": {"file_path": "app.py"}} if c == "EDIT" else
                {"type": "tool_use", "name": "Bash", "input": {"command": c}} for c in steps]
        lines.append(json.dumps({"type": "assistant", "timestamp": at, "sessionId": sess, "message": {"content": uses}}))
    (folder / "f.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


EDIT = "EDIT"


class Flows(ProjectCase):
    """The same steps in the same order in many tasks: a task flow or a pipeline, offered as a skill."""

    def setUp(self):
        super().setUp()
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[suggest]\ntranscripts = true\n", encoding="utf-8")
        self.home = Path(self.tmp.name) / "home"
        self.folder = self.home / ".claude" / "projects" / transcripts.mangle(self.repo)
        self.days = [(dt.date.today() - dt.timedelta(days=k)).isoformat() for k in range(3)]

    def skills(self):
        with mock.patch.object(Path, "home", return_value=self.home):
            return [s["why"] for s in json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json", "--full"])[1])[
                "suggestions"]]

    def test_a_pipeline_pings_the_header_and_is_scaffolded_without_its_commands(self):
        pipeline = ["python scripts/build.py --fast", "ls -la", "python -m unittest discover -s tests",
                    "git status", "npm run package", "cat out/log.txt", "gh release create v1 out/app.zip"]
        task_transcript(self.folder, [(d, ["git log -1"] + pipeline + ["echo done"]) for d in self.days])
        with mock.patch.object(Path, "home", return_value=self.home):
            self.assertNotIn("new suggestion", run(["-p", "t", "status"])[1])     # the header never scans
            run(["-p", "t", "index"])                                             # a slow command: the daily scan
            head = run(["-p", "t", "status"])[1]
            self.assertIn("tell the owner; list them only on their word", head)    # a ping, nothing more
            for word in ("build.py", "unittest", "npm", "gh "):
                self.assertNotIn(word, head)
            found = json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json"])[1])["suggestions"]
            flow = next(s for s in found if "pipeline" in s["why"])
            self.assertIn("build.py → unittest discover → npm run package → gh release", flow["why"])
            self.assertIn("in 3 tasks on 3 days", flow["why"])
            for glue in ("ls", "git status", "cat", "echo"):
                self.assertNotIn(glue + " ", flow["why"].split(" ran in ")[0] + " ")
            run(["-p", "t", "suggest", "apply", flow["id"], "--outside-wiki", "--name", "ship it"])
            text = (self.repo / ".claude" / "skills" / "ship-it" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", text)                   # it publishes: owner-only
        for leak in ("build.py", "unittest", "npm", "gh release", "--fast", "out/app.zip"):
            self.assertNotIn(leak, text)                                         # no command text in the file

    def test_task_flows_thresholds_and_everyday_git(self):
        flow = ["python -m pytest -q", EDIT, "python -m pytest -q tests/test_app.py", EDIT, "ruff check .",
                "make docs"]
        everyday = ["git add -A", "git commit -m wip", "git push"]
        rare = ["terraform plan", "terraform apply", "kubectl rollout status deploy/web"]
        tasks = [(d, ["python -m pytest", EDIT, "ruff check .", EDIT, "make docs"]) for d in self.days]
        tasks += [(d, everyday) for d in self.days for _ in range(3)]
        tasks += [(self.days[0], rare), (self.days[1], rare)]                      # 2 tasks: under the threshold
        tasks += [(self.days[2], flow)]
        task_transcript(self.folder, tasks)
        whys = [w for w in self.skills() if " ran in " in w and "tasks" in w]
        self.assertEqual(len(whys), 1, whys)
        self.assertIn("task flow pytest → ruff check → make docs ran in 4 tasks on 3 days", whys[0])   # edits between: a flow
        self.assertFalse(any("git" in w for w in whys))                                   # everyone's, not the project's
        self.assertFalse(any("terraform" in w for w in whys))

    def test_steps_are_named_by_what_they_run(self):
        step = suggest_flow.step
        self.assertEqual([step(x) for x in (
            "python scripts/export.py --out x", "python -m unittest discover -s tests", "memcrumbs -p t scan .",
            "python -m memcrumbs -p t index", "npm run build", "gh run watch 7", "git tag v1", 'python -c "x"')],
            ["export.py", "unittest discover", "memcrumbs scan", "memcrumbs index", "npm run build", "gh run",
             "git tag", ""])
        self.assertTrue(all(suggest_flow.noise(x) for x in ("ls", "git status", "memcrumbs find", "rm", "sleep")))


class Skills(ProjectCase):
    def setUp(self):
        super().setUp()
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[suggest]\ntranscripts = true\n", encoding="utf-8")
        self.home = Path(self.tmp.name) / "home"
        today = dt.date.today()
        cycle = ["scp build.zip web:/srv/in/", "ssh web /srv/bin/install.sh", "scp web:/srv/out/log.txt .", "ls"]
        status = ["curl http://127.0.0.1:8080/healthz"] * 9
        transcript(self.home / ".claude" / "projects" / transcripts.mangle(self.repo),
                   [((today - dt.timedelta(days=k)).isoformat(), cycle * 5 + status + ["git status"]) for k in range(3)])

    def test_a_repeated_sequence_scaffolds_an_owner_only_skill(self):
        with mock.patch.object(Path, "home", return_value=self.home):
            found = json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json"])[1])["suggestions"]
            seq = next(s for s in found if "sequence" in s["why"])
            self.assertIn("scp → ssh", seq["why"])
            run(["-p", "t", "suggest", "apply", seq["id"], "--outside-wiki", "--name", "remote run"])
            skill = self.repo / ".claude" / "skills" / "remote-run" / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            self.assertIn("name: remote-run", text)
            self.assertIn("disable-model-invocation: true", text)                         # ssh: live, owner-only
            for leak in ("build.zip", "/srv", "install.sh", "scp", "ssh"):
                self.assertNotIn(leak, text)                                             # no command text in files
            status = next(s for s in found if "status query" in s["why"])
            run(["-p", "t", "suggest", "apply", status["id"], "--outside-wiki", "--agent-may-use"])
            made = next((self.repo / ".claude" / "skills").glob("*status*/SKILL.md")).read_text(encoding="utf-8")
            self.assertNotIn("disable-model-invocation", made)
            run(["-p", "t", "suggest", "undo", seq["id"]])
            self.assertFalse(skill.exists())

    def test_shell_syntax_is_never_a_skill_and_a_cycle_is_one_offer(self):
        junk = ["for f in a b c", "do Remove-Item $f | Out-Null", "done", "$x = Get-Date", "[ -f x ]",
                "Get-ChildItem | Sort-Object | Out-String"]
        cycle = ["scp a.zip web:/in/", "ssh web /srv/run.sh", "scp web:/out/log .", "ls"]
        today = dt.date.today()
        transcript(self.home / ".claude" / "projects" / transcripts.mangle(self.repo),
                   [((today - dt.timedelta(days=k)).isoformat(), (junk + cycle) * 6) for k in range(3)])
        with mock.patch.object(Path, "home", return_value=self.home):
            found = json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json", "--full"])[1])["suggestions"]
        whys = [s["why"] for s in found if "sequence" in s["why"]]
        self.assertEqual(len(whys), 1, whys)                                                # one cycle, one offer
        for syntax in ("for ", "done", "out-null", "sort-object", "out-string", "[", "$x", "get-date"):
            self.assertNotIn(syntax, whys[0])
        self.assertIn("scp → ssh run.sh", whys[0])                                         # the remote command named

    def test_quotes_heredocs_and_wrappers_never_make_a_step(self):
        shapes = transcripts.shapes
        self.assertEqual(shapes('cat <<EOF > n.txt\nhello | deploy now; x\nEOF\nscp a.zip web:/in/'),
                         ["cat <<eof > n.txt", "scp a.zip web:/in/"])                       # heredoc body dropped
        self.assertEqual(shapes('git commit -m "fix | thing; more" && git push'),
                         ['git commit -m "fix thing more"', "git push"])                    # quoted separators
        self.assertEqual(shapes('echo "a | b" && make'), ["make"])                          # a dropped echo's text
        self.assertEqual(shapes("$x = @\"\nline | with ; seps\n\"@\nGet-Service web"), ["get-service web"])
        self.assertEqual(shapes("make \\\n  install"), ["make install"])                  # a line continuation
        head = suggest_skill.head
        self.assertEqual([head(x) for x in ("timeout 30 python.exe tool.py", "env A=1 nohup ./run.sh",
                                            "sudo -u deploy systemctl restart web", "ssh -i k web timeout 9 /srv/run.sh",
                                            "n", "python tool.py")],
                         ["python", "run.sh", "systemctl restart", "ssh run.sh", "", "python"])

    def test_a_cycle_and_its_parts_are_one_offer(self):
        cycle = ["scp a.zip web:/in/", "ssh web /srv/run.sh", "scp web:/out/log .", "ssh web /srv/clean.sh"]
        today = dt.date.today()
        transcript(self.home / ".claude" / "projects" / transcripts.mangle(self.repo),
                   [((today - dt.timedelta(days=k)).isoformat(), cycle * 6 + cycle[:2] * 4) for k in range(3)])
        with mock.patch.object(Path, "home", return_value=self.home):
            found = json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json", "--full"])[1])["suggestions"]
        seqs = [x for x in found if "sequence" in x["why"]]
        self.assertEqual(len(seqs), 1, [x["why"] for x in seqs])                              # parts fold in
        self.assertNotIn("procedure procedure", json.dumps(found).lower())

    def test_the_best_evidenced_form_represents_its_cycle(self):
        pair = ["scp a.zip web:/in/", "ssh web /srv/run.sh"]
        long = pair + ["scp web:/out/log .", "ssh web /srv/clean.sh"]
        fragment = ["ssh web /srv/run.sh", "rsync -a out/ web:/arch/"]
        today = dt.date.today()
        transcript(self.home / ".claude" / "projects" / transcripts.mangle(self.repo),
                   [((today - dt.timedelta(days=k)).isoformat(), pair * 20 + long * 4 + fragment * 5) for k in range(3)])
        with mock.patch.object(Path, "home", return_value=self.home):
            found = json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json", "--full"])[1])["suggestions"]
        seqs = [x for x in found if "sequence" in x["why"]]
        self.assertEqual(len(seqs), 1, [x["why"] for x in seqs])                             # variants fold in
        self.assertTrue(seqs[0]["why"].startswith("the sequence scp → ssh run.sh ran"), seqs[0]["why"])
        self.assertIn("longer or partial form", seqs[0]["why"])
        runs = int(seqs[0]["why"].split(" ran ")[1].split()[0])
        self.assertGreater(runs, 60)                                                          # the pair's own count

    def test_runbook_reads_and_restated_rules(self):
        page(self.wiki, "runbooks/restart-web.md", "---\ntitle: Restart the web service\nsummary: s\nverified: "
             "2026-10-01\n---\n# Restart\n")
        project = proj.resolve("t")
        project.data.mkdir(parents=True, exist_ok=True)
        (project.data / "hits.json").write_text(json.dumps({"wiki/runbooks/restart-web.md": 9}), encoding="utf-8")
        found = json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json"])[1])["suggestions"]
        book = next(s for s in found if "runbook" in s["why"])
        self.assertIn("owner-only", book["action"])                                     # restart: live
        page(self.wiki, "rules.md", "---\ntitle: Rules\nsummary: s\nverified: 2026-10-01\n---\n# Rules\n## Top\n"
             "- Ask before any live change.\n")
        run(["-p", "t", "status"])                                                      # today's rule is kept
        for name in ("a", "b"):
            page(self.wiki, name + ".md", "---\ntitle: %s\nsummary: s\nverified: 2026-10-01\n---\n# %s\n"
                 "- Never deploy on a Friday without the owner.\n" % (name, name))
        rule = ids("rule")[0]
        run(["-p", "t", "suggest", "apply", rule])
        rules = (self.wiki / "rules.md").read_text(encoding="utf-8")
        self.assertIn("- Ask before any live change.\n- Never deploy on a Friday without the owner.", rules)
        self.assertIn("1 new rule/gotcha line", run(["-p", "t", "status"])[1])           # waits for review
        run(["-p", "t", "rule", "Always ask before restarting the web service."])     # a correction kept
        self.assertIn("- Always ask before restarting the web service.", (self.wiki / "rules.md").read_text(encoding="utf-8"))
        self.assertIn("already in", run(["-p", "t", "rule", "Always ask before restarting the web service."])[1])
        self.assertIn("2 new rule/gotcha lines", run(["-p", "t", "status"])[1])

    def test_a_runbook_is_live_by_its_words_and_steps_not_only_its_name(self):
        books = {"tune-config": ("summary: retunes the live config within 30 s\n", "edit the file, save it"),
                 "rotate-logs": ("tags: [prod, logs]\n", "move the old logs aside"),
                 "apply-settings": ("", "```\nssh web-01 apply-settings\n```"),
                 "read-report": ("summary: the weekly totals\n", "open the report and read the totals")}
        for name, (fm, body) in books.items():
            page(self.wiki, "runbooks/%s.md" % name, "---\ntitle: %s\n%sverified: 2026-10-01\n---\n# %s\n%s\n"
                 % (name, fm, name, body))
        project = proj.resolve("t")
        project.data.mkdir(parents=True, exist_ok=True)
        (project.data / "hits.json").write_text(json.dumps({"wiki/runbooks/%s.md" % n: 9 for n in books}),
                                                encoding="utf-8")
        found = json.loads(run(["-p", "t", "suggest", "--kind", "skill", "--json", "--full"])[1])["suggestions"]
        owner_only = {n: "owner-only" in next(s for s in found if "runbooks/%s.md" % n in s["why"])["action"]
                      for n in books}
        self.assertEqual(owner_only, {"tune-config": True, "rotate-logs": True, "apply-settings": True,
                                      "read-report": False})

    def test_split_is_offered_only_where_there_are_sections(self):
        page(self.wiki, "hosts.md", "---\ntitle: Hosts\nsummary: s\nverified: 2026-10-01\n---\n# Hosts\n| host | role |\n"
             "|---|---|\n" + "".join("| h%03d | web |\n" % i for i in range(400)))
        page(self.wiki, "guide.md", "---\ntitle: Guide\nsummary: s\nverified: 2026-10-01\n---\n# Guide\n## One\n" +
             "a line\n" * 200 + "## Two\n" + "a line\n" * 200)
        whys = [s["why"] for s in json.loads(run(["-p", "t", "suggest", "--kind", "split", "--json"])[1])["suggestions"]]
        self.assertTrue(any("guide.md" in w for w in whys), whys)
        self.assertFalse(any("hosts.md" in w for w in whys), whys)      # one table: lookups already return its rows


class Gaps(ProjectCase):
    def setUp(self):
        super().setUp()
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[suggest]\nquery_log = true\ntranscripts = true\n",
                       encoding="utf-8")

    def test_failed_lookups_become_a_draft_and_never_enter_the_wiki(self):
        for q in ("glaze kiln wash recipe", "kiln wash recipe", "kiln wash for shelves"):
            run(["-p", "t", "find", q])
        log = proj.resolve("t").data / "gaps.jsonl"
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 3)
        rows[0]["t"] -= 2 * 86400                                                            # two days
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=Path(self.tmp.name) / "nohome"):
            sid = ids("gap")[0]
            shown = run(["-p", "t", "suggest", "show", sid])[1]
            self.assertIn("3 lookups on 2 days", shown)
            self.assertIn('"kiln wash recipe"', shown)
            run(["-p", "t", "suggest", "apply", sid])
        draft = next(self.wiki.glob("draft-*.md"))
        text = draft.read_text(encoding="utf-8")
        self.assertNotIn("kiln", text.lower())                                              # a neutral title
        self.assertIn("status: draft", text)
        self.assertIn("written_by: agent", text)
        for word in ("glaze", "shelves"):                                                     # no query text beyond
            self.assertNotIn(word, text)                                                     # the topic words

    def test_a_page_sharing_one_word_does_not_answer_and_a_page_read_does(self):
        (self.wiki / "kiln.md").write_text("---\ntitle: Kiln\nsummary: the kiln schedule\nverified: 2026-10-01\n---\n"
                                           "# Kiln\nThe kiln fires on Mondays.\n", encoding="utf-8")
        log = proj.resolve("t").data / "gaps.jsonl"
        for q in ("kiln shelf wash recipe", "shelf wash recipe for the kiln", "kiln wash recipe shelves"):
            run(["-p", "t", "find", q])                                  # the kiln page is a hit, not an answer
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 3)
        rows[0]["t"] -= 2 * 86400
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=Path(self.tmp.name) / "nohome"):
            self.assertEqual(len(ids("gap")), 1)
            run(["-p", "t", "find", "kiln", "fires", "mondays"])          # answered: not logged
            self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 3)
            for r in rows[1:]:                                           # each lookup followed by a wiki page read
                with log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": r["t"] + 30, "read": 1}) + "\n")
            self.assertEqual(ids("gap"), [])
        self.assertIn("unanswered lookups logged", run(["-p", "t", "doctor"])[1])

    def test_a_cluster_is_rechecked_with_its_questions_not_its_label(self):
        (self.wiki / "glaze.md").write_text("---\ntitle: Glaze notes\nsummary: s\nverified: 2026-10-01\n---\n"
                                            "# Glaze notes\nGlaze crawl happens; see the binder.\n", encoding="utf-8")
        log = proj.resolve("t").data / "gaps.jsonl"
        qs = ("glaze crawl stoneware tenmoku cone", "stoneware glaze crawl after wadding blisters",
              "stoneware glaze crawl magnesium shrinkage")       # the label (glaze crawl stoneware) is 2/3 on the page
        for q in qs:
            run(["-p", "t", "find", q])
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 3, rows)
        rows[0]["t"] -= 2 * 86400
        log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=Path(self.tmp.name) / "nohome"):
            self.assertEqual(len(ids("gap")), 1)                                             # still offered

    def test_a_gap_is_named_in_the_words_asked(self):
        from collections import Counter
        from memcrumbs import suggest_gaps
        items = [("d", q, []) for q in ("helm charts on staging", "staging charts", "chart staging helm")]
        c = dict(terms=Counter(t for _, q, _ in items for t in suggest_gaps.terms(q)), items=items)
        self.assertEqual(suggest_gaps.label(c), ["charts", "staging", "helm"])           # not "chart stag helm"

    def test_read_trails_from_transcripts(self):
        home = Path(self.tmp.name) / "home"
        folder = home / ".claude" / "projects" / transcripts.mangle(self.repo)
        folder.mkdir(parents=True)
        lines, today = [], dt.date.today()
        for k in range(3):
            day = (today - dt.timedelta(days=k)).isoformat()
            evs = [{"type": "tool_use", "name": "Bash", "input": {"command": 'memcrumbs find "invoice export format"'}}]
            evs += [{"type": "tool_use", "name": "Read", "input": {"file_path": "%s/f%d.py" % (self.repo.as_posix(), i)}}
                    for i in range(5)]
            lines.append(json.dumps({"timestamp": day + "T09:00:00Z", "sessionId": "s%d" % k,
                                     "message": {"content": evs}}))
        (folder / "a.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        cfg = self.projects / "t" / "memcrumbs.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("query_log = true\n", ""), encoding="utf-8")
        with mock.patch.object(Path, "home", return_value=home):
            shown = run(["-p", "t", "suggest", "show", ids("gap")[0]])[1]
        self.assertIn("read instead: f0.py (3×)", shown)
