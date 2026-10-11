"""Markdown outliner: headings with the line range each one covers."""
from memcrumbs.markdown import headings
from memcrumbs.outline import register
from memcrumbs.util import split_lines


def outline_md(text):
    lines = split_lines(text)
    hs = headings(lines)
    out = []
    for k, (i, lvl, h) in enumerate(hs):
        end = len(lines)
        for j, l2, _ in hs[k + 1:]:
            if l2 <= lvl:
                end = j
                break
        out.append(dict(name=h, qual=h, kind="h%d" % lvl, line=i + 1, end=end, sig="", doc="", depth=lvl - 1))
    return out


register((".md", ".markdown"), outline_md)
