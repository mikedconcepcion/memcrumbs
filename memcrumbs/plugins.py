"""Plugin API v1 (frozen under semver from 1.0; see docs/plugins.md).

A pack (memcrumbs.packs.X, or any distribution exposing the entry-point group `memcrumbs.packs`) or a project
plugin (<project>/plugins/*.py) exposes `register(api)`. memcrumbs.toml lists them:
`plugins = ["mypack", "mypkg.memcrumbs_pack", "plugins/myproject.py"]` (pack or entry-point name, module, file).
A plugin that fails to load is reported by `status` and `check`; it never stops a command."""
import importlib
import importlib.util
from pathlib import Path

from memcrumbs import markdown, outline, writeset
from memcrumbs.util import read_doc

API_VERSION = 1
GROUP = "memcrumbs.packs"


class Api:
    version = API_VERSION

    def __init__(self, project):
        self.project = project
        self.sources = {}      # name -> fn(project) yielding (path, stamp, loader); loader() -> (docs, syms)
        self.checks = []       # fn(project) -> [(level, where, message)]   level: E / W / I
        self.sections = []     # (name, fn(project) -> [lines], title): header section providers
        self.commands = {}     # name -> (setup(subparser), run(project, args), help)
        self.suggesters = {}   # kind -> fn(project, cheap_only=False) -> [suggest.Suggestion]
        self.errors = []       # (plugin spec, error type) for plugins that failed to load

    def add_source(self, name, fn):
        self.sources[name] = fn

    def add_check(self, fn):
        self.checks.append(fn)

    def add_section(self, name, fn, title=None):
        """A header section; listed by name in [status] sections, else shown where "plugins" is listed."""
        self.sections.append((name, fn, title))

    def add_status(self, fn):
        """v0.1 form of add_section: untitled lines in the "plugins" slot of the header."""
        self.add_section("status-%d" % len(self.sections), fn, None)

    def add_command(self, name, setup, run, help=""):
        self.commands[name] = (setup, run, help)

    def add_suggester(self, kind, fn):
        """A `memcrumbs suggest` kind: fn(project, cheap_only=False) returns memcrumbs.suggest.Suggestion objects."""
        self.suggesters[kind] = fn

    def add_outliner(self, exts, fn):
        outline.register(exts, fn)

    def redact(self, text):
        return self.project.redact(text)

    def write_generated(self, page, name, body):
        """The safe generated-block writer: replace block NAME in a wiki page (created if missing), redacted,
        keeping every byte outside the markers. `page` is wiki-relative ("systems/tasks.md")."""
        p = self.project.wiki / page
        text, info = read_doc(p) if p.exists() else ("", (b"", "utf-8"))
        new = markdown.replace_generated(text, name, self.project.redact(body))
        if new != text:
            writeset.write_text(self.project, p, new, info)
        return p


def _entry_point(name):
    """Scanning entry points reads every installed distribution (slow), so it is the last resort."""
    import importlib.metadata
    for ep in importlib.metadata.entry_points(group=GROUP):
        if ep.name == name:
            return ep.load()
    raise ModuleNotFoundError("no pack %r (not memcrumbs.packs.%s, nor an entry point in %s)" % (name, name, GROUP))


def _import(project, spec):
    """`plugins/x.py` (a file), `pkg.module` (a module), or a bare pack name: memcrumbs.packs.NAME, then the
    entry point NAME in group memcrumbs.packs."""
    if spec.endswith(".py"):
        path = (project.dir / spec).resolve()
        ms = importlib.util.spec_from_file_location("memcrumbs_plugin_" + Path(spec).stem, path)
        mod = importlib.util.module_from_spec(ms)
        ms.loader.exec_module(mod)
        return mod
    if "." in spec:
        return importlib.import_module(spec)
    if importlib.util.find_spec("memcrumbs.packs." + spec):
        return importlib.import_module("memcrumbs.packs." + spec)
    return _entry_point(spec)


def load(project):
    api = Api(project)
    from memcrumbs import sources
    sources.register_builtins(api)
    for spec in (project.cfg.get("plugins", []) if project else []):
        try:
            mod = _import(project, spec)
            (mod if callable(mod) and not hasattr(mod, "register") else mod.register)(api)
        except KeyboardInterrupt:
            raise
        except BaseException as e:                     # SystemExit too: a plugin never ends the command
            api.errors.append((spec, "%s: %s" % (type(e).__name__, str(e)[:120])))
    return api
