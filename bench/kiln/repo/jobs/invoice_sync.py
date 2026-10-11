"""InvoiceSync: export yesterday's paid bookings as invoice rows for the accountant (03:10)."""
import csv
import sqlite3
from datetime import date, timedelta

EXPORT_DIR = "D:/emberline/exports"


def paid_since(conn: sqlite3.Connection, day: date):
    """Return payments that succeeded on ``day`` (UTC date)."""
    return conn.execute(
        "SELECT p.id, p.booking_id, p.amount_cents, c.name, c.email "
        "FROM payments p JOIN bookings b ON b.id=p.booking_id JOIN customers c ON c.id=b.customer_id "
        "WHERE p.status='succeeded' AND date(b.hold_expires_utc)=?",
        (day.isoformat(),),
    ).fetchall()


def sync_invoices(db_path: str, day: date | None = None) -> str:
    """Write ``invoices-<day>.csv`` and return its path."""
    day = day or date.today() - timedelta(days=1)
    conn = sqlite3.connect(db_path)
    rows = paid_since(conn, day)
    conn.close()
    out = f"{EXPORT_DIR}/invoices-{day.isoformat()}.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["payment_id", "booking_id", "amount_cents", "name", "email"])
        w.writerows(rows)
    return out
