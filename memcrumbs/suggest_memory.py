"""Two stores → one: a note in the host's auto-memory that the wiki already holds becomes a pointer.

Claude Code loads the memory index (MEMORY.md, its first 200 lines or 25 KB) in every session. When the wiki was
grown from those notes, the same knowledge lives twice, and the copies drift apart (F1). A note is a duplicate when
its own name finds a wiki page first and most of its words are in that page. Applying:
- turns its index line into `- [Title](note.md) → memcrumbs page <page>`;
- reduces the note to a pointer plus the lines the page does not have yet ("not in the wiki yet").
It writes the host's memory folder, outside the wiki: `--outside-wiki`, a backup first, `suggest undo` restores
every byte."""
import re
from pathlib import Path

from memcrumbs import markdown, transcripts
from memcrumbs.query import STOPWORDS
from memcrumbs.suggest import Suggestion
from memcrumbs.util import read_doc, read_text, shq

LINK = re.compile(r"^(\s*[-*]\s*\[([^\]]+)\]\(([^)\s]+\.md)\))(.*)$")
CONTAINED = 0.6                    # share of the note's words in the page, for the page to be its match
COVERED = 0.8                      # a real duplicate: this share of the note's content lines are in the page
LINE_WORDS = 0.8                   # a line is in the page when this share of its words are
FIGURE = re.compile(r"\d[\d.,:/%-]*")
# a state an index line can record: losing it from the always-loaded index loses a fact
STATE = re.compile(r"(?i)\b(on|off|live|paused|retired|enabled|disabled|active|inactive|running|stopped|deprecated|"
                   r"frozen|down|blocked|broken|archived|pending|open|closed|rejected|accepted|superseded|parked|"
                   r"shelved|removed|replaced|migrated|unused|primary|fallback|read-only|readonly)\b")
SAVES = 10                         # below this many tokens, an offer does not claim a saving


def folders(project):
    """Where the project reads its memory: the configured `kind = "memory"` docs roots that hold a MEMORY.md, else
    the host's auto-memory folders for the project's repos."""
    roots = [project.path(spec["root"]) for spec in project.cfg.get("docs", []) if spec.get("kind") == "memory"]
    mine = [Path(r) for r in roots if (Path(r) / "MEMORY.md").is_file()]
    return mine or [f / "memory" for f in transcripts.folders(project) if (f / "memory" / "MEMORY.md").is_file()]


def coverage(lines, page_words):
    """(content lines in the page, all content lines): a line is in the page when most of its words are."""
    content = [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#") and len(_words(ln)) >= 2]
    covered = [ln for ln in content if len(_words(ln) & page_words) >= LINE_WORDS * len(_words(ln))]
    return covered, content


def lost_facts(hook, page_text):
    """Figures (numbers, versions, dates, ids) and state words (live, paused, retired …) of an index line that the
    page does not hold: replacing the line would drop those facts from the always-loaded index. Ordinary words do
    not count: the pointer keeps the line's wording instead."""
    low = page_text.lower()
    states = {m.group(0).lower() for m in STATE.finditer(page_text)}
    return [f for f in FIGURE.findall(hook) if f.strip(".,:-") and f.strip(".,:-") not in low] + \
        sorted({m.group(0).lower() for m in STATE.finditer(hook)} - states)


def lost_words(hook, page_text):
    """Ordinary words of the index line that the page lacks: kept in the pointer line, not a reason to wait."""
    have = _words(page_text)
    return [w for w in _words(hook) if w not in have]


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower()) if w not in STOPWORDS}


def _norm(line):
    return " ".join(re.sub(r"[^\w]+", " ", line.lower()).split())


def _store(project):
    if not project.index_path.exists():
        return None
    from memcrumbs import synonyms
    from memcrumbs.store import Store
    try:
        return Store(project.index_path, synonyms.for_project(project))
    except Exception:
        return None


def _match(project, store, title, desc, body):
    """The wiki page that holds this note, or None."""
    from memcrumbs.store import WIKI_KINDS
    try:
        hits = store.search("%s %s" % (title, desc), kinds=list(WIKI_KINDS), limit=1)
    except Exception:
        return None
    if not hits:
        return None
    page = Path(hits[0]["path"])
    if not page.exists():
        return None
    note, have = _words("%s %s %s" % (title, desc, body)), _words(read_text(page))
    return page if note and len(note & have) / len(note) >= CONTAINED else None


def _pointer(index_text, link_line, page_stem, keep_words=False):
    """(the index with that line as a pointer, the new line). With `keep_words` the line's own text stays after
    the link (it says something the page does not word that way)."""
    m = LINK.match(link_line)
    new = "%s%s → memcrumbs page %s" % (m.group(1), m.group(4).rstrip() if keep_words else "", shq(page_stem))
    return index_text.replace(link_line, new, 1), new


def _note_body(note_text, page, page_title):
    meta_end = markdown.frontmatter(note_text)[2]
    lines = note_text.splitlines()
    head, body = lines[:meta_end], lines[meta_end:]
    have = _norm(read_text(page))
    extra = [ln for ln in body if ln.strip() and not ln.lstrip().startswith("#") and len(_norm(ln)) > 12
             and _norm(ln) not in have]
    nl = "\r\n" if "\r\n" in note_text else "\n"
    out = head + ["", "This note now lives in the wiki: `memcrumbs page %s` (%s)." % (shq(page.stem), page_title)]
    if extra:
        out += ["", "Not in the wiki yet (move these there, then delete them here):"] + extra
    return nl.join(out) + nl


def _memory(project, cheap_only=False):
    store = _store(project)
    if store is None:
        return []
    out = []
    try:
        for folder in folders(project):
            index = folder / "MEMORY.md"
            index_text = read_doc(index)[0]
            for line in index_text.splitlines():
                m = LINK.match(line)
                if not m or "→ memcrumbs page" in m.group(4):
                    continue
                note = (folder / m.group(3)).resolve()
                if folder.resolve() not in note.parents or not note.is_file():
                    continue                          # a link out of the memory folder is never followed
                note_text = read_doc(note)[0]
                meta, body, _ = markdown.frontmatter(note_text)
                desc = str(meta.get("description") or m.group(4).strip(" -—:"))
                page = _match(project, store, m.group(2), desc, body)
                if page is None:
                    continue
                page_text = read_text(page)
                covered, content = coverage(body.splitlines(), _words(page_text))
                lost = lost_facts(m.group(4), page_text)
                if not content or len(covered) < COVERED * len(content) or len(lost) > 0:
                    out.append(Suggestion(
                        "migrate", "%s|%s|%s" % (folder.parent.name, m.group(3), project.rel(page)),
                        "memory note %s overlaps %s, but the wiki does not hold all of it" % (m.group(3), project.rel(page)),
                        "move what only the note says into the page first; the pointer is offered once it is a duplicate",
                        ["%d of %d content lines are in the page" % (len(covered), len(content))] +
                        (["its index line holds what the page lacks: %s" % ", ".join(lost[:6])] if lost else []),
                        agent="add the note's missing lines (and the index line's figures) to %s with sources, then run "
                              "memcrumbs suggest --kind memory" % page.stem, score=len(content) - len(covered)))
                    continue
                title = str(markdown.frontmatter(page_text)[0].get("title") or page.stem)
                words = lost_words(m.group(4), page_text)
                new_index, new_line = _pointer(index_text, line, page.stem, keep_words=bool(words))
                new_note = _note_body(note_text, page, title)
                saved = (len(line) - len(new_line)) // 4
                gain = ("≈ %d tokens less in every session's index" % saved if saved >= SAVES else
                        "one place for it: the note body, read only on demand, points at the page")
                out.append(Suggestion(
                    "memory", "%s|%s|%s" % (folder.parent.name, m.group(3), project.rel(page)),
                    "memory note %s duplicates %s" % (m.group(3), project.rel(page)),
                    "point the note and its index line at the page (%s; unique lines kept%s)"
                    % (gain, "; the index line keeps its wording" if words else ""),
                    ["its name finds %s first; %d of %d content lines are in that page" % (
                        project.rel(page), len(covered), len(content)),
                     "note %d → %d characters" % (len(note_text), len(new_note))],
                    risk="writes-outside-wiki", changes=[(index, new_index), (note, new_note)],
                    agent="move the 'not in the wiki yet' lines into %s, then delete them from the note" % page.stem,
                    score=1 + len(note_text) / 1000))
    finally:
        store.close()
    return out


SUGGESTERS = {"memory": _memory, "migrate": _memory}   # one pass yields both: pointers, and moves to make first
