---
title: Inventory sync created duplicate glaze rows
summary: GlazeInventorySync ran twice after a manual start and doubled every glaze row in inventory.db
verified: 2026-09-22
tags: [incident, inventory, sync]
sources: [repo/jobs/inventory_sync.py, repo/db/inventory.sql]
aliases: [double glaze entries, duplicate stock]
---

# Inventory sync created duplicate glaze rows

## What happened
On 2026-09-14 the operator started `GlazeInventorySync` by hand at 01:05 and the schedule fired at 01:10. Every
glaze showed double stock the next morning.

## Root cause
The insert had no unique key on `supplier_sku`; two overlapping runs both inserted.

## Fix
Added a unique index and changed the job to upsert. Duplicates were marked `void`, not deleted ([[rules]]).

## Prevention
The job takes a lock file `inventory_sync.lock`. Machine notes: [[studio-srv]].
