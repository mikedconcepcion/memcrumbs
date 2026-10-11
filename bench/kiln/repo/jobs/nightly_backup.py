"""Nightly online backup of the local SQLite databases (the NightlyBackup task).

Uses sqlite3's backup API so services keep running, then verifies integrity and
prunes files older than the retention window (14 days).
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

RETENTION_DAYS = 14
BACKUP_DIR = Path("D:/emberline/backups")


def backup_one(db_path: Path, out_dir: Path = BACKUP_DIR) -> Path:
    """Copy ``db_path`` into ``out_dir`` as <name>-<YYYYMMDD>.db using the online backup API."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{db_path.stem}-{datetime.now():%Y%m%d}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    check = sqlite3.connect(target)
    result = check.execute("PRAGMA integrity_check").fetchone()[0]
    check.close()
    if result != "ok":
        raise RuntimeError(f"integrity check failed for {target}: {result}")
    return target


def prune(out_dir: Path = BACKUP_DIR, days: int = RETENTION_DAYS) -> int:
    """Delete backup files older than ``days``; returns how many were removed."""
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for f in out_dir.glob("*.db"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            removed += 1
    return removed


def main(argv: list[str]) -> int:
    """Back up every database path given on the command line."""
    for p in argv:
        print("backed up", backup_one(Path(p)))
    print("pruned", prune())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
