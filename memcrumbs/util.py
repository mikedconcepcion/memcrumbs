"""Small shared helpers: utf-8 console, BOM-aware reads, byte-exact round trips, ** globs, pruned walks."""
import os
import re
import sys
from pathlib import Path

PRUNE = {"node_modules", "__pycache__", "venv", "site-packages", "dist", "build"}
_BOMS = ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be"))


def utf8_stdout():
    # Windows consoles default to cp1252 and crash on emoji / box characters
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_text(path):
    """Decode by BOM (some editors save UTF-16), else utf-8 with replacement. For reading only."""
    b = Path(path).read_bytes()
    for bom, enc in _BOMS:
        if b.startswith(bom):
            return b[len(bom):].decode(enc, errors="replace")
    return b.decode("utf-8", errors="replace")


def read_doc(path):
    """Read a file we may rewrite: (text, encoding info). `encode_doc` restores the exact bytes, BOM and
    undecodable bytes included, so an edit never changes text it did not mean to touch."""
    b = Path(path).read_bytes()
    for bom, enc in _BOMS:
        if b.startswith(bom):
            return b[len(bom):].decode(enc, errors="surrogatepass" if enc != "utf-8" else "surrogateescape"), (bom, enc)
    return b.decode("utf-8", errors="surrogateescape"), (b"", "utf-8")


def encode_doc(text, info=(b"", "utf-8")):
    bom, enc = info
    return bom + text.encode(enc, errors="surrogateescape" if enc == "utf-8" else "surrogatepass")


def newline_of(text):
    """The file's newline style, so inserted lines match it."""
    return "\r\n" if "\r\n" in text else "\n"


def posix(p):
    return str(p).replace("\\", "/")


_glob_cache = {}


def glob_re(pat):
    r = _glob_cache.get(pat)
    if r is None:
        out, i = "", 0
        while i < len(pat):
            if pat.startswith("**/", i):
                out += "(?:.*/)?"
                i += 3
                continue
            if pat.startswith("**", i):
                out += ".*"
                i += 2
                continue
            c = pat[i]
            out += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
            i += 1
        r = _glob_cache[pat] = re.compile(out + r"\Z", re.I)
    return r


_any_cache = {}


def matches(rel, pats):
    """Does `rel` match any of the globs? One compiled alternation per pattern list (a `find` checks every wiki
    page against the ~40 never_index globs)."""
    key = tuple(pats)
    r = _any_cache.get(key)
    if r is None:
        if len(_any_cache) > 256:
            _any_cache.clear()
        r = _any_cache[key] = re.compile("|".join("(?:%s)" % glob_re(p).pattern for p in key), re.I) if key else False
    return bool(r) and r.match(rel) is not None


def walk(root, include, exclude=(), max_bytes=2_000_000, blocked=None):
    """Yield (abs_path, rel_posix) under root matching include and not exclude (the v0.1 contract)."""
    for p, rel, _ in walk_stat(root, include, exclude, max_bytes, blocked):
        yield p, rel


def walk_stat(root, include, exclude=(), max_bytes=2_000_000, blocked=None):
    """Yield (abs_path, rel_posix, stat) under root matching include and not exclude (nor `blocked(path)`).
    Dot-directories and PRUNE names are skipped, as is any directory an exclude pattern swallows.
    Uses scandir, so on Windows the stat comes free with the directory listing."""
    root = Path(root)
    if not root.is_dir():
        return
    stack, seen = [(str(root), "")], set()
    while stack:
        dp, rel_dir = stack.pop()
        try:
            key = (os.stat(dp).st_dev, os.stat(dp).st_ino)
        except OSError:
            continue
        if key in seen and key != (0, 0):
            continue                                       # a loop through a junction or a bind mount
        seen.add(key)
        try:
            with os.scandir(dp) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            continue
        subdirs = []
        for e in entries:
            rel = rel_dir + e.name
            try:
                if e.is_dir(follow_symlinks=False):
                    if _junction(e):
                        continue                                   # Windows junctions are never followed
                    if not e.name.startswith(".") and e.name not in PRUNE and not matches(rel + "/x", exclude):
                        subdirs.append((e.path, rel + "/"))
                    continue
                if not matches(rel, include) or matches(rel, exclude):
                    continue
                st = e.stat()
            except OSError:
                continue
            if st.st_size <= max_bytes and not (blocked and blocked(e.path)):
                yield Path(e.path), rel, st
        stack.extend(reversed(subdirs))


def _junction(entry):
    try:
        return entry.is_junction()                         # Python 3.12+
    except AttributeError:
        try:
            return bool(entry.stat(follow_symlinks=False).st_file_attributes & 0x400)   # a reparse point
        except (AttributeError, OSError):
            return False


def split_lines(text):
    """Lines as editors number them: split on newlines only. str.splitlines() also splits on U+2028, form feeds and
    other separators, which would shift every later path:line."""
    parts = text.split("\n") if text else []
    if parts and parts[-1] == "":
        parts.pop()                                        # like splitlines(): a final newline adds no line
    return [ln[:-1] if ln.endswith("\r") else ln for ln in parts]


def stamp(st):
    """Change-detection stamp: mtime plus size, so a same-second rewrite on a coarse filesystem is seen."""
    return "%d:%d" % (st.st_mtime_ns, st.st_size)


def clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


SHELL_SAFE = re.compile(r"^[\w.+=/:-]+$")


def shq(word):
    """A word for a command line someone will copy (an agent's next step, a dashboard button): bare when it is plainly
    safe, else in single quotes, which bash and PowerShell both read literally. A word that holds a single quote
    cannot be quoted the same way in both, so it is withheld: a page name must never run code in a terminal."""
    word = str(word)
    if SHELL_SAFE.match(word):
        return word
    return "'%s'" % word if "'" not in word and "\n" not in word else "<rename it: unsafe characters>"
