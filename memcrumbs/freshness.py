"""How old and how trustworthy a crumb is: `verified` age, staleness (by date, and by `sources:` changed after
the page was verified), status (superseded, rejected …) and injection flags.

Search hits carry the cheap labels (age, status, flags). Source changes are checked by `check` and `page`:
inside a git work tree a source's change time is its last commit (a fresh clone resets every mtime), or its
mtime when it has local edits; outside git, its mtime."""
import datetime as dt
import os
import re
import subprocess
from pathlib import Path

from memcrumbs import markdown
from memcrumbs.util import read_text

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}$")
LOUD = {"superseded", "rejected", "parked", "draft"}
_GIT = {}


def parse_date(date, today=None):
    """A real YYYY-MM-DD date that is not in the future (a day of clock skew allowed), else None. A page dated
    2099 would otherwise look fresh forever."""
    if not date or not _DATE.match(str(date)):
        return None
    try:
        d = dt.date.fromisoformat(str(date))
    except ValueError:
        return None                                        # 2026-02-30
    return d if (d - (today or dt.date.today())).days <= 1 else None


def days_since(date, today=None):
    d = parse_date(date, today)
    return max(0, ((today or dt.date.today()) - d).days) if d else None


def page_meta(path):
    try:
        return markdown.frontmatter(read_text(path))[0]
    except OSError:
        return {}


def source_paths(project, sources):
    """Existing files named in `sources:` (relative to the project folder, the wiki or a repo); ids and URLs skip."""
    out = []
    for s in sources if isinstance(sources, list) else [sources] if sources else []:
        s = str(s).strip()
        if not s or "://" in s or not re.search(r"[./\\]", s):
            continue
        roots = [project.dir, project.wiki] + project.repos + [r.parent for r in project.repos]
        for root in roots:
            p = Path(s) if Path(s).is_absolute() else root / s
            if p.is_file():
                out.append(p.resolve())
                break
    return out


def _git_root(path):
    for d in [path.parent] + list(path.parent.parents):
        if (d / ".git").exists():
            return d
    return None


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root), "-c", "core.quotePath=false"] + list(args), capture_output=True,
                           text=True, timeout=20,
                           encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _commit_time(line):
    """'@<time> <parents>' → the time, or None for a root commit: the repo's first import is not a change."""
    parts = line[1:].split()
    return int(parts[0]) if len(parts) > 1 else None


def _git_times(root, since):
    """({posix relpath: last commit time} since `since`, {paths with local edits or untracked}) or None."""
    key = (str(root), since)
    if key not in _GIT:
        log = _git(root, "log", "--since=%s" % since, "--format=@%ct %P", "--name-only", "--no-renames")
        status = _git(root, "status", "--porcelain", "-uall")
        if log is None or status is None:
            _GIT[key] = None
        else:
            times, t = {}, 0
            for ln in log.splitlines():
                if ln.startswith("@"):
                    t = _commit_time(ln)
                elif ln.strip() and t is not None:
                    times.setdefault(ln.strip(), t)
            dirty = {ln[3:].split(" -> ")[-1].strip().strip('"') for ln in status.splitlines() if len(ln) > 3}
            _GIT[key] = (times, dirty)
    return _GIT[key]


def changed_at(path, since):
    """When `path` last changed, for comparing with a verified date (YYYY-MM-DD)."""
    root = _git_root(path)
    info = _git_times(root, since) if root else None
    if info:
        times, dirty = info
        rel = path.relative_to(root).as_posix()
        if rel not in dirty:
            return times.get(rel, 0)              # no commit since `since`: unchanged since then
    return path.stat().st_mtime


def changed_sources(project, meta, today=None):
    """`sources:` files changed after the day the page was verified (the facts may have moved)."""
    d = parse_date(meta.get("verified"), today)
    if d is None:
        return []
    day_after = d + dt.timedelta(days=1)
    cutoff = dt.datetime.combine(day_after, dt.time()).timestamp()
    return [p for p in source_paths(project, meta.get("sources")) if changed_at(p, day_after.isoformat()) > cutoff]


def _times(paths, since):
    """{path: last change time} for many files at once: one `git log` (and one `git status`) per repo, limited to
    these paths and to commits since `since`; a file with local edits, or outside git, gives its mtime."""
    by_root, out = {}, {}
    for p in set(paths):
        by_root.setdefault(_git_root(p), []).append(p)
    for root, files in by_root.items():
        rels = {}
        if root is not None:
            for f in files:
                try:
                    rels[f.relative_to(root).as_posix()] = f
                except ValueError:
                    pass
        times, dirty, ok = {}, set(), root is not None
        names = sorted(rels)
        for i in range(0, len(names), 150):                  # Windows caps a command line at ~32k characters
            log = _git(root, "log", "--since=%s" % since, "--format=@%ct %P", "--name-only", "--no-renames", "--",
                       *names[i:i + 150]) if ok else None
            status = _git(root, "status", "--porcelain", "-uall", "--", *names[i:i + 150]) if ok else None
            if log is None or status is None:
                ok = False
                break
            t = 0
            for ln in log.splitlines():
                if ln.startswith("@"):
                    t = _commit_time(ln)
                elif ln.strip() and t is not None:
                    times.setdefault(ln.strip(), t)
            dirty |= {ln[3:].split(" -> ")[-1].strip().strip('"') for ln in status.splitlines() if len(ln) > 3}
        for f in files:
            rel = next((r for r, x in rels.items() if x == f), None)
            if ok and rel is not None and rel not in dirty:
                out[f] = times.get(rel, 0)                   # no commit since `since`: unchanged since then
            else:
                try:
                    out[f] = f.stat().st_mtime
                except OSError:
                    out[f] = 0
    return out


def page_freshness(project):
    """[(page key, last source change, changed file names)] for every current wiki page whose `sources:` changed
    after its `verified` day. Computed once per index refresh, so hits can show it at no cost."""
    from memcrumbs.util import posix
    pages = []
    for p in project.wiki_pages():
        meta = page_meta(p)
        v, status = str(meta.get("verified") or ""), str(meta.get("status") or "").lower()
        if parse_date(v) is None or status in ("superseded", "rejected") or "journal" in p.relative_to(project.wiki).parts:
            continue
        srcs = source_paths(project, meta.get("sources"))
        if srcs:
            pages.append((p, v, srcs))
    if not pages:
        return []
    times = _times([s for _, _, srcs in pages for s in srcs], min(v for _, v, _ in pages))
    out = []
    for p, v, srcs in pages:
        cutoff = dt.datetime.combine(dt.date.fromisoformat(v) + dt.timedelta(days=1), dt.time()).timestamp()
        moved = sorted(((times.get(s, 0), s.name) for s in srcs if times.get(s, 0) > cutoff), reverse=True)
        if moved:
            out.append((posix(p), moved[0][0], ", ".join(n for _, n in moved[:3])))
    return out


def label(project, hit, today=None, cache=None, sources=False):
    """Compact trust label, e.g. 'v12d', 'v400d STALE', 'v3d SUPERSEDED→backup-system'. `sources=True` also checks
    `sources:` (one page; search hits skip it to stay fast)."""
    stale_days = int(project.check_cfg.get("stale_days", 45))
    parts = []
    age = days_since(hit.get("verified"), today)
    if age is not None:
        parts.append("v%dd" % age)
        if age > stale_days:
            parts.append("STALE")
    else:
        try:
            parts.append("m%dd" % ((dt.datetime.now().timestamp() - os.stat(hit["path"]).st_mtime) // 86400))
        except OSError:
            pass
    status = (hit.get("status") or "").lower()
    meta = None
    if status == "superseded" or (sources and age is not None):
        cache = {} if cache is None else cache
        meta = cache.get(hit["path"])
        if meta is None:
            meta = cache[hit["path"]] = page_meta(hit["path"])
    if sources and age is not None and "STALE" not in parts:
        moved = changed_sources(project, meta, today)
        if moved:
            parts.append("STALE(sources changed: %s)" % ", ".join(p.name for p in moved[:2]))
    elif not sources and hit.get("src_changed") and status not in ("superseded", "rejected"):
        parts.append("SRC-CHANGED %dd" % max(0, (dt.datetime.now().timestamp() - float(hit["src_changed"])) // 86400))
    tokens = (hit.get("flags") or "").split()
    if "destructive" in tokens:
        parts.append("DESTRUCTIVE")
    if "unreviewed" in tokens:                         # agent-written, no human has reviewed it
        parts.append("UNREVIEWED")
    if status in LOUD:
        by = (meta or {}).get("superseded_by") if status == "superseded" else None
        parts.append(status.upper() + ("→" + str(by) if by else ""))
    if [f for f in (hit.get("flags") or "").split() if f not in ("destructive", "unreviewed")]:
        parts.append("⚠INSTRUCTION-LIKE TEXT")
    return " ".join(parts)
