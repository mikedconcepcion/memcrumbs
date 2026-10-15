"""Readable names for offered skills, built from the steps' own names (`suggest_flow.step`): `test-scan-and-push`,
`push-and-watch-ci`, `tag-and-check-after-ci`, never a hash.

Each step gets a word from a small table (`unittest discover` → test, `gh run` → watch CI); a script gives its stem
(`export_public.py` → export public). Glue steps drop out when others carry the meaning: staging always, a commit
when a push follows, a push when a tag is pushed. Waiting for CI at the start reads "after CI". At most three
words (the first two and the last, which is usually the point), then "and"; the title is the same words as a
sentence. The step names are already the offer's evidence, so the name adds no other text."""
import re

WORDS = {
    "unittest discover": "test", "unittest": "test", "pytest": "test", "tox": "test", "nox": "test",
    "npm test": "test", "npm run test": "test", "go test": "test", "cargo test": "test", "dotnet test": "test",
    "memcrumbs scan": "scan", "memcrumbs check": "check the wiki", "memcrumbs index": "index",
    "memcrumbs bench": "bench", "memcrumbs update": "update memcrumbs",
    "ruff check": "lint", "flake8": "lint", "pylint": "lint", "eslint": "lint", "npm run lint": "lint",
    "mypy": "type-check", "black": "format", "ruff format": "format", "prettier": "format",
    "git add": "stage", "git commit": "commit", "git push": "push", "git tag": "tag", "git pull": "pull",
    "git fetch": "fetch", "git merge": "merge", "git rebase": "rebase", "git stash": "stash",
    "git checkout": "switch", "git switch": "switch",
    "gh run": "watch CI", "gh pr": "open a PR", "gh release": "release",
    "npm run build": "build", "make": "build", "cargo build": "build", "go build": "build", "docker build": "build",
    "docker compose": "compose", "docker push": "push the image", "pip install": "install", "npm install": "install",
    "twine upload": "publish", "npm publish": "publish", "kubectl apply": "deploy", "terraform apply": "apply",
    "terraform plan": "plan", "curl": "check", "Invoke-WebRequest": "check", "ssh": "ssh", "scp": "copy",
    "rsync": "sync",
}
GLUE = {"stage"}
WAIT = "watch CI"
MAX_WORDS = 3


def word(step):
    """The word for one step."""
    if step in WORDS:
        return WORDS[step]
    if step.endswith(".py"):
        return step[:-3].replace("_", " ").replace("-", " ")
    parts = step.split()
    if parts[:2] in (["npm", "run"], ["pnpm", "run"], ["yarn", "run"]) and len(parts) > 2:
        return parts[2].replace(":", " ")
    if parts[0] == "make" and len(parts) > 1:
        return parts[1]
    return step


def _words(steps):
    out = []
    for w in (word(s) for s in steps):
        if w not in out:
            out.append(w)
    keep = [w for w in out if w not in GLUE] or out
    if "push" in keep and "commit" in keep:
        keep.remove("commit")
    if "tag" in keep and "push" in keep and keep.index("push") > keep.index("tag"):
        keep.remove("push")
    after = len(keep) > 1 and keep[0] == WAIT
    keep = keep[1:] if after else keep
    if len(keep) > MAX_WORDS:                        # the last step is usually the point: release, push, deploy
        keep = keep[:MAX_WORDS - 1] + keep[-1:]
    return keep, after


def _join(ws):
    return ws[0] if len(ws) == 1 else "%s and %s" % (", ".join(ws[:-1]), ws[-1])


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-") or "procedure"


def readable(steps, used=()):
    """(name, title) for a run of steps; the name is unique among `used`."""
    ws, after = _words(steps)
    title = _join(ws) + (", after CI" if after else "")
    name = slug(" ".join(ws[:-1] + ["and", ws[-1]] if len(ws) > 1 else ws) + (" after ci" if after else ""))
    return unique(name, used), title[:1].upper() + title[1:]


def unique(name, used):
    base, n = name, 2
    while name in used:
        name, n = "%s-%d" % (base[:37], n), n + 1
    return name
