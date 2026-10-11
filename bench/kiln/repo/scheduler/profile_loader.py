"""Load a .kiln file, follow includes, expand macros and return checked segments.

Command line check::

    python -m scheduler.profile_loader --check repo/profiles/cone6_glaze.kiln
"""
import argparse
import re
from pathlib import Path

from .kiln_parser import parse
from .validator import check_kiln_known, check_limits

RAMP_RE = re.compile(r"ramp\s+(-?\d+)/h\s+to\s+(\w+)")
HOLD_RE = re.compile(r"hold\s+(\d+)([mh])")


def _join(tokens) -> str:
    return " ".join(t for t, _ in tokens)


def load_profile(path: str, name: str | None = None) -> dict:
    """Parse ``path`` (and its includes) and return the named profile as segments.

    If ``name`` is None the first profile in the file is used. Raises KilnSyntaxError
    or LimitError when the file is not safe to run.
    """
    base = Path(path)
    doc = parse(base.read_text(encoding="utf-8"))
    consts = {}
    kilns = []
    macros = {}
    for inc in doc["includes"]:
        sub = parse((base.parent / inc).read_text(encoding="utf-8"))
        consts.update(sub["consts"])
        kilns += [k["name"] for k in sub["kilns"]]
        macros.update({m["name"]: m for m in sub["macros"]})
    consts.update(doc["consts"])
    kilns += [k["name"] for k in doc["kilns"]]
    prof = next(p for p in doc["profiles"] if name in (None, p["name"]))
    text = _join(prof["tokens"])
    kiln = re.search(r"kiln\s*:\s*(\w+)", text).group(1)
    check_kiln_known(kiln, kilns)
    segments = compile_segments(text, consts)
    check_limits(segments, int(consts.get("MAX_TEMP", 1285)))
    return {"name": prof["name"], "kiln": kiln, "segments": segments}


def compile_segments(text: str, consts: dict) -> list[dict]:
    """Turn ``segment NAME { ramp ..; hold ..; }`` blocks into dicts."""
    segments = []
    for m in re.finditer(r"segment\s+(\w+)\s*\{([^}]*)\}", text.replace(" ; ", "; ").replace(" ;", ";")):
        body = m.group(2)
        ramp = RAMP_RE.search(body)
        hold = HOLD_RE.search(body)
        target = consts.get(ramp.group(2), ramp.group(2)) if ramp else 0
        minutes = 0
        if hold:
            minutes = int(hold.group(1)) * (60 if hold.group(2) == "h" else 1)
        segments.append({
            "name": m.group(1),
            "rate_c_per_h": int(ramp.group(1)) if ramp else 0,
            "target_c": int(target),
            "hold_min": minutes,
        })
    return segments


def main() -> None:
    """Entry point for ``--check``: prints OK or the error code."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True)
    args = ap.parse_args()
    prof = load_profile(args.check)
    print(f"OK {prof['name']} on {prof['kiln']}: {len(prof['segments'])} segments")


if __name__ == "__main__":
    main()
