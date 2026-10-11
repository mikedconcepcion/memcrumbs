"""Card payments against the payment provider.

Rules learned the hard way: every charge carries an idempotency key built from the
booking id, and a failed charge is never retried automatically (see wiki decisions
2026-04-20 and incident 2026-04-02).
"""
import hashlib
import json
import urllib.request


class PaymentError(Exception):
    """Raised when the provider rejects or fails a charge."""


class PaymentClient:
    """Thin client for the provider HTTP API."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 15):
        if not api_key:
            raise PaymentError("PAYPROV_API_KEY is not set on this machine")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout = timeout

    @staticmethod
    def idempotency_key(booking_id: int, amount_cents: int) -> str:
        """Stable key so the provider can recognise a duplicate of the same charge."""
        digest = hashlib.sha256(f"booking:{booking_id}:{amount_cents}".encode()).hexdigest()
        return digest[:32]

    def charge_card(self, booking_id: int, amount_cents: int, card_token: str) -> dict:
        """Charge a tokenised card once. Does NOT retry; the customer presses retry."""
        body = json.dumps({"amount": amount_cents, "card": card_token}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/charges",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Idempotency-Key": self.idempotency_key(booking_id, amount_cents),
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp)
        except OSError as exc:
            raise PaymentError(f"charge failed for booking {booking_id}: {exc}") from exc

    def refund(self, provider_ref: str, amount_cents: int) -> dict:
        """Ask the provider to refund part or all of a charge (owner approval checked by the caller)."""
        body = json.dumps({"charge": provider_ref, "amount": amount_cents}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/refunds", data=body, method="POST",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp)
        except OSError as exc:
            raise PaymentError(f"refund failed for {provider_ref}: {exc}") from exc
