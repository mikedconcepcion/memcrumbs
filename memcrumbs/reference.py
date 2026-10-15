"""The user's development reference: optional, set once per machine.

After `memcrumbs init` finishes, it asks once per machine: point to a folder with your development reference
(your principles, philosophy, how you work), pick a starter, or skip. Under an agent (no terminal) it is not asked:
`init` names the command for the owner.

    memcrumbs reference                          what is set up
    memcrumbs reference set PATH                 your own folder (its markdown files)
    memcrumbs reference set software|agile|lean  a starter, copied into a folder you own (projects folder/_reference)
    memcrumbs reference reflect on|off           count how the work goes across your projects (counts only)
    memcrumbs reference refresh                  after editing the folder: the skill lists its files again
    memcrumbs reference skip                     no reference, and the question is not asked again
    memcrumbs reference off                      remove the skill; the folder stays

`set` wires a personal Claude Code skill (`~/.claude/skills/dev-reference/SKILL.md`) that points the agent at the
folder. About once a week the session header shows one line from it, picked against what the counts show (when
the reflection is on). The reference is the user's: memcrumbs never writes into the user's folder, and a starter
is copied once and never over an edited copy. Nothing ships with anyone's philosophy: the starters are short pages
in our own words. The answer is kept machine-wide in the projects folder (`.memcrumbs-reference.json`)."""
import datetime as dt
import json
import re
from pathlib import Path

from memcrumbs import markdown, project as proj
from memcrumbs.util import clip, posix, read_text

STARTERS = ("software", "agile", "lean")
SKILL = "dev-reference"
REMIND_DAYS = 7
MAX_FILES = 50
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.{12,200})$")
# what the counts show → words of a principle that speaks to it
SIGNAL_WORDS = {"unfinished": ("finish", "done", "progress", "start", "half", "loose"),
                "unreleased": ("ship", "release", "deliver", "done", "use"),
                "tokens": ("small", "waste", "simple", "cost", "measure")}


def _state_path():
    return proj.projects_dir() / ".memcrumbs-reference.json"


def load():
    try:
        data = json.loads(read_text(_state_path()))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data):
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)


def skill_path():
    return Path.home() / ".claude" / "skills" / SKILL / "SKILL.md"


def starter_dir():
    return proj.projects_dir() / "_reference"


def files(folder):
    """The reference's markdown files, relative to the folder (README or index first)."""
    folder = Path(folder)
    found = sorted((p for p in folder.rglob("*.md") if not any(x.startswith(".") for x in p.relative_to(folder).parts)),
                   key=lambda p: (p.stem.lower() not in ("readme", "index"), posix(p.relative_to(folder)).lower()))
    return [posix(p.relative_to(folder)) for p in found[:MAX_FILES]]


def _render(folder):
    names = files(folder)
    shown = ", ".join("`%s`" % n for n in names[:8]) + (" and %d more" % (len(names) - 8) if len(names) > 8 else "")
    tpl = (Path(__file__).parent / "templates" / "skill_reference.md").read_text(encoding="utf-8")
    return tpl.replace("{folder}", posix(folder)).replace("{files}", shown).replace("{main}", names[0])


def _write_skill(folder):
    p = skill_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_render(folder), encoding="utf-8")
    return p


def _ours(p):
    return p.exists() and "set up with memcrumbs" in read_text(p)


def set_(out, target, reflect=None):
    data = load()
    if target in STARTERS:
        folder = starter_dir()
        folder.mkdir(parents=True, exist_ok=True)
        page = folder / ("%s.md" % target)
        kept = page.exists()
        if not kept:                                       # copied once: an edited copy is never overwritten
            page.write_text((Path(__file__).parent / "templates" / ("reference_%s.md" % target)).read_text(
                encoding="utf-8"), encoding="utf-8")
        data.update(answer="starter", starter=target)
        said = "%s starter %s %s (yours to edit)" % (target, "kept at" if kept else "copied to", posix(page))
    else:
        folder = Path(target).expanduser().resolve()
        if not folder.is_dir() or not files(folder):
            raise SystemExit("memcrumbs: %s is not a folder with markdown files; or pick a starter: %s"
                             % (posix(folder), ", ".join(STARTERS)))
        data.update(answer="folder", starter=None)
        said = "your folder %s (%d markdown files)" % (posix(folder), len(files(folder)))
    data.update(folder=posix(folder), asked=dt.date.today().isoformat())
    if reflect is not None:
        data["reflect"] = bool(reflect)
    save(data)
    p = _write_skill(folder)
    out.set(folder=posix(folder), skill=posix(p), reflect=bool(data.get("reflect")))
    out("development reference: %s" % said)
    out("skill %s: %s (Claude Code reads it in every project)" % (SKILL, posix(p)))
    if not data.get("reflect"):
        out("the reflection is off: memcrumbs reference reflect on counts how the work goes across your projects "
            "(commits, open items, tokens; counts only)")


def reflect_switch(out, on):
    data = load()
    data["reflect"] = on
    save(data)
    out.set(reflect=on)
    out("reflection %s%s" % ("on: memcrumbs counts commits, open items and tokens across your projects (counts "
                             "only; a project opts out with [reference] reflect = false); memcrumbs reflect shows "
                             "them" if on else "off", ""))


def refresh(out):
    data = load()
    if not data.get("folder") or not Path(data["folder"]).is_dir():
        raise SystemExit("memcrumbs: no reference folder is set: memcrumbs reference set PATH|%s" % "|".join(STARTERS))
    p = _write_skill(Path(data["folder"]))
    out("skill %s refreshed: %d files in %s" % (SKILL, len(files(data["folder"])), data["folder"]))
    out.set(skill=posix(p))


def skip(out):
    data = load()
    data.update(answer="skip", asked=dt.date.today().isoformat())
    save(data)
    out("no development reference; not asked again (memcrumbs reference set … any time)")


def off(out):
    data = load()
    p = skill_path()
    if _ours(p):
        p.unlink()
        try:
            p.parent.rmdir()
        except OSError:
            pass
    data.update(answer="off")
    save(data)
    out("development reference off: the skill is removed%s" % (
        "; your folder %s stays" % data["folder"] if data.get("folder") else ""))


def show(out):
    data = load()
    out.set(**{k: data.get(k) for k in ("answer", "folder", "starter", "reflect", "reminded", "reflected")})
    if not data.get("answer"):
        out("no development reference yet: memcrumbs reference set PATH|%s, or skip" % "|".join(STARTERS))
        return
    if data["answer"] in ("skip", "off"):
        out("development reference: %s (memcrumbs reference set … turns it on)" % data["answer"])
        return
    out("development reference: %s%s" % (data["folder"], " (starter %s)" % data["starter"] if data.get("starter") else ""))
    out("skill %s: %s" % (SKILL, posix(skill_path()) if skill_path().exists() else "missing (memcrumbs reference refresh)"))
    out("reflection: %s · last reminder %s" % ("on" if data.get("reflect") else "off", data.get("reminded") or "never"))


def after_init(out, interactive):
    """Once per machine, after init: ask in a terminal; under an agent, name the command for the owner."""
    if load().get("answer"):
        return
    if not interactive:
        out("development reference (optional, asked once per machine): the owner runs memcrumbs reference set "
            "PATH|software|agile|lean, or memcrumbs reference skip")
        return
    from memcrumbs.setup_repo import _flush
    _flush(out)
    print("Development reference (optional, asked once on this machine): a folder with your principles,\n"
          "philosophy or how you work, for the agent to follow and for an occasional reminder.\n"
          "  1) my own folder   2) starter: software development   3) starter: agile   4) starter: lean   5) skip")
    try:
        pick = input("Choice [5]: ").strip() or "5"
        target = input("Folder: ").strip().strip('"') if pick == "1" else {"2": "software", "3": "agile",
                                                                          "4": "lean"}.get(pick)
        if not target:
            return skip(out)
        yes = input("Also count how the work goes across your memcrumbs projects (commits, open items, tokens; "
                    "counts only), for an occasional reflection? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return
    try:
        set_(out, target, reflect=yes)
    except SystemExit as e:
        out(str(e.code))


def principles(folder):
    """The reference's list items: the lines a reminder picks from."""
    out = []
    for name in files(folder):
        body = markdown.frontmatter(read_text(Path(folder) / name))[1]
        out += [m.group(1).strip() for m in (ITEM.match(ln) for ln in body.splitlines()) if m]
    return out


def pick(lines, flags, today):
    """The principle that speaks to what the counts show; else this week's line in turn."""
    for flag in flags:
        words = SIGNAL_WORDS.get(flag, ())
        hit = [ln for ln in lines if any(re.search(r"\b%s" % w, ln.lower()) for w in words)]
        if hit:
            return hit[today.isocalendar()[1] % len(hit)], flag
    return lines[today.isocalendar()[1] % len(lines)], None


def header_line(project, today=None):
    """About once a week, one line from the user's reference. It records when it was shown; it never fails."""
    today = today or dt.date.today()
    try:
        data = load()
        if data.get("answer") not in ("folder", "starter") or not data.get("folder"):
            return ""
        last = data.get("reminded")
        if last and (today - dt.date.fromisoformat(last)).days < REMIND_DAYS:
            return ""
        lines = principles(data["folder"])
        if not lines:
            return ""
        from memcrumbs import reflect
        line, flag = pick(lines, reflect.flags(), today)
        data["reminded"] = today.isoformat()
        save(data)
        why = {"unfinished": " (many projects are quiet and unfinished)", "unreleased": " (much is built without a "
               "release tag)", "tokens": " (token use is up)"}.get(flag, "")
        return "your reference%s: %s (skill %s)" % (why, clip(line, 140), SKILL)
    except Exception:
        return ""
