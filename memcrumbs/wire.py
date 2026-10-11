"""`wire`: connect a repo to an agent. Dry run unless --apply; --remove takes out exactly what wire added.

Targets:
  claude  CLAUDE.md generated block · .claude/settings.json SessionStart hook · .claude/skills/memcrumbs/SKILL.md
          (--user-skill: ~/.claude/skills instead of the repo) · with --allow: allow rules for the read-only
          lookups (find, page, outline, sym, status) for the Bash and PowerShell tools, so they need no approval
  agents  AGENTS.md generated block (agents without hooks are told to run `memcrumbs status` first)

Every edit is textual and reversible: wire, then wire --remove, gives back each file byte for byte. A file wire
created and that holds nothing else afterwards (CLAUDE.md with only the block, settings.json `{}`) is deleted.
If an inserted span was edited by hand, --remove refuses rather than guess."""
import hashlib
import json
from pathlib import Path

from memcrumbs import __version__, claude_settings as cs, markdown, writeset
from memcrumbs.jsonedit import JsonEditError, check_object
from memcrumbs.util import posix, read_doc

TPL = Path(__file__).parent / "templates"
# sha256 of the skills earlier memcrumbs versions wrote, over the text with LF line endings: those are ours to
# update or remove. Line endings never count: git's autocrlf rewrites them on every Windows checkout.
OLD_SKILLS = {"sha256:833110da09379bbaf379f3964563cc7d5253feff2b1bb1fad9dc2b71a62c3485",     # 0.1.0
              "sha256:47cec81a2c823e16a4c470adf512728e4dc87be454ff0c3f5e3c3c9bd5a16632",     # 0.2.0.dev0
              "sha256:ed5ac17c5edfe1dec670ee72f62200a2ed682b1266b0b2556fb84a623e1338cd",     # 0.2.0.dev1-dev5
              "sha256:e5b8c3db45712581e73218b350bdc96fa2c368103759356be9e64ac1bdd88fb5"}     # 0.2.0.dev6-0.3.0
BLOCKS = {"claude": ("CLAUDE.md", "claude", "claude_block.md"), "agents": ("AGENTS.md", "agents", "agents_block.md")}
hook_command = cs.hook_command                       # kept importable from here


def _tpl(tpl_name, **kw):
    t = (TPL / tpl_name).read_text(encoding="utf-8")
    for k, v in kw.items():
        t = t.replace("{%s}" % k, str(v))
    return t


def _change(path, new, info, what, empty=False, allow=None):
    """new: text, bytes, None (delete) or False (report only). empty: the file holds nothing but what wire added
    was removed; it is deleted only if wire created it. allow: the allow-rule text this change inserts."""
    return dict(path=path, new=new, info=info, what=what, empty=empty, allow=allow)


def _md(project, path, block, body, remove):
    if not path.exists() and remove:
        return None
    text, info = read_doc(path) if path.exists() else ("", (b"", "utf-8"))
    new = markdown.remove_generated(text, block) if remove else markdown.replace_generated(text, block, body)
    if new == text:
        return None
    what = "remove block" if remove else ("update block" if markdown.find_block(text, block) else "add block")
    return _change(path, new, info, what, empty=remove and not new.strip())


def _settings(project, path, remove, allow, inserted_allow):
    exists = path.exists()
    if remove and not exists:
        return None
    text, info = read_doc(path) if exists else ("{}\n", (b"", "utf-8"))
    try:
        data = check_object(text)
    except JsonEditError as e:
        if remove:
            return None
        raise SystemExit("memcrumbs: %s is %s; add this SessionStart hook by hand: %s" % (posix(path), e, cs.hook_text(project)))
    new, what, added = text, [], None
    if remove:                                       # undo in reverse order of insertion: allow rules, then the hook
        for entries in filter(None, (inserted_allow, cs.allow_text(cs.allow_rules(project)))):
            out = cs.take_out(new, ("permissions", "allow"), entries)
            if out is not None:
                new, what = out, what + ["remove allow rules"]
                break
        else:                                        # reformatted by an editor: take out our rules one by one
            rules = json.loads("[%s]" % inserted_allow) if inserted_allow else cs.allow_rules(project)
            out = cs.remove_items(new, ("permissions", "allow"), rules)
            if out is not None:
                new, what = out, what + ["remove allow rules"]
        if cs.has_hook(data):
            out = cs.take_out(new, ("hooks", "SessionStart"), cs.hook_text(project))
            out = out if out is not None else cs.canonical_remove_hook(new, check_object(new))
            if out is None:
                raise SystemExit("memcrumbs: %s was edited around the memcrumbs hook; remove it by hand" % posix(path))
            new, what = out, what + ["remove SessionStart hook"]
    else:
        if not cs.has_hook(data):
            new, what = cs.insert(new, ("hooks", "SessionStart"), cs.hook_text(project)), ["add SessionStart hook `%s`"
                                                                                       % cs.hook_command(project)]
        missing = cs.missing_allow(data, project)
        if allow and missing:
            added = cs.allow_text(missing)
            new, what = cs.insert(new, ("permissions", "allow"), added), what + [
                "allow %d read-only lookup rules (%s; Bash and PowerShell)" % (len(missing), ", ".join(cs.READ_ONLY))]
        elif missing:
            what.append("note: lookups will ask for approval each time — add --allow")
    if new == text:
        return _change(path, False, info, what[0]) if what else None
    try:
        check_object(new)                            # never write a settings file Claude Code cannot read
    except JsonEditError as e:
        raise SystemExit("memcrumbs: editing %s would leave invalid JSON (%s); nothing written" % (posix(path), e))
    return _change(path, new, info, "; ".join(what), empty=remove and new.strip() == "{}", allow=added)


def lf(data):
    return data.replace(b"\r\n", b"\n")


def skill_hash(data):
    return "sha256:" + hashlib.sha256(lf(data)).hexdigest()


def _skill(path, remove):
    ours = lf((TPL / "skill.md").read_bytes())
    have = path.read_bytes() if path.exists() else None
    same = have is not None and lf(have) == ours                 # the same text, whatever its line endings
    older = have is not None and skill_hash(have) in OLD_SKILLS
    if remove:
        return _change(path, None, None, "remove skill") if same or older else None
    if have is None:
        return _change(path, ours, None, "write skill")
    if same:
        return None
    if older:
        return _change(path, ours, None, "update skill (an older memcrumbs version)")
    return _change(path, False, None, "skill differs from this version (kept)")


def plan(project, repo, targets=("claude",), remove=False, user_skill=False, allow=False, state=None):
    changes = []
    inserted = ((state or {}).get("allow") or {})
    for t in targets:
        fname, block, tpl = BLOCKS[t]
        body = _tpl(tpl, name=project.name, wiki=posix(project.wiki)).strip()
        changes.append(_md(project, repo / fname, block, body, remove))
        if t == "claude":
            sp = repo / ".claude" / "settings.json"
            changes.append(_settings(project, sp, remove, allow, inserted.get(posix(sp.resolve()))))
            base = Path.home() / ".claude" if user_skill else repo / ".claude"
            changes.append(_skill(base / "skills" / "memcrumbs" / "SKILL.md", remove))
    return [c for c in changes if c]


def _state(project):
    """What wire created and inserted (paths and our own rule text, nothing else), so --remove takes out exactly
    that and keeps a pre-existing empty file. Kept in the index dir; if it is gone, an emptied file counts as
    created and the allow rules are looked for in their full form."""
    p = project.data / "wire.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")), p
    except (OSError, ValueError):
        return None, p


def wire(out, project, repo=None, targets=("claude",), apply=False, remove=False, user_skill=False, allow=False):
    repo = Path(repo) if repo else (project.repos[0] if project.repos else None)
    if not repo or not repo.is_dir():
        raise SystemExit("memcrumbs: no repo folder: pass --repo PATH")
    state, state_path = _state(project)
    changes = plan(project, repo.resolve(), targets, remove, user_skill, allow, state)
    out.set(repo=posix(repo), apply=apply, remove=remove, changes=[dict(path=posix(c["path"]), what=c["what"]) for c in changes])
    created = set((state or {}).get("created", []))
    inserted = dict((state or {}).get("allow") or {})
    if not changes:
        out("nothing to %s in %s" % ("remove" if remove else "change", posix(repo)))
    for c in changes:
        out("%s: %s" % (posix(c["path"]), c["what"]))
    if not apply or all(c["new"] is False for c in changes):
        if changes:
            out("(dry run — add --apply)" if not apply else "nothing to apply.")
        if apply and state is not None and state.get("version") != __version__:
            _record(project, state_path, created, inserted)          # this version has checked the wiring
        return
    extra = [c["path"] for c in changes]
    try:
        for c in changes:                            # the record changes only after each write succeeds
            path, new, key = c["path"], c["new"], posix(c["path"].resolve())
            if new is False:
                continue
            if c["empty"] and (state is None or key in created):
                new = None
            if new is None:
                writeset.delete(project, path, extra)
                created.discard(key)
                inserted.pop(key, None)
                for d in (path.parent, path.parent.parent, path.parent.parent.parent):
                    if d.name in ("memcrumbs", "skills", ".claude") and d.is_dir() and not any(d.iterdir()):
                        d.rmdir()
                continue
            fresh = not path.exists()
            if isinstance(new, bytes):
                writeset.write_bytes(project, path, new, extra)
            else:
                writeset.write_text(project, path, new, c["info"], extra)
            if fresh:
                created.add(key)
            if c["allow"]:
                inserted[key] = c["allow"]
            elif remove:
                inserted.pop(key, None)
    finally:                                         # a failed write still leaves a record of what was done
        _record(project, state_path, created, inserted)
    out("applied.")


def _record(project, state_path, created, inserted):
    """`version` is the memcrumbs that last applied the wiring: `update` and the header use it to tell whether an
    upgrade made by hand (pip, git) still has its index and wiring steps to run."""
    writeset.write_text(project, state_path, json.dumps({"created": sorted(created), "allow": inserted,
                                                         "version": __version__}, indent=1) + "\n")
