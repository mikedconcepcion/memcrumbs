---
title: Hello API service
summary: the HTTP API — where it runs, how to deploy, restart and roll back
verified: 2026-10-10
tags: [api, ops]
sources: [hello-src/app.py]
---
# Hello API service

## Where it runs
- Host `web-01`, port 8080, behind the proxy. Secrets: the API key lives in `/etc/hello/env` (never in the wiki).

## Deploy
1. Copy the build, keep the previous one as `app.prev`.
2. Restart the service, then check `GET /health`.

## Rollback
- Swap `app.prev` back and restart. Takes ~10 s.

## History
- 2026-10-10 — page created (example).
