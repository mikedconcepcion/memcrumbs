"""Class reminder emails, run every 15 minutes by the ReminderMailer task."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def render_local(when_utc: datetime, tz_name: str) -> str:
    """Format an aware UTC time in the studio zone, e.g. '18:00'.

    Fix for the 2026-06-08 incident: times are stored in UTC and converted only here.
    """
    if when_utc.tzinfo is None:
        raise ValueError("naive datetime not allowed; store UTC with tzinfo")
    return when_utc.astimezone(ZoneInfo(tz_name)).strftime("%H:%M")


def due_sessions(conn, now_utc: datetime | None = None, lead_hours: int = 24):
    """Return bookings whose class starts within ``lead_hours`` and have no reminder yet."""
    now_utc = now_utc or datetime.now(timezone.utc)
    horizon = now_utc + timedelta(hours=lead_hours)
    return conn.execute(
        "SELECT b.id, c.email, s.title, s.starts_utc FROM bookings b "
        "JOIN customers c ON c.id=b.customer_id JOIN class_sessions s ON s.id=b.session_id "
        "WHERE b.status='paid' AND b.reminder_sent=0 AND s.starts_utc<=? AND s.starts_utc>?",
        (horizon.isoformat(), now_utc.isoformat()),
    ).fetchall()


def build_message(row, tz_name: str) -> str:
    """Compose the plain-text reminder body."""
    start = datetime.fromisoformat(row["starts_utc"])
    return f"Hello! Your class '{row['title']}' starts tomorrow at {render_local(start, tz_name)}."
