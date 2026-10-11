"""Refund logic. Refunds are real money and need explicit owner approval."""
import argparse
import sqlite3
from datetime import datetime, timezone


class RefundRefused(Exception):
    """Raised when a refund breaks a safety rule."""


def issue_refund(conn: sqlite3.Connection, client, booking_id: int, amount_cents: int,
                 reason: str, approved_by: str) -> int:
    """Refund a paid booking and record it in the refunds table.

    Refuses when ``approved_by`` is empty, when the amount exceeds what was paid,
    or when the booking already has a refund. Returns the new refund id.
    """
    if not approved_by:
        raise RefundRefused("owner approval is required (approved_by)")
    pay = conn.execute(
        "SELECT id, amount_cents, provider_ref FROM payments WHERE booking_id=? AND status='succeeded'",
        (booking_id,),
    ).fetchone()
    if pay is None:
        raise RefundRefused(f"no succeeded payment for booking {booking_id}")
    if amount_cents > pay["amount_cents"]:
        raise RefundRefused("refund exceeds the amount paid")
    if conn.execute("SELECT 1 FROM refunds WHERE payment_id=?", (pay["id"],)).fetchone():
        raise RefundRefused("booking was already refunded")
    result = client.refund(pay["provider_ref"], amount_cents)
    cur = conn.execute(
        "INSERT INTO refunds (payment_id, amount_cents, reason, approved_by, status, created_utc) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (pay["id"], amount_cents, reason, approved_by, result.get("status", "pending"),
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def main() -> None:
    """Command line entry used by the issue-refund runbook."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--booking", type=int, required=True)
    ap.add_argument("--amount-cents", type=int, required=True)
    ap.add_argument("--reason", required=True)
    ap.add_argument("--approved-by", default="")
    args = ap.parse_args()
    from .config import load_settings
    from .db import connect
    from .payments import PaymentClient

    cfg = load_settings()
    client = PaymentClient(cfg.provider_url, cfg.api_key, cfg.payment_timeout)
    print(issue_refund(connect(cfg.db_path), client, args.booking, args.amount_cents,
                       args.reason, args.approved_by))


if __name__ == "__main__":
    main()
