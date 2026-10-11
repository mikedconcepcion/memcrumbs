"""Reference plugin: an outliner for a niche brace language with no language server (the bench's `.kiln`
firing-profile language). Shows that a new brace language takes well under 100 lines.

Symbols: const, kiln, macro, profile at the top level; segment and `on EVENT` handlers inside a profile."""
import re

from memcrumbs.outline.braces import block_end

_TOP = re.compile(r"^\s*(kiln|macro|profile)\s+(\w+)\s*(\([^)]*\))?")
_CONST = re.compile(r"^\s*const\s+(\w+)\s*=\s*([^;]+);\s*(?://\s*(.*))?")
_INNER = re.compile(r"^\s*(segment)\s+(\w+)|^\s*on\s+(\w+)")


def _doc(lines, i):
    """The // comment block right above line i."""
    out = []
    while i > 0 and lines[i - 1].strip().startswith("//"):
        i -= 1
        out.insert(0, lines[i].strip().lstrip("/").strip())
    return " ".join(out)[:140]


def outline_kiln(text):
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        m = _CONST.match(ln)
        if m:
            out.append(dict(name=m.group(1), qual=m.group(1), kind="const", line=i + 1, end=i + 1,
                            sig="= " + m.group(2).strip(), doc=(m.group(3) or "").strip(), depth=0))
            i += 1
            continue
        m = _TOP.match(ln)
        if not m:
            i += 1
            continue
        kind, name = m.group(1), m.group(2)
        end = block_end(lines, i)
        out.append(dict(name=name, qual=name, kind=kind, line=i + 1, end=end + 1, sig=m.group(3) or "",
                        doc=_doc(lines, i), depth=0))
        if kind == "profile":
            for j in range(i + 1, end):
                n = _INNER.match(lines[j])
                if n:
                    inner = n.group(2) or "on " + n.group(3)
                    out.append(dict(name=inner, qual="%s.%s" % (name, inner), kind=n.group(1) or "handler",
                                    line=j + 1, end=block_end(lines, j) + 1, sig="", doc="", depth=1))
        i = end + 1
    return out


def register(api):
    api.add_outliner(".kiln", outline_kiln)
