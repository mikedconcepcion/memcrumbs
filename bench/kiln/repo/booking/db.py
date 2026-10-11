"""SQLite connection helper for bookings.db."""
import sqlite3


def connect(path: str, busy_timeout_ms: int = 5000) -> sqlite3.Connection:
    """Open bookings.db in WAL mode with a busy timeout.

    WAL mode was accepted in decision 2026-05-05 so readers never block the nightly writers.
    """
    conn = sqlite3.connect(path, timeout=busy_timeout_ms / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def void_booking(conn: sqlite3.Connection, booking_id: int) -> None:
    """Mark a booking void. Production rows are never deleted (standing rule)."""
    conn.execute("UPDATE bookings SET status='void' WHERE id=?", (booking_id,))
    conn.commit()
