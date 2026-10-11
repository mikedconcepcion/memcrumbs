---
title: TLS certificate expired and the booking site went dark
summary: The public certificate lapsed after the proxy was reconfigured and the renewal check was left pointing at the old path
verified: 2026-09-30
tags: [incident, tls, web-srv]
sources: [repo/ops/Test-Health.ps1, repo/ops/Register-Tasks.ps1]
aliases: [https error, certificate expired, browser warning]
---

# TLS certificate expired

## What happened
On 2026-09-23 customers saw a browser security warning on the booking site for 90 minutes.

## Root cause
The edge proxy was moved to a new folder two weeks earlier; `CertRenewCheck` still looked at the old certificate path
and reported healthy.

## Fix
Renewed the certificate and pointed `CertRenewCheck` at the new path; it now alerts when fewer than 20 days remain.

## Prevention
After any proxy change run `Test-Health.ps1 -Target web -CheckCert`. See [[web-srv]] and [[scheduled-tasks]].
