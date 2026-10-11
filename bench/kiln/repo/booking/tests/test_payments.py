"""Tests for the payment client (no network)."""
import unittest

from booking.payments import PaymentClient, PaymentError

# Test fixture only: a made-up key, never valid anywhere.
FIXTURE_API_KEY = "9fK2LmQx7Tz4WpB8cN3vH6yD1sA5gE0r"  # memcrumbs:allow


class PaymentClientTests(unittest.TestCase):
    def test_idempotency_key_is_stable(self):
        a = PaymentClient.idempotency_key(4112, 6800)
        b = PaymentClient.idempotency_key(4112, 6800)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 32)

    def test_different_booking_gives_different_key(self):
        self.assertNotEqual(PaymentClient.idempotency_key(1, 6800), PaymentClient.idempotency_key(2, 6800))

    def test_missing_key_raises(self):
        with self.assertRaises(PaymentError):
            PaymentClient("https://pay.provider.example/v1", "")

    def test_client_accepts_fixture_key(self):
        client = PaymentClient("https://pay.provider.example/v1/", FIXTURE_API_KEY)
        self.assertEqual(client.base_url, "https://pay.provider.example/v1")


if __name__ == "__main__":
    unittest.main()
