"""MQL4/MQL5 outliner: inputs, #defines, structs/classes, top-level functions (brace-matched)."""
import re

from memcrumbs.outline import register
from memcrumbs.outline.braces import block_end
from memcrumbs.util import clip, split_lines

_INPUT = re.compile(r"^\s*(?:sinput|input|extern)\s+([\w<>]+)\s+(\w+)\s*(?:=\s*([^;]+))?;\s*(?://\s*(.*))?")
_DEFINE = re.compile(r"^\s*#define\s+(\w+)\s*(.*)")
_TYPE = re.compile(r"^\s*(struct|class|enum)\s+(\w+)")
_FUNC = re.compile(r"^(?:(?:static|virtual|const|inline)\s+)*([\w<>:*&]+(?:\s*[*&])?)\s+([\w:~]+)\s*\(([^;]*)$")
_SKIP = {"if", "for", "while", "switch", "return", "else", "do", "case", "new", "delete"}


def outline_mql(text):
    lines = split_lines(text)
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _INPUT.match(ln)
        if m:
            sig = "%s = %s" % (m.group(1), (m.group(3) or "").strip())
            out.append(dict(name=m.group(2), qual=m.group(2), kind="input", line=i + 1, end=i + 1,
                            sig=clip(sig, 60), doc=clip(m.group(4) or "", 100), depth=0))
            i += 1
            continue
        m = _DEFINE.match(ln)
        if m:
            out.append(dict(name=m.group(1), qual=m.group(1), kind="define", line=i + 1, end=i + 1,
                            sig=clip(m.group(2), 60), doc="", depth=0))
            i += 1
            continue
        m = _TYPE.match(ln)
        if m and not ln.rstrip().endswith(";"):
            end = block_end(lines, i)
            out.append(dict(name=m.group(2), qual=m.group(2), kind=m.group(1), line=i + 1, end=end + 1,
                            sig="", doc="", depth=0))
            i += 1
            continue
        m = _FUNC.match(ln) if ln[:1].strip() else None          # top-level only (column 0)
        if m and m.group(2) not in _SKIP and m.group(1) not in _SKIP:
            head = ln
            j = i
            while ")" not in head and j + 1 < len(lines) and j - i < 6:   # multi-line parameter lists
                j += 1
                head += " " + lines[j].strip()
            if ")" in head and not head.split(")")[-1].strip().startswith(";"):
                end = block_end(lines, i)
                params = head[head.index("(") + 1:head.rindex(")")]
                out.append(dict(name=m.group(2), qual=m.group(2), kind="function", line=i + 1, end=end + 1,
                                sig=clip("%s (%s)" % (m.group(1), params), 110), doc="", depth=0))
                i = end + 1
                continue
        i += 1
    return out


register((".mq5", ".mqh", ".mq4"), outline_mql)
