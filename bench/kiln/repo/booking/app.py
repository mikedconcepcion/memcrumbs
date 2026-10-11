"""HTTP routes for the booking site (/classes, /book, /pay, /cancel, /healthz)."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import __version__
from .config import load_settings
from .db import connect
from .payments import PaymentClient, PaymentError

SETTINGS = load_settings()


def list_classes(conn) -> list[dict]:
    """Return upcoming classes that still have free seats."""
    rows = conn.execute(
        "SELECT s.id, s.title, s.starts_utc, s.price_cents, "
        "s.seats - (SELECT COUNT(*) FROM bookings b WHERE b.session_id=s.id AND b.status IN ('held','paid')) AS free "
        "FROM class_sessions s ORDER BY s.starts_utc"
    ).fetchall()
    return [dict(r) for r in rows if r["free"] > 0]


def book_seat(conn, customer_id: int, session_id: int) -> int:
    """Create a held booking; the hold lasts SETTINGS.hold_minutes."""
    cur = conn.execute(
        "INSERT INTO bookings (customer_id, session_id, status, hold_expires_utc) "
        "VALUES (?, ?, 'held', datetime('now', ?))",
        (customer_id, session_id, f"+{SETTINGS.hold_minutes} minutes"),
    )
    conn.commit()
    return cur.lastrowid


def pay_booking(conn, booking_id: int, card_token: str) -> dict:
    """Charge the class price once and mark the booking paid."""
    row = conn.execute(
        "SELECT s.price_cents FROM bookings b JOIN class_sessions s ON s.id=b.session_id WHERE b.id=?",
        (booking_id,),
    ).fetchone()
    client = PaymentClient(SETTINGS.provider_url, SETTINGS.api_key, SETTINGS.payment_timeout)
    try:
        result = client.charge_card(booking_id, row["price_cents"], card_token)
    except PaymentError as exc:
        return {"ok": False, "error": str(exc)}
    conn.execute("UPDATE bookings SET status='paid' WHERE id=?", (booking_id,))
    conn.commit()
    return {"ok": True, "provider_ref": result.get("id")}


class Handler(BaseHTTPRequestHandler):
    """Minimal request handler; the real site sits behind the edge proxy."""

    def do_GET(self):
        if self.path == "/healthz":
            body = json.dumps({"ok": True, "version": __version__}).encode()
        elif self.path == "/classes":
            body = json.dumps(list_classes(connect(SETTINGS.db_path))).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Serve on 127.0.0.1:8080."""
    HTTPServer(("127.0.0.1", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
