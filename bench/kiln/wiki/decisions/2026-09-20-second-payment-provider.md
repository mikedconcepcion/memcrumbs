---
title: Add a second payment provider
summary: Idea to add a backup payment provider for outages; parked until the first provider causes another outage
verified: 2026-09-21
tags: [decision, payments]
status: parked
sources: [repo/booking/payments.py]
aliases: [fallback provider, payment redundancy]
---

# Add a second payment provider

## Question
Should checkout fall back to another provider when the main one is down?

## What we tried
Read the other provider docs and sketched an adapter around `PaymentClient`. No code merged.

## Verdict
Parked on 2026-09-20. Revisit if the main provider has more than two outages in a quarter.

## Why
One outage in 2026 so far, 40 minutes. A second provider doubles reconciliation work in `PaymentReconcile`
and needs a second key to rotate ([[rotate-payment-key]]). See [[payments]].
