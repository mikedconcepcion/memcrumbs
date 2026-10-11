"""The write set: memcrumbs writes only to the project's wiki, its index dir, its
`secrets.deny`, and the exact files `wire` names. Every write goes through here; anything else raises.

Writes are atomic (temp file + replace) and byte-exact: callers pass text plus the encoding info from
`util.read_doc`, so a BOM, CRLF newlines or undecodable bytes outside the edited span survive."""
import os
import time
from pathlib import Path

from memcrumbs.util import encode_doc


class WriteSetError(PermissionError):
    pass


def _inside(p, root):
    return p == root or root in p.parents


def check(project, path, extra=()):
    """Resolve `path` (symlinks followed) and raise unless it is inside the write set."""
    p = Path(path).resolve()
    roots = [project.wiki.resolve(), project.data.resolve()]
    if any(_inside(p, r) for r in roots):
        return p
    files = [(project.dir / "secrets.deny").resolve()] + [Path(f).resolve() for f in extra]
    if p in files:
        if Path(path).is_symlink() or any(Path(f).is_symlink() for f in extra if Path(f).resolve() == p):
            raise WriteSetError("memcrumbs: refusing to write through a symlink: %s" % path)
        return p
    raise WriteSetError("memcrumbs: refusing to write outside the write set: %s" % p)


def _replace(tmp, p, tries=20):
    for i in range(tries):                          # Windows: a reader holding the file blocks os.replace briefly
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05)


def write_bytes(project, path, data, extra=()):
    p = check(project, path, extra)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(".%s.%d.tmp" % (p.name, os.getpid()))
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        _replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()
    return p


def write_text(project, path, text, info=(b"", "utf-8"), extra=()):
    return write_bytes(project, path, encode_doc(text, info), extra)


def append_text(project, path, text):
    """Append (journal lines): a single small write, safe enough for concurrent appenders. The line takes the
    file's encoding (a UTF-16 BOM) and newline style, and a missing final newline is added first."""
    p = check(project, path)
    p.parent.mkdir(parents=True, exist_ok=True)
    enc, head, tail = "utf-8", b"", b""
    try:
        with open(p, "rb") as f:
            head = f.read(4)
            f.seek(max(0, f.seek(0, 2) - 4096))
            tail = f.read()
    except FileNotFoundError:
        pass
    for bom, e in ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if head.startswith(bom):
            enc = e
    nl = "\r\n" if "\r\n".encode(enc) in tail else "\n"
    text = text.replace("\r\n", "\n").replace("\n", nl)
    if tail and not tail.endswith("\n".encode(enc)):
        text = nl + text
    with open(p, "ab") as f:
        f.write(text.encode(enc))
    return p


def create_new(project, path, text="", extra=()):
    """Create a file that must not exist yet (a lock, a new page): raises FileExistsError instead of replacing."""
    p = check(project, path, extra)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "xb") as f:
        f.write(text.encode("utf-8"))
    return p


def move(project, src, dst):
    """Rename inside the write set (a broken state file is moved aside, never overwritten)."""
    s, d = check(project, src), check(project, dst)
    os.replace(s, d)
    return d


def delete(project, path, extra=()):
    p = check(project, path, extra)
    if p.exists():
        p.unlink()
