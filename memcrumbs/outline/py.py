"""Python outliner (ast; regex fallback for files that do not parse)."""
import ast
import re

from memcrumbs.outline import register
from memcrumbs.util import clip, split_lines


def _doc(node):
    try:
        d = ast.get_docstring(node)
    except Exception:
        d = None
    return clip(d.strip().splitlines()[0], 140) if d else ""


def _start(node):
    decos = getattr(node, "decorator_list", None) or []
    return min([node.lineno] + [d.lineno for d in decos])


def outline_py(text):
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return _fallback(text)
    out = []

    def visit(node, prefix, depth, in_class):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                try:
                    sig = "(" + ast.unparse(n.args) + ")"
                except Exception:
                    sig = "(…)"
                out.append(dict(name=n.name, qual=prefix + n.name, kind="method" if in_class else "def",
                                line=_start(n), end=n.end_lineno, sig=clip(sig, 110), doc=_doc(n), depth=depth))
                if depth < 2:
                    visit(n, prefix + n.name + ".", depth + 1, False)
            elif isinstance(n, ast.ClassDef):
                bases = ", ".join(ast.unparse(b) for b in n.bases) if n.bases else ""
                out.append(dict(name=n.name, qual=prefix + n.name, kind="class", line=_start(n), end=n.end_lineno,
                                sig="(%s)" % bases if bases else "", doc=_doc(n), depth=depth))
                visit(n, prefix + n.name + ".", depth + 1, True)
            elif depth == 0 and isinstance(n, (ast.Assign, ast.AnnAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Name) and t.id.isupper() and len(t.id) > 1:
                        out.append(dict(name=t.id, qual=t.id, kind="const", line=n.lineno, end=n.end_lineno,
                                        sig="", doc="", depth=0))
    visit(tree, "", 0, False)
    return out


_RX = re.compile(r"^(\s*)(?:async\s+)?(def|class)\s+(\w+)\s*(\([^)]*\)?)?")


def _fallback(text):
    out = []
    for i, ln in enumerate(split_lines(text), 1):
        m = _RX.match(ln)
        if m:
            depth = len(m.group(1)) // 4
            out.append(dict(name=m.group(3), qual=m.group(3), kind=m.group(2), line=i, end=i,
                            sig=clip(m.group(4) or "", 110), doc="", depth=depth))
    return out


register((".py", ".pyw"), outline_py)
