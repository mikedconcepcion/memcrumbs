"""Code hygiene without extra tools (stdlib ast): no name defined twice at module level (a second definition
silently wins), and no module over the size limit (800 lines, see CONTRIBUTING.md)."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted(list((ROOT / "memcrumbs").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")) +
               list((ROOT / "bench").rglob("plugins/*.py")))


def top_level_names(tree):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node.name, node.lineno
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    yield t.id, node.lineno


class Hygiene(unittest.TestCase):
    def test_no_duplicate_top_level_definitions(self):
        for f in FILES:
            seen, dupes = {}, []
            for name, line in top_level_names(ast.parse(f.read_text(encoding="utf-8"))):
                if name in seen and name != "_":
                    dupes.append("%s (lines %d and %d)" % (name, seen[name], line))
                seen.setdefault(name, line)
            with self.subTest(f.relative_to(ROOT).as_posix()):
                self.assertEqual(dupes, [])

    def test_modules_stay_small(self):
        for f in FILES:
            with self.subTest(f.relative_to(ROOT).as_posix()):
                self.assertLessEqual(len(f.read_text(encoding="utf-8").splitlines()), 800)


if __name__ == "__main__":
    unittest.main()
