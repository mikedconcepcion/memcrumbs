"""Text-level JSON edits for `wire`: insert one member or array element right after an opening brace or
bracket, leaving every other byte (formatting, key order, unicode escapes) as it was, so removal can
take out exactly the inserted text."""
import json
from json.decoder import scanstring


class JsonEditError(ValueError):
    pass


def _ws(s, i):
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _string_end(s, i):
    if s[i] != '"':
        raise JsonEditError("expected a string at offset %d" % i)
    return scanstring(s, i + 1)


def value_end(s, i):
    """Offset just past the JSON value starting at s[i]."""
    c = s[i]
    if c == '"':
        return _string_end(s, i)[1]
    if c in "{[":
        close = "}" if c == "{" else "]"
        i = _ws(s, i + 1)
        if s[i] == close:
            return i + 1
        while True:
            if c == "{":
                i = _ws(s, _string_end(s, i)[1])
                if s[i] != ":":
                    raise JsonEditError("expected ':' at offset %d" % i)
                i = _ws(s, i + 1)
            i = _ws(s, value_end(s, i))
            if s[i] == ",":
                i = _ws(s, i + 1)
                continue
            if s[i] != close:
                raise JsonEditError("expected %r at offset %d" % (close, i))
            return i + 1
    j = i
    while j < len(s) and s[j] not in ",}] \t\r\n":
        j += 1
    return j


def members(s, i):
    """For the object whose '{' is at s[i]: {key: (value_start, value_end)}."""
    out = {}
    i = _ws(s, i + 1)
    if s[i] == "}":
        return out
    while True:
        key, i = _string_end(s, i)
        i = _ws(s, _ws(s, i) + 1)
        end = value_end(s, i)
        out[key] = (i, end)
        i = _ws(s, end)
        if s[i] != ",":
            return out
        i = _ws(s, i + 1)


def is_empty(s, i):
    return s[_ws(s, i + 1)] in "}]"


def insert_after_open(s, i, fragment, indent, nl):
    """Insert `fragment` as the first member/element of the container opened at s[i]. Returns (text, snippet)."""
    snippet = nl + indent + fragment + (nl if is_empty(s, i) else ",")
    return s[:i + 1] + snippet + s[i + 1:], snippet


def check_object(text):
    try:
        data = json.loads(text)
    except ValueError as e:
        raise JsonEditError("not plain JSON (%s)" % e) from None
    if not isinstance(data, dict):
        raise JsonEditError("top level is not an object")
    return data
