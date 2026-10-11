"""Brace matching for C-like / PowerShell sources (ignores // and # comments and quoted strings, roughly)."""


def block_end(lines, start, line_comment="//"):
    """From 0-based `start`, find the first '{' within 4 lines and return the 0-based index of its matching '}'."""
    depth, opened = 0, False
    for i in range(start, len(lines)):
        ln = lines[i]
        in_str = None
        j = 0
        while j < len(ln):
            c = ln[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == in_str:
                    in_str = None
            elif ln.startswith(line_comment, j):
                break
            elif c in "\"'":
                in_str = c
            elif c == "{":
                depth += 1
                opened = True
            elif c == "}":
                depth -= 1
                if opened and depth == 0:
                    return i
            j += 1
        if not opened and i - start >= 4:
            return start
    return len(lines) - 1
