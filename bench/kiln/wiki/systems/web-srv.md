---
title: web-srv
summary: Windows server that hosts the public booking website with card payments, the student chat bot and the nightly jobs
verified: 2026-10-02
tags: [systems, web-srv, booking]
sources: [repo/ops/Deploy-Booking.ps1, repo/config/booking.toml, repo/db/bookings.sql]
aliases: [web server, public server]
---

# web-srv

Hosts everything customers and students touch. SSH on port 22, private network only.

## What runs here
- `BookingWeb` - the booking app on 127.0.0.1:8080, published as https on 443 by the edge proxy. See [[booking-app]].
- `ChatBot` - student assistant on port 8091. See [[chat-bot]].
- `NightlyBackup` 02:30, `InvoiceSync` 03:10, `ReminderMailer` every 15 min, `PaymentReconcile` 06:00. See [[scheduled-tasks]].

## Data and secrets
- `D:\emberline\data\bookings.db` - bookings, customers, payments, refunds.
- Releases live in `D:\emberline\booking\releases\<version>`; `D:\emberline\booking\current` is a junction to the live one.
- The payment provider API key is a machine-level environment variable `PAYPROV_API_KEY`. See [[rotate-payment-key]] and [[payments]].
- Logs: `D:\emberline\logs`, rotated weekly (see [[2026-08-16-disk-full-web-srv]]).

## Health check
`repo/ops/Test-Health.ps1 -Target web` calls `http://127.0.0.1:8080/healthz` and the chat bot `/ping`.
Deploys must follow [[deploy-booking]] and need owner approval ([[rules]]).
