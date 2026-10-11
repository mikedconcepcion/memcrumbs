"""Reference plugin: live state as a source, a check, a header section and a generated wiki block.

Reads an exported scheduled-task inventory (what a host scanner pack would write; JSON list of tasks with
host, name, kind, time_limit, state, last_result) and:
  - source  "tasks":      one searchable doc per task (kind "inventory"), so `find KilnScheduler` hits live state
  - check:                daemons with a finite execution time limit (the 72-hour trap) and failed last runs
  - section "tasks":      one header line per task that needs attention
  - command tasks-page:   rewrites the generated block "tasks" in wiki/systems/scheduled-tasks.md
Shows that a source plus a check fits in well under 150 lines."""
import json
from pathlib import Path

from memcrumbs.sources import Doc
from memcrumbs.util import posix, read_text, stamp

UNLIMITED = ("PT0S", "", None, "unlimited")


def _inventory(project):
    rel = (project.cfg.get("tasks") or {}).get("inventory")
    return project.path(rel) if rel else None


def _tasks(project):
    p = _inventory(project)
    if not p or not p.exists():
        return [], None
    data = json.loads(read_text(p))
    return (data.get("tasks", data) if isinstance(data, dict) else data), p


def _problems(tasks):
    for t in tasks:
        where = "%s/%s" % (t.get("host", "?"), t.get("name", "?"))
        if t.get("kind") == "daemon" and t.get("time_limit") not in UNLIMITED:
            yield "W", where, "daemon has execution time limit %s: it will be killed (set PT0S)" % t["time_limit"]
        if t.get("last_result") not in (0, "0", None):
            yield "W", where, "last run failed (result %s)" % t["last_result"]
        if t.get("kind") == "daemon" and t.get("state") not in ("Running", None):
            yield "W", where, "daemon is %s, expected Running" % t.get("state")


def source(project):
    p = _inventory(project)
    if p and p.exists():
        yield p, stamp(p.stat()), lambda: _docs(project)


def _docs(project):
    tasks, p = _tasks(project)
    key, red, docs = posix(p), project.redact, []
    for i, t in enumerate(tasks, 1):
        body = "scheduled task %s on %s · kind %s · schedule %s · time limit %s · state %s · last result %s · %s" % (
            t.get("name"), t.get("host"), t.get("kind"), t.get("schedule"), t.get("time_limit"), t.get("state"),
            t.get("last_result"), t.get("action", ""))
        docs.append(Doc("inventory", key, i, "Task inventory",
                        "%s on %s" % (t.get("name"), t.get("host")), red(body), "task " + str(t.get("kind", "")),
                        verified=str(t.get("exported", ""))[:10]))
    return docs, []


def check(project):
    tasks, p = _tasks(project)
    return [(lvl, where, msg) for lvl, where, msg in _problems(tasks)]


def section(project):
    tasks, p = _tasks(project)
    bad = list(_problems(tasks))
    if not p:
        return []
    if not bad:
        return ["all %d tasks healthy (inventory %s)" % (len(tasks), p.name)]
    return ["%s: %s" % (where, msg) for _, where, msg in bad]


def tasks_page(api, project):
    tasks, _ = _tasks(project)
    rows = ["| Task | Host | Kind | Time limit | State | Last result |", "|---|---|---|---|---|---|"]
    rows += ["| %s | %s | %s | %s | %s | %s |" % (t.get("name"), t.get("host"), t.get("kind"), t.get("time_limit"),
                                                  t.get("state"), t.get("last_result")) for t in tasks]
    f = api.write_generated("systems/scheduled-tasks.md", "tasks", "\n".join(rows))
    print("wrote %s (%d tasks)" % (project.rel(f), len(tasks)))


def register(api):
    api.add_source("tasks", source)
    api.add_check(check)
    api.add_section("tasks", section, "Live tasks (inventory)")
    api.add_command("tasks-page", lambda sp: None, lambda project, args: tasks_page(api, project),
                    "write the live task table into wiki/systems/scheduled-tasks.md")


if __name__ == "__main__":                       # quick look: python plugins/tasks.py inventory/tasks.json
    import sys
    print("\n".join(" ".join(x) for x in _problems(json.loads(Path(sys.argv[1]).read_text()))))
