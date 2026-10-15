"""`memcrumbs doctor`: is this install and this project healthy? Environment, config, wiki, secrets file, plugins,
index, the wired SessionStart hook (run for real: exit 0, time, output size), usage and the project's own bench.

`--share` prints only shape — versions, counts, timings and pass/fail per check, no paths, names or text — so
it can be pasted into a public bug report without revealing anything about the project."""
import json
import os
import platform
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from memcrumbs import __version__, claude_settings, header, plan, synonyms, usage
from memcrumbs.lint import DEPRECATED
from memcrumbs.store import SCHEMA_VERSION, IndexBroken, Locked, Store
from memcrumbs.util import posix, read_text

SCHEMA = {"": {"name", "title", "wiki", "repos", "plugins", "code", "docs", "security", "search", "check", "status",
               "facts", "suggest", "review", "update", "reference"},
          "code": {"roots", "include", "exclude"}, "docs": {"name", "root", "include", "exclude", "kind"},
          "security": {"never_index", "secret_keys"}, "search": {"synonyms", "thesaurus", "thesaurus_remove"},
          "check": {"max_lines", "stale_days"},
          "status": {"sections", "max_tokens", "max_chars", "rules", "map_lines", "gotchas", "journal", "style_rules"},
          "facts": {"page", "bind"}, "suggest": {"transcripts", "query_log", "gap_cover"}, "review": {"gate_header"}, "update": {"notify"},
          "reference": {"reflect"}}
HOOK_SLOW_MS, HOOK_FAIL_MS = 1500, 5000


def _environment():
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        fts = True
    except sqlite3.OperationalError:
        fts = False
    yield ("ok" if fts else "fail", "sqlite", "SQLite %s, FTS5 %s" % (sqlite3.sqlite_version, "yes" if fts else "MISSING"),
           dict(sqlite=sqlite3.sqlite_version, fts5=fts))
    yield ("ok" if sys.version_info >= (3, 11) else "fail", "python", "Python %s on %s" % (
        platform.python_version(), platform.platform(terse=True)), dict(python=platform.python_version(), os=sys.platform))
    exe = shutil.which("memcrumbs")
    if not exe:
        yield ("fail", "on PATH", "`memcrumbs` is not on PATH: the SessionStart hook cannot run", dict(on_path=False))
        return
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30)
        v = r.stdout.split()[-1] if r.returncode == 0 and r.stdout.split() else None
        err = (r.stderr.strip().splitlines() or ["no output"])[-1]
        if v is None and "usage: memcrumbs" in r.stderr:
            v = "0.1 (no --version)"                  # runs, but predates --version
    except (OSError, subprocess.SubprocessError) as e:
        v, err = None, type(e).__name__
    if v is None:
        yield ("fail", "on PATH", "%s does not run (%s): every wired hook fails. Reinstall: pip install <memcrumbs wheel>"
               % (exe, err[:120]), dict(on_path=True, path_runs=False))
        return
    same = v == __version__
    yield ("ok" if same else "warn", "on PATH", "%s is memcrumbs %s%s" % (exe, v, "" if same else
           " but this is %s: the hook runs the PATH one" % __version__), dict(on_path=True, path_version_matches=same))


def _config(project):
    from memcrumbs.project import BROKEN
    unknown, tables = [], []
    for key in project.cfg:
        if key not in SCHEMA[""]:
            (tables if isinstance(project.cfg[key], dict) else unknown).append(key)
    if tables and not project.cfg.get("plugins"):    # a typo ([serach]) is ignored silently: say so
        unknown += ["[%s]" % t for t in tables]
    for name, why in sorted(BROKEN.items()):
        yield "warn", "config", "project folder %s: memcrumbs.toml cannot be read (%s); that project is skipped" % (
            name, why), dict(broken_configs=len(BROKEN))
    for table, keys in SCHEMA.items():
        if not table:
            continue
        for t in project.cfg.get(table, []) if table == "docs" else [project.cfg.get(table, {})]:
            unknown += ["%s.%s" % (table, k) for k in (t if isinstance(t, dict) else {}) if k not in keys]
    old = ["[%s] %s → %s" % (t, k, use) for t, k, use in DEPRECATED if k in project.cfg.get(t, {})]
    status = "warn" if unknown or old else "ok"
    detail = "; ".join(x for x in ("unknown keys: " + ", ".join(unknown) if unknown else "",
                                   "deprecated: " + ", ".join(old) if old else "") if x) or "schema v1, no unknown keys"
    if tables and project.cfg.get("plugins"):        # a plugin's own table: listed, not a warning
        detail += "; tables for plugins: " + ", ".join("[%s]" % t for t in tables)
    yield status, "config", detail, dict(unknown_keys=len(unknown), deprecated_keys=len(old))


def _wiki(project):
    pages = project.wiki_pages()
    missing = [n for n, f in (("rules", "rules.md"), ("map", "index.md"), ("gotchas", "gotchas.md"))
               if not (project.wiki / f).exists()]
    yield ("warn" if missing or not pages else "ok", "wiki", "%d pages%s" % (len(pages), "; header sections without a "
           "page: " + ", ".join(missing) if missing else ""), dict(pages=len(pages), header_pages_missing=len(missing)))
    deny = project.dir / "secrets.deny"
    plain = 0
    if deny.exists():
        plain = sum(1 for ln in deny.read_text(encoding="utf-8", errors="replace").splitlines()
                    if ln.strip() and not ln.startswith(("#", "sha256:")))
    tracked = False
    if deny.exists():
        try:
            inside = subprocess.run(["git", "-C", str(project.dir), "rev-parse"], capture_output=True).returncode == 0
            tracked = inside and subprocess.run(["git", "-C", str(project.dir), "check-ignore", "-q", str(deny)],
                                                capture_output=True).returncode != 0
        except OSError:                              # no git: nothing to leak into
            tracked = False
    bad = getattr(project.redact, "malformed", 0)
    status = "fail" if tracked else "warn" if plain or bad else "ok"
    detail = ("in a git work tree and NOT ignored: add it to .gitignore" if tracked else
              "%d plain-text values: re-add each with `memcrumbs secret-add` (stores a hash) and delete the line" % plain
              if plain else "hashes only")
    if bad:                                          # counted, never shown: a broken line may hold the secret itself
        detail += "; %d malformed sha256: lines are ignored: re-add those values with `memcrumbs secret-add`" % bad
    yield status, "secrets.deny", detail, dict(plain=plain, unignored=tracked, malformed=bad)


def _index(project):
    try:
        st = Store(project.index_path, synonyms.for_project(project))
    except (IndexBroken, Locked) as e:
        yield "fail", "index", "%s — run: memcrumbs index --full" % e, dict(index_ok=False)
        return
    try:
        kinds, nsym, nfiles = st.counts()
        ok = st.db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        age = st.age()
    finally:
        st.close()
    if not nfiles:
        yield ("warn", "index", "needs a build (new install or schema upgrade to v%d): it builds on the first lookup, "
               "or run memcrumbs index" % SCHEMA_VERSION, dict(index_ok=ok, files=0, needs_build=True))
        return
    yield ("ok" if ok else "warn", "index", "schema v%d · %d files · %d docs · %d symbols · refreshed %s" % (
        SCHEMA_VERSION, nfiles, sum(kinds.values()), nsym, "%d min ago" % (age // 60) if age else "never"),
        dict(index_ok=ok, files=nfiles, docs=sum(kinds.values()), symbols=nsym))


def _header_hook(argv):
    """Exactly `memcrumbs [-p NAME] status --hook`: what wire writes."""
    if not argv or Path(argv[0]).name.lower() not in ("memcrumbs", "memcrumbs.exe"):
        return False
    rest = argv[1:]
    if rest[:1] == ["-p"] and len(rest) >= 2 and re.match(r"^[\w.-]+$", rest[1]):
        rest = rest[2:]
    return rest == ["status", "--hook"]


def _hooks(project):
    found = False
    for repo in project.repos:
        sp = Path(repo) / ".claude" / "settings.json"
        try:
            data = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cmds = [h.get("command", "") for e in (data.get("hooks") or {}).get("SessionStart") or [] if isinstance(e, dict)
                for h in e.get("hooks") or [] if isinstance(h, dict) and str(h.get("command", "")).startswith("memcrumbs ")]
        if cmds:
            missing = claude_settings.missing_allow(data, project)
            yield ("warn" if missing else "ok", "allow rules", "%d of %d read-only lookup rules missing: each lookup asks "
                   "for approval and agents fall back to grep — memcrumbs wire --allow --apply" % (
                       len(missing), len(claude_settings.allow_rules(project))) if missing else
                   "find, page, outline, sym, status allowed for Bash and PowerShell", dict(allow_missing=len(missing)))
        for cmd in cmds:
            found = True
            try:
                argv = shlex.split(cmd)
            except ValueError:
                argv = []
            if not _header_hook(argv):            # doctor runs the header hook only, never another command
                yield ("warn", "hook", "`%s` is not the memcrumbs header hook (not run): expected `memcrumbs -p NAME "
                       "status --hook`" % cmd, dict(hook_ok=None))
                continue
            exe = shutil.which(argv[0])
            if not exe:
                yield "fail", "hook", "`%s`: %s is not on PATH" % (cmd, argv[0]), dict(hook_ok=False)
                continue
            t0 = time.perf_counter()
            try:
                r = subprocess.run([exe] + argv[1:], cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
                                   timeout=HOOK_FAIL_MS / 1000 * 3, env=dict(os.environ, MEMCRUMBS_AGENT="1"))
                ms, code, size = (time.perf_counter() - t0) * 1000, r.returncode, len(r.stdout)
            except subprocess.TimeoutExpired:
                ms, code, size = HOOK_FAIL_MS * 3, -1, 0
            cap = header.HARD_CAP_TOKENS * 4 + 400
            bad = code != 0 or ms > HOOK_FAIL_MS or size > cap or size == 0
            yield ("fail" if bad else "warn" if ms > HOOK_SLOW_MS else "ok", "hook",
                   "`%s` in %s: exit %d, %d ms, ≈ %d tokens" % (cmd, repo.name, code, ms, (size + 3) // 4),
                   dict(hook_ok=not bad, hook_ms=round(ms), hook_tokens=(size + 3) // 4))
    if not found:
        yield "warn", "hook", "no SessionStart hook in any repo: memcrumbs wire --apply", dict(hook_ok=None)


def _use(project):
    u = usage.summary(project).get("find")
    if u:
        bad = u["p95_tokens"] > 600 or u.get("zero_results_pct", 0) > 20
        yield ("warn" if bad else "ok", "find usage", "%d runs · p95 ≈ %d tokens · %s%% without results" % (
            u["n"], u["p95_tokens"], u.get("zero_results_pct", "-")), dict(find_runs=u["n"], find_p95_tokens=u["p95_tokens"],
                                                                         find_zero_pct=u.get("zero_results_pct")))
    from memcrumbs import suggest_gaps
    if suggest_gaps.enabled(project):                # a log that never fills is visible
        log = project.data / "gaps.jsonl"
        n = sum(1 for ln in read_text(log).splitlines() if ln.strip() and '"q"' in ln) if log.exists() else 0
        yield "ok", "gap log", "%d unanswered lookups logged%s" % (n, "" if n else " (none yet: lookups the wiki "
                                                                   "answers are not logged)"), dict(gap_log=n)
    from memcrumbs import bench
    path = bench.default_path(project)
    if not path.exists():
        yield "warn", "bench", "no questions yet: when a lookup misses, memcrumbs bench --add \"<q>\" --expect <page>", \
            dict(bench_questions=0)
        return
    st = Store(project.index_path, synonyms.for_project(project))
    try:
        if not st.counts()[2]:
            yield ("warn", "bench", "skipped: the index is not built yet (memcrumbs index, then doctor again)",
                   dict(bench_skipped=True))
            return
        total = bench._agg(bench.run(project, st, bench.load(path)))
    finally:
        st.close()
    yield ("ok" if total["recall_at_3"] >= 0.85 else "warn", "bench", "%d questions · recall@3 %.2f · recall@1 %.2f" % (
        total["n"], total["recall_at_3"], total["recall_at_1"]),
        dict(bench_questions=total["n"], recall_at_3=total["recall_at_3"], recall_at_1=total["recall_at_1"]))


def _update(project):
    from memcrumbs import update, update_install
    done = update.unfinished(project)
    if done:
        yield "warn", "update", "memcrumbs was upgraded to %s; the wiring is from %s: memcrumbs update finishes it " \
            "(index, wire)" % (__version__, done), dict(upgrade_unfinished=True)
    site, left = update_install.stash()
    if left:
        yield "warn", "update", "a failed upgrade left %s in %s, pip's copy of an old memcrumbs: delete them (until " \
            "then pip warns \"Ignoring invalid distribution\")" % (", ".join(left), posix(site)), dict(pip_stash=len(left))
    if not update.notify_on(project):
        return
    latest = update._stored(project).get("latest")
    if update.newer(latest):
        yield "warn", "update", "memcrumbs %s is available (you have %s): memcrumbs update" % (latest, __version__), \
            dict(update_available=True)
    else:
        yield "ok", "update", "newest known release: %s" % (latest or "not checked yet"), dict(update_available=False)


def _plan(project):
    items = plan.candidates(project)
    state = plan.load_state(project)
    yield ("ok", "refresh plan", "%d pages need attention (≈ %d tokens est.) · approved %d · budget %s" % (
        len(items), sum(c["tokens"] for c in items), len(state.get("approved", [])), state.get("budget") or "none"),
        dict(plan_items=len(items), plan_tokens=sum(c["tokens"] for c in items)))


def _plugin_fix(project, spec):
    """The fix for a plugin that did not load. Until it loads, its documents are not refreshed (`index` says so)."""
    if spec.endswith(".py"):
        return "Fix or remove %s, or take it out of `plugins` in memcrumbs.toml" % posix(project.dir / spec)
    name = spec.rsplit(".", 1)[-1]
    return ("If that pack or module is no longer installed, keep it as a project plugin: copy its module to %s and "
            'list "plugins/%s.py" in `plugins`; or take it out of `plugins`' % (posix(project.dir / "plugins" /
                                                                                     (name + ".py")), name))


def run(out, project, api, share=False):
    checks = list(_environment()) + list(_config(project))
    checks += [("fail", "plugin", "%s failed to load: %s. %s" % (spec, err, _plugin_fix(project, spec)),
                dict(plugin_ok=False)) for spec, err in api.errors]
    for gen in (_wiki, _index, _use, _plan, _update, _hooks):     # the hook runs memcrumbs from PATH: last
        try:
            checks += list(gen(project))
        except Exception as e:                       # a broken check is itself a finding, never a crash
            checks.append(("fail", gen.__name__.strip("_"), "check crashed: %s" % type(e).__name__, {}))
    fails = sum(1 for c in checks if c[0] == "fail")
    if share:
        shape = dict(memcrumbs=__version__, platform=sys.platform, results={})
        for status, name, _, data in checks:
            shape["results"].setdefault(name, []).append(dict(status=status, **data))
        out.set(**shape)
        out(json.dumps(shape, indent=1))
    else:
        out.set(checks=[dict(status=s, check=n, detail=d) for s, n, d, _ in checks])
        out("memcrumbs %s · project %s · %d checks · %d fail · %d warn" % (
            __version__, project.name, len(checks), fails, sum(1 for c in checks if c[0] == "warn")))
        for status, name, detail, _ in checks:
            out("%-4s %-14s %s" % ({"ok": "ok", "warn": "WARN", "fail": "FAIL"}[status], name, detail))
    return 1 if fails else 0

