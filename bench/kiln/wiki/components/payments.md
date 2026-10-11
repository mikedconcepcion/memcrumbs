---
title: Payments
summary: How card charges and refunds work against the payment provider, idempotency keys, and where the API key is stored
verified: 2026-10-01
tags: [payments, booking, component]
sources: [repo/booking/payments.py, repo/booking/refunds.py, repo/booking/tests/test_payments.py]
aliases: [card processing, billing, checkout]
---

# Payments

- `repo/booking/payments.py` - `PaymentClient.charge_card()` posts to the provider; every charge carries an `Idempotency-Key` derived from the booking id.
- `repo/booking/refunds.py` - `issue_refund()` refuses to run without an `approved_by` value (owner approval, see [[rules]]).
- The provider API key is read from the machine environment variable `PAYPROV_API_KEY` on [[web-srv]]; rotation: [[rotate-payment-key]].
- Failed charges are **not** retried automatically: [[2026-04-20-auto-retry-failed-payments]].
- `PaymentReconcile` (06:00) compares provider payouts with the `payments` table and alerts on any mismatch.
- Past money incident: [[2026-04-02-double-charge-on-retry]]. Refund steps: [[issue-refund]].
- A second provider was parked: [[2026-09-20-second-payment-provider]].
