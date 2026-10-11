"""Code outliners: file -> symbols with line ranges, so an agent reads 40 lines instead of 4,000.

Each outliner takes the file text and returns a list of dicts:
  name, qual (dotted path), kind (class/def/method/const/input/define/function/heading), line, end, sig, doc, depth
Packs and project plugins can register more extensions via `register`.
"""
import re
from pathlib import Path

from memcrumbs.util import clip, read_text

REGISTRY = {}
_COMMENT = re.compile(r"^\s*(?:#(?!!)|//|--|;|<#|#>|\*|/\*)")


def register(exts, fn):
    for e in ([exts] if isinstance(exts, str) else exts):
        REGISTRY[e.lower()] = fn


def outline_text(path, text):
    fn = REGISTRY.get(Path(path).suffix.lower())
    if not fn:
        return None
    try:
        return fn(text)
    except Exception:
        return []


def outline(path):
    return outline_text(path, read_text(path))


def file_doc(path, text, n=300):
    """What the file says about itself: a Python module docstring, or the comment block at the top."""
    if Path(path).suffix.lower() in (".py", ".pyw"):
        m = re.match(r'\s*(?:#[^\n]*\n\s*)*(?:[rRuU]?("""|\'\'\'))(.*?)\1', text, re.S)
        return clip(m.group(2), n) if m else ""
    out = []
    for ln in text.splitlines()[:40]:
        if not ln.strip() or ln.startswith("#!"):
            if out:
                break
            continue
        if not _COMMENT.match(ln):
            break
        out.append(re.sub(r"^\s*(?:<#|#>|#|//|--|;|/\*|\*/|\*)\s?", "", ln).strip())
    return clip(" ".join(x for x in out if x), n)


def _load_builtins():
    from memcrumbs.outline import md, mql, ps, py  # noqa: F401  (each registers itself)


_load_builtins()
