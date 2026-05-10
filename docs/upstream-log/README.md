# Upstream Log

This directory holds the bookkeeping artifacts of the **daily-upstream-check** routine (see [`.claude/routines/daily-upstream-check.md`](../../.claude/routines/daily-upstream-check.md)).

## What lives here

- `state.json` — last-known versions of all monitored upstream packages. The routine reads and updates this every run.
- `YYYY-MM.md` — one file per calendar month, with one section per day. Each day records what the routine found (changes, no-changes, fetch failures).

## How to read

- Look at the latest `YYYY-MM.md` for the most recent run.
- Each line is one upstream source with its outcome.
- Lines that say `PR opened: #N` link to a PR the routine generated for adapter review.

## How to suspend

To pause the routine without deleting it, visit https://claude.ai/code/routines and toggle `enabled: false` on the daily-upstream-check routine.

## How to extend

To add a new upstream source, edit `.claude/routines/daily-upstream-check.md` and add a row to the "Sources to monitor" table. The routine picks up the change on its next run.
