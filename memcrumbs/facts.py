"""Single-sourced facts: one registry of current values, so a value that changes is written once.

The registry is a table in `wiki/facts.md` with the columns `key | value | about | source | verified` (only key
and value are required). A key can be bound to a file in memcrumbs.toml; its value is then read from the file
every time, so it cannot go stale:

    [facts.bind.live_version]
    from = "repo/VERSION"              # relative to the project folder, the wiki or a repo
    pattern = '^(\\S+)'                # the first group (or the whole match) is the value

`memcrumbs fact <key>` answers in one line; facts are indexed as `fact` hits that rank first; `{{fact:key}}` in a
page prints the current value in `page`; `check` flags a page (or a `memory` note) that states a registered
subject with another value in the present tense."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from memcrumbs import freshness, markdown
from memcrumbs.util import read_text, split_lines

PAGE = "facts"
TOKEN = re.compile(r"\{\{\s*fact:([\w.-]+)\s*\}\}")
CODE = re.compile(r"(`+[^`\n]*`+)")
HISTORY = re.compile(r"(?i)\b(history|changelog|change log|timeline|previous|earlier|old|before|archive|past)\b")
PAST = re.compile(r"(?i)\b(was|were|used to|previously|formerly|until|before|had been|no longer|old)\b|\d{4}-\d{2}-\d{2}")
RECORDS = ("journal", "incidents", "decisions")         # dated records state the value of their day
NEAR = 48                                               # a value must follow the subject within this many characters


@dataclass
class Fact:
    key: str
    value: str
    about: list = field(default_factory=list)
    source: str = ""
    verified: str = ""
    line: int = 0
    bound: str = ""             # the file a bound value comes from
    written: str = ""           # the table's value when a binding overrides it
    error: str = ""


def page_path(project):
    return project.wiki / (str(project.cfg.get("facts", {}).get("page", PAGE)) + ".md")


def _cells(line):
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _table(text):
    """Rows of every table whose header has `key` and `value`: [(line number, {column: cell})]."""
    lines, rows, cols = split_lines(text), [], None
    for i, ln in enumerate(lines):
        if not ln.lstrip().startswith("|"):
            cols = None
            continue
        cells = [c.lower() for c in _cells(ln)]
        if cols is None:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            if "key" in cells and "value" in cells and set(nxt.replace("|", "").strip()) <= set("-: "):
                cols = cells
            continue
        if set(ln.replace("|", "").strip()) <= set("-: "):
            continue
        rows.append((i + 1, dict(zip(cols, _cells(ln)))))
    return rows


def _bound(project, spec):
    for p in freshness.source_paths(project, [spec.get("from", "")]):
        if project.blocked(p):                       # a never_index file (keys, .env …) is never read for a value
            return "", None, "bound file %s matches [security] never_index" % p.name
        try:
            m = re.search(str(spec.get("pattern", r"^(.+)$")), read_text(p), re.M)
        except re.error as e:                        # a bad pattern is that fact's error, never a crash
            return "", None, "pattern is not a valid regex (%s)" % e
        if not m:
            return "", p, "pattern not found in %s" % p.name
        return ((m.group(1) if m.groups() else m.group(0)) or "").strip(), p, ""
    return "", None, "bound file %r not found" % spec.get("from", "")


def bind_stamp(project):
    """The bound files' stamps, so the registry page is re-indexed when one of them changes."""
    from memcrumbs.util import stamp
    parts = []
    for spec in (project.cfg.get("facts", {}).get("bind") or {}).values():
        for p in freshness.source_paths(project, [spec.get("from", "")]):
            parts.append(stamp(p.stat()))
    return ("|" + "|".join(parts)) if parts else ""


def load(project):
    """Every registered fact; a binding wins over the table and keeps the table's value in `written`."""
    out, f = {}, page_path(project)
    if f.exists():
        text = read_text(f)
        _, body, fm = markdown.frontmatter(text)
        for line, row in _table(body):
            key = row.get("key", "").strip("` ")
            if key:
                about = [a.strip() for a in re.split(r"[;,]", row.get("about", row.get("aliases", ""))) if a.strip()]
                out[key] = Fact(key, row.get("value", "").strip("` "), about, row.get("source", ""),
                                row.get("verified", ""), line + fm)
    for key, spec in (project.cfg.get("facts", {}).get("bind") or {}).items():
        fact = out.setdefault(key, Fact(key, ""))
        value, path, err = _bound(project, spec)
        fact.error = err
        if path is not None and not err:
            fact.written, fact.value, fact.bound = fact.value, value, str(spec.get("from"))
    return list(out.values())


def lookup(facts, name):
    """The fact named `name`: its key exactly, else one whose key or about words contain it."""
    n = name.lower().replace(" ", "_")
    exact = [f for f in facts if f.key.lower() == n]
    if exact:
        return exact
    words = name.lower().replace("_", " ")
    return [f for f in facts if n in f.key.lower() or any(words in a.lower() for a in f.about)]


def describe(project, f):
    age = freshness.days_since(f.verified)
    src = ("bound to %s" % f.bound) if f.bound else (("source: %s" % f.source) if f.source else "no source")
    stale = " · the table says %s: update it" % f.written if f.bound and f.written and f.written != f.value else ""
    return "%s = %s — %s%s · %s:%d%s" % (f.key, f.value or "(none)", src, " · v%dd" % age if age is not None else "",
                                       project.rel(page_path(project)), f.line, stale + (" · " + f.error if f.error else ""))


def substitute(project, text, facts=None):
    """`{{fact:key}}` → the current value (unknown keys stay as written)."""
    if "{{" not in text:
        return text
    table = {f.key: f.value for f in (facts if facts is not None else load(project))}
    parts = CODE.split(text)                 # `{{fact:x}}` in a code span shows the syntax: left as written
    return "".join(p if i % 2 else TOKEN.sub(lambda m: table.get(m.group(1), m.group(0)), p) for i, p in enumerate(parts))


def live_tokens(text):
    """Fact keys used outside code spans."""
    return {m.group(1) for i, p in enumerate(CODE.split(text)) if not i % 2 for m in TOKEN.finditer(p)}


def _phrase(name):
    """A subject that also matches across punctuation: 'chat bot port' ~ 'Chat bot: port'."""
    return r"[\W_]{1,3}".join(re.escape(w) for w in re.split(r"[\W_]+", name) if w)


def shape(value):
    """A regex for values of the same form ('2.3.1' → '\\d+\\.\\d+\\.\\d+'), or None if it has no digit."""
    if not re.search(r"\d", value or ""):
        return None
    return re.sub(r"\d+", lambda _: r"\d+", re.escape(value))


def conflicts(project, facts, files):
    """(path, line, fact, stated value) for lines that name a fact's subject and state another value of the same
    form, outside history sections and dated or past-tense lines."""
    checks = []
    for f in facts:
        form = shape(f.value)
        if form:
            names = [f.key.replace("_", " ")] + f.about
            subject = re.compile(r"(?i)\b(%s)\b" % "|".join(_phrase(n) for n in names if _phrase(n)))
            checks.append((f, subject, re.compile(r"(?<![\d.])(%s)(?![\w.]*\d)" % form)))
    out = []
    for path in files if checks else []:
        text = read_text(path)
        meta, body, fm = markdown.frontmatter(text)
        if str(meta.get("status") or "").lower() in ("superseded", "rejected"):
            continue                                       # a retired page is history
        in_history = False
        for i, ln in enumerate(split_lines(body)):
            if ln.lstrip().startswith("#"):
                in_history = bool(HISTORY.search(ln))
                continue
            if in_history or PAST.search(ln) or TOKEN.search(ln):
                continue
            for f, subject, value in checks:
                for m in subject.finditer(ln):
                    v = value.search(ln, m.end())        # to the end of the line: lookarounds see it all
                    if v and v.start() <= m.end() + NEAR and v.group(1) != f.value:
                        out.append((path, i + 1 + fm, f, v.group(1)))
                        break
    return out


def checked_files(project):
    """Wiki pages that state facts (not the registry, not dated records) plus `memory` doc trees."""
    reg = page_path(project)
    files = [p for p in project.wiki_pages() if p != reg
             and not set(RECORDS) & set(p.relative_to(project.wiki).parts)]
    from memcrumbs.util import walk_stat
    for spec in project.cfg.get("docs", []):
        if spec.get("kind") == "memory":
            files += [p for p, _, _ in walk_stat(project.path(spec["root"]), spec.get("include", ["**/*.md"]),
                                                 spec.get("exclude", []), blocked=project.blocked)]
    return files


def lint(project):
    """`check` findings: conflicting current values (W), and bindings that disagree with the table or fail (W)."""
    facts = load(project)
    known, out, reg = {f.key for f in facts}, [], project.rel(page_path(project))
    for p in project.wiki_pages():
        if p == page_path(project):
            continue
        for key in sorted(live_tokens(markdown.frontmatter(read_text(p))[1]) - known):
            out.append(("W", project.rel(p), "unknown fact {{fact:%s}}: add it to %s" % (key, reg)))
    if not facts:
        return out
    for f in facts:
        if f.error:
            out.append(("W", reg, "fact %s: %s" % (f.key, f.error)))
        elif f.bound and f.written and f.written != f.value:
            out.append(("W", reg, "fact %s: the table says %s, %s says %s — update the table (or drop the value)"
                        % (f.key, f.written, f.bound, f.value)))
    for path, line, f, said in conflicts(project, facts, checked_files(project)):
        out.append(("W", "%s:%d" % (project.rel(path), line), "states %s = %s, the facts registry says %s: write "
                    "{{fact:%s}} or memcrumbs fact %s" % (f.key, said, f.value, f.key, f.key)))
    return out


def docs(project, path):
    """`fact` docs for the index: one per key, at its table line, so `find` can answer "what is the current X"."""
    from memcrumbs.sources import Doc, split_ident
    from memcrumbs.util import posix
    red, out = project.redact, []
    for f in load(project):
        title = "%s · %s" % (f.key, " · ".join(f.about)) if f.about else f.key
        body = "%s = %s%s" % (f.key, f.value, (" (" + f.source + ")") if f.source else "")
        out.append(Doc("fact", posix(path), f.line or 1, red(title), "", red(body),
                       red(" ".join([split_ident(f.key)] + f.about)), f.verified))
    return out


def command(out, project, name=None):
    facts = load(project)
    out.list_key = "facts"
    if not facts:
        out("no facts registered — add a table `| key | value | about | source | verified |` to %s"
            % project.rel(page_path(project)))
        return 1
    hits = lookup(facts, name) if name else facts
    out.set(facts=[dict(key=f.key, value=f.value, about=f.about, source=f.source or f.bound, verified=f.verified,
                        line=f.line, bound=bool(f.bound), table_value=f.written or None, error=f.error or None)
                   for f in hits])
    if not hits:
        out("no fact %r (keys: %s)" % (name, ", ".join(sorted(f.key for f in facts))))
        return 1
    for f in hits:
        out(describe(project, f))
    return 0
