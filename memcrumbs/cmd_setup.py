"""Setup commands: init (new project) and template (page skeleton)."""
import datetime as dt
import re
from pathlib import Path

from memcrumbs.project import CONFIG_NAME, projects_dir
from memcrumbs.util import posix

TPL = Path(__file__).parent / "templates"


def _tpl(tpl_name, **kw):
    t = (TPL / tpl_name).read_text(encoding="utf-8")
    for k, v in kw.items():
        t = t.replace("{%s}" % k, str(v))
    return t


def _toml(text):
    """Text inside a TOML basic string: backslashes and quotes escaped, line breaks dropped."""
    return " ".join(str(text).split()).replace("\\", "\\\\").replace('"', '\\"')


MAP = "- What it is: …\n- Where things live: …\n- Start here: [[gotchas]]"


def _config(name, title, repos, code_exclude=(), docs=None):
    """memcrumbs.toml from the template, plus what `init` found in the repo: generated folders to skip, and the
    repo's markdown (README, docs/) as a doc tree."""
    text = _tpl(CONFIG_NAME, name=name, title=_toml(title or name),
                repos=", ".join('"%s"' % _toml(posix(Path(r).resolve())) for r in repos))
    if code_exclude:
        text = text.replace('"**/__pycache__/**"]', '"**/__pycache__/**", %s]' % ", ".join(
            '"%s"' % _toml(x) for x in code_exclude), 1)
    if docs:
        text += ('\n[[docs]]                         # found by init: the repo\'s own markdown\nname = "repo-docs"\n'
                 'root = "%s"\ninclude = [%s]\nkind = "doc"\n' % (_toml(posix(Path(docs["root"]).resolve())),
                                                                ", ".join('"%s"' % _toml(g) for g in docs["include"])))
    return text


def create(name, repos=(), title=None, code_exclude=(), docs=None, map_lines=None):
    """Write a new project folder: config, starter wiki, secrets file. Never over an existing file."""
    if not re.match(r"^[A-Za-z0-9][\w.-]{0,63}$", name) or name.endswith(".") or ".." in name:
        raise SystemExit("memcrumbs: a project name is letters, digits, '.', '-' and '_' (not a path): %r" % name)
    d = projects_dir() / name
    if (d / CONFIG_NAME).exists():
        raise SystemExit("project %s already exists: %s" % (name, d))
    if d.exists() and any(d.iterdir()):
        raise SystemExit("memcrumbs: %s exists and is not empty; nothing written (pick another name)" % d)
    today = dt.date.today().isoformat()
    (d / "wiki" / "journal").mkdir(parents=True, exist_ok=True)
    (d / "plugins").mkdir(exist_ok=True)
    files = {CONFIG_NAME: _config(name, title, repos, code_exclude, docs),
             "wiki/index.md": _tpl("index.md", title=title or name, today=today, map="\n".join(map_lines or [MAP])),
             "wiki/gotchas.md": _tpl("gotchas.md", today=today),
             "wiki/rules.md": _tpl("rules.md", today=today),
             "secrets.deny": "# one secret per line, or sha256:<len>:<hex> from `memcrumbs secret-add` (git-ignored)\n"}
    for rel, text in files.items():
        with open(d / rel, "xb") as f:                 # never over an existing file
            f.write(text.encode("utf-8"))
    return d


def init(out, name, repos=(), title=None):
    """A project without a repo (a wiki of its own): only the folder. Inside a repo, `setup_repo.init` does it all."""
    d = create(name, repos, title)
    out.set(path=posix(d))
    out("created %s\nnext: memcrumbs -p %s index · then wire --apply from the repo (or pass --repo)" % (posix(d), name))


def template(out):
    out((TPL / "page.md").read_text(encoding="utf-8"))
