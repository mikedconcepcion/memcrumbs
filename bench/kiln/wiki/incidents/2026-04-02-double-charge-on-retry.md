---
title: Customers charged twice after a payment timeout
summary: Eleven customers were charged twice when the booking app retried a timed-out card charge without an idempotency key
verified: 2026-09-08
tags: [incident, payments, money]
sources: [repo/booking/payments.py, repo/booking/refunds.py]
aliases: [duplicate charge, charged two times]
---

# Customers charged twice

## What happened
On 2026-04-02 the payment provider was slow for 40 minutes. The booking app timed out, retried, and the provider
had completed the first call. Eleven customers saw two charges of the class price.

## Root cause
`charge_card()` retried up to three times and generated a new random request id on each attempt, so the provider
could not recognise duplicates.

## Fix
The owner approved refunds for all eleven duplicates ([[issue-refund]]). `charge_card()` now sends an `Idempotency-Key`
built from the booking id and has no retry loop at all. See [[2026-04-20-auto-retry-failed-payments]].

## Prevention
`PaymentReconcile` at 06:00 flags booking ids with more than one successful charge. Details in [[payments]].
