"""Verdicts (rejected, parked, accepted, superseded) read from how people actually write them down:

- a title or heading that ends in one: "Read-through cache — REJECTED", "Sharding (parked)";
- a `Verdict: rejected` line, or a `## Verdict` (Outcome, Decision, Result) section whose first line starts with one;
- table cells: a cell that is exactly a verdict word, or, in a column headed Verdict, Status, Outcome, Decision
  or Result, a cell that *starts* with one followed by ":", "(", a dash, "as", a date or the end of the cell
  ("REJECTED: slower", "ADOPTED as default", "PARKED 10-02: …", "NOT ADOPTED: …").

A verdict found here is a label (and a `status:` filter); rejected and parked never change a hit's rank."""
import re

VERDICT_WORDS = {"rejected": "rejected", "parked": "parked", "accepted": "accepted", "adopted": "accepted",
                 "superseded": "superseded", "not adopted": "rejected", "not accepted": "rejected"}
_WORD = r"(not adopted|not accepted|rejected|parked|accepted|adopted|superseded)"
_SUFFIX = re.compile(r"(?i)[—–:(\[-]\s*\**" + _WORD + r"\**\s*[)\]]?\s*$")
_LINE = re.compile(r"(?im)^\s*[*_]*verdict[*_]*\s*[:—–-]+[*_\s]*" + _WORD + r"\b")
_LEAD_CELL = re.compile(r"(?i)^[*_`\s]*" + _WORD + r"[*_`]*(?=\s*(?:$|[:(—–-]|as\b|\d))")
_LEAD_LINE = re.compile(r"(?i)^[*_`>\s-]*" + _WORD + r"\b")
_LEAD_CAPS = re.compile(r"^[*_`\s]*(NOT ADOPTED|NOT ACCEPTED|REJECTED|PARKED|ACCEPTED|ADOPTED|SUPERSEDED)\b")
_UNDONE = re.compile(r"(?i)\b(reversed|reverted|rolled back|backed out)\b")
_COLUMN = re.compile(r"(?i)^[*_`\s]*(verdict|status|outcome|decision|result)s?[*_`\s]*$")
_SECTION = re.compile(r"(?i)^(verdict|outcome|decision|result)s?\b")


def _norm(word):
    return VERDICT_WORDS[" ".join(word.lower().split())]


def cells(row):
    parts = row.strip().split("|")
    return parts[1:-1] if row.strip().startswith("|") and row.strip().endswith("|") else parts


def verdict_columns(header):
    """Indices of the columns whose header names a verdict (Verdict, Status, Outcome, Decision, Result)."""
    return [i for i, c in enumerate(cells(header)) if _COLUMN.match(c)]


def row_verdicts(row, cols=()):
    """Statuses a table row states: whole-cell verdict words anywhere; in verdict columns, a leading verdict word
    (lower case: followed by ":", "(", a dash, "as", a date or the end; ALL CAPS: whatever follows, e.g.
    "ADOPTED v1.3.18 (…)", "ADOPTED fleet-wide"). A cell that says it was reversed or reverted gets no label."""
    cs = cells(row)
    found = {_norm(c.strip().strip("*_`")) for c in cs if " ".join(c.strip().strip("*_`").lower().split()) in VERDICT_WORDS}
    for i in cols:
        cell = cs[i] if i < len(cs) else ""
        if _UNDONE.search(cell):                     # "ADOPTED v1.2, then REVERSED": no label is the honest one
            continue
        m = _LEAD_CELL.match(cell) or _LEAD_CAPS.match(cell)
        if m:
            found.add(_norm(m.group(1)))
    return found


def row_status(part):
    """A table row group (header, separator, rows) whose rows all state one verdict carries that status."""
    if len(part) < 3 or not part[0].lstrip().startswith("|"):
        return ""
    cols = verdict_columns(part[0])
    found = set().union(*(row_verdicts(r, cols) for r in part[2:]))
    return found.pop() if len(found) == 1 else ""


def verdict(text, lines_only=False):
    """From a title or heading ending in a verdict, or a `Verdict: …` line. Empty when there is none."""
    m = (None if lines_only else _SUFFIX.search(text or "")) or _LINE.search(text or "")
    return _norm(m.group(1)) if m else ""


def section_verdict(lines, headings):
    """From a `## Verdict` (Outcome, Decision, Result) section: a verdict word leading its first non-empty line."""
    for k, (i, _, h) in enumerate(headings):
        if _SECTION.match(h.strip("*_ ")):
            end = headings[k + 1][0] if k + 1 < len(headings) else len(lines)
            first = next((ln for ln in lines[i + 1:end] if ln.strip()), "")
            m = _LEAD_LINE.match(first)
            if m:
                return _norm(m.group(1))
    return ""
