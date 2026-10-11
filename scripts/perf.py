"""Speed targets on a generated repo: full index of N files, incremental refresh, find, header.

    python scripts/perf.py [--files 10000] [--json out.json] [--check]

Builds an invented project in a temp folder (wiki pages + Python/PowerShell/markdown code files), then times
each command both in-process (memcrumbs' own work) and as a fresh process (what an agent's shell sees,
including interpreter start-up). --check exits 1 if a target is missed."""
import argparse
import math
import contextlib
import io
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TARGETS = {"full_index_s": 30.0, "incremental_s": 0.5, "find_ms": 150.0, "header_p95_ms": 1000.0}
WORDS = ("deploy restart service config rollback api backup worker queue retry cache disk invoice payment kiln "
         "scheduler timeout lock token report export import sync mail alert health probe".split())


def build(root, files, seed=7):
    rng = random.Random(seed)
    projects, repo = root / "projects", root / "repo"
    wiki = projects / "big" / "wiki"
    wiki.mkdir(parents=True)
    (projects / "big" / "memcrumbs.toml").write_text('name = "big"\nrepos = ["../../repo"]\n', encoding="utf-8")
    pages = max(50, files // 50)
    for i in range(pages):
        w = rng.sample(WORDS, 4)
        (wiki / ("p%04d.md" % i)).write_text(
            "---\ntitle: %s %s %d\nsummary: %s\nverified: 2026-10-01\n---\n# %s\n## %s\n%s\n## Notes\n%s\n" % (
                w[0], w[1], i, " ".join(w), w[0], w[2], " ".join(rng.choices(WORDS, k=60)),
                " ".join(rng.choices(WORDS, k=40))), encoding="utf-8")
    for i in range(files - pages):
        d = repo / ("pkg%03d" % (i % 200))
        d.mkdir(parents=True, exist_ok=True)
        w = rng.sample(WORDS, 3)
        if i % 5 == 0:
            (d / ("Ops%05d.ps1" % i)).write_text("".join(
                "function Invoke-%s%d {\n    param($x)\n    # %s\n    if ($x) { 'ok' }\n}\n\n" % (w[k].title(), k, " ".join(w))
                for k in range(3)), encoding="utf-8")
        else:
            (d / ("m%05d.py" % i)).write_text('"""%s module."""\n\n' % " ".join(w) + "".join(
                'def %s_%s_%d(a, b=1):\n    """%s %s."""\n    return a + b\n\n\nclass %s%d:\n    def run(self):\n'
                '        return %d\n\n\n' % (w[k], w[(k + 1) % 3], k, w[k], w[2], w[k].title(), k, k) for k in range(3)),
                encoding="utf-8")
    return projects


def inproc(argv):
    from memcrumbs import cli
    t = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            cli.main(argv)
        except SystemExit:
            pass
    return (time.perf_counter() - t) * 1000


def proc(argv, env):
    t = time.perf_counter()
    subprocess.run([sys.executable, "-m", "memcrumbs"] + argv, env=env, capture_output=True, cwd=str(ROOT))
    return (time.perf_counter() - t) * 1000


def p95(xs):
    xs = sorted(xs)
    return xs[max(0, math.ceil(0.95 * len(xs)) - 1)]          # nearest rank: of 20 samples, the 19th


TREND = ("full_index_s", "incremental_s", "find_ms", "find_p95_ms", "find_process_ms", "header_p95_ms")


def slower(old, new, by=0.25):
    """{metric: (last, now)} for timings more than `by` slower than the last run (same files count only). Two runs of
    the same code on one Windows machine differed by 28 % in `find` median (61 → 78 ms), so the default is 25 %."""
    if old.get("files") != new.get("files"):
        return {}
    return {k: (old[k], new[k]) for k in TREND if isinstance(old.get(k), (int, float)) and old[k] > 0
            and new.get(k, 0) > old[k] * (1 + by)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", type=int, default=10000)
    ap.add_argument("--json", help="write the result here (and compare with the result already there)")
    ap.add_argument("--against", help="a previous --json result to compare with (default: the --json file)")
    ap.add_argument("--slower", type=float, default=25.0, help="flag timings this many percent slower (default 25)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        projects = build(Path(d), a.files)
        os.environ["MEMCRUMBS_PROJECTS"] = str(projects)
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        r = {"files": a.files, "platform": sys.platform, "python": sys.version.split()[0]}
        r["full_index_cold_s"] = round(inproc(["-p", "big", "index", "--full"]) / 1000, 2)   # just-written files:
        runs = [round(inproc(["-p", "big", "index", "--full"]) / 1000, 2) for _ in range(2)]  # AV scans them once
        r["full_index_runs_s"] = runs
        r["full_index_s"] = min(runs)        # best of two: a shared CI runner varied 15-31 s between full indexes
        r["incremental_s"] = round(statistics.median(inproc(["-p", "big", "index"]) for _ in range(5)) / 1000, 3)
        page = projects / "big" / "wiki" / "p0001.md"
        page.write_text(page.read_text(encoding="utf-8") + "\nedited\n", encoding="utf-8")
        r["incremental_one_change_s"] = round(inproc(["-p", "big", "index"]) / 1000, 3)
        qs = ["deploy rollback", "where is the payment retry function", "kiln scheduler timeout", "cache lock",
              "how do I restart the worker service", "export report mail", "health probe alert", "sync invoice"]
        inproc(["-p", "big", "find", "warm"])
        finds = [inproc(["-p", "big", "find", q]) for q in qs * 3]
        r["find_ms"] = round(statistics.median(finds), 1)
        r["find_p95_ms"] = round(p95(finds), 1)
        r["find_process_ms"] = round(statistics.median(proc(["-p", "big", "find", q], env) for q in qs), 1)
        heads = [proc(["-p", "big", "status", "--hook"], env) for _ in range(20)]
        r["header_p95_ms"] = round(p95(heads), 1)
        r["python_startup_ms"] = round(statistics.median(
            (lambda t: (subprocess.run([sys.executable, "-c", "pass"]), (time.perf_counter() - t) * 1000)[1])(
                time.perf_counter()) for _ in range(5)), 1)
    miss = {k: (r[k], v) for k, v in TARGETS.items() if r[k] > v}
    r["targets"] = TARGETS
    r["missed"] = miss
    last = a.against or a.json
    if last and Path(last).is_file():                # say when this build is slower than the last one
        r["slower_than_last"] = slower(json.loads(Path(last).read_text(encoding="utf-8")), r, a.slower / 100)
    print(json.dumps(r, indent=1))
    for k, (old, new) in (r.get("slower_than_last") or {}).items():
        print("slower than the last run: %s %s -> %s (+%d%%)" % (k, old, new, round(100 * (new / old - 1))))
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1), encoding="utf-8")
    return 1 if a.check and miss else 0


if __name__ == "__main__":
    sys.exit(main())
