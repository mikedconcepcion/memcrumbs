"""Markdown parsing for wiki pages and doc sources: frontmatter, sections, links, generated blocks.

Edits made here (generated blocks, frontmatter fields) keep every other byte of the file as it was:
newline style, trailing whitespace and hand-written text outside the touched lines."""
import re

from memcrumbs.verdicts import row_verdicts, verdict_columns

_FM = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_HEAD = re.compile(r"^(#{1,6})[ \t]+(\S.*)$")         # no nested quantifiers: linear on any line
_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
GEN_START = "<!-- memcrumbs:gen %s -->"
GEN_END = "<!-- memcrumbs:end -->"
_MARK = re.compile(r"^[ \t]*<!-- memcrumbs:(?:gen ([\w.-]+)|end) -->[ \t]*\r?$", re.M)


class BlockError(ValueError):
    """A generated block is malformed (no end marker, nested); refusing to guess which text is generated."""


def _scalar(v):
    v = v.strip()
    if v.startswith("[[") and v.endswith("]]") and v.count("[[") == 1:
        return v                                       # a [[wiki link]], not a list
    if v.startswith("[") and v.endswith("]"):
        return [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def frontmatter(text):
    """Return (meta dict, body text, number of lines the frontmatter used). Minimal YAML subset:
    `key: value`, `key: [a, b]`, and `key:` followed by `- item` lines."""
    m = _FM.match(text)
    if not m:
        return {}, text, 0
    meta, key = {}, None
    for ln in m.group(1).splitlines():
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        if ln.lstrip().startswith("- ") and key:
            if not isinstance(meta.get(key), list):
                meta[key] = []
            item = _scalar(ln.lstrip()[2:])
            meta[key].extend(item if isinstance(item, list) else [item])     # never a list inside a list
            continue
        if ":" in ln and not ln[:1].isspace():
            key, v = ln.split(":", 1)
            key = key.strip()
            meta[key] = _scalar(v) if v.strip() else []
    body = text[m.end():]
    return meta, body, text[:m.end()].count("\n")


def set_frontmatter(text, updates):
    """Set top-level frontmatter keys (value None removes the key), touching only those lines. A page without
    frontmatter gets a new block at the top. Values are written as `key: value` or `key: [a, b]`."""
    nl = "\r\n" if "\r\n" in text else "\n"

    def render(k, v):
        return "%s: %s" % (k, "[%s]" % ", ".join(v) if isinstance(v, (list, tuple)) else v)
    m = _FM.match(text)
    if not m:
        new = [render(k, v) for k, v in updates.items() if v is not None]
        return ("---" + nl + nl.join(new) + nl + "---" + nl + text) if new else text
    a, b = m.span(1)
    parts = re.split(r"(\r?\n)", text[a:b])            # each line keeps its own ending (mixed files stay as they are)
    lines, ends = parts[0::2], parts[1::2] + [""]
    out, i, done = [], 0, set()
    while i < len(lines):
        ln, end = lines[i], ends[i]
        key = ln.split(":", 1)[0].strip() if ":" in ln and not ln[:1].isspace() else None
        if key in updates:
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith("- ") and lines[i][:1].isspace():
                end = ends[i]
                i += 1                                         # the old block-style list items
            if updates[key] is not None:
                out.append(render(key, updates[key]) + end)
            done.add(key)
            continue
        out.append(ln + end)
        i += 1
    new = [render(k, v) for k, v in updates.items() if k not in done and v is not None]
    body = "".join(out)
    if new:
        tail = "" if body.endswith(("\n", "\r")) or not body else nl
        body = body + tail + nl.join(new)
    if body.endswith("\n") and not text[a:b].endswith("\n"):
        body = body.rstrip("\r\n")                           # the last line's ending belongs to the closing ---
    return text[:a] + body + text[b:]


def headings(lines):
    """[(index, level, text)] for ATX headings outside code fences (0-based line index)."""
    out, fence = [], False
    for i, ln in enumerate(lines):
        s = ln.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if not fence:
            m = _HEAD.match(ln)
            if m:                                     # closing #s and whitespace are trimmed outside the regex
                out.append((i, len(m.group(1)), m.group(2).rstrip().rstrip("#").rstrip()))
    return out


TABLE_ROWS = 8          # a table longer than this is indexed in groups of TABLE_GROUP rows
TABLE_GROUP = 5
_SEP = re.compile(r"^[ \t]*+\|?[ \t]*+:?-{2,}+:?[ \t]*+(?:\|[ \t]*+:?-{2,}+:?[ \t]*+)*+\|?[ \t]*+$")   # possessive: linear


def _tables(seg):
    """[(first, end)] index ranges of markdown tables (header, separator, rows) inside a segment."""
    out, i = [], 0
    while i + 1 < len(seg):
        if seg[i].lstrip().startswith("|") and _SEP.match(seg[i + 1]):
            j = i + 2
            while j < len(seg) and seg[j].lstrip().startswith("|"):
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def chunks(lines, max_lines=80):
    """Split into retrieval chunks: one per heading (until the next heading of any level), long ones
    split further. A long table becomes groups of rows that each repeat the header, so the one row that
    matters is not diluted by forty others. Yields (start_index, heading_text, chunk_lines)."""
    hs = headings(lines)
    bounds = [(0, "")] + [(i, h) for i, _, h in hs]
    if hs and hs[0][0] == 0:
        bounds = bounds[1:]
    for k, (start, head) in enumerate(bounds):
        end = bounds[k + 1][0] if k + 1 < len(bounds) else len(lines)
        seg = lines[start:end]
        if not "".join(seg).strip():
            continue
        big = [(a, b) for a, b in _tables(seg) if b - a - 2 > TABLE_ROWS or _has_verdicts(seg, a, b)]
        rest = [ln if not any(a <= n < b for a, b in big) else "" for n, ln in enumerate(seg)]
        yield from _plain(start, head, rest, max_lines)           # prose (tables blanked: line numbers stay)
        for a, b in big:
            for r, n in _row_groups(seg, a + 2, b):
                yield start + r, head, seg[a:a + 2] + seg[r:r + n]


def _has_verdicts(seg, a, b):
    """Any table that states verdicts is grouped, whatever its size, so each row group carries its own status."""
    cols = verdict_columns(seg[a])
    return any(row_verdicts(seg[r], cols) for r in range(a + 2, b))


def _row_groups(seg, first, end):
    """(start, count) groups of up to TABLE_GROUP rows; a new group starts where the verdict changes, so each group
    carries one status."""
    groups, start, key = [], first, None
    cols = verdict_columns(seg[first - 2])
    for r in range(first, end):
        k = frozenset(row_verdicts(seg[r], cols))
        if r > start and (r - start >= TABLE_GROUP or k != key):
            groups.append((start, r - start))
            start = r
        if r == start:
            key = k
    if start < end:
        groups.append((start, end - start))
    return groups


def _plain(start, head, seg, max_lines):
    for j in range(0, len(seg), max_lines):
        part = seg[j:j + max_lines]
        if "".join(part).strip():
            yield start + j, (head + (" (cont.)" if j else "")), part


def section_span(lines, query):
    """Find the heading best matching `query`; return (start, end) covering it and its subsections."""
    hs = headings(lines)
    q = query.lower().strip().lstrip("#").strip()
    best = None
    for test in (lambda h: h.lower() == q, lambda h: h.lower().startswith(q), lambda h: q in h.lower()):
        for i, lvl, h in hs:
            if test(h):
                best = (i, lvl)
                break
        if best:
            break
    if not best:
        return None
    start, lvl = best
    end = len(lines)
    for i, l2, _ in hs:
        if i > start and l2 <= lvl:
            end = i
            break
    return start, end


def links(text):
    return [x.strip() for x in _LINK.findall(text)]


def truthy(v):
    """A frontmatter flag: true / yes / 1 / on."""
    return v is True or str(v).strip().lower() in ("true", "yes", "1", "on")


def find_block(text, name):
    """(start, end) of the generated block NAME: from its start-marker line through its end-marker line and
    that line's newline. None if absent; BlockError if it is not closed or another block starts inside it."""
    marks = list(_MARK.finditer(text))
    for k, m in enumerate(marks):
        if m.group(1) == name:
            nxt = marks[k + 1] if k + 1 < len(marks) else None
            if nxt is None or nxt.group(1) is not None:
                raise BlockError("generated block %r has no end marker before the next block or end of file" % name)
            end = nxt.end()
            for eol in ("\r\n", "\n"):
                if text.startswith(eol, end):
                    end += len(eol)
                    break
            return m.start(), end
    return None


def block_names(text):
    return [m.group(1) for m in _MARK.finditer(text) if m.group(1)]


def replace_generated(text, name, new_body):
    """Rewrite the block between `<!-- memcrumbs:gen NAME -->` and its `<!-- memcrumbs:end -->` (each on its own
    line), keeping every other byte. A missing block is appended after one newline, so `remove_generated`
    restores the original exactly."""
    if _MARK.search(new_body):
        raise BlockError("generated text may not contain memcrumbs markers")
    nl = "\r\n" if "\r\n" in text else "\n"
    body = nl.join(new_body.rstrip().splitlines())
    block = GEN_START % name + nl + (body + nl if body else "") + GEN_END + nl
    span = find_block(text, name)
    if span:
        return text[:span[0]] + block + text[span[1]:]
    return text + nl + block if text else block


def remove_generated(text, name):
    """Inverse of `replace_generated`: drop the block; an appended block (last in the file) also takes the one
    newline that was added before it."""
    span = find_block(text, name)
    if not span:
        return text
    a, b = span
    if b == len(text):
        for eol in ("\r\n", "\n"):
            if text[:a].endswith(eol):
                a -= len(eol)
                break
    return text[:a] + text[b:]
