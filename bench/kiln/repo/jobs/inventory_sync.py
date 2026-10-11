"""GlazeInventorySync: upsert glaze stock from the supplier CSV into inventory.db (01:10)."""
import csv
import os
import sqlite3

LOCK_FILE = "D:/emberline/data/inventory_sync.lock"


class AlreadyRunning(Exception):
    """Raised when another sync holds the lock file."""


def upsert_glaze(conn: sqlite3.Connection, sku: str, name: str, stock_kg: float) -> None:
    """Insert or update a glaze keyed by supplier_sku (unique index since 2026-09-14)."""
    conn.execute(
        "INSERT INTO glazes (supplier_sku, name, stock_kg) VALUES (?, ?, ?) "
        "ON CONFLICT(supplier_sku) DO UPDATE SET name=excluded.name, stock_kg=excluded.stock_kg",
        (sku, name, stock_kg),
    )


def sync(db_path: str, csv_path: str) -> int:
    """Read the supplier CSV and upsert every row; returns the row count."""
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AlreadyRunning("inventory sync already running") from exc
    try:
        conn = sqlite3.connect(db_path)
        count = 0
        with open(csv_path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                upsert_glaze(conn, row["sku"], row["name"], float(row["stock_kg"]))
                count += 1
        conn.commit()
        conn.close()
        return count
    finally:
        os.close(fd)
        os.remove(LOCK_FILE)
