"""`.claude/settings.json` edits for `wire`: the SessionStart hook, and allow rules for the read-only lookups.

Each edit is one textual insertion right after an opening brace or bracket (jsonedit.py), so `--remove` takes
out exactly the inserted text and every other byte stays as it was. A hook written by memcrumbs 0.1 (whole file
re-serialized by json.dumps) is removed at the JSON level when the file is still in that exact format."""
import json

from memcrumbs import jsonedit
from memcrumbs.jsonedit import JsonEditError
from memcrumbs.util import newline_of

READ_ONLY = ("find", "page", "outline", "sym", "status", "about", "fact")   # never log/decision/incident/verify/plan
SHELLS = ("Bash", "PowerShell")                              # Claude Code on Windows runs commands via PowerShell


def hook_command(project):
    return "memcrumbs -p %s status --hook" % project.name     # -p before the subcommand: valid for any argparse


def hook_entry(project):
    return {"matcher": "", "hooks": [{"type": "command", "command": hook_command(project), "timeout": 30}]}


def allow_rules(project):
    """Prefix rules for the read-only subcommands, with and without `-p NAME`, for both shell tools."""
    return ["%s(memcrumbs %s%s:*)" % (sh, pre, cmd) for sh in SHELLS for pre in ("", "-p %s " % project.name)
            for cmd in READ_ONLY]


def ours(cmd):
    return isinstance(cmd, str) and cmd.startswith("memcrumbs ") and " status" in cmd


def has_hook(data):
    hooks = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    return any(ours(h.get("command")) for e in hooks.get("SessionStart") or [] if isinstance(e, dict)
               for h in e.get("hooks") or [] if isinstance(h, dict))


def missing_allow(data, project):
    perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    have = set(perms.get("allow") or [])
    return [r for r in allow_rules(project) if r not in have]


def _snippets(keys, entries):
    k0, k1 = keys
    for frag in ('"%s": {"%s": [%s]}' % (k0, k1, entries), '"%s": [%s]' % (k1, entries), entries):
        for indent in ("  ", "    ", "      "):
            for nl in ("\r\n", "\n"):                         # CRLF first: an LF snippet also matches inside it
                for tail in (",", nl):
                    yield nl + indent + frag + tail


def insert(text, keys, entries):
    """Insert `entries` (JSON array items as text) into data[k0][k1], creating the object and list as needed."""
    k0, k1 = keys
    top = jsonedit._ws(text, 0)
    m = jsonedit.members(text, top)
    if k0 not in m:
        at, frag, indent = top, '"%s": {"%s": [%s]}' % (k0, k1, entries), "  "
    elif text[m[k0][0]] == "{":
        inner = jsonedit.members(text, m[k0][0])
        if k1 not in inner:
            at, frag, indent = m[k0][0], '"%s": [%s]' % (k1, entries), "    "
        elif text[inner[k1][0]] == "[":
            at, frag, indent = inner[k1][0], entries, "      "
        else:
            raise JsonEditError("%s.%s is not a list" % keys)
    else:
        raise JsonEditError("%s is not an object" % k0)
    return jsonedit.insert_after_open(text, at, frag, indent, newline_of(text))[0]


def take_out(text, keys, entries):
    """Remove exactly what `insert` added; None if that text is not there (edited by hand)."""
    for snip in _snippets(keys, entries):
        if snip in text:
            return text.replace(snip, "", 1)
    return None


def remove_items(text, keys, items):
    """Fallback when an editor reformatted the list: drop each string in `items` from data[k0][k1] by its element
    span, keeping every other byte. None if the list is missing or holds none of them."""
    k0, k1 = keys
    m = jsonedit.members(text, jsonedit._ws(text, 0))
    if k0 not in m or text[m[k0][0]] != "{":
        return None
    inner = jsonedit.members(text, m[k0][0])
    if k1 not in inner or text[inner[k1][0]] != "[":
        return None
    start, end = inner[k1]
    spans, i = [], jsonedit._ws(text, start + 1)
    while text[i] != "]":
        j = jsonedit.value_end(text, i)
        spans.append((i, j))
        i = jsonedit._ws(text, j)
        if text[i] == ",":
            i = jsonedit._ws(text, i + 1)
    want = set(items)
    drop = [k for k, (a, b) in enumerate(spans) if text[a] == '"' and json.loads(text[a:b]) in want]
    if not drop:
        return None
    runs = []
    for k in drop:
        if runs and runs[-1][1] == k - 1:
            runs[-1][1] = k
        else:
            runs.append([k, k])
    for lo, hi in reversed(runs):                     # an element goes with the separator after it (before, if last)
        if hi < len(spans) - 1:
            text = text[:spans[lo][0]] + text[spans[hi + 1][0]:]
        elif lo > 0:
            text = text[:spans[lo - 1][1]] + text[spans[hi][1]:]
        else:
            text = text[:start + 1] + text[end - 1:]
    return text


def hook_text(project):
    return json.dumps(hook_entry(project))


def allow_text(rules):
    return ", ".join(json.dumps(r) for r in rules)


def canonical_remove_hook(text, data):
    """settings.json written by json.dumps(indent=2) (memcrumbs 0.1 did this): drop our hook at the JSON level and
    re-serialize in the same style, which reproduces every other byte. None if the file is hand-formatted."""
    nl = newline_of(text)
    body = text.replace("\r\n", "\n")
    for ascii_ in (True, False):
        canon = json.dumps(data, indent=2, ensure_ascii=ascii_)
        if body.rstrip("\n") != canon or len(body) - len(canon) > 1:
            continue
        hooks = data["hooks"]
        kept = [e for e in hooks["SessionStart"] if not (isinstance(e, dict) and any(
            ours(h.get("command")) for h in e.get("hooks") or [] if isinstance(h, dict)))]
        if kept:
            hooks["SessionStart"] = kept
        else:
            del hooks["SessionStart"]
            if not hooks:
                del data["hooks"]
        return (json.dumps(data, indent=2, ensure_ascii=ascii_) + body[len(canon):]).replace("\n", nl)
    return None
