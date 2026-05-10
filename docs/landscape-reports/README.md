# Landscape Reports

This directory holds the weekly research artifacts of the **weekly-landscape-scan** routine (see [`.claude/routines/weekly-landscape-scan.md`](../../.claude/routines/weekly-landscape-scan.md)).

## What lives here

- `YYYY-MM-DD.md` — one file per scan run. Captures the AI-coding-tool landscape that week, ranks discoveries, and identifies candidates worth integrating.

## How to read

- Sort files by date (filename is the scan date).
- Each report opens with the scan window + a count of action candidates.
- Action candidates link to draft integration specs in `../superpowers/specs/`.

## Workflow when a candidate appears

1. Open the linked draft spec.
2. Review the integration mechanism, effort estimate, and open questions.
3. If it makes sense, promote the spec from `DRAFT` status by running through the brainstorming + writing-plans skills with a human.
4. Otherwise, dismiss the GitHub issue (`integration-proposal` label) — the routine won't re-suggest it for at least 30 days.

## How to suspend

To pause the routine, visit https://claude.ai/code/routines and toggle `enabled: false`.

## How to tune

To adjust the scoring thresholds or sources, edit `.claude/routines/weekly-landscape-scan.md`.
