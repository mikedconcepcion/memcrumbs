"""Project resolution + config (<projects_dir>/<name>/memcrumbs.toml)."""
import os
import subprocess
import tomllib
from functools import cached_property
from pathlib import Path

from memcrumbs.redact import Redactor
from memcrumbs.util import matches, posix

CONFIG_NAME = "memcrumbs.toml"
USER_DIR = Path.home() / ".memcrumbs"
# [security] never_index: always applied; a project's list adds to it. A pattern without "/" matches the file
# name, one with "/" the whole path. Matching ignores case.
NEVER_INDEX = (
    ".env", ".env.*", "*.env", ".envrc", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
    "*.ppk", "*.ovpn", "*.tfstate", "*.tfstate.*", "*.tfvars", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".netrc", "_netrc", ".pgpass", ".npmrc", ".pypirc", ".git-credentials", ".htpasswd", "credentials",
    "credentials.*", "*credentials*.json", "client_secret*.json", "secrets.*", "*.secrets", "*.secret",
    "secrets.deny", "**/.ssh/**", "**/.aws/**", "**/.gnupg/**", "**/.docker/config.json", "**/.kube/config",
)
STATUSES = ("current", "draft", "accepted", "rejected", "parked", "superseded")


def projects_dir():
    """Where project folders live — keep them OUT of the package repo (they hold private wikis):
    $MEMCRUMBS_PROJECTS, else `projects_dir` in ~/.memcrumbs/config.toml, else ~/.memcrumbs/projects."""
    if os.environ.get("MEMCRUMBS_PROJECTS"):
        return Path(os.environ["MEMCRUMBS_PROJECTS"])
    cfg = USER_DIR / "config.toml"
    if cfg.exists():
        with open(cfg, "rb") as f:
            d = tomllib.load(f).get("projects_dir")
        if d:
            return Path(d).expanduser()
    return USER_DIR / "projects"


class Project:
    def __init__(self, cfg_path):
        self.cfg_path = Path(cfg_path).resolve()
        self.dir = self.cfg_path.parent
        with open(self.cfg_path, "rb") as f:
            self.cfg = tomllib.load(f)
        for table in ("check", "security", "status", "search", "code", "facts", "review", "suggest"):
            if table in self.cfg and not isinstance(self.cfg[table], dict):
                raise ValueError("[%s] must be a table" % table)
        self.name = self.cfg.get("name", self.dir.name)
        self.title = self.cfg.get("title", self.name)
        self.wiki = (self.dir / self.cfg.get("wiki", "wiki")).resolve()
        self.repos = [self.path(r) for r in self.cfg.get("repos", [])]
        self.data = self.dir / ".memcrumbs"
        self.index_path = self.data / "index.db"
        self.check_cfg = self.cfg.get("check", {})
        sec = self.cfg.get("security", {})
        self.never_index = NEVER_INDEX + tuple(sec.get("never_index", []))
        self.secret_keys = tuple(sec.get("secret_keys", []))

    @cached_property
    def redact(self):
        return Redactor(self.dir / "secrets.deny", self.secret_keys)

    def path(self, p):
        """Config paths: absolute as given, relative ones resolve against the project folder."""
        p = Path(p).expanduser()
        return p if p.is_absolute() else (self.dir / p).resolve()

    def blocked(self, path):
        """True if [security] never_index forbids indexing or printing this file."""
        return is_blocked(path, self.never_index)

    def rel(self, path):
        """Short display path: wiki-relative for wiki pages, else absolute posix."""
        p = Path(path)
        s, w = posix(p), posix(self.wiki) + "/"
        if s.startswith(w) and "/../" not in s and "/./" not in s:
            return "wiki/" + s[len(w):]                   # the usual case: no filesystem call
        try:
            return "wiki/" + posix(p.resolve().relative_to(self.wiki))
        except ValueError:
            return posix(p)

    def wiki_pages(self):
        from memcrumbs.util import walk_stat              # no junction loops, dot folders skipped
        return sorted(p for p, _, _ in walk_stat(self.wiki, ["**/*.md"], [], max_bytes=1 << 40)
                      if not self.blocked(p))


_split = {}


def is_blocked(path, patterns=NEVER_INDEX):
    key = tuple(patterns)
    if key not in _split:
        _split[key] = (tuple(x for x in key if "/" not in x), tuple(x for x in key if "/" in x))
    names, paths = _split[key]
    p = posix(path)
    return matches(p.rsplit("/", 1)[-1], names) or matches(p.lstrip("/"), paths)


BROKEN = {}                     # folder name -> why its memcrumbs.toml could not be read (shown when it is chosen)


def all_projects():
    """Every project whose config parses. One broken config never stops the others (it is recorded in BROKEN)."""
    out = []
    for p in sorted(projects_dir().glob("*/" + CONFIG_NAME)):
        try:
            out.append(Project(p))
        except (OSError, ValueError, TypeError) as e:       # tomllib.TOMLDecodeError is a ValueError
            BROKEN[p.parent.name] = "%s: %s" % (type(e).__name__, str(e).splitlines()[0][:160] if str(e) else "")
    return out


def resolve(name=None, cwd=None):
    """By explicit name / $MEMCRUMBS_PROJECT, else by cwd inside a project dir or one of its repos."""
    name = name or os.environ.get("MEMCRUMBS_PROJECT")
    projects = all_projects()
    if name:
        for p in projects:
            if p.name == name or p.dir.name == name:
                return p
        if name in BROKEN:
            raise SystemExit("memcrumbs: the config of project %r cannot be read (%s)" % (name, BROKEN[name]))
        raise SystemExit("memcrumbs: no project named %r (have: %s)" % (name, ", ".join(p.name for p in projects) or "none"))
    cwd = Path(cwd or os.getcwd()).resolve()
    best = _by_path(projects, cwd)
    if best is None:
        main = _main_worktree_path(cwd)              # a git worktree (parallel agents) maps to its main checkout
        best = _by_path(projects, main) if main else None
    if best:
        return best
    if len(projects) == 1:
        return projects[0]
    raise SystemExit("memcrumbs: cannot tell which project (cwd %s); use -p NAME" % cwd)


def _by_path(projects, cwd):
    best, best_len = None, -1
    for p in projects:
        for root in [p.dir] + p.repos:
            try:
                root = root.resolve()
            except OSError:
                continue
            if (cwd == root or root in cwd.parents) and len(str(root)) > best_len:
                best, best_len = p, len(str(root))
    return best


def _main_worktree_path(cwd):
    """The same place in the main checkout when cwd is inside a linked git worktree; None otherwise."""
    try:
        r = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir",
                            "--show-toplevel"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = r.stdout.splitlines()
    if r.returncode != 0 or len(lines) < 2:
        return None
    common, top = Path(lines[0]).resolve(), Path(lines[1]).resolve()
    if common.name != ".git" or common.parent == top:
        return None
    try:
        return common.parent / cwd.relative_to(top)
    except ValueError:
        return common.parent
