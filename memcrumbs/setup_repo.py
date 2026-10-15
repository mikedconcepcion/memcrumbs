"""`memcrumbs init` inside a repo: the whole setup in one run, safe to repeat, and reversible.

    cd your-repo && memcrumbs init

1. The repo is the git root of the current folder (or `--repo`). The project is named after the repo's folder (made
   unique) and titled from its README. Its config indexes the repo's code and markdown and skips the generated
   folders found at the top; its map is drafted from the repo (`repo_signals`). The wiki goes to the projects folder.
2. index.
3. wire Claude Code (CLAUDE.md block, session hook, read-only allow rules, skill) after one yes. `--yes` gives it
   ahead. Without a terminal (under an agent) the wiring waits for `--yes`, which the agent passes only after the
   owner said yes.
4. doctor.

Run again in a set-up repo, it repairs and upgrades: index, the wiring refreshed to this version, doctor; when all
is current it says so and changes nothing. `--remove` takes the wiring out of every repo the project wired, byte for
byte, and keeps the wiki; `--delete-wiki` also deletes the project folder (asked in a terminal, `--yes` otherwise)."""
import shutil
import sys
import time
from pathlib import Path

from memcrumbs import cmd_setup, indexer, plugins, project as proj, repo_signals as signals, writeset
from memcrumbs.redact import safe
from memcrumbs.util import newline_of, posix, read_doc, walk_stat

OFFERS = ("[suggest]                        # turned on with the wiring: skill offers from repeated work (Claude "
          "Code's transcripts, read locally)\ntranscripts = true\n")


class Collect:
    """An `Out` stand-in for the steps init runs in-process: it keeps their lines and data for the summary."""
    json = False

    def __init__(self):
        self.lines, self.data = [], {}

    def __call__(self, line=""):
        self.lines.extend(str(line).split("\n"))

    def set(self, **kw):
        self.data.update(kw)

    def hint(self, _next):
        pass


def _interactive(out):
    return not out.json and sys.stdin.isatty() and sys.stdout.isatty()


def _flush(out):
    if out.lines:                                    # what was said so far comes before a question
        print("\n".join(safe(out.redact, ln) for ln in out.lines), flush=True)
        out.lines = []


def _ask(out, question, default):
    _flush(out)
    try:
        answer = input("%s [%s] " % (question, "Y/n" if default else "y/N")).strip().lower()
    except EOFError:
        return False
    return default if not answer else answer in ("y", "yes")


def _repos(args):
    if args.repo:
        repos = [Path(r).expanduser().resolve() for r in args.repo]
        for r in repos:
            if not r.is_dir():
                raise SystemExit("memcrumbs: no folder %s" % posix(r))
        return repos
    top = signals.git_root(Path.cwd())
    return [top] if top else []


TOO_MANY = 20000                 # files: a folder this big is not one project (or not on purpose)


def _plain_folder():
    """The working folder, when it is not in git: (folder, None), or (None, why it is refused). A drive root, the
    home folder, a folder holding the memcrumbs projects, or a tree too big for one project is refused."""
    here, home, projects = Path.cwd().resolve(), Path.home().resolve(), proj.projects_dir().resolve()
    if here == Path(here.anchor) or here == home or here in projects.parents or projects in [here, *here.parents]:
        return None, "is too broad to be one project"
    for n, _ in enumerate(walk_stat(here, ["**/*"], max_bytes=1 << 40), 1):
        if n > TOO_MANY:
            return None, "holds more than %d files" % TOO_MANY
    return here, None


def _owner(name, repo):
    """The project already set up for this repo (or named NAME), or None. One repo, one project: a second name
    for a set-up repo would add a second hook."""
    projects = proj.all_projects()
    found = proj._by_path(projects, repo)
    if name:
        p = next((p for p in projects if name in (p.name, p.dir.name)), None)
        if p and not any(r.resolve() == repo for r in p.repos):
            raise SystemExit("memcrumbs: project %s exists for %s; pick another name" % (
                name, ", ".join(posix(r) for r in p.repos) or "no repo"))
        if p is None and found is not None:
            raise SystemExit("memcrumbs: this repo is set up as %s already: memcrumbs init (no name) repairs it"
                             % found.name)
        return p
    return found


def init(out, args):
    if args.remove:
        return remove(out, args)
    repos = _repos(args)
    if not repos and not args.name:                  # not in git: this folder is the project's folder
        here, why = _plain_folder()
        if here is None:
            raise SystemExit("memcrumbs: %s is not in a git repository and %s. Run memcrumbs init in your project "
                             "folder, pass --repo PATH, or pass a NAME for a wiki without a repo" % (posix(Path.cwd()), why))
        out("not a git repository: setting up this folder")
        repos = [here]
    if not repos:
        cmd_setup.init(out, args.name, [], args.title)
        return 0
    repo = repos[0]
    project = _owner(args.name, repo)
    fresh = project is None
    if fresh:
        found = signals.detect(repo)
        name = args.name or signals.free_name(signals.slug(repo.name))
        cmd_setup.create(name, repos, args.title or found["title"], found["exclude"], found["docs"],
                         signals.map_lines(found))
        project = proj.resolve(name)
        out("created %s: wiki %s" % (name, posix(project.wiki)))
        out(signals.found_line(found))
    else:
        out("already set up: %s (wiki %s)" % (project.name, posix(project.wiki)))
    api = plugins.load(project)
    out(_index(project, api))
    wired = _wire(out, project, repo, args)
    fails, warns = _doctor(project, api)
    out("doctor: %d fail, %d warn%s" % (fails, warns, " (memcrumbs doctor)" if fails or warns else ""))
    out.set(project=project.name, repo=posix(repo), created=fresh, wired=bool(wired), doctor=dict(fail=fails, warn=warns))
    from memcrumbs import reference
    reference.after_init(out, _interactive(out))     # once per machine, optional
    out(_next(wired, fails))
    return 0


def _index(project, api):
    from memcrumbs.cli import open_store
    t0 = time.time()
    store, _ = open_store(project)
    try:
        stats = indexer.refresh(project, api, store, wait=30)
        kinds, nsym, nfiles = store.counts()
    finally:
        store.close()
    if "skipped" in stats:
        return "index: %s" % stats["skipped"]
    return "index: %d files, %d docs, %d code symbols in %.1f s" % (nfiles, sum(kinds.values()), nsym, time.time() - t0)


def _rel(path, repo):
    try:
        return posix(Path(path).resolve().relative_to(repo))
    except ValueError:
        return posix(path)


def _offers(project, on):
    """Turn skill offers from repeated work on (appending OFFERS) or off (taking out exactly that text). The
    owner's own `[suggest] transcripts` setting is never touched."""
    p = project.dir / "memcrumbs.toml"
    text, info = read_doc(p)
    nl = newline_of(text)
    block = nl + OFFERS.replace("\n", nl)
    if on and "transcripts" not in (project.cfg.get("suggest") or {}):
        writeset.write_text(project, p, text + ("" if text.endswith(nl) else nl) + block, info, extra=[p])
        return True
    if not on and text.endswith(block):
        writeset.write_text(project, p, text[:-len(block)], info, extra=[p])
        return True
    return False


def _wire(out, project, repo, args):
    from memcrumbs import update, wire
    if args.no_wire:
        out("wire: skipped (--no-wire); run memcrumbs init again to wire")
        return None
    entry = next((w for w in update.wired(project) if w[0].resolve() == repo), None)
    targets, allow, user_skill = (entry[1], entry[2], entry[3]) if entry else (["claude"], True, False)
    plan = wire.plan(project, repo, targets, allow=allow, user_skill=user_skill, state=wire._state(project)[0])
    todo = [c for c in plan if c["new"] is not False]
    kept = ["kept %s: %s" % (_rel(c["path"], repo), c["what"]) for c in plan if c["new"] is False]
    names = ", ".join(_rel(c["path"], repo) for c in todo)
    offers = entry is None and "transcripts" not in (project.cfg.get("suggest") or {})
    also = ("; and it turns on skill offers from repeated work (Claude Code's transcripts, read locally; memcrumbs.toml "
            "[suggest] transcripts)" if offers else "")
    if entry is None:                                # a first wiring: the owner's yes, once
        if not args.yes and not _interactive(out):
            out("wire: not applied. Ask the owner, then run memcrumbs init --yes. It changes %s%s" % (names, also))
            return None
        if not args.yes:
            for c in todo:
                out("  %s: %s" % (_rel(c["path"], repo), c["what"]))
            if offers:
                out("  memcrumbs.toml: skill offers from repeated work (task flows, pipelines): Claude Code's "
                    "transcripts, read locally; nothing leaves this machine")
            if not _ask(out, "Wire Claude Code?", True):
                out("wire: not applied (run memcrumbs init again to wire)")
                return None
    c = Collect()
    wire.wire(c, project, repo, targets, apply=True, user_skill=user_skill, allow=allow)
    said = ("wire: Claude Code is wired and current" if not todo else
            "wire: %s %s (undo: memcrumbs init --remove)" % ("updated" if entry else "wrote", names))
    if offers and _offers(project, True):
        said += "; skill offers from repeated work: on"
    out("; ".join([said] + kept))
    return "again" if entry else "first"


def _doctor(project, api):
    from memcrumbs import doctor
    c = Collect()
    doctor.run(c, project, api)
    checks = c.data.get("checks", [])
    return sum(1 for x in checks if x["status"] == "fail"), sum(1 for x in checks if x["status"] == "warn")


def _next(wired, fails):
    if fails:
        return "next: memcrumbs doctor says what to fix"
    if not wired:
        return "next: memcrumbs init --yes wires Claude Code"
    if wired == "first":
        return ("next: start Claude Code here. The header says the wiki is new: the agent drafts rules and gotchas, "
                "and you approve them in the session: /memcrumbs-review")
    return "next: nothing to do"


def remove(out, args):
    from memcrumbs import update, wire
    if args.name:
        project = proj.resolve(args.name)
    else:
        repos = _repos(args) or [Path.cwd().resolve()]      # a folder set up without git is found the same way
        project = proj._by_path(proj.all_projects(), repos[0])
    if project is None:
        raise SystemExit("memcrumbs: no project is set up here; pass its name: memcrumbs init --remove NAME")
    from memcrumbs.cli import owner_gate
    owner_gate(project, args)
    if args.delete_wiki and not args.yes and not _interactive(out):        # refused before anything changes
        raise SystemExit("memcrumbs: --delete-wiki deletes %s (%d wiki pages, the index, the config). Ask the owner, "
                         "then add --yes" % (posix(project.dir), len(project.wiki_pages())))
    done = []
    for repo, targets, _allow, user_skill in update.wired(project):
        wire.wire(Collect(), project, repo, targets, apply=True, remove=True, user_skill=user_skill)
        done.append(posix(repo))
    if _offers(project, False):
        done.append("skill offers from repeated work (off)")
    out("unwired: %s" % (", ".join(done) if done else "nothing was wired"))
    out.set(project=project.name, unwired=done, deleted=False)
    if not args.delete_wiki:
        out("kept the wiki: %s (to delete it too: memcrumbs init --remove --delete-wiki)" % posix(project.dir))
        return 0
    return _delete(out, project, args)


def _delete(out, project, args):
    d, root = project.dir.resolve(), proj.projects_dir().resolve()
    if root not in d.parents or not (d / proj.CONFIG_NAME).is_file():
        raise SystemExit("memcrumbs: %s is not a project folder under %s; delete it by hand" % (posix(d), posix(root)))
    pages = len(project.wiki_pages())
    if not args.yes and not _ask(out, "Delete %s (%d wiki pages, the index, the config)?" % (posix(d), pages), False):
        out("kept the wiki: %s" % posix(d))
        return 0
    try:
        shutil.rmtree(d)
    except OSError as e:
        raise SystemExit("memcrumbs: could not delete %s (%s); close other memcrumbs processes and retry"
                         % (posix(d), type(e).__name__))
    out("deleted %s" % posix(d))
    out.set(deleted=True)
    wiki = project.wiki.resolve()
    if d not in wiki.parents:
        out("the wiki at %s is outside the project folder: kept" % posix(wiki))
    return 0
