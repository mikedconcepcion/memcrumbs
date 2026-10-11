"""Fresh clone to first useful answer: run the README quick start, in order, in a throwaway
home, and fail if any step errors, prints nothing useful, or the whole thing takes over 2 minutes.

    python scripts/quickstart.py            # uses the installed `memcrumbs`
    python scripts/quickstart.py --venv     # times it all from scratch: new venv, pip install ., the steps"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT_S = 120


def main():
    sys.stdout.reconfigure(errors="replace")                   # a failure's output prints on any console
    t0 = time.time()
    path = os.environ.get("PATH", "")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        home = Path(d)
        exe = shutil.which("memcrumbs")
        if "--venv" in sys.argv:
            subprocess.run([sys.executable, "-m", "venv", str(home / "venv")], check=True)
            bindir = home / "venv" / ("Scripts" if os.name == "nt" else "bin")
            subprocess.run([str(bindir / "python"), "-m", "pip", "install", "-q", str(ROOT)], check=True)
            exe = str(bindir / ("memcrumbs.exe" if os.name == "nt" else "memcrumbs"))
            path = str(bindir) + os.pathsep + path               # installed: on PATH, as the session hook needs
            print("installed into a fresh venv in %.1f s" % (time.time() - t0))
        repo = home / "code" / "myapp"
        shutil.copytree(ROOT / "examples" / "hello-src", repo)
        env = dict(os.environ, MEMCRUMBS_PROJECTS=str(home / "projects"), HOME=str(home), USERPROFILE=str(home),
                   PATH=path)
        env.pop("MEMCRUMBS_PROJECT", None)
        exe = exe or sys.exit("memcrumbs is not on PATH: pip install . first, or use --venv")
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)          # a repo, as yours is
        steps = [  # the README quick start, run inside the repo; --yes is the one keypress `init` asks for
            (["init", "--yes"], "created myapp"),
            (["doctor"], "0 fail"),
            (["log", "rotated the API key", "--tag", "ops"], "logged"),
            (["decision", "Move bookings to Postgres", "--status", "rejected", "--why", "too much to run for our size"],
             "wrote"),
            (["incident", "Nightly task died after 72 h", "--symptom", "no reports since Tuesday", "--cause",
              "task time limit"], "wrote"),
            (["check"], "findings"),
            (["find", "load config"], "app.py"),            # what the agent then does
            (["outline", str(repo / "app.py")], "def load_config"),
            (["status"], "memcrumbs · "),
            (["scan", str(repo)], "0 secret-like hits"),
            (["init", "--remove"], "unwired"),
        ]
        for argv, expect in steps:
            r = subprocess.run([exe] + argv, env=env, cwd=str(repo), capture_output=True, text=True, encoding="utf-8")
            ok = expect in r.stdout and not r.stderr.strip()
            print("%s memcrumbs %s" % ("ok  " if ok else "FAIL", " ".join(argv[:4])))
            if not ok:
                print(r.stdout[-1500:], r.stderr[-1500:], sep="\n")
                return 1
    took = time.time() - t0
    print("quick start: %d steps in %.1f s (limit %d s)" % (len(steps), took, LIMIT_S))
    return 0 if took <= LIMIT_S else 1


if __name__ == "__main__":
    sys.exit(main())
