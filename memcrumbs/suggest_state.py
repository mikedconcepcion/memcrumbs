"""State and writes for `memcrumbs suggest`: what is open, seen, dismissed and applied, with the backups that
let `undo` put every byte back.

- One writer at a time: an exclusive lock file around every read-modify-write (a lock older than a minute is
  stale). Detection runs outside the lock; only the save holds it.
- A state file that cannot be parsed is moved aside, never saved over, so its undo records survive for a person.
- `apply` refuses an id that is already applied, a patch that names one file twice, and a file that changed since
  the owner looked at its diff (`show` records what it showed). It writes backups first, then the record, then the
  files, and puts back what it wrote if a write fails. Each apply keeps its own backup folder."""
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import time
from pathlib import Path

from memcrumbs import writeset
from memcrumbs.util import posix, read_doc, read_text

LOCK_WAIT, LOCK_STALE = 10.0, 60.0


def _path(project):
    return project.data / "suggest.json"


def load_state(project):
    p = _path(project)
    st = {}
    for _ in range(20):
        try:
            st = json.loads(read_text(p)) if p.exists() else {}
            break
        except PermissionError:                     # Windows: another memcrumbs is replacing it right now
            time.sleep(0.05)
        except (OSError, ValueError):
            st = None
            break
    if not isinstance(st, dict):
        try:
            writeset.move(project, p, p.with_name("suggest.json.broken-%d" % int(time.time())))
        except OSError:
            pass
        st = {}
    for k in ("open", "decided", "applied", "shown"):
        if not isinstance(st.get(k), dict):
            st[k] = {}
    return st


def save_state(project, st):
    writeset.write_text(project, _path(project), json.dumps(st, indent=1, sort_keys=True) + "\n")


@contextlib.contextmanager
def locked(project, wait=LOCK_WAIT):
    lock = project.data / "suggest.lock"
    t0 = time.time()
    while True:
        try:
            writeset.create_new(project, lock, str(os.getpid()))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE:
                    writeset.delete(project, lock)
                    continue
            except OSError:
                pass
            if time.time() - t0 > wait:
                raise SystemExit("memcrumbs: another memcrumbs is saving suggestions; try again in a moment")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            writeset.delete(project, lock)
        except OSError:
            pass


def _sha(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def remember_shown(project, s):
    """What the owner saw: the base of each file in the patch. `apply` refuses if a base changed since."""
    with locked(project):
        st = load_state(project)
        st["shown"][s.id] = {str(p): _sha(p) for p, _ in s.changes}
        save_state(project, st)


def wiki_only(project, s):
    roots = [project.wiki.resolve(), project.data.resolve()]
    return all(any(Path(p).resolve() == r or r in Path(p).resolve().parents for r in roots) for p, _ in s.changes)


def apply(project, s, outside_wiki=False, allow_destructive=False):
    """Write a suggestion's patch: all of it, or none of it."""
    if s.risk == "destructive" and not allow_destructive:
        raise SystemExit("memcrumbs: %s is destructive: add --allow-destructive after the owner's yes" % s.id)
    if not wiki_only(project, s) and not outside_wiki:
        raise SystemExit("memcrumbs: %s writes outside the wiki: add --outside-wiki after the owner's yes" % s.id)
    if getattr(s, "human", False):                     # it loosens a guard: never an agent's own decision
        from memcrumbs import review
        review.confirm("apply %s" % s.id, project, ("suggest", "apply"))
    paths = [str(Path(p)) for p, _ in s.changes]
    if len(set(p.lower() for p in paths)) != len(paths):
        raise SystemExit("memcrumbs: %s names one file twice; nothing written" % s.id)
    with locked(project):
        st = load_state(project)
        if s.id in st["applied"]:
            raise SystemExit("memcrumbs: %s is already applied (%s); undo it first" % (s.id, st["applied"][s.id].get("at")))
        seen = st["shown"].get(s.id)
        if seen and any(_sha(p) != seen.get(p, _sha(p)) for p in paths):
            raise SystemExit("memcrumbs: a file in %s changed since you looked at it: memcrumbs suggest show %s again"
                             % (s.id, s.id))
        bdir = project.data / "suggest-backups" / ("%s-%d" % (s.id, int(time.time() * 1000)))
        files = []
        for n, (path, _) in enumerate(s.changes):          # every backup first, then the record, then the writes
            path = Path(path)
            existed = path.exists()
            if existed:
                writeset.write_bytes(project, bdir / ("%d.bak" % n), path.read_bytes())
            files.append(dict(path=str(path), existed=existed, backup=n, after=None))
        st["applied"][s.id] = dict(kind=s.kind, key=s.key, at=dt.date.today().isoformat(), files=files, risk=s.risk,
                                   backups=posix(bdir.relative_to(project.data)), pending=True)
        save_state(project, st)
        written = []
        try:
            for f, (_, new) in zip(files, s.changes):
                path = Path(f["path"])
                if new is None:
                    writeset.delete(project, path, paths)
                else:
                    info = read_doc(path)[1] if f["existed"] else (b"", "utf-8")
                    writeset.write_text(project, path, new, info, paths)
                    f["after"] = _sha(path)
                written.append(f)
        except BaseException:                               # put back what was already written
            for f in reversed(written):
                path = Path(f["path"])
                if f["existed"]:
                    writeset.write_bytes(project, path, (bdir / ("%d.bak" % f["backup"])).read_bytes(), paths)
                elif path.exists():
                    writeset.delete(project, path, paths)
            st["applied"].pop(s.id, None)
            save_state(project, st)
            raise
        st["applied"][s.id].pop("pending", None)
        st["decided"].pop(s.id, None)
        st["shown"].pop(s.id, None)
        save_state(project, st)
    return files


def undo(project, sid):
    with locked(project):
        st = load_state(project)
        rec = st["applied"].get(sid)
        if not rec:
            raise SystemExit("memcrumbs: %s was not applied" % sid)
        bdir = project.data / rec.get("backups", "suggest-backups/" + sid)
        paths = [f["path"] for f in rec["files"]]
        for f in rec["files"]:
            p = Path(f["path"])
            now, backup = _sha(p), bdir / ("%d.bak" % f["backup"])
            untouched = f["existed"] and p.exists() and backup.exists() and p.read_bytes() == backup.read_bytes()
            if now != f["after"] and not untouched and not (rec.get("pending") and not f["existed"] and now is None):
                raise SystemExit("memcrumbs: %s changed since %s was applied; undo it by hand (git)" % (posix(p), sid))
        for f in rec["files"]:
            p = Path(f["path"])
            if f["existed"]:
                writeset.write_bytes(project, p, (bdir / ("%d.bak" % f["backup"])).read_bytes(), paths)
            elif p.exists():
                writeset.delete(project, p, paths)
        del st["applied"][sid]
        save_state(project, st)
    return paths


def period_days(period):
    """'14', '14d' or '2w' → days. Anything else is refused."""
    m = re.match(r"^\s*(\d{1,4})\s*([dw]?)\s*$", (period or "14d").lower())
    if not m or int(m.group(1)) == 0:
        raise SystemExit("memcrumbs: --for takes days or weeks, like 14d or 2w")
    return int(m.group(1)) * (7 if m.group(2) == "w" else 1)


def dismiss(project, sid, period=None, never=False):
    days = period_days(period)
    until = None if never else (dt.date.today() + dt.timedelta(days=days)).isoformat()
    with locked(project):
        st = load_state(project)
        st["decided"][sid] = dict(never=bool(never), until=until, at=dt.date.today().isoformat())
        save_state(project, st)
    return until
