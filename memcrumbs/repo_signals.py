"""What a repo shows, for `memcrumbs init`: its title and first paragraph, languages, top folders, test command, CI,
generated folders to skip, and its own markdown. Deterministic: file names, plus the README and the test and CI
config files; nothing is guessed."""
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from memcrumbs import project as proj
from memcrumbs.redact import Redactor, safe
from memcrumbs.util import clip, read_text, walk_stat

LANGS = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
         ".mjs": "JavaScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".cs": "C#", ".rb": "Ruby",
         ".php": "PHP", ".ps1": "PowerShell", ".psm1": "PowerShell", ".sh": "Shell", ".c": "C", ".h": "C",
         ".cpp": "C++", ".hpp": "C++", ".swift": "Swift", ".mq5": "MQL5", ".mq4": "MQL4", ".mqh": "MQL"}
GENERATED = ("target", "vendor", "coverage", "obj", "out")      # dist/, build/, venv/ … are always skipped
CI = ((".gitlab-ci.yml", "GitLab CI"), ("azure-pipelines.yml", "Azure Pipelines"), (".circleci/config.yml", "CircleCI"),
      ("Jenkinsfile", "Jenkins"))


def git_root(path):
    try:
        r = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                           timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    top = r.stdout.strip()
    return Path(top).resolve() if r.returncode == 0 and top else None


def slug(text):
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-._")[:64] or "project"


def free_name(base):
    taken = {p.dir.name for p in proj.all_projects()} | {p.name for p in proj.all_projects()}
    d = proj.projects_dir()
    name, i = base, 2
    while name in taken or (d / name).exists():
        name, i = "%s-%d" % (base, i), i + 1
    return name


def _plain(md):
    """Markdown inline text as plain words: links, images, code marks and tags removed."""
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    md = re.sub(r"<[^>]+>", "", md)
    return " ".join(md.replace("`", "").replace("**", "").split())


def _readme(repo):
    try:
        f = next((p for p in sorted(repo.iterdir()) if p.is_file() and p.name.lower().startswith("readme")), None)
    except OSError:
        return ""
    return read_text(f) if f else ""


def _about(readme):
    """The README's first paragraph of prose, clipped: what the project is, in its own words."""
    para = []
    for ln in readme.splitlines():
        s = ln.strip()
        if not s:
            if para:
                break
            continue
        if s[0] in "#<|!>=-[`" or s.startswith(("```", "~~~")):
            if para:
                break
            continue
        para.append(s)
    text = _plain(" ".join(para))
    cut = text.find(". ", 40)
    return clip(text[:cut + 1] if 0 < cut < 240 else text, 240)


def _title(repo, readme):
    m = re.search(r"(?m)^#\s+(.+?)\s*#*\s*$", readme)
    if m and _plain(m.group(1)):
        return _plain(m.group(1))[:80]
    for f, rx in (("pyproject.toml", r'(?m)^name\s*=\s*"([^"]+)"'), ("package.json", r'"name"\s*:\s*"([^"]+)"')):
        try:
            m = re.search(rx, read_text(repo / f)) if (repo / f).is_file() else None
        except OSError:
            m = None
        if m:
            return m.group(1)
    return repo.name


def _tests(repo):
    def has(f, rx=None):
        p = repo / f
        try:
            return p.is_file() and (rx is None or re.search(rx, read_text(p)) is not None)
        except OSError:
            return False
    if has("pytest.ini") or has("conftest.py") or has("pyproject.toml", r"\[tool\.pytest") or \
            has("setup.cfg", r"\[tool:pytest\]") or has("tox.ini", r"\[pytest\]"):
        return "python -m pytest"
    try:
        script = (json.loads(read_text(repo / "package.json")).get("scripts") or {}).get("test", "") \
            if has("package.json") else ""
    except (OSError, ValueError, AttributeError):
        script = ""
    if script and "no test specified" not in script:
        return "npm test"
    for f, cmd in (("go.mod", "go test ./..."), ("Cargo.toml", "cargo test")):
        if has(f):
            return cmd
    return "make test" if has("Makefile", r"(?m)^test:") else None


def _ci(repo):
    wf = sorted(p.name for p in (repo / ".github" / "workflows").glob("*.y*ml")) if \
        (repo / ".github" / "workflows").is_dir() else []
    if wf:
        return "GitHub Actions (%s)" % ", ".join(wf[:4] + (["…"] if len(wf) > 4 else []))
    return next((name for f, name in CI if (repo / f).exists()), None)


def detect(repo):
    """Deterministic signals from the repo's files: nothing is guessed, and nothing is read past the top level but
    file names (and the README, test and CI config files)."""
    top = [d for d in sorted(repo.iterdir()) if d.is_dir() and not d.name.startswith(".")]
    skip = [d.name for d in top if (d / "pyvenv.cfg").exists() or d.name in GENERATED]
    exclude = ["%s/**" % n for n in skip]
    langs, dirs, md_dirs = Counter(), Counter(), set()
    md_top = False
    for _, rel, _ in walk_stat(repo, ["**/*"], exclude, max_bytes=1 << 40):
        ext = Path(rel).suffix.lower()
        if ext in LANGS:
            langs[LANGS[ext]] += 1
        head, sep, _ = rel.partition("/")
        if sep:
            dirs[head] += 1
            if ext == ".md" and head in ("docs", "doc"):
                md_dirs.add(head)
        elif ext == ".md":
            md_top = True
    readme = _readme(repo)
    include = (["*.md"] if md_top else []) + ["%s/**/*.md" % d for d in sorted(md_dirs)]
    return dict(title=_title(repo, readme), about=_about(readme), langs=langs.most_common(3),
                dirs=[d for d, _ in sorted(dirs.items(), key=lambda kv: (-kv[1], kv[0]))[:8]], tests=_tests(repo),
                ci=_ci(repo), exclude=exclude,
                docs=dict(root=repo, include=include) if include else None)


def map_lines(sig):
    red = Redactor()
    out = ["- What it is: %s" % (safe(red, sig["about"]) if sig["about"] else "…")]
    if sig["langs"]:
        out.append("- Languages: " + ", ".join("%s (%d files)" % kv for kv in sig["langs"]))
    if sig["dirs"]:
        out.append("- Where things live: " + " · ".join("`%s/`" % d for d in sig["dirs"]))
    more = ["Tests: `%s`" % sig["tests"]] if sig["tests"] else []
    more += ["CI: %s" % sig["ci"]] if sig["ci"] else []
    if more:
        out.append("- " + " · ".join(more))
    return out + ["- Start here: [[gotchas]]"]


def found_line(sig):
    parts = [", ".join("%s %d" % kv for kv in sig["langs"]) or "no code files"]
    if sig["docs"]:
        parts.append("docs: " + ", ".join(sig["docs"]["include"]))
    parts += ["tests: " + sig["tests"]] if sig["tests"] else []
    parts += ["CI: " + sig["ci"].split(" (")[0]] if sig["ci"] else []
    parts += ["skipped: " + ", ".join(x.split("/")[0] + "/" for x in sig["exclude"])] if sig["exclude"] else []
    return "found: " + " · ".join(parts)
