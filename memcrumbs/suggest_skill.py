"""Skill suggester: repeated work becomes a private skill or a rule, on the owner's yes.

Sources (deterministic, no model):
- session transcripts (opt-in `[suggest] transcripts = true`): command sequences of 2–4 steps that repeat across
  sessions (wrappers and everyday commands skipped), and status queries run over and over; ranked by
  occurrences × days, with a floor;
- read counts: a runbook agents keep re-reading;
- the wiki: one imperative rule restated on two or more pages and missing from rules.md.

memcrumbs scaffolds; it never writes the steps. `apply` writes `.claude/skills/NAME/SKILL.md` in the repo with a
name, pointers to wiki pages and the counts; the session's agent writes the steps after the owner's yes, from
what `suggest show` lists. No command text from transcripts goes into a file. A live or destructive procedure
defaults to `disable-model-invocation: true` (only the owner starts it, and its description costs nothing).
Apply-time options: `--name NAME`, `--owner-only`, `--agent-may-use`. Unused skills: the host's `/skill-doctor`."""
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

from memcrumbs import markdown, transcripts
from memcrumbs.suggest import Suggestion
from memcrumbs.util import read_text, shq

EVERYDAY = {"ls", "dir", "cd", "cat", "type", "echo", "pwd", "git", "grep", "rg", "find", "head", "tail", "wc",
            "python", "python3", "py", "node", "npm", "npx", "pip", "uv", "memcrumbs", "get-content", "get-childitem",
            "select-string", "test-path", "set-location", "sort", "uniq", "which", "where", "mkdir", "touch", "code",
            "claude", "sed", "awk", "less", "more", "clear", "sleep", "start-sleep", "get-location", "write-host",
            "write-output", "out-file", "get-item", "bash", "sh", "pwsh", "powershell", "cmd", "true", "false", "exit",
            "measure-object", "select-object", "where-object", "foreach-object", "format-table", "diff", "jq"}
LIVE = re.compile(r"(?i)ssh|scp|rsync|plink|pscp|invoke-command|enter-pssession|deploy|restart|stop|kill|remove|"
                  r"delete|drop|reboot|publish|release|push")
LIVE_WORDS = re.compile(r"(?i)\b(live|prod|production)\b")
CODE_SPANS = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]+`", re.S)
STATUS_WORD = re.compile(r"(?i)status|health|ping|uptime|ready|alive")
READ_ONLY = re.compile(r"(?i)^(get-|test-|show\b|list\b|ps\b|uptime|ping|curl|wget|invoke-webrequest|invoke-restmethod|"
                       r"systemctl status|sc(\.exe)? query|docker ps|kubectl get|service \S+ status)")
COPY = {"scp", "rsync", "cp", "mv", "copy-item", "move-item", "robocopy", "xcopy", "pscp"}
MIN_SEQ, MIN_RUNS, MIN_SESSIONS, MIN_READS = 10, 20, 2, 8
TOP = 3                                    # skill offers listed; --kind skill --full lists the rest
RULE = re.compile(r"(?i)^\s*[-*]\s+.*\b(always|never|must|do not|don't|only)\b")
# shell syntax and plumbing are not commands worth a skill
KEYWORDS = {"for", "do", "done", "if", "then", "else", "elif", "fi", "while", "until", "case", "esac", "in", "function",
            "return", "break", "continue", "exit", "foreach", "switch", "try", "catch", "finally", "trap", "[", "[[",
            "test", "!", "{", "}", "(", ")", "time", "sudo", "nohup", "exec", "eval", "local", "declare", "export",
            "set", "unset", "source", ".", "read", "wait", "shift", "true", "false", ":", "param", "begin", "process",
            "end", "else{", "}else"}
SINKS = {"out-null", "sort-object", "out-string", "select-object", "where-object", "foreach-object", "format-table",
         "format-list", "format-wide", "measure-object", "tee-object", "out-file", "write-host", "write-output",
         "cut", "sort", "uniq", "head", "tail", "wc", "grep", "egrep", "awk", "sed", "tee", "xargs", "jq", "tr",
         "column", "less", "more", "printf", "select-string", "convertto-json", "convertfrom-json", "group-object",
         "get-member", "%", "?", "where", "select", "foreach"}
LEADING = {"do", "then", "else", "&", "!", "{", "(", "exec"}
REMOTE = {"ssh", "plink"}
# wrappers run another command: the step is the command they wrap. Value: positional words to skip.
WRAPPERS = {"timeout": 1, "nohup": 0, "env": 0, "time": 0, "sudo": 0, "nice": 0, "stdbuf": 0, "command": 0,
            "builtin": 0, "doas": 0, "caffeinate": 0, "ionice": 0, "chronic": 0, "unbuffer": 0}
TAKES_VALUE = {"-n", "-s", "-k", "-u", "-g", "-c", "-p", "-C", "--signal", "--kill-after", "--user", "--group",
               "--chdir", "-o", "-e", "-i0"}


def unwrap(words):
    """Drop leading wrappers (`timeout 30`, `env A=1`, `sudo -u x`, `nohup`) with their options and values."""
    while words and words[0].lower().removesuffix(".exe") in WRAPPERS:
        skip = WRAPPERS[words[0].lower().removesuffix(".exe")]
        words = words[1:]
        while words and (words[0].startswith("-") or "=" in words[0]):
            opt = words.pop(0)
            if opt in TAKES_VALUE and words:
                words.pop(0)
        words = words[skip:]
    return words


def head(shape):
    """The command a shell part runs: its name (a script's file name), with a subcommand for multi-command tools
    and, for a remote run, the remote command. '' for shell syntax, assignments, expressions and pipeline sinks."""
    from memcrumbs.suggest_guard import SUBCOMMANDS
    words = shape.split()
    while words and (words[0].lower() in LEADING or words[0].lower().removesuffix(".exe") in WRAPPERS):
        words = unwrap(words[1:] if words[0].lower() in LEADING else words)
    if not words:
        return ""
    w = words[0].strip("&'\"")
    if not w or w.lower() in KEYWORDS or "=" in w or w[0] in "$([-@{" or (w[0] == "." and not w[1:2] in ("/", "\\")):
        return ""
    first = re.split(r"[\\/]", w)[-1].lower().removesuffix(".exe")      # python.exe and python are one head
    if not re.match(r"^[a-z][\w.-]+$", first) or first in SINKS or first in KEYWORDS:
        return ""                                  # a lone letter (`n` from an escaped newline) is no command
    if first in SUBCOMMANDS and len(words) > 1 and re.match(r"^[a-z][\w-]*$", words[1]):
        return first + " " + words[1]
    if first in REMOTE:                            # ssh host 'cmd …': the remote command names the step
        rest, skip = [], False
        for x in words[1:]:
            if skip:
                skip = False
            elif x.startswith("-"):
                skip = x in ("-i", "-p", "-l", "-o", "-F", "-J", "-P", "-pw")    # options that take a value
            else:
                rest.append(x)
        inner = unwrap(rest[1:])
        remote = re.split(r"[\\/]", inner[0].strip("'\"")).pop().lower().removesuffix(".exe") if inner else ""
        return first + (" " + remote if re.match(r"^[a-z][\w.-]*$", remote or "-") else "")
    return first


def sequences(events):
    """{(heads…): (runs, sessions, days, forms, steps)} for repeated 2–4 step sequences of non-everyday commands, one
    per cycle. The cycle is represented by its best-evidenced form (runs × days), not its longest; a form
    folds into it when its steps are all steps of the cycle, when it contains the cycle's most frequent step (a
    longer variant or a fragment), or when it is a rotation. `forms` counts what folded in; `runs` stays the
    representative's own count, since the runs of overlapping forms are the same runs counted again."""
    per = {}
    for day, sess, kind, val in events:
        if kind == "cmd":
            h = head(val)
            if h and h.split()[0] not in EVERYDAY:
                seq = per.setdefault(sess, [])
                if not seq or seq[-1][1] != h:
                    seq.append((day, h))
    runs, where = Counter(), {}
    for sess, seq in per.items():
        for n in (2, 3, 4):
            for i in range(len(seq) - n + 1):
                gram = tuple(h for _, h in seq[i:i + n])
                if len(set(gram)) < 2:
                    continue
                runs[gram] += 1
                where.setdefault(gram, set()).add((sess, seq[i][0]))
    keep = {g: (n, len({s for s, _ in where[g]}), len({d for _, d in where[g]})) for g, n in runs.items()
            if n >= MIN_SEQ and len({s for s, _ in where[g]}) >= MIN_SESSIONS}
    count = Counter(h for seq in per.values() for _, h in seq)
    families = []                                  # best evidence first; variants and fragments fold in
    for g in sorted(keep, key=lambda g: (-keep[g][0] * keep[g][2], -len(set(g)), g)):
        fam = next((f for f in families if set(g) <= f["steps"] or f["top"] in g or _inside(f["rep"], g + g)), None)
        if fam is None:
            families.append(dict(rep=g, steps=set(g), forms=1, top=max(g, key=lambda h: (count[h], h))))
        else:
            fam["forms"] += 1
            fam["steps"] |= set(g)
    return {f["rep"]: keep[f["rep"]] + (f["forms"], tuple(sorted(f["steps"]))) for f in families}


def _inside(short, long):
    return any(long[i:i + len(short)] == short for i in range(len(long) - len(short) + 1))


def statuses(events):
    """{head: (runs, days)} for read-only status queries run at least MIN_RUNS times on MIN_SESSIONS days."""
    runs, days = Counter(), {}
    for day, _, kind, val in events:
        if kind != "cmd":
            continue
        h = head(val)
        if not h or h.split()[0] in EVERYDAY or h.split()[0] in COPY or not READ_ONLY.match(val):
            continue
        if STATUS_WORD.search(val) or h in ("get-service", "get-process", "get-scheduledtask", "get-scheduledtaskinfo"):
            runs[h] += 1
            days.setdefault(h, set()).add(day)
    return {h: (n, len(days[h])) for h, n in runs.items() if n >= MIN_RUNS and len(days[h]) >= MIN_SESSIONS}


def _short(key):
    import hashlib
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "procedure"


def skill_path(project, name):
    repo = project.repos[0] if project.repos else project.dir
    return Path(repo) / ".claude" / "skills" / name / "SKILL.md"


def scaffold(name, title, evidence, pages, owner_only):
    lines = ["---", "name: %s" % name,
             "description: %s (suggested by memcrumbs; the agent writes the steps and this description after the "
             "owner's yes)" % title]
    if owner_only:
        lines.append("disable-model-invocation: true")
    lines += ["---", "# %s" % title, "", "Suggested by memcrumbs: %s." % evidence, "", "## When to use", "",
              "(the agent writes this after the owner's yes)", "", "## Steps", "",
              "(the agent writes the steps; facts stay in the wiki and are pointed to, not copied)"]
    if pages:
        lines += ["", "## Wiki", ""] + ["- `memcrumbs page %s`" % shq(p) for p in pages]
    return "\n".join(lines) + "\n"


def _skill(project, kind, key, why, action, evidence_line, name, title, pages, live, score, cheap=False):
    def make(n, owner_only, t=title):
        return [(skill_path(project, n), scaffold(n, t, evidence_line, pages, owner_only))]

    def tailor(s, args):
        n = slug(getattr(args, "name", None) or name)
        if n != name and skill_path(project, n).exists():
            raise SystemExit("memcrumbs: the skill %s already exists; pick another --name (nothing written)" % n)
        owner = (live or getattr(args, "owner_only", False)) and not getattr(args, "agent_may_use", False)
        return replace(s, changes=make(n, owner, n.replace("-", " ").capitalize() if n != name else title))
    if skill_path(project, name).exists():
        return None
    return Suggestion(kind, key, why, action + (" (owner-only: it touches live systems)" if live else ""),
                      [evidence_line], risk="writes-outside-wiki", changes=make(name, live),
                      agent="write the skill's description, When to use and Steps from the evidence and the wiki "
                            "pages listed; keep facts in the wiki", score=score, cheap=cheap, tailor=tailor)


def live_runbook(meta, body, stem):
    """A runbook touches live systems when it says `destructive:`, its name holds a live verb, its summary, tags or
    aliases name live or production, or a step in its code runs remotely or deploys: its skill is then owner-only."""
    if markdown.truthy(meta.get("destructive")) or LIVE.search(stem):
        return True
    said = " ".join(" ".join(map(str, v)) if isinstance(v, list) else str(v)
                    for v in (meta.get(k) for k in ("summary", "tags", "aliases")) if v)
    return bool(LIVE_WORDS.search(said)) or any(LIVE.search(span) for span in CODE_SPANS.findall(body))


def _runbook(project, words):
    from memcrumbs.store import Store
    from memcrumbs import synonyms
    if not project.index_path.exists():
        return None
    try:
        store = Store(project.index_path, synonyms.for_project(project))
    except Exception:
        return None
    try:
        hits = store.search(words, kinds=["runbook"], limit=1)
    finally:
        store.close()
    return Path(hits[0]["path"]).stem if hits else None


def _skills(project, cheap_only=False):
    out = []
    if not cheap_only:
        evs = transcripts.events(project)
        used = set()
        for gram, (runs, sess, days, forms, steps) in sorted(sequences(evs).items(),
                                                             key=lambda kv: -kv[1][0] * kv[1][2]):
            book = _runbook(project, " ".join(steps))
            # named after the runbook it points to (a wiki name); otherwise neutral: no transcript text in a file
            name = slug(book) if book and slug(book) not in used else "procedure-" + _short("seq:" + " > ".join(gram))
            used.add(name)
            title = ("Run the %s runbook" % book.replace("-", " ")) if book else "A repeated project procedure"
            more = " (and %d longer or partial form(s) of it; steps seen: %s)" % (forms - 1, ", ".join(steps)) \
                if forms > 1 else ""
            s = _skill(project, "skill", "seq:" + " > ".join(gram), "the sequence %s ran %d times in %d sessions on %d "
                       "days%s" % (" → ".join(gram), runs, sess, days, more), "scaffold the skill %s" % name,
                       "%d runs in %d sessions on %d days, in %d form(s)" % (runs, sess, days, forms), name, title,
                       [book] if book else [], bool(LIVE.search(" ".join(steps))), runs * days)
            if s:
                out.append(s)
        for h, (runs, days) in sorted(statuses(evs).items(), key=lambda kv: -kv[1][0] * kv[1][1]):
            name = "status-" + _short("status:" + h)
            s = _skill(project, "skill", "status:" + h, "a status query (%s) ran %d times on %d days" % (h, runs, days),
                       "scaffold a status skill %s (a script or skill beats repeating it; a schedule is up to you)"
                       % name, "%d runs on %d days" % (runs, days), name, "A repeated status check", [], False,
                       runs * days)
            if s:
                out.append(s)
    from memcrumbs import plan
    reads = plan.hits(project)
    for p in project.wiki_pages():
        n = reads.get(project.rel(p), 0)
        if n < MIN_READS or not (p.parent.name == "runbooks" or
                                 str(markdown.frontmatter(read_text(p))[0].get("kind") or "") == "runbook"):
            continue
        meta, body, _ = markdown.frontmatter(read_text(p))
        live = live_runbook(meta, body, p.stem)
        s = _skill(project, "skill", "runbook:" + p.stem, "the runbook %s was read %d times" % (project.rel(p), n),
                   "scaffold a skill that runs it", "the runbook was read %d times" % n, slug(p.stem),
                   str(meta.get("title") or p.stem), [p.stem], live, n, cheap=True)
        if s:
            out.append(s)
    return out


def _rules(project, cheap_only=False):
    """An imperative line restated on two or more pages (or the journal) and missing from rules.md."""
    rules_page = project.wiki / "rules.md"
    have = {_key(ln) for ln in read_text(rules_page).splitlines()} if rules_page.exists() else set()
    seen = {}
    for p in project.wiki_pages():
        if p == rules_page:
            continue
        for ln in markdown.frontmatter(read_text(p))[1].splitlines():
            if RULE.match(ln) and len(_key(ln)) > 20:
                seen.setdefault(_key(ln), {})[project.rel(p)] = ln.strip()
    out = []
    for key, where in sorted(seen.items()):
        if len(where) < 2 or key in have:
            continue
        line = next(iter(where.values()))
        new = _add_rule(read_text(rules_page) if rules_page.exists() else "# Rules\n", line)
        out.append(Suggestion("rule", key[:80], "a rule is restated on %d pages but is not in rules.md" % len(where),
                              "add it to rules.md ## Top (it reaches the header after the owner's review)",
                              ["on: " + ", ".join(sorted(where))], changes=[(rules_page, new)], score=len(where)))
    return out


def _key(line):
    return " ".join(re.sub(r"[^\w]+", " ", re.sub(r"\[\[[^\]]*\]\]", "", line.lower())).split())


def _add_rule(text, line):
    nl = "\r\n" if "\r\n" in text else "\n"
    m = re.search(r"(?m)^##\s+Top\s*$", text)
    if not m:
        return text.rstrip("\r\n") + nl + nl + "## Top" + nl + nl + line + nl
    end = text.find(nl, m.end())
    rest = text[end + len(nl):] if end >= 0 else ""
    lines = rest.split(nl)
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith(("-", "*"))):
        i += 1                                     # after the section's last bullet
    while i > 0 and not lines[i - 1].strip():
        i -= 1
    return text[:end + len(nl)] + nl.join(lines[:i] + [line] + lines[i:])


def add_rule(out, project, text):
    """`memcrumbs rule "<text>"`: a correction from the owner becomes a standing rule in rules.md ## Top. The agent
    offers it and runs it on a yes; the line reaches the header after the owner's review."""
    from memcrumbs import writeset
    from memcrumbs.util import read_doc
    p = project.wiki / "rules.md"
    text = " ".join(project.redact(text).split())
    line = text if text.startswith(("- ", "* ")) else "- " + text
    old, info = read_doc(p) if p.exists() else ("---\ntitle: Rules\nsummary: standing rules from the owner\n---\n# Rules\n",
                                                (b"", "utf-8"))
    if _key(line) in {_key(ln) for ln in old.splitlines()}:
        out("already in %s" % project.rel(p))
        return
    new = _add_rule(old, line)
    writeset.write_text(project, p, new, info)
    out.set(path=project.rel(p), line=line)
    out("added to %s ## Top; it reaches the session header after the owner's review (memcrumbs review)" % project.rel(p))
    from memcrumbs.util import split_lines
    body = split_lines(markdown.frontmatter(new)[1])
    span = markdown.section_span(body, "Top")
    seg = [ln.strip() for ln in body[span[0] + 1:span[1]] if ln.strip()] if span else []
    cap = int(project.cfg.get("status", {}).get("rules", 8))
    at = seg.index(line.strip()) + 1 if line.strip() in seg else 0
    if at > cap:                                       # past the cap it would only count in "… N more"
        out.set(position=at, header_cap=cap)
        out("note: it is line %d of ## Top and the header shows %d: move it up (or raise [status] rules) for it to "
            "show in every session" % (at, cap))


SUGGESTERS = {"skill": _skills, "rule": _rules}
