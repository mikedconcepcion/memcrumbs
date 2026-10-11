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


def init(out, name, repos=(), title=None):
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
    repos_toml = ", ".join('"%s"' % _toml(posix(Path(r).resolve())) for r in repos)
    files = {CONFIG_NAME: _tpl(CONFIG_NAME, name=name, title=_toml(title or name), repos=repos_toml),
             "wiki/index.md": _tpl("index.md", title=title or name, today=today),
             "wiki/gotchas.md": _tpl("gotchas.md", today=today),
             "wiki/rules.md": _tpl("rules.md", today=today),
             "secrets.deny": "# one secret per line, or sha256:<len>:<hex> from `memcrumbs secret-add` (git-ignored)\n"}
    for rel, text in files.items():
        with open(d / rel, "xb") as f:                 # never over an existing file
            f.write(text.encode("utf-8"))
    out.set(path=posix(d))
    out("created %s\nnext: memcrumbs -p %s index · then wire --apply from the repo (or pass --repo)" % (posix(d), name))


def template(out):
    out((TPL / "page.md").read_text(encoding="utf-8"))
