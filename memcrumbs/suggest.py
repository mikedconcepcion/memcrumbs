"""One framework for every offer memcrumbs makes: why it was raised, the evidence (counts and dates, never
raw text), a reviewable dry-run patch, nothing applied without a yes, and remembered dismissals.

    memcrumbs suggest [--kind K]                    open suggestions (a fresh scan)
    memcrumbs suggest show ID                       why, evidence, and the patch as a diff
    memcrumbs suggest apply ID|--kind K             write it; --outside-wiki / --allow-destructive per risk
    memcrumbs suggest undo ID                       put back exactly what was there (if unchanged since)
    memcrumbs suggest dismiss ID [--for 14d|--never]

Detection is deterministic and needs no model. Kinds come from suggesters (built in, or `api.add_suggester`):
each returns `Suggestion`s. State lives in the index folder (`suggest.json`, backups in `suggest-backups/`).
A dismissed suggestion comes back after its period only if it is still detected."""
import datetime as dt
import difflib
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from memcrumbs import suggest_state as state
from memcrumbs.suggest_state import load_state, save_state  # noqa: F401  (re-exported for plugins and tests)
from memcrumbs.util import posix, read_text

RISKS = ("safe", "review", "writes-outside-wiki", "destructive")   # review: wiki only, but read it first
SCAN_EVERY = 86400                 # the header refreshes the cheap kinds at most once a day
PER_KIND = 5                       # the list shows this many of each kind (--full for all)
LIMITS = {"skill": 3}              # skill offers: the top 3


@dataclass
class Suggestion:
    kind: str
    key: str                       # the stable subject ("wiki/a.md|wiki/b.md"): the id is derived from it
    why: str                       # one line
    action: str                    # what applying does, in words
    evidence: list = field(default_factory=list)      # short lines: counts and dates, never raw transcript text
    risk: str = "safe"
    changes: list = field(default_factory=list)       # [(path, new text or None to delete)]: the patch
    agent: str = ""                # when there is no mechanical patch: what the agent does after the owner's yes
    score: float = 0.0
    cheap: bool = True             # cheap enough for the daily header scan
    tailor: object = None          # fn(suggestion, args) -> suggestion: apply-time options of a kind
    human: bool = False            # it loosens a guard: applied only by a human at a terminal

    @property
    def id(self):
        return "%s-%s" % (self.kind, hashlib.sha1(("%s|%s" % (self.kind, self.key)).encode("utf-8")).hexdigest()[:6])


def suggesters(project, api=None):
    from memcrumbs import suggest_wiki
    found = dict(suggest_wiki.SUGGESTERS)
    for mod in ("suggest_guard", "suggest_gaps", "suggest_memory", "suggest_skill"):
        try:
            found.update(__import__("memcrumbs." + mod, fromlist=["SUGGESTERS"]).SUGGESTERS)
        except ImportError:
            pass
    found.update(getattr(api, "suggesters", {}) or {})
    return found


def detect(project, api=None, kinds=None, cheap_only=False):
    """Run the suggesters; a failing one is skipped (its name goes in the result's errors)."""
    out, errors, ran, ids = [], [], set(), set()
    for kind, fn in sorted(suggesters(project, api).items()):
        if (kinds and kind not in kinds) or fn in ran:
            continue                                  # one function may serve two kinds: run it once
        ran.add(fn)
        try:
            found = list(fn(project, cheap_only=cheap_only) or [])
        except Exception as e:
            errors.append("%s: %s" % (kind, type(e).__name__))
            continue
        for s in found:
            if (not cheap_only or s.cheap) and (not kinds or s.kind in kinds) and s.id not in ids:
                ids.add(s.id)
                out.append(s)
    out.sort(key=lambda s: (-s.score, s.kind, s.key))
    return out, errors


def _active(st, sid, today):
    d = st["decided"].get(sid)
    if not isinstance(d, dict) or not d:
        return sid not in st["applied"]
    if d.get("never"):
        return False
    until = d.get("until")
    return bool(until) and until <= today and sid not in st["applied"]


def refresh(project, api=None, kinds=None, cheap_only=False):
    """Detect, remember what is open (first seen), and return the active suggestions."""
    today = dt.date.today().isoformat()
    found, errors = detect(project, api, kinds, cheap_only)        # slow: outside the lock
    ids = {s.id for s in found}
    with state.locked(project):
        st = load_state(project)
        if not kinds and not cheap_only:
            st["open"] = {k: v for k, v in st["open"].items() if k in ids}
        for s in found:
            st["open"].setdefault(s.id, dict(kind=s.kind, why=s.why, first_seen=today, seen=False))
        st["scanned"] = dt.datetime.now().timestamp()
        save_state(project, st)
    return [s for s in found if _active(st, s.id, today)], errors, st


def maybe_scan(project, api=None):
    """The daily scan of the cheap kinds. It runs after commands whose speed does not matter (check, index,
    dashboard, doctor, the write commands), never in a lookup or the header. It never fails the command."""
    try:
        if dt.datetime.now().timestamp() - float(load_state(project).get("scanned") or 0) > SCAN_EVERY:
            refresh(project, api, cheap_only=True)
    except Exception:
        pass


def header_line(project, api=None):
    """One line, only when there is something new and undecided: read from the stored scan, never run here."""
    try:
        st = load_state(project)
        today = dt.date.today().isoformat()
        new = [k for k, v in st["open"].items() if isinstance(v, dict) and not v.get("seen") and _active(st, k, today)]
    except Exception:                                  # a broken state never costs the header
        return ""
    return "%d new suggestion%s: memcrumbs suggest" % (len(new), "s" if len(new) != 1 else "") if new else ""


def _diff(project, path, new):
    old = read_text(path) if Path(path).exists() else ""
    rel = project.rel(path) if str(path).startswith(str(project.dir)) else posix(path)
    if new is None:
        return ["--- %s (deleted)" % rel]
    return list(difflib.unified_diff(old.splitlines(), (new or "").splitlines(), "a/" + rel, "b/" + rel, lineterm="", n=1))


def _find(project, api, sid):
    kind = sid.rsplit("-", 1)[0]
    found, _ = detect(project, api, [kind])
    hit = next((s for s in found if s.id == sid), None)
    if hit is None:
        raise SystemExit("memcrumbs: no open suggestion %s (memcrumbs suggest lists them)" % sid)
    return hit


def tailor(s, args):
    """Apply-time choices a kind offers (e.g. a skill's --owner-only / --name): `s.tailor(args)` if it has one."""
    fn = getattr(s, "tailor", None)
    return fn(s, args) if callable(fn) else s


undo, dismiss = state.undo, state.dismiss


def command(out, project, api, args):
    """`memcrumbs suggest [show|apply|undo|dismiss] [ID] …`"""
    action, sid = args.action or "list", args.id
    out.list_key = "suggestions"
    if action == "list":
        kinds = [k.strip() for k in (args.kind or "").split(",") if k.strip()] or None
        active, errors, st = refresh(project, api, kinds)
        out.set(suggestions=[dict(id=s.id, kind=s.kind, why=s.why, action=s.action, risk=s.risk, evidence=s.evidence,
                                  patch=bool(s.changes)) for s in active], errors=errors)
        out.hint("memcrumbs suggest show ID · apply ID · dismiss ID [--for 14d|--never]")
        if not active:
            out("no suggestions%s" % (" (failed: %s)" % ", ".join(errors) if errors else ""))
            return 0
        out("%d suggestion%s — show ID · apply ID (after the owner's yes) · dismiss ID [--for 14d|--never]"
            % (len(active), "s" if len(active) != 1 else ""))
        shown = {}
        listed = []
        for s in active:
            shown[s.kind] = shown.get(s.kind, 0) + 1
            if shown[s.kind] > LIMITS.get(s.kind, PER_KIND) and not getattr(args, "full", False):
                continue
            out("[%s] %s · %s → %s" % (s.id, s.risk, s.why, s.action))
            listed.append(s.id)
        for kind, n in sorted(shown.items()):
            cap = LIMITS.get(kind, PER_KIND)
            if n > cap and not getattr(args, "full", False):
                out("… %d more %s suggestion(s): memcrumbs suggest --kind %s --full" % (n - cap, kind, kind))
        with state.locked(project):
            st = load_state(project)
            for sid_ in listed:
                if isinstance(st["open"].get(sid_), dict):
                    st["open"][sid_]["seen"] = True
            save_state(project, st)
        if errors:
            out("(suggesters that failed: %s)" % ", ".join(errors))
        return 0
    if not sid and not (action == "apply" and args.kind):
        raise SystemExit("memcrumbs: suggest %s needs an ID" % action)
    if action == "show":
        s = _find(project, api, sid)
        out.set(id=s.id, kind=s.kind, why=s.why, action=s.action, risk=s.risk, evidence=s.evidence, agent=s.agent,
                patch=[dict(path=posix(p), deleted=new is None) for p, new in s.changes])
        out("[%s] %s · %s" % (s.id, s.risk, s.why))
        for e in s.evidence:
            out("  evidence: " + e)
        out("  action: " + s.action)
        if s.agent:
            out("  after a yes, the agent: " + s.agent)
        for path, new in s.changes:
            for ln in _diff(project, path, new):
                out("  " + ln)
        if s.changes:
            state.remember_shown(project, s)              # apply refuses if these files change before it
        return 0
    if action == "apply":
        done = set()
        while True:                    # one at a time, each patch re-made from the files as they are now:
            if sid:                    # two suggestions that edit one file must not overwrite each other
                s = _find(project, api, sid) if sid not in done else None
            else:
                s = next((x for x in refresh(project, api, [args.kind])[0] if x.id not in done), None)
            if s is None:
                return 0
            done.add(s.id)
            if not s.changes:
                out("[%s] has no mechanical patch; the agent does it: %s" % (s.id, s.agent or s.action))
                continue
            s = tailor(s, args)
            files = state.apply(project, s, args.outside_wiki, args.allow_destructive)
            out("[%s] applied: %s (memcrumbs suggest undo %s)" % (s.id, ", ".join(
                project.rel(f["path"]) if str(f["path"]).startswith(str(project.dir)) else posix(f["path"]) for f in files), s.id))
    if action == "undo":
        paths = undo(project, sid)
        out("[%s] undone: %s" % (sid, ", ".join(posix(p) for p in paths)))
        return 0
    if action == "dismiss":
        until = dismiss(project, sid, args.period, args.never)
        out("[%s] dismissed %s" % (sid, "for good" if args.never else "until %s (it comes back only if still true)" % until))
        return 0
    raise SystemExit("memcrumbs: unknown suggest action %r" % action)
