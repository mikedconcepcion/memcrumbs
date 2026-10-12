"""Day 0 on any repo: what `memcrumbs init` alone gives (no wiki page written), measured with blind questions.

    python scripts/day0.py <repo> <questions.toml> [--memcrumbs memcrumbs] [--json out.json]

1. `memcrumbs init --no-wire` in the repo, with a temporary projects folder: the repo is not touched.
2. `memcrumbs bench` with the questions: recall@1/@3, MRR and tokens per `find` answer (characters / 4).
3. For comparison, the file that answers each question read whole (the cheapest one when several do): what an
   agent pays for opening exactly the right file, before it reads anything else.

Questions use the bench format (`[[q]] id, q, expect = ["path/in/repo"]`); write them without looking at how
memcrumbs searches."""
import argparse
import json
import os
import shlex
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path


def run(argv, env, cwd):
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=cwd)
    if r.returncode not in (0, 1):
        raise SystemExit("%s failed (%d): %s" % (" ".join(argv), r.returncode, r.stderr or r.stdout))
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo")
    ap.add_argument("questions")
    ap.add_argument("--memcrumbs", default="memcrumbs", help="the command to run, e.g. \"python -m memcrumbs\" "
                    "(default: memcrumbs on PATH)")
    ap.add_argument("--json", help="write the full result here")
    a = ap.parse_args()
    repo, questions = Path(a.repo).resolve(), Path(a.questions).resolve()
    import tomllib
    qs = tomllib.loads(questions.read_text(encoding="utf-8"))["q"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        env = {k: v for k, v in os.environ.items() if not k.startswith("MEMCRUMBS_") and k != "CLAUDECODE"}
        env["MEMCRUMBS_PROJECTS"] = d
        mc = shlex.split(a.memcrumbs, posix=False)
        print(run(mc + ["init", "--no-wire"], env, repo).strip())
        name = next(p.name for p in Path(d).iterdir() if (p / "memcrumbs.toml").exists())
        version = run(mc + ["--version"], env, repo).strip()
        bench = json.loads(run(mc + ["-p", name, "bench", str(questions), "--json", "--full"], env, repo))
    whole = []
    for q in qs:
        sizes = [len((repo / e.split("#")[0]).read_text(encoding="utf-8", errors="replace")) // 4
                 for e in q["expect"] if (repo / e.split("#")[0]).is_file()]
        whole.append(min(sizes) if sizes else None)
    t = bench["total"]
    files = [w for w in whole if w]
    result = dict(repo=str(repo), commit=run(["git", "-C", str(repo), "rev-parse", "HEAD"], env, repo).strip(),
                  memcrumbs=version, questions=len(qs), bench=t, by_category=bench.get("by_category"),
                  file_tokens_median=int(statistics.median(files)) if files else None,
                  file_tokens_mean=round(sum(files) / len(files)) if files else None,
                  misses=[(r["id"], r["rank"], r["q"], r["top3"]) for r in bench.get("questions", [])
                          if not r["rank"] or r["rank"] > 3])
    print("%s · %s @ %s · %d questions" % (version, repo.name, result["commit"][:8], len(qs)))
    print("recall@1 %.3f · recall@3 %.3f · MRR %.3f" % (t["recall_at_1"], t["recall_at_3"], t["mrr"]))
    print("tokens per find answer: mean %d, p95 %d" % (t["tokens_mean"], t["tokens_p95"]))
    print("the answering file read whole: median %s, mean %s tokens" % (result["file_tokens_median"],
                                                                        result["file_tokens_mean"]))
    for c, s in sorted((result["by_category"] or {}).items()):
        print("  %-10s n=%-3d r@1 %.2f  r@3 %.2f" % (c, s["n"], s["recall_at_1"], s["recall_at_3"]))
    for m in result["misses"]:
        print("  miss %s (rank %s): %s → %s" % (m[0], m[1] or "-", m[2], ", ".join(m[3]) or "no hits"))
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
