"""The wiki refresh plan: which pages need an agent's attention, why, and roughly what it would cost — so a
human decides what gets refreshed and with how many tokens (`memcrumbs dashboard` is its control panel).

memcrumbs itself never spends tokens: re-indexing is local. Refreshing a page means an agent reads what
changed and rewrites the page, which costs model tokens. So nothing here runs on its own:
  memcrumbs plan                                   list candidates with reasons, priority and est. tokens
  memcrumbs plan --approve a,b|top:N --budget N    the human approves pages and a token budget
  memcrumbs plan next                              the agent takes the next approved page (until the budget is used)
  memcrumbs verify <page>                          marks it done
State lives in the index folder (plan.json); estimates are chars/4 and labelled as such."""
import json
import math
import subprocess
import time

from memcrumbs import freshness, markdown, writeset
from memcrumbs.guard import instruction_like
from memcrumbs.util import shq, posix, read_text

HEADER_PAGES = {"rules", "index", "gotchas"}
OVERHEAD = 600                       # est. tokens per page for instructions, commands and the rewrite itself
SOURCE_CAP = 6000                    # est. tokens: past this, the agent should use outline/sym, not read whole files
REASONS = {"secret": 100, "injection": 80, "sources-changed": 60, "stale": 40, "unverified": 30,
           "broken-link": 20, "frontmatter": 15, "too-long": 10}


def _state_path(project):
    return project.data / "plan.json"


def load_state(project):
    """The approved refresh, typed: anything malformed falls back to "nothing approved"."""
    empty = {"approved": [], "budget": 0, "spent": 0, "done": []}
    try:
        st = json.loads(_state_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(st, dict):
        return empty
    for k in ("approved", "done"):
        st[k] = [str(x) for x in st.get(k)] if isinstance(st.get(k), list) else []
    for k in ("budget", "spent"):
        st[k] = st.get(k) if isinstance(st.get(k), (int, float)) and not isinstance(st.get(k), bool) else 0
    return st


def save_state(project, state):
    writeset.write_text(project, _state_path(project), json.dumps(state, indent=1) + "\n")


def hits(project):
    try:
        return json.loads((project.data / "hits.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _changed_tokens(path, since):
    """Est. tokens to read what changed in a source file since a date: the git diff size when possible."""
    size = path.stat().st_size
    root = freshness._git_root(path)
    if root:
        base = freshness._git(root, "rev-list", "-1", "--before=%s" % since, "HEAD")
        if base and base.strip():
            num = freshness._git(root, "diff", "--numstat", base.strip(), "--", path.relative_to(root).as_posix())
            if num and num.split():
                parts = num.split()
                if parts[0].isdigit() and parts[1].isdigit():
                    lines = max(1, sum(1 for _ in open(path, "rb")))
                    changed = (int(parts[0]) + int(parts[1])) * 3            # with some context around each change
                    return min(SOURCE_CAP, math.ceil(size / lines * changed / 4))
    return min(SOURCE_CAP, math.ceil(size / 4))


def _git_hint(path, since):
    """The exact command that shows what changed in a source since the page was verified."""
    root = freshness._git_root(path)
    if root:
        return "git -C %s log -p --since=%s -- %s" % (posix(root), since, path.relative_to(root).as_posix())
    return "%s (not in git: compare it with the page by hand)" % posix(path)


def candidates(project, lint_findings=None, today=None):
    """[{page, path, reasons, priority, tokens, hits, sources}] sorted by priority (highest first)."""
    from memcrumbs.lint import lint
    findings = lint(project, today) if lint_findings is None else lint_findings
    by_page = {}
    for level, where, msg in findings:
        reason = ("secret" if msg.startswith("secret") else "injection" if msg.startswith("instruction-like") else
                  "sources-changed" if msg.startswith("sources changed") else "stale" if msg.startswith("verified ") and
                  "days ago" in msg else "broken-link" if msg.startswith("broken link") else
                  "frontmatter" if msg.startswith("frontmatter missing") else "too-long" if "split it" in msg else None)
        if reason:
            by_page.setdefault(where, set()).add(reason)
    counts = hits(project)
    out = []
    for p in project.wiki_pages():
        rel = project.rel(p)
        meta, body, _ = markdown.frontmatter(read_text(p))
        reasons = set(by_page.get(rel, ()))
        journal = "journal" in p.relative_to(project.wiki).parts
        if not meta.get("verified") and not journal and str(meta.get("status", "")).lower() not in ("superseded", "rejected"):
            reasons.add("unverified")
        if not reasons:
            continue
        moved = freshness.changed_sources(project, meta, today) if "sources-changed" in reasons else []
        since = str(meta.get("verified") or "")
        tokens = OVERHEAD + math.ceil(p.stat().st_size / 4) + sum(_changed_tokens(s, since) for s in moved)
        n = counts.get(rel, 0)
        prio = max(REASONS[r] for r in reasons) + (50 if p.stem.lower() in HEADER_PAGES else 0) + round(10 * math.log1p(n))
        out.append(dict(page=p.stem, path=rel, reasons=sorted(reasons, key=lambda r: -REASONS[r]), priority=prio,
                        tokens=tokens, hits=n, sources=[posix(s.name) for s in moved], since=since,
                        changes=[_git_hint(s, since) for s in moved],
                        flags=instruction_like(read_text(p)) if "injection" in reasons else []))
    out.sort(key=lambda c: (-c["priority"], c["tokens"], c["path"]))
    return out


def approve(project, items, spec, budget=None):
    """spec: comma list of page names, `all`, or `top:N`. Returns the new state."""
    names = [c["page"] for c in items]
    if spec == "all":
        chosen = names
    elif spec.startswith("top:"):
        chosen = names[:int(spec[4:])]
    else:
        chosen = [x.strip().removesuffix(".md") for x in spec.split(",") if x.strip()]
        unknown = [x for x in chosen if x not in names]
        if unknown:
            raise SystemExit("memcrumbs: not in the plan: %s (memcrumbs plan lists candidates)" % ", ".join(unknown))
    state = load_state(project)
    state["approved"] = [x for x in names if x in chosen]                   # priority order
    state["costs"] = {c["page"]: c["tokens"] for c in items if c["page"] in chosen}
    if budget is not None:
        state["budget"], state["spent"] = int(budget), 0
    state["done"] = [d for d in state.get("done", []) if d in state["approved"]]
    state["approved_at"] = time.strftime("%Y-%m-%d %H:%M")
    save_state(project, state)
    return state


def mark_done(project, page):
    """`verify` calls this: an approved page is done; its estimate counts against the budget."""
    state = load_state(project)
    if page in state.get("approved", []) and page not in state.get("done", []):
        state["done"].append(page)
        state["spent"] = state.get("spent", 0) + int(state.get("costs", {}).get(page, 0))
        save_state(project, state)
        return True
    return False


def next_item(project, items, state):
    """(item, why-not): the next approved page that is not done and fits the remaining budget."""
    by_name = {c["page"]: c for c in items}
    left = state.get("budget", 0) - state.get("spent", 0)
    for name in state.get("approved", []):
        if name in state.get("done", []) or name not in by_name:
            continue
        item = by_name[name]
        if state.get("budget") and item["tokens"] > left:
            return None, "budget reached: %d of %d est. tokens used; next page needs ≈ %d. Ask the user." % (
                state.get("spent", 0), state["budget"], item["tokens"])
        return item, None
    return None, "no approved pages left (the user approves with: memcrumbs plan --approve … --budget N)"


def show(out, project, approve_spec=None, budget=None, clear=False, take_next=False):
    items = candidates(project)
    if clear:
        save_state(project, {"approved": [], "budget": 0, "spent": 0, "done": []})
    if approve_spec:
        approve(project, items, approve_spec, budget)
    elif budget is not None:
        state = load_state(project)
        state["budget"] = int(budget)
        save_state(project, state)
    state = load_state(project)
    out.list_key = "items"
    out.set(items=items, state=state)
    if take_next:
        item, why = next_item(project, items, state)
        out.set(next=item, reason=why)
        if not item:
            out(why)
            return
        out("refresh %s — %s · ≈ %d tokens est. (budget left ≈ %d)" % (
            item["path"], ", ".join(item["reasons"]), item["tokens"], state.get("budget", 0) - state.get("spent", 0)))
        for hint in item["changes"]:
            out("changed since %s — read only the change: %s" % (item["since"], hint))
        out("then: update only what changed, keep hand-written text, run memcrumbs check, then memcrumbs verify %s"
            % shq(item["page"]))
        return
    approved, done = set(state.get("approved", [])), set(state.get("done", []))
    total = sum(c["tokens"] for c in items)
    out("%d pages need attention · ≈ %d tokens est. to refresh all · approved %d · budget %s (used ≈ %d)" % (
        len(items), total, len(approved), state.get("budget") or "none", state.get("spent", 0)))
    for c in items:
        mark = "done" if c["page"] in done else "ok" if c["page"] in approved else "  "
        out("%-4s %3d %-46s %6d  %s%s" % (mark, c["priority"], c["path"][:46], c["tokens"], ", ".join(c["reasons"]),
                                         (" · %d hits" % c["hits"]) if c["hits"] else ""))
    out("approve: memcrumbs plan --approve <pages>|top:N --budget <tokens> · or open: memcrumbs dashboard")
