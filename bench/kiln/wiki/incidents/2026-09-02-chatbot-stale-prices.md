---
title: Chat bot quoted old class prices
summary: Students were told the old class price for two days after a price rise because the bot cached the price table
verified: 2026-09-25
tags: [incident, chatbot, prices]
sources: [repo/chatbot/prices.py, repo/chatbot/knowledge.py]
aliases: [bot gave wrong price, outdated answers, cache not refreshed]
---

# Chat bot quoted old class prices

## What happened
Prices rose on 2026-09-01. Until 09-03 the bot still answered 60 for a wheel class instead of 68. Two students
arrived with the old amount.

## Root cause
`PriceCache` loaded prices once at start and never expired; the daemon had been up for weeks.

## Fix
`PriceCache` now has a 10-minute TTL and `ChatKnowledgeRefresh` reloads the FAQ file at 04:00.

## Prevention
After any price change ask the operator to call the bot `/reload` endpoint on port 8091. See [[chat-bot]].
