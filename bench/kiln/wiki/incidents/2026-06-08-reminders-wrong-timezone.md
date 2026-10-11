---
title: Class reminders sent at the wrong hour
summary: Reminder emails went out two hours early or late because naive local times were mixed with a UTC server clock
verified: 2026-09-03
tags: [incident, reminders, time-zone]
sources: [repo/booking/reminders.py, repo/booking/models.py]
aliases: [timezone bug, daylight saving, reminder time off]
---

# Class reminders sent at the wrong hour

## What happened
On 2026-06-08 students received the "your class is tomorrow at 18:00" email saying 16:00. Some got the reminder
two hours late. Four people missed the start of a wheel class.

## Root cause
`reminders.py` built `class_start` from a naive datetime in studio local time and compared it with
`datetime.utcnow()` on web-srv, which runs in UTC. After the spring clock change the offset became two hours.

## Fix
Store all times as aware UTC; `render_local()` converts to the studio zone only when formatting.
A unit test pins a class on both sides of the clock change.

## Prevention
Never call `utcnow()` or `now()` without a zone in booking code. Component notes: [[booking-app]].
