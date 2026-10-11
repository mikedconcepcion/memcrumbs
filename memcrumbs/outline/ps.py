"""PowerShell outliner: functions/filters with brace-matched ranges; the doc is the comment-based help
(.SYNOPSIS / .DESCRIPTION) inside or above the function, or the `#` comment lines right above it."""
import re

from memcrumbs.outline import register
from memcrumbs.outline.braces import block_end
from memcrumbs.util import clip, split_lines

_FN = re.compile(r"^\s*(function|filter)\s+([\w:.-]+)\s*(\([^)]*\))?", re.I)
_HELP = re.compile(r"<#(.*?)#>", re.S)


def _help(block):
    m = _HELP.search(block)
    if not m:
        return ""
    text = re.sub(r"(?im)^\s*\.(?:synopsis|description)\s*$", "", m.group(1))
    text = re.split(r"(?im)^\s*\.(?:parameter|example|notes|inputs|outputs|link)\b", text)[0]
    return " ".join(text.split())


def _above(lines, i):
    out = []
    while i > 0 and lines[i - 1].strip().startswith("#") and not lines[i - 1].strip().startswith("#>"):
        i -= 1
        out.insert(0, lines[i].strip().lstrip("#").strip())
    return " ".join(out)


def outline_ps(text):
    lines = split_lines(text)
    out = []
    for i, ln in enumerate(lines):
        m = _FN.match(ln)
        if m:
            end = block_end(lines, i, "#")
            doc = _help("\n".join(lines[i:min(end + 1, i + 25)])) or _help("\n".join(lines[max(0, i - 15):i])) \
                or _above(lines, i)
            out.append(dict(name=m.group(2), qual=m.group(2), kind="function", line=i + 1, end=end + 1,
                            sig=clip(m.group(3) or "", 110), doc=clip(doc, 140), depth=0))
    return out


register((".ps1", ".psm1"), outline_ps)
