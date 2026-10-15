"""memcrumbs command line: resolve the project, open the index, run one command through `Out`."""
import argparse
import os
import sys
import time

from memcrumbs import __version__, cmd_read, indexer, plugins, project as proj, synonyms, writeset
from memcrumbs.cli_args import NO_PROJECT, build_parser
from memcrumbs.output import Out
from memcrumbs.redact import Redactor, secret_hash
from memcrumbs.store import IndexBroken, Locked, Store
from memcrumbs.util import posix, utf8_stdout

READS = ("find", "page", "sym", "bench", "about")
SCAN_AFTER = ("check", "index", "dashboard", "doctor", "log", "decision", "incident", "verify", "supersede", "gotcha")


def _kinds(s):
    return [k.strip() for k in s.split(",") if k.strip()] if s else None


def _quiet_project(name):
    try:
        return proj.resolve(name)
    except SystemExit:
        return None


BROKEN_RETRIES = 5


def _state(path):
    """The index files' sizes and times: if they change while we wait, another process is writing them."""
    out = []
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            st = path.with_name(path.name + suffix).stat()
            out.append((suffix, st.st_size, st.st_mtime_ns))
        except OSError:
            pass
    return out


def open_store(project, broken_ok=False):
    """Open the index; a broken file is set aside and rebuilt (it is a cache). Returns (store, why-stale).

    "Broken" can be a moment in another process's work (a file being created), so it is retried first, and an
    index whose files change meanwhile is never set aside. Setting aside moves the database with its -wal and
    -shm files: on Linux and macOS a delete succeeds even while other processes hold the file, and a new database
    next to an old -wal corrupts both (found by running the suite on Linux)."""
    table = synonyms.for_project(project)
    err, before = None, _state(project.index_path)
    for i in range(BROKEN_RETRIES):
        try:
            store = Store(project.index_path, table)
            store.roots = tuple(posix(r).lower().rstrip("/") + "/" for r in project.repos)
            return store, None
        except Locked as e:
            return None, "index locked: %s" % e
        except IndexBroken as e:
            err = e
            if broken_ok:
                return None, str(e)
            time.sleep(0.05 * (i + 1))
    if _state(project.index_path) != before:
        raise SystemExit("memcrumbs: the index is being written by another process (%s); try again in a moment"
                         % err)
    stamp = "%d-%d" % (os.getpid(), time.time() * 1000)
    for suffix in ("", "-wal", "-shm"):
        f = project.index_path.with_name(project.index_path.name + suffix)
        if not f.exists():
            continue
        try:
            aside = writeset.move(project, f, f.with_name(f.name + ".broken-" + stamp))
            writeset.delete(project, aside)
        except OSError:
            raise SystemExit("memcrumbs: the index is broken (%s) and in use; close other memcrumbs processes "
                             "and run: memcrumbs index --full" % err)
    return Store(project.index_path, table), None


def _cited(project):
    """For `outline`: the wiki's citations of a file, from the existing index (no refresh, no new index)."""
    if project is None or not project.index_path.exists():
        return None

    def cited(path):
        from memcrumbs import cites
        try:
            store = Store(project.index_path, synonyms.for_project(project))
        except (IndexBroken, Locked):
            return ""
        try:
            return cites.summary(store, project, path)
        except Exception:                            # an index mid-rebuild: no footer
            return ""
        finally:
            store.close()
    return cited


def _status(out, project, api):
    """The header reads the index without migrating it or waiting on a writer: a session never blocks on it."""
    from memcrumbs import header
    from memcrumbs.store import peek
    seen = peek(project.index_path) if project.index_path.exists() else "version"     # a new project: not an error
    if seen == "version":
        counts, stale, unreviewed = (0, 0), None, 0       # "index builds on the first lookup"
    elif seen is None:
        counts, stale, unreviewed = None, "not built, busy or unreadable", 0
    else:
        counts, stale, unreviewed = seen[:2], None, seen[2]
    header.status(out, project, api, counts, stale, unreviewed)


def _json_error(out, e):
    if out.json and isinstance(e.code, str):
        out.set(error=e.code.removeprefix("memcrumbs: "))


def owner_gate(project, args):
    """Inside Claude Code, the owner's decisions run only in the form memcrumbs' ask rules name: then Claude Code
    asks the owner before the command runs, in every permission mode. Other agent hosts are unchanged."""
    from memcrumbs import claude_settings as cs
    cmd = cs.decision(args)
    if cmd and cs.in_claude_code():
        why = cs.owner_form(project, cmd)
        if why:
            raise SystemExit("memcrumbs: this is the owner's decision: %s; or the owner runs it in their own "
                             "terminal" % why)


def run(args, project, api):
    c = args.cmd
    out = Out(c, project, json_mode=args.json, full=args.full)
    code = 0
    try:
        owner_gate(project, args)
        if c == "status":
            _status(out, project, api)
        elif c == "schedule":
            from memcrumbs import schedule
            if args.action and not args.name:
                raise SystemExit("memcrumbs: schedule %s needs the skill's name" % args.action)
            if args.action == "add":
                schedule.add(out, project, args.name, args.every, args.at, args.agent, args.print_only)
            elif args.action == "remove":
                schedule.remove(out, project, args.name)
            elif args.action == "run":
                code = schedule.run(out, project, args.name)
            else:
                schedule.show(out, project)
        elif c == "skills":
            from memcrumbs import skill_use
            skill_use.command(out, project, args.page, args.days)
        elif c == "gotcha":
            from memcrumbs import gotcha_hits
            if args.hit:
                gotcha_hits.hit(out, project, args.hit)
            elif args.add:
                gotcha_hits.add(out, project, args.add)
            else:
                gotcha_hits.show(out, project)
        elif c in ("log", "decision", "incident", "verify", "supersede"):
            from memcrumbs import cmd_write, curate
            if c == "log":
                cmd_write.log(out, project, " ".join(args.text), args.tag, args.skill)
            elif c == "decision":
                curate.decision(out, project, args.title, args.status, args.why, args.tag, args.considered,
                                args.evidence, args.revisit_if)
            elif c == "incident":
                curate.incident(out, project, args.title, args.cause, args.fix, args.tag, args.symptom, args.guard,
                                args.lucky)
            elif c == "verify":
                curate.verify(out, project, args.page, args.date)
            else:
                curate.supersede(out, project, args.page, args.by)
        elif c == "check":
            from memcrumbs import lint
            code = lint.check(out, project, api, args.baseline, args.all, args.strict, args.dupes)
        elif c == "suggest":
            from memcrumbs import suggest
            code = suggest.command(out, project, api, args)
        elif c == "rule":
            from memcrumbs import suggest_skill
            suggest_skill.add_rule(out, project, " ".join(args.text))
        elif c == "review":
            from memcrumbs import review
            code = review.command(out, project, args.approve, args.kept)
        elif c == "quarantine":
            from memcrumbs import review
            review.quarantine(out, project, args.page, args.lift)
        elif c == "fact":
            from memcrumbs import facts
            code = facts.command(out, project, args.key)
        elif c == "plan":
            from memcrumbs import plan
            plan.show(out, project, args.approve, args.budget, args.clear, args.action == "next")
        elif c == "dashboard":
            from memcrumbs import dashboard
            dashboard.write(out, project, api, args.open)
        elif c == "doctor":
            from memcrumbs import doctor
            code = doctor.run(out, project, api, args.share)
        elif c == "bench" and (args.add or args.expect_add):
            from memcrumbs import bench
            if args.add:
                bench.add(out, project, args.add, args.expect, args.category)
            else:
                bench.expect_add(out, project, *args.expect_add)
        elif c == "wire":
            from memcrumbs import wire
            wire.wire(out, project, args.repo, _kinds(args.target), args.apply, args.remove, args.user_skill, args.allow)
        elif c == "secret-add":
            import getpass
            v = getpass.getpass("secret (not echoed): ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\r\n")
            if len(v) < 4:
                raise SystemExit("too short")
            writeset.append_text(project, project.dir / "secrets.deny", secret_hash(v) + "\n")
            out("added (hash only) -> %s" % (project.dir / "secrets.deny"))
        elif c in api.commands:
            api.commands[c][1](project, args)
        else:
            t0 = time.time()
            store, _ = open_store(project)
            try:
                stats = indexer.refresh(project, api, store, force=(c == "index" and args.full),
                                        wait=30 if c == "index" else 0.25)
                if "skipped" in stats and c in READS:
                    out("(%s)" % stats["skipped"])
                if c == "find":
                    if args.explain:
                        cmd_read.explain(out, store, " ".join(args.query))
                    cmd_read.find(out, project, store, " ".join(args.query), _kinds(args.kind), args.n)
                elif c == "page":
                    cmd_read.page(out, project, store, args.name, args.section, args.full)
                elif c == "sym":
                    cmd_read.sym(out, project, store, args.name, args.path_like, args.body, args.n)
                elif c == "about":
                    cmd_read.about(out, project, store, args.path, args.full)
                elif c == "bench":
                    from memcrumbs import bench
                    code = bench.report(out, project, store, args.questions, args.min_recall3, args.k)
                elif c in ("index", "stats"):
                    kinds, nsym, nfiles = store.counts()
                    out.set(refreshed=stats, files=nfiles, docs=kinds, symbols=nsym)
                    if c == "index":
                        out("refreshed in %.1fs: %s" % (time.time() - t0, ", ".join("%s %s" % kv for kv in stats.items())
                                                        or "nothing due"))
                    out("files %d · docs %s · symbols %d" % (nfiles, dict(sorted(kinds.items())), nsym))
                    if c == "stats" and args.usage:
                        from memcrumbs import usage
                        u = usage.summary(project)
                        out.set(usage=u)
                        out("usage (tokens est. chars/4): cmd n p50 p95 max · truncated% · p95 ms · no-result%")
                        for cmd, r in u.items():
                            out("  %-10s %5d %5d %5d %5d · %5.1f%% · %6.1f · %s" % (
                                cmd, r["n"], r["p50_tokens"], r["p95_tokens"], r["max_tokens"], r["truncated_pct"],
                                r["p95_ms"], "%.1f%%" % r["zero_results_pct"] if "zero_results_pct" in r else "-"))
            finally:
                store.close()
    except SystemExit as e:
        _json_error(out, e)
        raise
    finally:
        out.close()
    if c in SCAN_AFTER:                          # after the output: the daily scans never delay a lookup
        from memcrumbs import lint, suggest, update
        suggest.maybe_scan(project, api)
        lint.maybe_check(project)                # the daily secret check: its count reaches the header
        update.maybe_check(project)              # opt-in ([update] notify): at most once a day
        from memcrumbs import reflect, skill_use
        skill_use.maybe_refresh(project)         # wiki/skills.md, when the owner made it
        reflect.maybe_refresh()                  # opt-in: the cross-project counts, at most once a week
    return code


def _main(argv):
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("-p", "--project")
    known, rest = pre.parse_known_args(argv)
    first = next((a for a in rest if not a.startswith("-")), None)
    project = _quiet_project(known.project) if first not in ("init", "template", None) else None
    api = plugins.load(project) if project else None
    args = build_parser(api.commands if api else None, api.errors if api else None).parse_args(argv)
    if args.version:
        print("memcrumbs %s" % __version__)
        return 0
    if not args.cmd:
        build_parser().print_help()
        return 2
    c = args.cmd
    if c in NO_PROJECT:
        from memcrumbs import cmd_setup, cmd_write
        name = getattr(args, "project", None)
        out = Out(c, project, json_mode=args.json, full=args.full)
        try:
            if c == "init":
                from memcrumbs import setup_repo
                return setup_repo.init(out, args)
            elif c == "template":
                cmd_setup.template(out)
            elif c == "reference":
                from memcrumbs import reference
                owner_gate(project, args)            # set and reflect are the owner's decision
                if args.action == "set" and args.value:
                    reference.set_(out, args.value)
                elif args.action == "reflect" and args.value in ("on", "off"):
                    reference.reflect_switch(out, args.value == "on")
                elif args.action in ("set", "reflect"):
                    raise SystemExit("memcrumbs: reference set PATH|software|agile|lean · reference reflect on|off")
                elif args.action:
                    getattr(reference, args.action)(out)
                else:
                    reference.show(out)
            elif c == "reflect":
                from memcrumbs import reflect
                reflect.command(out)
            elif c == "update":
                from memcrumbs import update
                chosen = name or os.environ.get("MEMCRUMBS_PROJECT")
                return update.command(out, args, [proj.resolve(chosen)] if chosen else proj.all_projects())
            elif c == "outline":
                cmd_read.outline(out, args.path, _kinds(args.kinds), args.grep, args.depth,
                                 project.blocked if project else proj.is_blocked, _cited(project))
            else:
                redact = proj.resolve(name).redact if name or os.environ.get("MEMCRUMBS_PROJECT") else (
                    project.redact if project else Redactor())
                return cmd_write.scan(out, redact, args.path)
        except SystemExit as e:
            _json_error(out, e)
            raise
        finally:
            out.close()
        return 0
    if project is None or (getattr(args, "project", None) and args.project not in (project.name, project.dir.name)):
        project = proj.resolve(getattr(args, "project", None))
        api = plugins.load(project)
    return run(args, project, api)


def main(argv=None):
    utf8_stdout()
    argv = sys.argv[1:] if argv is None else argv
    hook = "status" in argv and "--hook" in argv
    try:
        code = _main(argv)
    except SystemExit as e:
        if hook and e.code not in (0, None):          # a SessionStart hook never fails the session
            print("memcrumbs: no header (%s)" % (e.code if isinstance(e.code, str) else "error"))
            sys.exit(0)
        raise
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        if hook:
            print("memcrumbs: header unavailable (%s); run memcrumbs status" % type(e).__name__)
            sys.exit(0)
        if isinstance(e, OSError):                    # disk full, a locked file, no permission: one line, exit 1
            sys.exit("memcrumbs: %s" % e)
        raise
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
