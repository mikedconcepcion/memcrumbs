"""The session header (`status`): configurable sections under one hard token cap.

Sections come from wiki files only (rules, map, gotchas, journal) plus plugin section providers; external doc
trees and transcripts never enter it. An over-budget section is cut with a notice naming the command that
shows the rest, never dropped. The header reads files, not the index, so a locked or broken index only
changes the counts line (labelled stale)."""
import json

from memcrumbs import freshness, markdown
from memcrumbs.cmd_write import journal_tail
from memcrumbs.plan import load_state as plan_state
from memcrumbs.output import TOKEN_CHARS
from memcrumbs.util import clip, read_text, shq, split_lines

HARD_CAP_TOKENS = 1500
DEFAULT_TOKENS = 1000
DEFAULT_SECTIONS = ("rules", "map", "gotchas", "plan", "journal", "plugins")
# name: (file, heading, default lines, title, config key for the line count)
BUILTIN = {"rules": ("rules.md", "Top", 8, "Rules (ask before acting against these)", "rules"),
           "map": ("index.md", "Map", 30, "Map", "map_lines"),
           "gotchas": ("gotchas.md", "Top", 12, "Top gotchas", "gotchas")}
# opt-in (`[status] sections` lists "style"): a few working rules that keep answers short.
# Off by default: every always-loaded line costs tokens in every session.
STYLE = ("Answer first: no greeting, recap or sign-off.",
         "Do not re-read a file you read this session unless it changed.",
         "A file over ~1,000 lines: memcrumbs outline <file>, then read only the range you need.",
         "Do not guess versions, flags or names: memcrumbs fact / find, or read the code.")
LOOKUP = ('Project knowledge: memcrumbs find "<words>" · page <name> [section] · outline <file> · sym <name> · '
          'log "<note>"; an exact name: grep for it  (skill: memcrumbs)')


NEW_WIKI = ("new wiki: rules and gotchas are empty. First run (skill memcrumbs): draft them from CLAUDE.md, the README "
            "and the code for the owner's review")


def _check_line(project):
    """One line while the last check (`check`, or the daily one) found secret-like text: pages, never the text."""
    try:
        st = json.loads(read_text(project.data / "check.json"))
        n = int(st.get("errors") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    if not n:
        return ""
    where = ", ".join(st.get("where") or []) + (" and %d more" % st["more"] if st.get("more") else "")
    return "check: %d error%s (secret-like text) in %s — memcrumbs check" % (n, "s" if n != 1 else "", where)


def _new_wiki(project):
    """rules.md and gotchas.md exist (init wrote them) and hold no line yet, reviewed or not."""
    from memcrumbs import review
    return all((project.wiki / f).exists() for f in ("rules.md", "gotchas.md")) and not review.standing(project)


def _file_section(project, fname, heading, n, name=""):
    path = project.wiki / fname
    if not path.exists():
        return None
    meta, body, _ = markdown.frontmatter(read_text(path))
    if markdown.truthy(meta.get("quarantined")):
        return None
    lines = split_lines(body)
    span = markdown.section_span(lines, heading)
    seg = [ln for ln in (lines[span[0] + 1: span[1]] if span else lines) if ln.strip()]
    from memcrumbs import review
    seg, waiting = review.gate(project, name, seg)          # standing lines show once a human reviewed them
    age = freshness.days_since(meta.get("verified"))
    src = project.rel(path) + (" · v%dd" % age if age is not None else "")
    return dict(lines=seg[:n], more=len(seg) - min(n, len(seg)), src=src, cmd="memcrumbs page %s" % shq(path.stem),
                waiting=waiting)


def sections(project, api, cfg):
    """[{name, title, src, lines, more, cmd}] in configured order. Each section is built on its own: one that fails
    (a corrupt state file, an odd page) drops only itself. Every line is redacted before anything clips it, and a line
    that reads like instructions to an agent is held back (it is shown by `check`), whatever section it is in."""
    from memcrumbs.guard import instruction_like
    from memcrumbs.redact import safe
    out = []
    wanted = list(cfg.get("sections", DEFAULT_SECTIONS))
    plugin = {name: (fn, title) for name, fn, title in api.sections}
    for name in wanted:
        try:
            got = _section(project, cfg, name, wanted, plugin)
        except Exception as e:
            got = [dict(name=name, title="", src=name, more=0, cmd="memcrumbs check",
                        lines=["(%s section unavailable: %s — memcrumbs doctor)" % (name, type(e).__name__)])]
        for s in got:
            lines = [safe(project.redact, str(ln)) for ln in s["lines"]]
            held = [ln for ln in lines if instruction_like(ln)]
            s["lines"] = [ln for ln in lines if ln not in held] + (
                ["(%d line%s held back: they read like instructions to an agent — memcrumbs check)"
                 % (len(held), "s" if len(held) != 1 else "")] if held else [])
            out.append(s)
    return out


def _section(project, cfg, name, wanted, plugin):
    out = []
    if name in BUILTIN:
        fname, heading, n, title, key = BUILTIN[name]
        s = _file_section(project, fname, heading, int(cfg.get(key, n)), name)
        if s:
            out.append(dict(name=name, title=title, **s))
    elif name == "plan":                       # only when the user approved a refresh: never invites spending
        st = plan_state(project)
        left = [p for p in st.get("approved", []) if p not in st.get("done", [])]
        if left:
            budget = st.get("budget") or 0
            out.append(dict(name=name, title="", src="plan", more=0, cmd="memcrumbs plan", lines=[
                "Wiki refresh approved by the user: %d page(s) left%s — memcrumbs plan next" % (
                    len(left), ", ≈ %d of %d tokens est. left" % (budget - st.get("spent", 0), budget) if budget else "")]))
    elif name == "style":
        lines = [str(x) for x in cfg.get("style_rules") or STYLE]
        out.append(dict(name=name, title="Working style", src="memcrumbs.toml", lines=lines, more=0,
                        cmd="memcrumbs status"))
    elif name == "journal":
        n = int(cfg.get("journal", 3))
        lines, f = journal_tail(project, n)
        if lines:
            out.append(dict(name=name, title="Recent", src=project.rel(f), lines=lines, more=0,
                            cmd="memcrumbs page %s" % shq(f.stem)))
    elif name == "plugins" or name in plugin:
        for pname, (fn, title) in plugin.items():
            if (name == "plugins" and pname in wanted) or (name != "plugins" and pname != name):
                continue
            try:
                lines = [str(x) for x in (fn(project) or [])]
            except Exception as e:
                lines = ["plugin section %s failed: %s" % (pname, type(e).__name__)]
            if lines:
                out.append(dict(name=pname, title=title or "", src="plugin", lines=lines, more=0,
                                cmd="memcrumbs status --full"))
    return out


def budget_tokens(cfg):
    want = int(cfg.get("max_tokens") or (int(cfg["max_chars"]) // TOKEN_CHARS if cfg.get("max_chars") else DEFAULT_TOKENS))
    return max(100, min(want, HARD_CAP_TOKENS))


def render(head, secs, budget_chars, width=220):
    """Lay out head lines then sections under budget_chars; every section keeps at least its title and a notice."""
    def title(s):
        return "%s (%s):" % (s["title"], s["src"]) if s["title"] else ""

    def notice(s, n, why):
        return "… %d more%s: %s" % (n, why, s["cmd"])
    lines = list(head)
    used = sum(len(x) + 1 for x in lines)
    floor = [len(title(s)) + 2 + len(notice(s, 99, " (header budget)")) + 1 for s in secs]
    cut = False
    for k, s in enumerate(secs):
        reserve = sum(floor[k + 1:])
        block = ["", title(s)] if s["title"] else [""]
        used += sum(len(x) + 1 for x in block)
        items = [clip(x, width) for x in s["lines"]]
        shown = 0
        for it in items:
            if used + len(it) + 1 + reserve + len(notice(s, 99, " (header budget)")) > budget_chars:
                break
            block.append(it)
            used += len(it) + 1
            shown += 1
        rest = len(items) - shown
        if rest:
            cut = True
            block.append(notice(s, rest + s["more"], " (header budget)"))
        elif s["more"]:
            block.append(notice(s, s["more"], ""))
        used += len(block[-1]) + 1 if (rest or s["more"]) else 0
        lines += block
    return "\n".join(lines), cut


def status(out, project, api, counts=None, stale=None, unreviewed=0):
    """counts = (docs, symbols) from the index, or None when the index is unavailable (`stale` says why)."""
    cfg = project.cfg.get("status", {})
    budget = budget_tokens(cfg) * TOKEN_CHARS
    pages = len(project.wiki_pages())
    if counts and not counts[0] and pages:      # fresh install or a schema upgrade: never show "0 docs" as fact
        idx = "index builds on the first lookup (new or upgraded; a few seconds once) — memcrumbs find works"
    elif counts:
        idx = "index %d docs / %d code symbols" % counts
    else:
        idx = "index unavailable (%s): header read from the wiki files, may be stale" % (stale or "not built")
    head = ["memcrumbs · %s — %d pages · %s" % (project.title, pages, idx), LOOKUP]
    for spec, err in api.errors:
        head.append("plugin %s failed to load (%s): memcrumbs check" % (spec, err))
    secs = sections(project, api, cfg)
    waiting = sum(s.get("waiting", 0) for s in secs)
    if waiting or unreviewed:                 # one line, only when something waits for the owner
        head.append("waiting for the owner's review: %s — memcrumbs review (skill: memcrumbs-review)" % ", ".join(x for x in (
            "%d new rule/gotcha line%s" % (waiting, "s" if waiting != 1 else "") if waiting else "",
            "%d agent-written page%s" % (unreviewed, "s" if unreviewed != 1 else "") if unreviewed else "") if x))
    elif _new_wiki(project):
        head.append(NEW_WIKI)
    found = _check_line(project)                           # read from the last check, never run here
    if found:
        head.append(found)
    secs = [s for s in secs if s["lines"] or s["more"]]      # an empty section prints no bare title
    from memcrumbs import suggest
    nudge = suggest.header_line(project, api)              # one line, only when something is new
    if nudge:
        head.append(nudge)
    from memcrumbs import update
    newer = update.header_line(project)                    # opt-in; read from the stored daily check
    if newer:
        head.append(newer)
    text, cut = render(head, secs, budget)
    if not out.json:
        out.cap = budget + 400                   # the layout above already fits the budget; this is a backstop
    out.set(project=project.name, pages=pages, index=dict(docs=counts[0], symbols=counts[1]) if counts else None,
            stale=stale, budget_tokens=budget // TOKEN_CHARS, truncated=cut,
            sections=[dict(name=s["name"], title=s["title"], source=s["src"], lines=s["lines"], more=s["more"])
                      for s in secs])
    out(text)
