"""Write firing records and temperature readings to firings.db."""
import sqlite3
from datetime import datetime, timezone


def now_utc() -> str:
    """ISO timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


def start_firing(conn: sqlite3.Connection, kiln_id: str, profile: str) -> int:
    """Insert a firings row and return its id."""
    cur = conn.execute(
        "INSERT INTO firings (kiln_id, profile, started_utc) VALUES (?, ?, ?)",
        (kiln_id, profile, now_utc()),
    )
    conn.commit()
    return cur.lastrowid


def log_reading(conn: sqlite3.Connection, firing_id: int, zone: int, temp_c: float,
                setpoint_c: float | None = None) -> None:
    """Record one reading; called once a minute by KilnTelemetryPoll."""
    conn.execute(
        "INSERT INTO readings (firing_id, ts_utc, zone, temp_c, setpoint_c) VALUES (?, ?, ?, ?, ?)",
        (firing_id, now_utc(), zone, temp_c, setpoint_c),
    )
    conn.commit()


def end_firing(conn: sqlite3.Connection, firing_id: int, outcome: str) -> None:
    """Close a firing with outcome complete, aborted or fault."""
    conn.execute("UPDATE firings SET ended_utc=?, outcome=? WHERE id=?", (now_utc(), outcome, firing_id))
    conn.commit()
