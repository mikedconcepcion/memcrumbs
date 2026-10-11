---
title: Rewrite the chat bot on a language model
summary: Trial of a generative language model for the student chat bot instead of keyword FAQ matching; rejected
verified: 2026-09-15
tags: [decision, chatbot]
status: rejected
sources: [repo/chatbot/bot.py, repo/chatbot/knowledge.py]
aliases: [AI assistant, generative bot, GPT-style replies]
---

# Rewrite the chat bot on a language model

## Question
Would a generative model answer student questions better than the keyword FAQ bot?

## What we tried
A two-week shadow run on 120 real questions: the model answered next to the FAQ bot, the operator graded both.

## Verdict
Rejected on 2026-06-15.

## Why
The model invented two policies (a refund window and a free glaze-firing offer) that do not exist. Money-related
answers must be exact. The FAQ bot got 104 of 120 right; the model 109 of 120 but with the invented policies.
It also needs a network call from web-srv and a paid key. See [[chat-bot]].
