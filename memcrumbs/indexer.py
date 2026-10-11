"""Incremental refresh: re-index only files whose stamp (mtime + size) changed.

Parsing happens outside any lock; the writes go in short batches, each its own transaction, so readers are
never blocked and a second refresher waits at most `wait` seconds before giving up. A refresh that cannot
get the lock leaves the last index in place and reports {"skipped": ...}, which callers label as stale."""
import time
from pathlib import Path

from memcrumbs import freshness
from memcrumbs.sources import Doc
from memcrumbs.store import Locked
from memcrumbs.util import posix

BATCH = 400


def _load(key, loader):
    try:
        out = loader()
        docs, syms = out[0], out[1]
        return list(docs), list(syms)
    except Exception as e:                       # one bad file must not stop the index; its text is not kept
        return [Doc("log", key, 1, Path(key).name, "index error", type(e).__name__)], []


def _fresh(project):
    """Which pages' sources changed since they were verified (one git call per repo); None if it cannot tell."""
    try:
        return freshness.page_freshness(project)
    except Exception:
        return None


def refresh(project, api, store, only=None, force=False, throttle=60, wait=0.25):
    """The wiki is checked on every call; other sources at most every `throttle` seconds unless forced."""
    now = time.time()
    last = float(store.get_meta("refreshed", 0) or 0)
    due = force or now - last >= throttle
    stats, pending, claimed = {}, [], set()
    for name, fn in api.sources.items():
        if (only and name not in only) or (name != "wiki" and not due):
            continue
        known, seen, n = store.known(name), set(), 0
        try:
            items = list(fn(project))
        except Exception as e:
            stats[name + " failed"] = type(e).__name__
            continue
        for path, st, loader in items:
            key = posix(path)
            if key in claimed:
                continue                                  # an earlier source owns this file
            claimed.add(key)
            seen.add(key)
            if force or known.get(key) != str(st):
                pending.append(("put", name, key, st, loader))
                n += 1
        for gone in sorted(set(known) - seen):
            if gone not in claimed:
                pending.append(("drop", name, gone, None, None))
            n += 1
        stats[name] = n
    try:
        if force and not only and pending:               # `index --full` rebuilds from empty tables
            with store.writer(wait):
                store.reset()
        for i in range(0, len(pending), BATCH):
            batch = [(op, name, key, st, _load(key, loader) if op == "put" else None)
                     for op, name, key, st, loader in pending[i:i + BATCH]]
            with store.writer(wait):
                for op, name, key, st, loaded in batch:
                    if op == "put":
                        store.replace(key, name, st, *loaded)
                    else:
                        store.drop(key)
        if due or pending:
            fresh = _fresh(project)                  # git runs outside the lock
            with store.writer(wait):
                if due:
                    store.set_meta("refreshed", now)
                if fresh is not None:
                    store.set_fresh(fresh)
                if pending or store.get_meta("ndocs") is None:
                    store.set_meta("ndocs", store.db.execute("SELECT count(*) FROM docs").fetchone()[0])
    except Locked:
        stats["skipped"] = "another memcrumbs process is writing the index; answers come from the last index"
    return stats
