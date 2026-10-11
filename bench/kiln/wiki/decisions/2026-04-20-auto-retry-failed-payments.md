---
title: Auto-retry failed card payments
summary: Proposal to retry declined or timed-out card charges automatically; rejected after the double-charge incident
verified: 2026-09-12
tags: [decision, payments]
status: rejected
sources: [repo/booking/payments.py]
aliases: [automatic retry, retry loop, dunning]
---

# Auto-retry failed card payments

## Question
Should the booking app silently retry a failed charge so fewer customers abandon checkout?

## What we tried
Modelled the last 90 days of declines: 31 failures, of which 24 were insufficient funds or expired cards that
a retry cannot fix. Prototyped a retry with backoff on a test provider account.

## Verdict
Rejected on 2026-04-20. A failed charge shows the customer a clear message and a button to try again.

## Why
Retries caused the [[2026-04-02-double-charge-on-retry]] incident and cost refunds. Only 3 of 31 failures were
transient. The customer must be the one to press retry. See [[payments]].
