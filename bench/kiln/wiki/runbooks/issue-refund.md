---
title: Issue a refund
summary: How to refund a customer booking after owner approval, using the refund function and recording the result
verified: 2026-10-06
tags: [runbook, refund, payments]
sources: [repo/booking/refunds.py, repo/booking/payments.py]
aliases: [give money back, reimburse customer, cancel with refund]
---

# Issue a refund

Real money. The owner must approve each booking id ([[rules]]).

1. Find the booking id and the original payment in `bookings.db` (`payments` table).
2. Get the owner written OK in the chat, with the amount.
3. On web-srv run `python -m booking.refunds --booking <id> --amount-cents <n> --reason <text> --approved-by owner`.
4. The function `issue_refund()` refuses amounts above the paid total and refuses a second refund of the same booking.
5. Check the `refunds` table row has status `succeeded`; if `pending`, check again in 10 minutes.
6. Tell the customer and journal it with `#refund` (booking id only, no card data).

Never delete the payment row ([[rules]]). Code: [[payments]].
