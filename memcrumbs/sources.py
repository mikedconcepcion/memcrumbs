"""Built-in sources: wiki pages, markdown doc trees, code symbols. A source yields (path, stamp, loader);
loader() -> (docs, symbols). Every text a loader returns has passed the redactor; if redaction fails the
loader raises and the file is not indexed (fail closed)."""
import functools
import re
from dataclasses import dataclass
from pathlib import Path

from memcrumbs import markdown, outline
from memcrumbs.guard import instruction_like
from memcrumbs.verdicts import row_status, section_verdict, verdict
from memcrumbs.util import clip, posix, read_text, split_lines, stamp, walk_stat

TEMPLATES = Path(__file__).parent / "templates"

CODE_INCLUDE = ["**/*.py", "**/*.ps1", "**/*.psm1", "**/*.mq5", "**/*.mqh", "**/*.mq4"]
FOLDER_KINDS = {"runbooks": "runbook", "decisions": "decision", "incidents": "incident", "journal": "journal",
                "research": "decision"}
KINDS = ("wiki", "runbook", "decision", "incident", "journal", "doc", "research", "memory", "legacy")


@dataclass
class Doc:
    kind: str
    path: str
    loc: int
    title: str
    section: str
    body: str
    tags: str = ""
    verified: str = ""
    status: str = ""
    flags: str = ""
    cites: str = ""          # `sources:` of the page, for the citation index (not searched)


def wiki_kind(project, path):
    """Wiki pages under runbooks/, decisions/, incidents/, journal/ get their own kind (searchable with -k)."""
    try:
        top = Path(path).resolve().relative_to(project.wiki).parts[0]
    except (ValueError, IndexError):
        return "wiki"
    return FOLDER_KINDS.get(top.lower(), "wiki")


def _norm(text):
    return " ".join(str(text).split()).lower()


@functools.lru_cache(maxsize=1)
def _boilerplate():
    """The starter pages' own text (their summaries and guidance sentences, as `init` writes them): never a hit,
    or on a new wiki every question with "every" or "page" in it finds the empty rules page first."""
    out = set()
    for name in ("rules.md", "gotchas.md", "index.md"):
        meta, body, _ = markdown.frontmatter((TEMPLATES / name).read_text(encoding="utf-8"))
        out.add(_norm(meta.get("summary") or ""))
        out.update(_norm("\n".join(part)) for _, _, part in markdown.chunks(split_lines(body), 80))
    out.discard("")
    return out


def md_docs(project, path, kind, text=None, max_lines=80):
    """Markdown file -> one Doc per heading chunk (+ a page-level Doc carrying title/summary/tags/aliases)."""
    text = read_text(path) if text is None else text
    meta, body, fm_lines = markdown.frontmatter(text)
    if markdown.truthy(meta.get("quarantined")):                # kept on disk, out of the index
        return []
    if str(meta.get("kind") or "").lower() in KINDS:            # frontmatter `kind:` beats the folder
        kind = str(meta["kind"]).lower()
    lines = split_lines(body)
    hs = markdown.headings(lines)
    red = project.redact
    title = red(str(meta.get("title") or next((h for _, lvl, h in hs if lvl == 1), Path(path).stem)))

    def words(key):
        v = meta.get(key) or []
        return " ".join(str(x) for x in v) if isinstance(v, list) else str(v)
    symptom = red(words("symptom"))           # what a repeater sees first (incidents): on the page doc only
    tags = red(" ".join(x for x in (words("tags"), words("aliases"), split_ident(Path(path).stem)) if x))
    verified, status = str(meta.get("verified") or ""), str(meta.get("status") or "").lower()
    status = status or verdict(title) or section_verdict(lines, hs) or verdict(body[:2000], lines_only=True)
    flags = " ".join(instruction_like(text) + (["destructive"] if markdown.truthy(meta.get("destructive")) else []) +
                     (["unreviewed"] if str(meta.get("written_by") or "").lower() == "agent" and not meta.get("reviewed")
                      else []))
    key = posix(path)
    docs = []
    summary = str(meta.get("summary") or "")
    boiler = _boilerplate() if kind == "wiki" else ()
    if (summary or kind in ("wiki", "runbook", "decision", "incident")) and _norm(summary) not in boiler:
        outline_txt = " · ".join(h for _, lvl, h in hs if lvl <= 3)[:600]
        docs.append(Doc(kind, key, 1, title, "symptom: " + symptom if symptom else "",
                        red("%s\n%s" % (summary, outline_txt)), tags, verified, status, flags, cites=red(words("sources"))))
    for start, head, part in markdown.chunks(lines, max_lines):
        if not any(ln.strip() and not ln.lstrip().startswith("#") for ln in part) or _norm("\n".join(part)) in boiler:
            continue                                     # a heading with nothing under it, or starter text
        docs.append(Doc(kind, key, start + 1 + fm_lines, title, red(head), red("\n".join(part)), tags, verified,
                        row_status(part) or verdict(head) or verdict("\n".join(part[:12]), lines_only=True) or status,
                        flags))
    return docs


def _wiki(project):
    from memcrumbs import facts
    registry = facts.page_path(project)                    # wiki_pages() are under project.wiki: no resolve()
    for p in project.wiki_pages():
        if p == registry:            # the facts page also yields one `fact` doc per key; a bound file's
            st = stamp(p.stat()) + facts.bind_stamp(project)        # change re-indexes it
            yield p, st, (lambda p=p: (md_docs(project, p, wiki_kind(project, p)) + facts.docs(project, p), []))
        else:
            yield p, stamp(p.stat()), (lambda p=p: (md_docs(project, p, wiki_kind(project, p)), []))


def _docs_source(spec):
    def gen(project):
        root = project.path(spec["root"])
        for p, rel, st in walk_stat(root, spec.get("include", ["**/*.md"]), spec.get("exclude", []), blocked=project.blocked):
            if project.wiki in p.resolve().parents:          # the wiki is its own source
                continue
            yield p, stamp(st), (lambda p=p: (md_docs(project, p, spec.get("kind", "doc")), []))
    return gen


def split_ident(s):
    """Identifier words, so `issue_refund`, `ProfileValidator` and `Register-Tasks` match "refund", "validator",
    "tasks" (the tokenizer keeps `issue_refund` whole for exact lookups)."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]
    return " ".join(words + [a + b for a, b in zip(words, words[1:]) if len(a) == 1])   # GZip: "gzip" too


def code_docs(project, path):
    text = read_text(path)
    syms = outline.outline_text(path, text) or []
    red = project.redact
    key, rel = posix(path), Path(path).name
    for s in syms:
        s["sig"], s["doc"], s["name"], s["qual"] = red(s["sig"]), red(s["doc"]), red(s["name"]), red(s["qual"])
    docs = []
    names = [s["qual"] for s in syms if s["kind"] not in ("h1", "h2", "h3", "h4", "h5", "h6")]
    where = split_ident(Path(path).parent.name)                   # booking/, chatbot/ … say what the file is about
    words = split_ident(Path(path).stem + " " + " ".join(names))
    about = red(outline.file_doc(path, text))
    docs.append(Doc("code", key, 1, rel, "", clip(about + " · " + " ".join(names), 1800), clip(where + " " + words, 1500)))
    for s in syms:
        if s["kind"] in ("const", "define"):
            continue
        if s["kind"] == "input":
            typ, _, default = s["sig"].partition(" = ")
            body = "input %s = %s (%s) %s" % (s["qual"], default, typ, s["doc"])
        else:
            body = "%s %s%s %s" % (s["kind"], s["qual"], s["sig"], s["doc"])
        docs.append(Doc("code", key, s["line"], rel, s["qual"], body, "%s %s %s" % (s["kind"], where, split_ident(s["qual"]))))
    return docs, syms


def _code(project):
    spec = project.cfg.get("code", {})
    roots = [project.path(r) for r in spec.get("roots", [])] or project.repos
    from memcrumbs.outline import REGISTRY
    include = spec.get("include") or CODE_INCLUDE + ["**/*%s" % e for e in REGISTRY if e not in (".md", ".markdown")]
    for root in roots:
        for p, rel, st in walk_stat(root, include, spec.get("exclude", []), blocked=project.blocked):
            yield p, stamp(st), (lambda p=p: code_docs(project, p))


def register_builtins(api):
    api.add_source("wiki", _wiki)
    for spec in api.project.cfg.get("docs", []) if api.project else []:
        api.add_source("docs:" + spec.get("name", spec["root"]), _docs_source(spec))
    if api.project and (api.project.repos or api.project.cfg.get("code")):
        api.add_source("code", _code)


def refresh(project, api, store, only=None, force=False, throttle=60):
    """v0.1 location of the indexer (kept for plugins that call it): see indexer.refresh."""
    from memcrumbs import indexer
    return indexer.refresh(project, api, store, only=only, force=force, throttle=throttle)
