"""Task flows and pipelines: the same steps, in the same order, in many tasks, become a skill offer.

A task is the work between two messages from the user. A step is a command named by what it runs: a script's file
name (`python scripts/build.py` → `build.py`), a module (`python -m unittest discover` → `unittest discover`), or a
tool and its subcommand (`git tag`, `gh run`, `npm run`). Lookups, listings, file plumbing and git's read-only
commands are not steps.

A flow is an ordered run of MIN_STEPS to MAX_STEPS steps found in at least MIN_TASKS tasks on MIN_DAYS days (or
in twice as many tasks on any day), each step within GAP commands of the one before (other commands may come
between). A flow made only of everyday git
steps (add, commit, push …) is everyone's, not the project's, and is not offered. When no file was edited between
its steps it is a pipeline (a script would do, or a skill that runs it); otherwise a task flow (a checklist for a
skill). Variants (a step more or less, another order) fold into the best-evidenced form.

Deterministic and local. Only step names and counts leave this module, never a command's arguments."""
import re
from collections import defaultdict

from memcrumbs.suggest_skill import EVERYDAY, head

MIN_TASKS, MIN_DAYS, MIN_STEPS, MAX_STEPS, GAP = 3, 2, 3, 6, 3
TOP = 3
PY = ("python", "python3", "py")
SUBTOOLS = {"gh", "npm", "pnpm", "yarn", "uv", "pip", "cargo", "go", "dotnet", "make", "ruff", "terraform", "docker",
            "kubectl", "helm", "mvn", "gradle", "poetry", "hatch", "just", "nox", "invoke", "az", "aws", "gcloud"}
# the second word of these names the step: `make docs`, `ruff check`, `terraform plan`
GLUE = {"rm", "cp", "mv", "del", "rmdir", "remove-item", "copy-item", "move-item", "new-item", "sleep",
        "start-sleep", "chmod", "ln", "tar", "unzip"}
GIT_READ = {"status", "log", "diff", "show", "check-ignore", "branch", "remote", "rev-parse", "ls-files", "blame",
            "config", "describe", "shortlog", "reflog", "grep"}
LOOKUPS = {"find", "page", "outline", "sym", "status", "about", "fact", "stats", "suggest", "review"}
GENERIC = {"git add", "git commit", "git push", "git pull", "git fetch", "git checkout", "git switch", "git merge",
           "git stash", "git tag", "git rebase"}
WORD = re.compile(r"^[a-z][\w-]*$")


def step(shape):
    """The step a shell part is, or '' when it is not one."""
    h = head(shape)
    if not h:
        return ""
    words, first = shape.split(), h.split()[0]
    if first in PY:
        rest = words[1:]
        while rest and rest[0].startswith("-") and rest[0] not in ("-m", "-c"):
            rest = rest[1:]
        if not rest or rest[0] in ("-c", "-"):
            return ""
        if rest[0] == "-m" and rest[1:2] == ["memcrumbs"]:
            return step(" ".join(rest[1:]))
        if rest[0] == "-m":
            return " ".join(rest[1:3]) if len(rest) > 2 and WORD.match(rest[2]) else " ".join(rest[1:2])
        script = re.split(r"[\\/]", rest[0].strip("'\""))[-1]
        return script if script.endswith(".py") else ""
    if first in ("npm", "pnpm", "yarn") and words[1:2] == ["run"] and len(words) > 2:
        return " ".join(words[:3])                         # npm run build: the script names the step
    if first in SUBTOOLS and len(h.split()) == 1 and len(words) > 1 and WORD.match(words[1]):
        return first + " " + words[1]
    if first in ("memcrumbs", "memcrumb"):
        rest = words[3:] if words[1:2] == ["-p"] else words[1:]
        return "memcrumbs " + rest[0] if rest and WORD.match(rest[0]) else ""
    return h


def noise(s):
    w = s.split()
    if w[0] in GLUE:
        return True
    if len(w) == 1:
        return w[0] in EVERYDAY
    if w[0] == "git":
        return w[1] in GIT_READ
    if w[0] == "memcrumbs":
        return w[1] in LOOKUPS
    return False


def tasks(events):
    """[(day, steps, edited)] per task: a session's commands split at the user's messages. edited[j]: a file was
    edited between step j-1 and step j."""
    out, cur = [], {}
    for day, sess, kind, val in events:
        if kind == "task":
            t = cur.pop(sess, None)
            if t and t[1]:
                out.append(t)
            continue
        t = cur.setdefault(sess, (day, [], [], [False]))
        if kind == "edit":
            t[3][0] = True
        elif kind == "cmd":
            s = step(val)
            if s and not noise(s) and (not t[1] or t[1][-1] != s):
                t[1].append(s)
                t[2].append(t[3][0])
                t[3][0] = False
    out += [t for t in cur.values() if t[1]]
    return [(day, steps, edited) for day, steps, edited, _ in out]


def _mine(db):
    """{steps: {task index}} for ordered runs in MIN_TASKS tasks or more, each step within GAP of the last."""
    out = {}

    def grow(prefix, proj):
        cnt = defaultdict(dict)
        for ti, ends in proj.items():
            t = db[ti]
            for e in ends:
                for j in range(e + 1, min(len(t), e + 1 + GAP)):
                    if t[j] not in prefix:
                        cnt[t[j]].setdefault(ti, set()).add(j)
        for s, m in cnt.items():
            if len(m) >= MIN_TASKS:
                new = prefix + (s,)
                out[new] = set(m)
                if len(new) < MAX_STEPS:
                    grow(new, {ti: sorted(js) for ti, js in m.items()})
    first = defaultdict(dict)
    for ti, t in enumerate(db):
        for j, s in enumerate(t):
            first[s].setdefault(ti, []).append(j)
    for s, m in first.items():
        if len(m) >= MIN_TASKS:
            grow((s,), m)
    return out


def _embedding(t, pat):
    """(first, last) positions of an occurrence of `pat` in `t` with each step within GAP of the last, or None."""
    def walk(k, pos):
        if k == len(pat):
            return pos
        for j in range(pos + 1, min(len(t), pos + 1 + GAP)):
            if t[j] == pat[k]:
                end = walk(k + 1, j)
                if end is not None:
                    return end
        return None
    for i, s in enumerate(t):
        if s == pat[0]:
            end = walk(1, i)
            if end is not None:
                return i, end
    return None


def _within(a, b):
    it = iter(b)
    return all(x in it for x in a)


def flows(events):
    """The offered flows, best evidence first: dicts of steps, tasks, days, forms, pipeline."""
    found = tasks(events)
    db = [steps for _, steps, _ in found]
    pats = {p: tis for p, tis in _mine(db).items()
            if len(p) >= MIN_STEPS and not set(p) <= GENERIC and
            (len({found[i][0] for i in tis}) >= MIN_DAYS or len(tis) >= 2 * MIN_TASKS)}
    best = {p: tis for p, tis in pats.items()               # maximal: no longer flow holds it with as much evidence
            if not any(len(q) > len(p) and len(qt) >= 0.8 * len(tis) and set(p) <= set(q) and _within(p, q)
                       for q, qt in pats.items())}
    families = []
    for p in sorted(best, key=lambda p: (-len(best[p]) * len(p), p)):
        own = set(p) - GENERIC
        fam = next((f for f in families if len(own & f["own"]) >= 0.6 * len(own)), None)
        if fam:
            fam["forms"] += 1
            fam["own"] |= own
            continue
        quiet = 0
        for ti in best[p]:
            span = _embedding(db[ti], p)
            quiet += bool(span) and not any(found[ti][2][span[0] + 1:span[1] + 1])
        families.append(dict(steps=p, tasks=len(best[p]), days=len({found[i][0] for i in best[p]}), forms=1,
                             own=own, pipeline=quiet >= 0.6 * len(best[p])))
    return families
