"""log (dated journal line) and scan (secret scan of a folder, a file, or a built sdist/wheel)."""
import datetime as dt
import os
import tarfile
import zipfile
from pathlib import Path

from memcrumbs import writeset
from memcrumbs.redact import RedactionError
from memcrumbs.util import posix, read_text, split_lines

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".memcrumbs", ".venv", "venv", ".tox"}


def log(out, project, text, tag=None):
    now = dt.datetime.now()
    f = project.wiki / "journal" / now.strftime("%Y-%m.md")
    if not f.exists():
        try:
            writeset.create_new(project, f, "---\ntitle: Journal %s\nsummary: dated one-line log of what happened "
                                "(episodic memory)\nverified: %s\ntags: [journal]\n---\n"
                                % (now.strftime("%Y-%m"), now.strftime("%Y-%m-%d")))
        except FileExistsError:
            pass                                     # another log call made it a moment ago
    line = "- %s %s%s\n" % (now.strftime("%Y-%m-%d %H:%M"), project.redact(" ".join(text.split())),
                            (" #" + tag) if tag else "")
    writeset.append_text(project, f, line)
    out.set(path=project.rel(f), line=line.strip())
    out("logged -> %s" % project.rel(f))


def recent_journal(project, n=3):
    """The last n journal lines (v0.1 contract)."""
    return journal_tail(project, n)[0]


def lint(project):
    """v0.1 location of the wiki lint (kept for plugins that call it): see lint.lint."""
    from memcrumbs.lint import lint as _lint
    return _lint(project)


def journal_tail(project, n=3):
    """(last n journal lines, the newest journal file or None)."""
    jdir = project.wiki / "journal"
    files = sorted(jdir.glob("*.md")) if jdir.exists() else []
    out = []
    for f in reversed(files):
        out = [ln for ln in read_text(f).splitlines() if ln.startswith("- ")][-n:] + out
        if len(out) >= n:
            break
    return out[-n:], (files[-1] if files else None)


def _decode(raw):
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if raw.startswith(bom):
            return raw[len(bom):].decode(enc, errors="replace")
    if b"\x00" in raw[:4096]:
        return None                                                    # binary
    return raw.decode("utf-8", errors="replace")


def _members(root, max_bytes):
    """(display name, bytes) for every file under a folder, a single file, or inside a .whl/.zip/.tar.gz."""
    root = Path(root)
    name = root.name.lower()
    if root.is_file() and name.endswith((".whl", ".zip")):
        with zipfile.ZipFile(root) as z:
            for i in z.infolist():
                if not i.is_dir() and i.file_size <= max_bytes:
                    yield "%s!%s" % (posix(root), i.filename), z.read(i)
        return
    if root.is_file() and name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(root) as t:
            for m in t.getmembers():
                if m.isfile() and m.size <= max_bytes:
                    yield "%s!%s" % (posix(root), m.name), t.extractfile(m).read()
        return
    walked = [(str(root.parent), [], [root.name])] if root.is_file() else os.walk(root)
    for dp, dns, fns in walked:
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        for f in sorted(fns):
            p = Path(dp) / f
            try:
                if p.stat().st_size <= max_bytes:
                    yield posix(p), p.read_bytes()
            except OSError:
                continue


def scan(out, redact, root, max_bytes=2_000_000):
    """Secret scan (run before publishing). Lines marked `memcrumbs:allow` are intentional fixtures.
    Exit 1 on any hit; a filter failure also counts as a hit (fail closed)."""
    hits = []
    for name, raw in _members(root, max_bytes):
        text = _decode(raw)
        if text is None:
            continue
        for i, ln in enumerate(split_lines(text), 1):
            if "memcrumbs:allow" in ln:
                continue
            try:
                found = redact.find(ln)
            except RedactionError as e:
                found = ["secret filter failed (%s)" % e]
            hits += [dict(path=name, line=i, what=h) for h in found]
    out.list_key = "hits"
    out.set(root=posix(root), hits=hits, count=len(hits))
    out.hint("memcrumbs scan %s --full" % posix(root))
    out("%d secret-like hits under %s" % (len(hits), posix(root)))
    for h in hits:
        out("E %s:%d %s" % (h["path"], h["line"], h["what"]))
    return 1 if hits else 0
