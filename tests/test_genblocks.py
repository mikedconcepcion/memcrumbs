"""Property tests: generated blocks and frontmatter edits never change hand-written text."""
import random
import unittest

from memcrumbs import markdown
from memcrumbs.markdown import GEN_END, GEN_START, BlockError

ATOMS = ["word", " ", "  ", "\t", "\n", "\r\n", "\n\n", "# Head", "## Sub", "- item", "```", "~~~", "é", "😀",
         "<!--", "-->", "memcrumbs", "`<!-- memcrumbs:gen x -->` inline", "trailing   ", "---", "\x00", "﻿"]


def rand_text(rng, n):
    return "".join(rng.choice(ATOMS) for _ in range(n))


def outside(text, name):
    span = markdown.find_block(text, name)
    return (text, "") if span is None else (text[:span[0]], text[span[1]:])


class GeneratedBlockProperties(unittest.TestCase):
    def test_hand_text_survives_any_sequence_of_writes(self):
        rng = random.Random(20261010)
        for case in range(600):
            original = rand_text(rng, rng.randint(0, 40))
            text = original
            for _ in range(rng.randint(1, 4)):
                body = rand_text(rng, rng.randint(0, 12)).replace("<!--", "<!-")
                text = markdown.replace_generated(text, "x", body)
                self.assertEqual(text[:len(original)], original, case)            # appended after the hand text
                self.assertEqual(markdown.block_names(text).count("x"), 1)
            self.assertEqual(markdown.remove_generated(text, "x"), original, case)  # exact inverse

    def test_block_in_the_middle_keeps_both_sides(self):
        rng = random.Random(7)
        for case in range(300):
            nl = rng.choice(["\n", "\r\n"])
            before, after = rand_text(rng, 10) + nl, rand_text(rng, 10)
            text = before + GEN_START % "x" + nl + "old" + nl + GEN_END + nl + after
            new = markdown.replace_generated(text, "x", rand_text(rng, 8).replace("<!--", "<!-"))
            self.assertEqual(outside(new, "x"), (before, after), case)

    def test_other_blocks_are_untouched(self):
        text = "a\n" + GEN_START % "one" + "\n1\n" + GEN_END + "\nb\n" + GEN_START % "two" + "\n2\n" + GEN_END + "\nc\n"
        new = markdown.replace_generated(text, "two", "22")
        self.assertEqual(new, text.replace("\n2\n", "\n22\n"))

    def test_refuses_to_guess(self):
        with self.assertRaises(BlockError):                   # end marker deleted: never clobber to end of file
            markdown.replace_generated("a\n" + GEN_START % "x" + "\nhand text\n", "x", "new")
        with self.assertRaises(BlockError):
            markdown.replace_generated("a\n", "x", "sneaky\n" + GEN_END)
        inline = "docs mention `%s` inline\n" % (GEN_START % "x")
        self.assertTrue(markdown.replace_generated(inline, "x", "b").startswith(inline))

    def test_crlf_and_no_trailing_newline(self):
        self.assertEqual(markdown.replace_generated("a\r\nb", "x", "y"),
                         "a\r\nb\r\n" + GEN_START % "x" + "\r\ny\r\n" + GEN_END + "\r\n")


class FrontmatterEditProperties(unittest.TestCase):
    PAGE = "---\r\ntitle: T\r\nsources:\r\n  - a.py\r\n  - b.py\r\nverified: 2026-01-01\r\n---\r\n# T\r\nbody  \r\n"

    def test_only_named_keys_change(self):
        new = markdown.set_frontmatter(self.PAGE, {"verified": "2026-10-10", "status": "superseded"})
        self.assertEqual(new, self.PAGE.replace("2026-01-01", "2026-10-10").replace(
            "verified: 2026-10-10\r\n", "verified: 2026-10-10\r\nstatus: superseded\r\n"))
        meta, body, _ = markdown.frontmatter(new)
        self.assertEqual((meta["status"], meta["sources"], body), ("superseded", ["a.py", "b.py"], "# T\r\nbody  \r\n"))

    def test_block_list_replaced_and_key_removed(self):
        new = markdown.set_frontmatter(self.PAGE, {"sources": ["c.py"], "title": None})
        meta, body, _ = markdown.frontmatter(new)
        self.assertEqual((meta["sources"], "title" in meta), (["c.py"], False))
        self.assertTrue(new.endswith("# T\r\nbody  \r\n"))

    def test_page_without_frontmatter(self):
        self.assertEqual(markdown.set_frontmatter("# T\n", {"status": "rejected"}), "---\nstatus: rejected\n---\n# T\n")


if __name__ == "__main__":
    unittest.main()
