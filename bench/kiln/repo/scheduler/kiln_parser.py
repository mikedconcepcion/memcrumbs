"""Tokenizer and parser for the Kiln Schedule Language (*.kiln).

Top-level items: const, include, kiln, macro, profile. One statement per line,
braces always balanced, ``//`` starts a line comment.
"""
import re

TOKEN_RE = re.compile(r'"[^"]*"|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?[hm]?|/h|[{}();:,=/-]')


class KilnSyntaxError(Exception):
    """Syntax problem with an error code such as E001 (unbalanced braces)."""

    def __init__(self, code: str, message: str, line: int):
        super().__init__(f"{code} line {line}: {message}")
        self.code = code
        self.line = line


def tokenize(text: str) -> list[tuple[str, int]]:
    """Split source text into (token, line_number) pairs, dropping comments."""
    tokens = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("//", 1)[0]
        for match in TOKEN_RE.finditer(line):
            tokens.append((match.group(0), lineno))
    return tokens


def check_braces(tokens: list[tuple[str, int]]) -> None:
    """Raise E001 when braces are not balanced."""
    depth = 0
    for tok, line in tokens:
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth -= 1
            if depth < 0:
                raise KilnSyntaxError("E001", "unexpected closing brace", line)
    if depth != 0:
        raise KilnSyntaxError("E001", "unclosed brace at end of file", tokens[-1][1] if tokens else 1)


def parse(text: str) -> dict:
    """Parse source into a dict of consts, includes, kilns, macros and profiles."""
    tokens = tokenize(text)
    check_braces(tokens)
    out = {"consts": {}, "includes": [], "kilns": [], "macros": [], "profiles": []}
    i = 0
    while i < len(tokens):
        word, line = tokens[i]
        if word == "const":
            out["consts"][tokens[i + 1][0]] = tokens[i + 3][0]
            i += 5
        elif word == "include":
            out["includes"].append(tokens[i + 1][0].strip('"'))
            i += 3
        elif word in ("kiln", "macro", "profile"):
            name = tokens[i + 1][0]
            depth, j = 0, i + 2
            while True:
                if tokens[j][0] == "{":
                    depth += 1
                elif tokens[j][0] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            out[word + "s"].append({"name": name, "tokens": tokens[i + 2:j + 1]})
            i = j + 1
        else:
            raise KilnSyntaxError("E002", f"unexpected token {word!r}", line)
    return out
