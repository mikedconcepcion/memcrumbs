"""Repeats of a known trap, counted in the gotcha line itself: `(hit N, last YYYY-MM-DD)`.

    memcrumbs gotcha --add "<the trap, one line>"     the first bite: a new line under ## More, hit 1
    memcrumbs gotcha --hit "<words of the line>"      it bit again: the count goes up
    memcrumbs gotcha                                  the lines with their counts

- The mark is not part of a line's identity: a counted Top line stays reviewed, and the header leaves the mark out.
- **Promote at two.** A `## More` line (the header never shows More) that bit twice is offered for `## Top`
  (suggest kind `gotcha`). Top is a fixed budget, so the offer also names the Top line with the fewest hits in 90
  days, to merge or demote. The moved line waits for review, like every header line.
- **Offer demotion at none.** Once counting has run for 90 days, `check` gives an info finding for each Top line
  with no hit in the last 90 days: is it still earning its place?"""
import datetime as dt
import json
import re

from memcrumbs import markdown, writeset
from memcrumbs.query import STOPWORDS
from memcrumbs.util import clip, read_doc, read_text

MARK = re.compile(r"\s*\(hit (\d+), last (\d{4}-\d{2}-\d{2})\)\s*$")
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
WINDOW = 90                      # days
PROMOTE = 2                      # hits that move a More line up
MATCH = 0.6                      # share of the query's words a line must hold


def strip(line):
    """The line without its hit mark."""
    return MARK.sub("", line.rstrip("\r"))


def _text(line):
    """The line as read: no list marker, no hit mark."""
    return re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", strip(line)).strip()


def hits(line):
    """(count, last date or None)."""
    m = MARK.search(line.rstrip("\r"))
    return (int(m.group(1)), dt.date.fromisoformat(m.group(2))) if m else (0, None)


def recent(line, today):
    """Hits that count for the 90-day window: the count when the last one is inside it, else 0."""
    n, last = hits(line)
    return n if last and (today - last).days <= WINDOW else 0


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in STOPWORDS}


def _path(project):
    return project.wiki / "gotchas.md"


def items(text):
    """[(section, index into text.split('\\n'), line)] for the list items under ## Top and ## More."""
    lines, out = text.split("\n"), []
    for heading in ("Top", "More"):
        span = markdown.section_span(lines, heading)
        if span:
            out += [(heading, i, lines[i]) for i in range(span[0] + 1, span[1]) if ITEM.match(lines[i])]
    return out


def _share(want, line):
    """The share of the query's words in the line; a word also matches its longer or shorter form (4+ letters
    shared: heredoc, heredocs)."""
    have = _words(strip(line))
    return sum(1 for w in want if any(w == h or (min(len(w), len(h)) >= 4 and (h.startswith(w) or w.startswith(h)))
                                      for h in have)) / len(want)


def _find(text, words):
    want = _words(words)
    if not want:
        raise SystemExit("memcrumbs: give a few words of the gotcha line")
    scored = sorted(((_share(want, ln), sec, i, ln) for sec, i, ln in items(text)), key=lambda x: -x[0])
    best = [x for x in scored if x[0] >= MATCH and x[0] == scored[0][0]] if scored else []
    if not best:
        raise SystemExit("memcrumbs: no gotcha line matches %r; a first bite is memcrumbs gotcha --add \"<line>\"" % words)
    if len(best) > 1:
        raise SystemExit("memcrumbs: %d gotcha lines match %r equally; add words:\n%s" % (
            len(best), words, "\n".join("  " + clip(_text(x[3]), 120) for x in best)))
    return best[0][1:]


def _with_mark(line, n, day):
    return "%s (hit %d, last %s)%s" % (strip(line).rstrip(), n, day.isoformat(), "\r" if line.endswith("\r") else "")


def hit(out, project, words, today=None):
    today = today or dt.date.today()
    p = _path(project)
    if not p.exists():
        raise SystemExit("memcrumbs: no gotchas.md in %s" % project.rel(project.wiki))
    text, info = read_doc(p)
    sec, i, line = _find(text, words)
    n = hits(line)[0] + 1
    lines = text.split("\n")
    lines[i] = _with_mark(line, n, today)
    writeset.write_text(project, p, "\n".join(lines), info)
    out.set(section=sec, hits=n, line=_text(line))
    out("hit %d (%s): %s" % (n, sec, clip(_text(line), 140)))
    if sec == "More" and n >= PROMOTE:
        out("it bit %d times but More is never in the header: memcrumbs suggest --kind gotcha offers it for Top" % n)


def add(out, project, line, today=None):
    """A first bite: the trap as a new line at the end of ## More, with hit 1."""
    today = today or dt.date.today()
    p = _path(project)
    if not p.exists():
        raise SystemExit("memcrumbs: no gotchas.md in %s" % project.rel(project.wiki))
    text, info = read_doc(p)
    lines = text.split("\n")
    span = markdown.section_span(lines, "More")
    if span is None:
        lines += ["", "## More"]
        span = (len(lines) - 1, len(lines))
    at = span[1]
    while at > span[0] + 1 and not lines[at - 1].strip():
        at -= 1
    lines.insert(at, _with_mark("- " + " ".join(line.split()), 1, today) + ("\r" if "\r\n" in text else ""))
    writeset.write_text(project, p, "\n".join(lines), info)
    out.set(section="More", hits=1)
    out("added under More (hit 1): a second bite is memcrumbs gotcha --hit \"<words>\"")


def show(out, project, today=None):
    today = today or dt.date.today()
    p = _path(project)
    found = items(read_doc(p)[0]) if p.exists() else []
    out.list_key = "lines"
    out.set(lines=[dict(section=s, line=_text(ln), hits=hits(ln)[0],
                        last=hits(ln)[1].isoformat() if hits(ln)[1] else None) for s, _, ln in found])
    for s, _, ln in found:
        n, last = hits(ln)
        out("%-4s %s%s" % (s, clip(_text(ln), 110), " · hit %d, last %s" % (n, last) if n else ""))
    if not found:
        out("no gotcha lines yet")


def _promote(project, cheap_only=False):
    from memcrumbs.suggest import Suggestion
    p = _path(project)
    if not p.exists():
        return []
    text = read_doc(p)[0]
    found, today, out = items(text), dt.date.today(), []
    top = [(i, ln) for s, i, ln in found if s == "Top"]
    head = markdown.section_span(text.split("\n"), "Top")
    for sec, i, line in found:
        n, last = hits(line)
        if sec != "More" or n < PROMOTE or head is None:
            continue
        lines = text.split("\n")
        moved = lines.pop(i)
        end = (top[-1][0] + 1) if top else head[0] + 1
        lines.insert(end, moved)
        evidence = ["hit %d, last %s" % (n, last)]
        if top:
            weak = min(reversed(top), key=lambda t: (recent(t[1], today), hits(t[1])[1] or dt.date.min))[1]
            evidence.append("Top holds %d line%s; the fewest hits in %d days: %s (merge or demote it to keep the "
                            "header's budget)" % (len(top), "s" if len(top) != 1 else "", WINDOW, clip(_text(weak), 90)))
        out.append(Suggestion(
            "gotcha", "top|" + " ".join(strip(line).split()).lower(),
            "a ## More gotcha bit %d times; the header shows only ## Top" % n,
            "move it to the end of ## Top, where it waits for review like every header line", evidence,
            risk="review", changes=[(p, "\n".join(lines))], score=n))
    return out


SUGGESTERS = {"gotcha": _promote}


def findings(project, today=None):
    """Info findings for Top lines with no hit in 90 days, once counting has run that long."""
    today = today or dt.date.today()
    p, state = _path(project), project.data / "gotcha-watch.json"
    if not p.exists():
        return []
    try:
        since = dt.date.fromisoformat(json.loads(read_text(state))["since"])
    except (OSError, ValueError, KeyError, TypeError):
        writeset.write_text(project, state, json.dumps(dict(since=today.isoformat())) + "\n")
        return []
    if (today - since).days < WINDOW:
        return []
    return [("I", "wiki/gotchas.md", "Top gotcha with no hit in %d days: is it still earning its place? %s"
             % (WINDOW, clip(_text(ln), 100)))
            for s, _, ln in items(read_doc(p)[0]) if s == "Top" and not recent(ln, today)]
