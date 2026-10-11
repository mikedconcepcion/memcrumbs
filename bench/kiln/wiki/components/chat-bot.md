---
title: Student chat bot
summary: Rule-based FAQ assistant for students on web-srv that answers from a knowledge file and a cached price table
verified: 2026-09-25
tags: [chatbot, component]
sources: [repo/chatbot/bot.py, repo/chatbot/knowledge.py, repo/chatbot/prices.py]
aliases: [assistant, student bot, faq bot]
---

# Student chat bot

Runs as `ChatBot` on [[web-srv]], port 8091, health at `/ping`. It is deliberately not an LLM; see [[2026-06-15-llm-chatbot-rewrite]].

## Code map
- `repo/chatbot/bot.py` - `answer(question)`: keyword scoring over FAQ entries, fallback to "ask the studio".
- `repo/chatbot/knowledge.py` - loads `knowledge/faq.json`, `reload()`.
- `repo/chatbot/prices.py` - `PriceCache` with a 10-minute TTL, read from `bookings.db` class prices.

## Operations
- `ChatKnowledgeRefresh` (04:00) calls `reload()`.
- Stale answers after a price change: see [[2026-09-02-chatbot-stale-prices]].
