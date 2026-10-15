"""Opt-in, local reading of the host's session transcripts: `[suggest] transcripts =
true` in memcrumbs.toml. Only shapes are kept, redacted: the first words of each shell command with its day, the
files the agent read or edited, memcrumbs lookups, and where the user's messages fall (task boundaries, no
text), the names of the skills and slash commands used, and each reply's token counts. Nothing derived from
transcripts enters the header (beyond a count) or a shared report; the wiki gets skill names and counts only.

Claude Code keeps one folder per working directory under ~/.claude/projects/, named by the path with every
non-alphanumeric character turned into '-'; sessions started in a repo or below it are read. Each file is parsed
once per size and mtime (cache in the index folder)."""
import datetime as dt
import json
import re
from pathlib import Path

from memcrumbs import writeset
from memcrumbs.util import read_text

WINDOW_DAYS = 30
CACHE_VERSION = 6                 # bump when what is kept per call changes
SLASH = re.compile(r"<command-name>/?([\w.:-]+)</command-name>")
WORDS = 12                        # words kept per command part: enough to match a permission rule, no more
NESTED = re.compile(r"^(powershell|pwsh|powershell\.exe|pwsh\.exe|bash|sh|cmd|cmd\.exe|ssh|plink|invoke-command)\b.*['\"]", re.I)
SHELLS = ("Bash", "PowerShell")
EDITS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
WRAPPER = re.compile(r"^\s*(cd\s+\S+|set-location\s+\S+|\$\w+\s*=.*|echo\b.*|export\s+\S+|source\s+\S+)\s*$", re.I)
SPLIT = re.compile(r"&&|\|\||;|\||\n")
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1([^\n]*)\n.*?^[ \t]*\2[ \t]*$", re.S | re.M)
HERESTRING = re.compile(r"@(['\"])[ \t]*\r?\n.*?^\1@", re.S | re.M)
QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")
LOOKUP = re.compile(r"\bmemcrumbs\b(?:\s+-p\s+\S+)?\s+(find|page)\s+(.+)", re.I)


def enabled(project):
    return bool(project.cfg.get("suggest", {}).get("transcripts"))


def mangle(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(path).resolve()))


def _cwd_of(folder):
    """The working directory a session folder's transcripts were recorded in (from their first lines), or None."""
    for f in sorted(folder.glob("*.jsonl"))[:3]:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for i, ln in enumerate(fh):
                    if i > 50:
                        break
                    if '"cwd"' in ln:
                        try:
                            return json.loads(ln).get("cwd")
                        except ValueError:
                            continue
        except OSError:
            continue
    return None


def folders(project):
    """Session folders of the project's repos: the repo's own, and those of sessions started below it. A folder
    that only shares a name prefix (repo `app` and a sibling `app-legacy`) is read only if its transcripts were
    recorded inside the repo."""
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return []
    out = []
    for f in sorted(base.iterdir()):
        if not f.is_dir():
            continue
        for repo in project.repos:
            n = mangle(repo)
            if f.name == n:
                out.append(f)
                break
            if f.name.startswith(n + "-"):
                cwd = _cwd_of(f)
                try:
                    inside = bool(cwd) and Path(repo).resolve() in [Path(cwd).resolve()] + list(Path(cwd).resolve().parents)
                except OSError:
                    inside = False
                if inside:
                    out.append(f)
                    break
    return out


def mask(command):
    """The command with heredoc bodies and here-strings dropped, line continuations joined, and separators inside
    quotes blanked: only real separators split it, and no word of a quoted string or a heredoc body is taken
    for a command."""
    c = HEREDOC.sub(lambda m: "<<" + m.group(2) + m.group(3), command or "")
    c = HERESTRING.sub("@''@", c)
    c = re.sub(r"[\\`]\r?\n", " ", c).replace("\r", "")
    return QUOTED.sub(lambda m: re.sub(r"[|;&\n]", " ", m.group(0)), c)


def shapes(command, redact=lambda s: s, words=WORDS):
    """The first words of each part of a shell command (split at |, ;, &&, || and newlines, outside quotes and
    heredocs), wrappers (cd …, $x = …, echo …) skipped, lower case, redacted."""
    out = []
    for part in SPLIT.split(mask(command)):
        part = part.strip()
        if not part or WRAPPER.match(part):
            continue
        out.append(redact(" ".join(part.split()[:words])).lower())
    return out


def nested(command):
    """Does the call run another shell with a quoted command string (powershell -Command "…", ssh host "…")? A
    permission rule sees only the outer command, so what runs inside is invisible to it."""
    return any(NESTED.match(p.strip()) for p in SPLIT.split(command or ""))


def _said(ev, content):
    """A message from the user (text, not a tool result): it starts a new task."""
    return ev.get("type") == "user" and (isinstance(content, str) or isinstance(content, list) and any(
        isinstance(b, dict) and b.get("type") == "text" for b in content))


def _parse(path, redact, since):
    """[(day, session, kind, value)] from one transcript file."""
    out, seen = [], set()
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            if '"tool_use"' not in ln and '"user"' not in ln and '"usage"' not in ln:
                continue
            try:
                ev = json.loads(ln)
            except ValueError:
                continue
            day = str(ev.get("timestamp") or "")[:10]
            if not day or day < since:
                continue
            sess = str(ev.get("sessionId") or path.stem)
            msg = ev.get("message")
            content = msg.get("content") if isinstance(msg, dict) else None
            used = _tokens(msg, seen)
            if used:
                out.append((day, sess, "tokens", used))
            if _said(ev, content):
                out.append((day, sess, "task", ""))
                m = SLASH.search(content if isinstance(content, str) else " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict) and isinstance(b.get("text"), str)))
                if m:                                    # a slash command the user typed: its name, no text
                    out.append((day, sess, "slash", m.group(1)[:80]))
                continue
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict) or b.get("type") != "tool_use" or not isinstance(b.get("input"), dict):
                    continue
                name, inp = b.get("name"), b["input"]
                if name in SHELLS and isinstance(inp.get("command"), str):
                    m = LOOKUP.search(inp["command"])
                    if m:                                # "find:<query>" or "page:<name>"
                        out.append((day, sess, "lookup", "%s:%s" % (m.group(1).lower(),
                                                                    redact(m.group(2).strip().strip("\"'"))[:120])))
                    out += [(day, sess, "cmd", s) for s in shapes(inp["command"], redact)]
                    if nested(inp["command"]):
                        out.append((day, sess, "nested", redact(" ".join(inp["command"].split()[:40])).lower()))
                elif name == "Read" and isinstance(inp.get("file_path"), str):
                    out.append((day, sess, "read", inp["file_path"].replace("\\", "/")))
                elif name in EDITS:
                    out.append((day, sess, "edit", ""))
                elif name == "Skill" and isinstance(inp.get("skill"), str):
                    out.append((day, sess, "skill", inp["skill"][:80]))     # its name only, never its arguments
    return out


def _tokens(msg, seen):
    """"input,output,cache reads" tokens of a model reply, once per reply (a reply is written as several lines that repeat its
    usage), or ''."""
    if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict) or msg.get("role") not in (None, "assistant"):
        return ""
    mid = msg.get("id")
    if mid in seen:
        return ""
    seen.add(mid)
    u = msg["usage"]
    num = (lambda k: u.get(k) if isinstance(u.get(k), int) else 0)
    tin, cached = num("input_tokens") + num("cache_creation_input_tokens"), num("cache_read_input_tokens")
    return "%d,%d,%d" % (tin, num("output_tokens"), cached) if tin or cached or num("output_tokens") else ""


def events(project, days=WINDOW_DAYS, opted=False):
    """Every event of the last `days` days, oldest first. [] when transcripts are not opted in (`opted`: the
    caller holds its own opt-in, the machine-wide reflection)."""
    if not (opted or enabled(project)):
        return []
    since = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    cache_path = project.data / "transcripts.json"
    try:
        cache = json.loads(read_text(cache_path))
    except (OSError, ValueError):
        cache = {}
    out, fresh = [], {}
    for folder in folders(project):
        for f in sorted(folder.glob("*.jsonl")):
            st = f.stat()
            if dt.date.fromtimestamp(st.st_mtime).isoformat() < since:
                continue
            key, stamp = str(f), "%d:%d" % (st.st_size, int(st.st_mtime))
            hit = cache.get(key)
            if hit and hit.get("stamp") == stamp and hit.get("since", since) <= since and hit.get("v") == CACHE_VERSION:
                evs = [tuple(e) for e in hit["events"]]
            else:
                evs = _parse(f, project.redact, since)
            fresh[key] = dict(stamp=stamp, since=since, events=evs, v=CACHE_VERSION)
            out += [e for e in evs if e[0] >= since]
    try:
        writeset.write_text(project, cache_path, json.dumps(fresh))
    except OSError:
        pass
    return sorted(out, key=lambda e: e[0])
