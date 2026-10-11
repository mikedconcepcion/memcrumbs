"""`stats --usage`: per-command output size and latency, logged without any content (no queries, no text).

One JSON line per command in <project>/.memcrumbs/usage.jsonl, trimmed to the last MAX_LINES lines."""
import json
import os
import time

from memcrumbs import writeset

MAX_BYTES = 1_000_000
MAX_LINES = 5000


def _path(project):
    return project.data / "usage.jsonl"


def record(project, cmd, chars, truncated, ms, json_mode=False, results=None):
    """Never fails the command it measures. `results`: how many hits/items it returned (a count, no content).
    MEMCRUMBS_NO_USAGE=1 turns logging off (benchmark and A/B runs)."""
    if os.environ.get("MEMCRUMBS_NO_USAGE"):
        return
    try:
        row = {"t": round(time.time()), "cmd": cmd, "chars": chars, "truncated": bool(truncated), "ms": round(ms, 1),
               "json": bool(json_mode)}
        if results is not None:
            row["results"] = results
        line = json.dumps(row) + "\n"
        p = writeset.append_text(project, _path(project), line)
        if p.stat().st_size > MAX_BYTES:
            keep = p.read_text(encoding="utf-8", errors="replace").splitlines()[-MAX_LINES // 2:]
            writeset.write_text(project, p, "\n".join(keep) + "\n")
    except Exception:
        pass


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else 0


def summary(project):
    """{cmd: {n, p50_tokens, p95_tokens, max_tokens, truncated_pct, p95_ms}} from the log."""
    rows = {}
    p = _path(project)
    if not p.exists():
        return rows
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        rows.setdefault(r.get("cmd", "?"), []).append(r)
    out = {}
    for cmd, rs in sorted(rows.items()):
        toks = [(r.get("chars", 0) + 3) // 4 for r in rs]
        out[cmd] = {"n": len(rs), "p50_tokens": _pct(toks, 0.5), "p95_tokens": _pct(toks, 0.95), "max_tokens": max(toks),
                    "truncated_pct": round(100 * sum(1 for r in rs if r.get("truncated")) / len(rs), 1),
                    "p95_ms": _pct([r.get("ms", 0) for r in rs], 0.95)}
        counted = [r["results"] for r in rs if "results" in r]
        if counted:
            out[cmd]["zero_results_pct"] = round(100 * sum(1 for n in counted if not n) / len(counted), 1)
    return out


LOOKUPS = ("find", "page", "sym", "outline", "explain")


def daily(project, days=30, now=None):
    """[{day, lookups, empty, sessions}] for the last `days` days, oldest first: counts only. `sessions` counts
    `status` runs (the session header), `empty` the lookups that returned nothing."""
    now = now or time.time()
    start = time.strftime("%Y-%m-%d", time.localtime(now - (days - 1) * 86400))
    out = {time.strftime("%Y-%m-%d", time.localtime(now - k * 86400)): dict(lookups=0, empty=0, sessions=0)
           for k in range(days)}
    p = _path(project)
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []:
        try:
            r = json.loads(ln)
            day = time.strftime("%Y-%m-%d", time.localtime(r["t"]))
        except (ValueError, KeyError, TypeError, OSError, OverflowError):
            continue
        if day < start or day not in out:
            continue
        if r.get("cmd") in LOOKUPS:
            out[day]["lookups"] += 1
            out[day]["empty"] += 1 if r.get("results") == 0 else 0
        elif r.get("cmd") == "status":
            out[day]["sessions"] += 1
    return [dict(day=d, **out[d]) for d in sorted(out)]


def record_hits(project, rel_paths):
    """Count how often each wiki page is served (find / page), for the refresh plan's priority. Page paths only:
    never queries or text. Never fails the command."""
    if not rel_paths or os.environ.get("MEMCRUMBS_NO_USAGE"):
        return
    try:
        p = project.data / "hits.json"
        try:
            counts = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            counts = {}
        for r in set(rel_paths):
            counts[r] = counts.get(r, 0) + 1
        writeset.write_text(project, p, json.dumps(counts, sort_keys=True) + "\n")
    except Exception:
        pass
