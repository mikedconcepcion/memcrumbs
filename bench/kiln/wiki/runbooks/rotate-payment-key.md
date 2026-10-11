---
title: Rotate the payment provider API key
summary: Steps to replace the payment API key, which lives only in a machine environment variable on web-srv
verified: 2026-09-18
tags: [runbook, payments, secrets]
sources: [repo/booking/config.py, repo/booking/payments.py]
aliases: [change api key, renew payment credentials]
---

# Rotate the payment provider API key

The key lives only in the machine-level environment variable `PAYPROV_API_KEY` on [[web-srv]]. It is
never in the repo, in `booking.toml` or in the wiki.

1. Owner creates a new key in the provider dashboard (restricted to charges and refunds).
2. Owner hands the key over out-of-band, never in chat or a file in the repo.
3. On web-srv run `setx /M PAYPROV_API_KEY <new key>` in an elevated session.
4. Restart `BookingWeb` (see [[deploy-booking]] step 5 for the restart command).
5. Make a 1.00 test charge on the test class and refund it ([[issue-refund]]).
6. Owner revokes the old key in the dashboard.
7. Journal the rotation without the value.

Example of a mistake to avoid: a leaked test-mode key pasted into an old note looked like this:
api_key: 3bR7NcY2xLk9WqH5tVd8PzJ4mFs1GaE6 <!-- memcrumbs:allow -->

See [[payments]].
