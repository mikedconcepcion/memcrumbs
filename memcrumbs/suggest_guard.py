"""Gotcha → guard: a rules or gotchas line that forbids a command becomes a permission rule, so
the agent is asked (or stopped) instead of reading a warning it may skip.

- **The command comes from the clause that forbids** ("never …", "don't …"); a code span in a clause that recommends
  ("use …", "prefer …") is never guarded.
- **The rule keeps every word of the forbidden form**: `docker *system *prune *-a`, never a cut `docker
  *system` that would also catch `docker system df`. Each word gets a `*` before it, so other words may come in
  between; a PowerShell option keeps its value next to it (`-Encoding UTF8`). Each rule comes as a pair, `… VALUE`
  for a call that ends there and `… VALUE *` for one that goes on: a trailing ` *` covers the bare end only when it
  is a rule's sole wildcard, and `VALUE*` would match `VALUENoBOM`. A cmdlet gets no `Bash(…)` twin.
- **`ask` by default**: a too-wide `ask` costs one prompt, a too-wide `deny` blocks work, and the host calls
  argument patterns fragile. `suggest apply ID --deny` makes it a refusal, on the owner's choice, and only for a
  line that is neither conditional nor scoped.
- **Conditional or scoped lines stay `ask`**: "without", "before", "unless", "first", "only after", "except"; a
  line about certain files ("on config files", "never write JSON files with …", `*.json`, `.ps1`) or hosts ("on
  the build host", "in production"), which a command rule cannot see.
- **What gets past is said**: short or split flags (`-f`, `-r -f`), other orders, aliases, scripts and nested
  shells.
- **Evidence is counted with the rule's own matcher** (with `[suggest] transcripts = true`): how often the
  forbidden form ran since the line's date, how many of those the rule would have caught, for a scoped line how
  many of those named the files the line is about, and how many ran inside a nested shell string that no rule can
  see (for those: a content lint, or the opt-in hook).
- Removing the line offers to take the rule out (`unguard`); that loosens a guard, so only a human applies it."""
import json
import re

from memcrumbs import claude_settings as cs, markdown, transcripts
from memcrumbs.jsonedit import JsonEditError, check_object
from memcrumbs.suggest import Suggestion, load_state
from memcrumbs.util import read_doc, read_text, split_lines

PAGES = ("gotchas.md", "rules.md")
NEG = re.compile(r"(?i)\b(never|don'?t|do not|must not|mustn'?t|avoid|forbidden)\b")
CONDITIONAL = re.compile(r"(?i)\b(without|before|unless|first|only after|only when|only if|except|until)\b")
FILE_NOUN = r"(?:config(?:uration)?s?|settings|json|yaml|yml|toml|ini|xml|csv|logs?|scripts?|files?|folders?|" \
            r"director(?:y|ies)|manifests?|lockfiles?)"
SCOPE_RX = (re.compile(r"(?i)\b(?:on|to|for|in|into|under)\s+(?:the\s+)?(?:\S+\s+)?" + FILE_NOUN + r"\b"),
            re.compile(r"[\w./-]*\*[\w.*/-]*[/.][\w.*/-]*|[\w.-]+/\*+"),        # globs: *.json, config/*, **/*.yml
            re.compile(r"(?<![\w./-])\.[A-Za-z][\w]{0,4}\b"))                       # extensions: .json, .ps1
WRITE_WITH = re.compile(r"(?i)\b(?:writ(?:e|es|ing)|edit(?:s|ing)?|sav(?:e|es|ing)|creat(?:e|es|ing)|modif(?:y|ies|ying)|"
                        r"updat(?:e|es|ing)|touch(?:es|ing)?|overwrit(?:e|es|ing))\s+((?:[\w.*/-]+\s+){1,3}?)"
                        r"(?:with|using|via|through|by)\b")
NOUN_FILES = re.compile(r"(?i)\b([\w.-]+)\s+(?:files?|configs?|scripts?)\b")
GENERIC = {"all", "any", "the", "these", "those", "some", "other", "your", "my", "our", "its", "their", "new",
           "existing", "many", "multiple", "several", "no", "every", "each", "such", "a", "an", "it", "them",
           "anything", "everything", "files", "file", "things", "stuff", "text", "output", "to", "into"}
PATHLIKE = re.compile(r"[/\\*~]|\.[A-Za-z]\w{0,4}$")
HOST = re.compile(r"(?i)\b(?:on|in|against|to)\s+(?:the\s+|a\s+|any\s+)?(?:[\w-]+\s+)?(?:servers?|hosts?|machines?|boxes|box|"
                  r"vms?|clusters?|nodes?|prod|production|staging|live|remote)\b")
PLACEHOLDER = re.compile(r"^(?:<[^>]*>|\{[^}]*\}|\$\w+|\.\.\.|…|\[[^\]]*\])$")
LONG = {"-f": "--force", "-a": "--all", "-r": "--recursive", "-R": "--recursive", "-y": "--yes", "-q": "--quiet",
        "-v": "--verbose", "-n": "--dry-run", "-d": "--delete", "-D": "--delete --force"}
CLAUSES = re.compile(r";|\s[—–]\s|\s-\s|(?<=[a-z0-9`)])\.\s|,\s+(?=(?:but|and|or|never|don'?t|do not|use|prefer)\b)", re.I)
SPAN = re.compile(r"`([^`\n]+)`")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
VERB_NOUN = re.compile(r"^[A-Z][a-z]+-[A-Z]\w+$")                     # PowerShell: Remove-Item, Set-Content
SHELL_CMDS = {"rm", "del", "rmdir", "rd", "erase", "mv", "cp", "dd", "chmod", "chown", "kill", "pkill", "taskkill",
              "sc", "sc.exe", "schtasks", "reg", "robocopy", "xcopy", "format", "shutdown", "git", "npm", "pip",
              "docker", "kubectl", "systemctl", "service", "psql", "mysql", "sqlite3", "truncate", "drop", "curl",
              "wget", "ssh", "scp", "sed", "terraform", "helm"}
SUBCOMMANDS = {"git", "npm", "pip", "docker", "kubectl", "systemctl", "service", "terraform", "helm", "sc", "sc.exe",
               "schtasks", "reg"}


def prefix(span):
    """The command a span names: its name, a subcommand for multi-command tools, and its leading options with
    their values ('rm -rf', 'git push --force', 'Set-Content -Encoding UTF8'). None if it is not a command."""
    words = span.strip().split()
    if not words:
        return None
    name = words[0]
    if not (VERB_NOUN.match(name) or name.lower() in SHELL_CMDS):
        return None
    out, rest = [name], words[1:]
    if name.lower() in SUBCOMMANDS and rest and re.match(r"^[a-z][\w-]*$", rest[0]):
        out.append(rest.pop(0))
    while rest and re.match(r"^--?[A-Za-z][\w-]*$", rest[0]):
        out.append(rest.pop(0))
        if VERB_NOUN.match(name) and rest and re.match(r"^[\w.-]+$", rest[0]) and not rest[0].startswith("-"):
            out.append(rest.pop(0))                       # a PowerShell option's value: -Encoding UTF8
    return " ".join(out)


def form(span):
    """Every word of the forbidden command in a code span: 'docker system prune -a', 'chmod -R 777'. Up to the
    first shell separator; placeholders (`<dir>`, `$X`, `...`) dropped. None if the span does not name a command."""
    words = []
    for w in span.strip().split():
        if w in ("|", "||", "&&", ";", ">", ">>", "<", "2>&1") or w.endswith(";"):
            break
        if not PLACEHOLDER.match(w):
            words.append(w)
    return " ".join(words) if words and prefix(words[0]) else None


def groups(pre):
    """The parts after the command, each matched on its own: words in order, and for a PowerShell cmdlet each option
    with its value ('-Encoding UTF8')."""
    out, ps = [], bool(VERB_NOUN.match(pre.split()[0]))
    for w in pre.split()[1:]:
        if ps and out and not w.startswith("-") and out[-1].startswith("-") and " " not in out[-1]:
            out[-1] += " " + w                            # a PowerShell option's value
        else:
            out.append(w)
    return out


def patterns(pre):
    """Rule bodies that end at the forbidden form: `X *-opt VALUE` when the call ends there and `X *-opt
    VALUE *` when more follows. One pattern cannot do both: a trailing ` *` also covers the bare end only when it
    is the rule's only wildcard (the host's rule), and `VALUE*` would match `VALUENoBOM`."""
    head, parts = pre.split()[0], groups(pre)
    if not parts:
        return ["%s *" % head]                            # its only wildcard: the bare command too
    rest = "".join(" *" + p for p in parts[1:])
    if parts[0].startswith("-"):
        bases = [head + " *" + parts[0] + rest]
    else:                                                 # a subcommand: right after the command, or after its
        bases = [head + " " + parts[0] + rest,            # options (`git -C repo push`), never glued to a longer
                 head + " -* " + parts[0] + rest]         # word (`npm uninstall`, `git stash push`)
    return [p for b in bases for p in (b, b + " *")]


def legacy_patterns(pre):
    """What earlier builds wrote, so `unguard` and an upgrade can still find those rules: `X *opts*` (cut forms)
    and `X *word *word` (a `*` glued to each word)."""
    head, *opts = pre.split()
    if not opts:
        return ["%s *" % head]
    glued = head + "".join(" *" + p for p in groups(pre))
    return ["%s *%s*" % (head, " ".join(opts)), glued, glued + " *"]


def shells(pre):
    """A PowerShell cmdlet only ever runs in the PowerShell tool; other commands in both."""
    return ["PowerShell"] if VERB_NOUN.match(pre.split()[0]) else list(cs.SHELLS)


def rules(pre, legacy=False):
    return ["%s(%s)" % (sh, p) for sh in shells(pre) for p in (legacy_patterns(pre) if legacy else patterns(pre))]


def host_rx(pat):
    """The host's matching for one rule body: `*` is any run of characters; a trailing ` *` that is the only
    wildcard also matches the bare command (`ls *` matches `ls`, not `lsof`)."""
    if pat.endswith(" *") and pat.count("*") == 1:
        return re.compile("^" + re.escape(pat[:-2]) + "(?: .*)?$", re.I)
    return re.compile("^" + ".*".join(re.escape(x) for x in pat.split("*")) + "$", re.I)


def matches(pre, part):
    """Does one of the rules match one part of a call, as the host matches it (case-insensitive: transcript shapes
    are lower case)?"""
    text = " ".join(part.split())
    return any(host_rx(p).match(text) for p in patterns(pre))


def forbidden_form(pre, part):
    """Does the call use the forbidden form at all: the command with every option and value as whole words, in any
    order? The safe form (`UTF8NoBOM`) does not count."""
    words = [w.lower() for w in part.split()]
    return bool(words) and words[0] == pre.split()[0].lower() and all(w.lower() in words for w in pre.split()[1:])


def scope(clause, span=""):
    """What the line limits the ban to, which a command rule cannot see: certain files, paths or hosts. None if the
    ban is about the command itself."""
    text = SPAN.sub(" ", clause)                          # a code span is the command, not its scope
    for rx in SCOPE_RX + (HOST,):
        m = rx.search(text)
        if m:
            return m.group(0).strip()
    m = WRITE_WITH.search(text)
    if m and any(w.lower().strip(".,") not in GENERIC for w in m.group(1).split()):
        return m.group(1).strip()
    for m in NOUN_FILES.finditer(text):
        if m.group(1).lower() not in GENERIC:
            return m.group(0).strip()
    pre = prefix(span) or ""
    rest = span.split()[len(pre.split()):]
    left = [w for w in rest if PATHLIKE.search(w)]        # a file or path after the command: `rm -rf build/`
    return " ".join(left) if left else None


def variants(pre):
    """Spellings of the same command that the rules do not match: short or long twins of a flag, split or
    reordered short flags."""
    out = []
    if VERB_NOUN.match(pre.split()[0]):                   # PowerShell takes any unique prefix of a parameter
        return ["%s … %s" % (pre.split()[0], w[:4]) for w in pre.split()[1:] if re.fullmatch(r"-[A-Za-z]{4,}", w)]
    for w in pre.split()[1:]:
        if re.fullmatch(r"-[A-Za-z]{2,4}", w):            # -rf: -r -f, -fr
            out += [" ".join("-" + c for c in w[1:]), "-" + w[:0:-1]]
        elif re.fullmatch(r"--[a-z][\w-]*", w):
            short = next((k for k, v in LONG.items() if v == w), None)
            if short:
                out.append(short)
        elif w in LONG:
            out.append(LONG[w])
    head = pre.split()[0]
    return ["%s … %s" % (head, v) for v in dict.fromkeys(out)]


def scope_terms(text):
    """Words a call would name if it touched the scope's files: extensions, path parts, non-generic nouns."""
    out = set(re.findall(r"\.[a-z]\w{0,4}\b", text.lower()))
    for w in re.findall(r"[\w-]+", text.lower()):
        if len(w) > 2 and w not in GENERIC and not re.fullmatch(FILE_NOUN, w) or w in ("json", "yaml", "yml",
                                                                                        "toml", "ini", "xml", "csv"):
            out.add(w)
        elif re.fullmatch(r"config(?:uration)?s?", w):
            out.add("config")
    return sorted(out)


def _clauses(line):
    return [c.strip() for c in CLAUSES.split(line) if c and c.strip()]


def forbidden(project):
    """[(page, line number, clause, form, date, strength)] for clauses that forbid a command. strength: `ask` for a
    conditional or scoped line (ask only), `deny` when the owner may choose a refusal."""
    out = []
    for fname in PAGES:
        p = project.wiki / fname
        if not p.exists():
            continue
        meta, body, fm = markdown.frontmatter(read_text(p))
        for i, ln in enumerate(split_lines(body)):
            if not NEG.search(ln):
                continue
            d = DATE.search(ln)
            for clause in _clauses(ln):
                m = NEG.search(clause)
                if not m:
                    continue                              # a clause that recommends: its commands are never denied
                for span in SPAN.findall(clause[m.start():]):      # only what follows "never" in this clause
                    pre = form(span)
                    if pre:
                        mode = "ask" if CONDITIONAL.search(clause) or scope(clause, span) else "deny"
                        out.append((fname, i + 1 + fm, clause, pre, d.group(0) if d else str(meta.get("verified") or ""),
                                    mode))
    return out


def settings_files(project):
    return [r / ".claude" / "settings.json" for r in project.repos if r.is_dir()]


def _listed(text, mode):
    try:
        perms = check_object(text).get("permissions")
    except JsonEditError:
        return None
    return set((perms or {}).get(mode) or []) if isinstance(perms, dict) else set()


def _take_out(text, mode, pre):
    """The settings text with this command's rules (this form, or the dev4–dev6 form) gone from one list."""
    for these in (", ".join(json.dumps(r) for r in rules(pre)), ", ".join(json.dumps(r) for r in rules(pre, legacy=True))):
        new = cs.take_out(text, ("permissions", mode), these)
        if new is not None:
            return new
    return cs.remove_items(text, ("permissions", mode), rules(pre) + rules(pre, legacy=True))   # reformatted


def _patch(project, pre, mode, remove=False):
    """Add the rules to the `mode` list, or (remove) take them out of both lists: an offer is `ask`, and the owner
    may have applied it as `deny`."""
    changes = []
    entries = ", ".join(json.dumps(r) for r in rules(pre))
    for sp in settings_files(project):
        text = read_doc(sp)[0] if sp.exists() else "{}\n"
        have = _listed(text, mode)
        if have is None:
            continue                                     # not plain JSON: never edit it
        if remove:
            new = text
            for m in ("deny", "ask"):
                new = _take_out(new, m, pre) or new
            if new != text:
                changes.append((sp, new))
        elif not set(rules(pre)) <= have:
            changes.append((sp, cs.insert(text, ("permissions", mode), entries)))
    return changes


def _evidence(project, pre, since, cheap_only, where=None):
    """Counts of the forbidden form (not the command with any option), what the rules would catch, and for a
    scoped line how many of those touched the files it names."""
    if cheap_only:
        return [], 0
    if not transcripts.enabled(project):
        return ["transcripts are off: `[suggest] transcripts = true` counts how often it still runs"], 0
    evs = transcripts.events(project)
    later = [e for e in evs if not since or e[0] >= since]
    ran = [e for e in later if e[2] == "cmd" and forbidden_form(pre, e[3])]
    caught = [e for e in ran if matches(pre, e[3])]
    words = [re.escape(w.lower()) for w in pre.split()]
    hidden = [e for e in later if e[2] == "nested"
              and all(re.search(r"(?<![\w-])%s(?![\w-])" % w, e[3]) for w in words)]
    lines = ["`%s` ran %d time(s) on %d day(s)%s; these rules would have asked on %d" % (
        pre, len(ran), len({e[0] for e in ran}), " since " + since if since else "", len(caught))]
    if where:
        terms = scope_terms(where)
        named = [e for e in caught if any(t in e[3] for t in terms)]
        lines.append("the line is about %s: %d of those named %s (a rule cannot see which file a command writes)"
                     % (where, len(named), "/".join(terms) or where))
    if hidden:
        lines.append("at least %d more call(s) ran it inside a nested shell string (scripts written and run remotely "
                     "are not counted), which no permission rule can see: a check lint or the opt-in hook covers "
                     "those" % len(hidden))
    return lines, len(caught)


def _older(project, fname, pre):
    """The id of an applied guard from this line in an earlier, cut or glued form, if one is still in place."""
    words = pre.lower().split()
    for sid, rec in load_state(project)["applied"].items():
        parts = str(rec.get("key", "")).split("|", 2) if isinstance(rec, dict) and rec.get("kind") == "guard" else []
        if len(parts) == 3 and parts[0] == fname and words[:len(parts[2].split())] == parts[2].lower().split():
            if set(rules(parts[2], legacy=True)) & _present(project):
                return sid
    return None


def _present(project):
    have = set()
    for sp in settings_files(project):
        if sp.exists():
            text = read_doc(sp)[0]
            for mode in ("deny", "ask"):
                have |= _listed(text, mode) or set()
    return have


def _tailor(project, pre, strength):
    def tailor(s, args):
        if not getattr(args, "deny", False):
            return s
        if strength != "deny":
            raise SystemExit("memcrumbs: the line is conditional or limited to certain files or hosts, so a refusal "
                             "would also block what it allows; apply it without --deny (the agent asks)")
        from dataclasses import replace
        changes = _patch(project, pre, "deny")
        if not changes:
            raise SystemExit("memcrumbs: the deny rules for `%s` are already in place" % pre)
        return replace(s, changes=changes, action=s.action.replace("ask before", "deny", 1))
    return tailor


def _guards(project, cheap_only=False):
    out, seen = [], set()
    for fname, line, clause, pre, since, strength in forbidden(project):
        if pre.lower() in seen:
            continue
        seen.add(pre.lower())
        changes = _patch(project, pre, "ask")
        if not changes:
            continue                                     # already in place, or no repo settings to edit
        span = next((s for s in SPAN.findall(clause) if form(s) == pre), "")
        where = scope(clause, span)
        ev, caught = _evidence(project, pre, since, cheap_only, where)
        past = variants(pre)
        older = _older(project, fname, pre)
        if older:
            ev.append("an older, wider rule from this line is still applied (%s): memcrumbs suggest undo %s"
                      % (older, older))
        ev.append("gets past: %sother orders, aliases, scripts and nested shells"
                  % ("".join("`%s`, " % v for v in past)))
        why = (("the line is about %s, which a command rule cannot see" % where) if where else
               "the line is conditional" if strength == "ask" else
               "--deny makes it a refusal, if the owner chooses")
        out.append(Suggestion(
            "guard", "%s|ask|%s" % (fname, pre), "%s:%d forbids `%s`" % (fname, line, pre),
            "ask before %s (the agent asks the owner first; %s; suggest undo takes it out)"
            % (", ".join("`%s`" % r for r in rules(pre)), why),
            ["the clause: %s" % project.redact(clause)[:160]] + ev, risk="writes-outside-wiki", changes=changes,
            score=1 + caught, tailor=_tailor(project, pre, strength)))
    return out


def _unguards(project, cheap_only=False):
    """A guard whose line is gone (or superseded): offer to take its rule out. A human applies it."""
    live = [(f, pre.lower().split()) for f, _, _, pre, _, _ in forbidden(project)]
    out = []
    for sid, rec in load_state(project)["applied"].items():
        if not isinstance(rec, dict) or rec.get("kind") != "guard":
            continue
        parts = str(rec.get("key", "")).split("|", 2)
        if len(parts) != 3:
            continue
        fname, mode, pre = parts
        words = pre.lower().split()                      # a dev5/dev6 key holds the cut form: a prefix of today's
        if any(f == fname and w[:len(words)] == words for f, w in live):
            continue
        changes = _patch(project, pre, mode, remove=True)
        if changes:
            out.append(Suggestion("unguard", rec["key"], "the line that forbade `%s` is gone from %s" % (pre, fname),
                                  "remove the rules for `%s`" % pre, ["applied as %s on %s" % (sid, rec.get("at"))],
                                  risk="writes-outside-wiki", changes=changes, score=2, human=True))
    return out


SUGGESTERS = {"guard": _guards, "unguard": _unguards}
