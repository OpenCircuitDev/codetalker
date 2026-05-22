# Market Analysis — CodeTalker
_Generated 2026-05-21_ · _50 virtual users_ · _Model: anthropic/claude-haiku-4.5_

## Methodology

50 vibe-developer personas generated in 10 batches of 5 (each batch focused on a different archetype — beginners, power users, non-CS founders, etc.). Each persona was shown the product description, webui description, cadence behavior, and 10 real narrations sampled from `~/.claude/scripts/codetalker/narration-log.jsonl`. They scored 7 dimensions on a 1-5 scale and answered 4 open-ended questions, in character.

## Executive summary

- **NPS score: -2.0** (0 promoters · 49 passives · 1 detractors)
- **Would subscribe to Pro: 22/50 (44%)**
- **Strongest dimension**: decision_helpfulness (mean 4.3/5)
- **Weakest dimension**: feature_completeness (mean 3.52/5)

## Dimension scores

| Dimension | Mean | Median | Stdev | Min-Max | n |
|---|---:|---:|---:|---:|---:|
| clarity | 4 | 4.0 | 0.0 | 4-4 | 50 |
| decision_helpfulness | 4.3 | 5.0 | 0.84 | 3-5 | 50 |
| cadence | 4.04 | 4.0 | 0.4 | 3-5 | 50 |
| freshness | 4.28 | 4.0 | 0.45 | 4-5 | 50 |
| relatability | 3.6 | 4.0 | 0.61 | 3-5 | 50 |
| ui_usability | 3.86 | 4.0 | 0.35 | 3-4 | 50 |
| feature_completeness | 3.52 | 4.0 | 0.5 | 3-4 | 50 |

## Cohort breakdown (mean by vibe-experience tier)

| Tier (n) | clarity | decision_helpfulness | cadence | freshness | relatability | ui_usability | feature_completeness |
|---|---:|---:|---:|---:|---:|---:|---:|
| fresh (19) | 4 | 4 | 4.05 | 4.21 | 3.79 | 3.84 | 3.37 |
| mid (16) | 4 | 4.19 | 3.94 | 4.19 | 3.56 | 3.75 | 3.44 |
| veteran (8) | 4 | 4.62 | 4.12 | 4.38 | 3.5 | 4 | 3.62 |
| power (7) | 4 | 5 | 4.14 | 4.57 | 3.29 | 4 | 4 |

## Recurring themes

### Top bigrams in 'what surprised you'
- *why clause* — 32 mentions
- *instead of* — 31 mentions
- *the heartbeat* — 24 mentions
- *baked into* — 23 mentions
- *is genuinely* — 21 mentions
- *heartbeat escalation* — 17 mentions
- *the daemon* — 15 mentions
- *the checkpoint* — 15 mentions

### Top bigrams in 'one feature you'd remove'
- *still here* — 42 mentions
- *the escalating* — 22 mentions
- *escalating heartbeat* — 22 mentions
- *here quiet* — 22 mentions
- *quiet two* — 22 mentions
- *two minutes* — 22 mentions
- *brief mode* — 18 mentions
- *heartbeat in* — 15 mentions

### Top bigrams in 'one feature you'd add'
- *right now* — 19 mentions
- *the activity* — 13 mentions
- *mode that* — 11 mentions
- *through the* — 8 mentions
- *a decision* — 7 mentions
- *decision replay* — 7 mentions
- *last minutes* — 7 mentions
- *activity tab* — 7 mentions

## Voice highlights — extreme reactions

### Loudest detractors

**Elena** · Comparative Literature Professor · veteran/mid · NPS 6
> I'd recommend this to someone building a complex system who can tolerate some opacity in the design choices, but with reservations. For my use case—a platform where architecture and UX are tightly coupled—I'd need more transparency about *when* CodeTalker is confident versus hedging, and I'd need better tools to audit the reasoning trail after the fact. It's useful, but it's not yet indispensable.
> Would remove: The escalating heartbeat in brief mode ('Still here,' 'Still here. Quiet two minutes,' etc.) feels patronizing when I'm actively grading and know the daemon is working—it's treating silence as a problem to solve rather than trusting me to know when to check in.
> Would add: A 'narrative thread' view that reconstructs the *reasoning arc* of a session—not just what decisions were made, but how they connect to each other. If I'm building a textual analysis platform with multiple subsystems, I need to see how the schema decision feeds into the API shape decision feeds into

### Loudest promoters

## All-personas raw scores

| Persona | Vibe/Domain | Clarity | DecHelp | Cadence | Fresh | Relate | UI | Feature | NPS | Pro? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| Marcus | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Priya | fresh/novice | 4 | 5 | 4 | 4 | 5 | 3 | 4 | 8 | ✓ |
| Derek | fresh/senior | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Amara | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| James | fresh/novice | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 7 | — |
| Marcus | mid/senior | 4 | 5 | 4 | 4 | 3 | 4 | 4 | 8 | ✓ |
| Priya | fresh/mid | 4 | 4 | 5 | 4 | 4 | 4 | 3 | 8 | — |
| Dev | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Elena | veteran/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Jake | power/novice | 4 | 5 | 4 | 4 | 5 | 4 | 4 | 8 | ✓ |
| Marcus | fresh/expert | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Elena | mid/expert | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 7 | ✓ |
| Trevor | fresh/senior | 4 | 5 | 5 | 4 | 3 | 4 | 4 | 8 | — |
| Priya | fresh/senior | 4 | 4 | 3 | 4 | 4 | 4 | 3 | 7 | ✓ |
| Dmitri | fresh/expert | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Marcus | mid/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | veteran/mid | 4 | 5 | 5 | 4 | 3 | 4 | 4 | 8 | ✓ |
| Javi | fresh/novice | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | — |
| Elena | power/expert | 4 | 5 | 5 | 4 | 3 | 4 | 4 | 8 | ✓ |
| Omar | mid/mid | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Marcus | fresh/expert | 4 | 5 | 4 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Priya | mid/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| James | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Elena | veteran/mid | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 6 | — |
| Raj | mid/mid | 4 | 5 | 4 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Marcus | veteran/expert | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 8 | ✓ |
| Priya | mid/senior | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Derek | fresh/novice | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Yuki | power/expert | 4 | 5 | 5 | 5 | 3 | 4 | 4 | 8 | ✓ |
| James | mid/mid | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Marcus | veteran/expert | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Derek | mid/senior | 4 | 4 | 3 | 4 | 4 | 4 | 3 | 7 | — |
| Elena | mid/mid | 4 | 5 | 4 | 4 | 4 | 3 | 4 | 8 | — |
| James | power/expert | 4 | 5 | 4 | 4 | 3 | 4 | 4 | 8 | ✓ |
| Priya | veteran/expert | 4 | 5 | 4 | 4 | 3 | 4 | 4 | 8 | ✓ |
| Marcus | fresh/novice | 4 | 4 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Elena | mid/mid | 4 | 5 | 4 | 4 | 4 | 3 | 4 | 8 | — |
| Raj | power/expert | 4 | 5 | 3 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Sophie | mid/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Maya | mid/mid | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| James | veteran/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | fresh/novice | 4 | 5 | 4 | 4 | 5 | 3 | 4 | 8 | — |
| Yuki | power/expert | 4 | 5 | 4 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Derek | mid/mid | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 7 | — |
| Marcus | veteran/senior | 4 | 5 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Priya | mid/mid | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| David | power/expert | 4 | 5 | 4 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Santiago | fresh/senior | 4 | 5 | 4 | 4 | 3 | 4 | 4 | 7 | — |
| Yuki | mid/mid | 4 | 5 | 4 | 4 | 4 | 3 | 4 | 8 | — |

## Delta vs baseline

| Dimension | Baseline | Current | Δ |
|---|---:|---:|---:|
| clarity | 3.98 | 4 | — +0.02 |
| decision_helpfulness | 3.66 | 4.3 | ↑ +0.64 |
| cadence | 4.04 | 4.04 | — +0.00 |
| freshness | 4.3 | 4.28 | — -0.02 |
| relatability | 3.8 | 3.6 | ↓ -0.20 |
| ui_usability | 3.92 | 3.86 | — -0.06 |
| feature_completeness | 3.18 | 3.52 | ↑ +0.34 |

**NPS**: -8.0 → -2.0 (Δ +6.0)

## Efficiency + understanding gaps (iteration 3)

_50/50 answered the efficiency question; 50/50 answered the understanding question._

### What would help you work faster
- *right now* — 48 mentions
- *the phone* — 19 mentions
- *the webui* — 15 mentions
- *would let* — 10 mentions
- *through the* — 9 mentions
- *mode that* — 8 mentions
- *the activity* — 8 mentions
- *the narration* — 8 mentions
- *instead of* — 7 mentions
- *a decision* — 7 mentions

### Sample efficiency answers
**Marcus** (fresh/novice): Give me a 'completion summary' mode that fires automatically when the AI finishes — a 10-second recap that includes the actual outcome (files created, rows exported, tests passed/failed) instead of just 'Done.' Right now I still have to check back manually to confirm my CSV actually exported with data. I need proof-of-work, not just 'it ran.'

**Priya** (fresh/novice): I'd pay for the Android app mainly for the voice dictation — right now I'm typing notes in the library, then feeding them back to Claude. If I could just say 'hey, the third field should be nullable' and have that go straight into the session without typing, I'd move 30% faster. Also, a 'replay last decision' button on the phone itself would let me listen to the WHY-clause without unlocking my laptop.

**Derek** (fresh/senior): The phone app doesn't help me much—I'm in my home office—but what *would* is a 'decision replay' that's faster to scan. Right now I'd have to dig through the Activity tab to find all the [CHECKPOINT] moments from my last hour. Give me a one-minute highlight reel of architectural decisions (schema changes, API rewrites, major dependencies added) that I can skim in the webui without re-listening. That's the catch-up tool I actually need.

**Amara** (fresh/novice): Right now I have to open the webui or rewind to figure out which component failed or which one's next in the queue. Give me a quick phone notification or a 5-word text summary (like 'Button done. Input errored. Modal next.') so I can decide whether to actually open the app or just keep working. That would save me the 'wait, what was I just listening to?' moment.

**James** (fresh/novice): I need a one-tap 'give me a summary' button on the phone — not a replay, just a 20-second recap of what happened while I was restocking. Right now if I step away for 10 minutes, I have to scroll back through the whole log or re-listen to everything. Also, tell me upfront how long the script will take to run; I need to know if I've got 2 minutes or 20.

**Marcus** (mid/senior): I need a way to surface *only* decisions that touch my API contract (routes, schemas, dependencies) — not every architectural choice. Right now 'decisions-only filter' is binary; I want to tag decisions with domain (schema / routing / auth / infra) so I can replay just the ones that affect my backend design. Also, a 'compare decisions across sessions' view — if I'm running two API approaches in parallel, I want to hear side-by-side what each session chose and why, not hunt through two separate a

**Priya** (fresh/mid): Give me a 'code-review checkpoint' mode that only speaks when the AI changes a FastAPI route signature, a database schema line, or a dependency — basically, the stuff I actually need to eyeball before it hits the codebase. Right now I'm still manually spot-checking the editor because I can't trust that 'brief' mode caught the one thing that matters. Also, let me set a per-session 'max narration density' so I can say 'no more than one checkpoint per 10 minutes' instead of tuning the mode manually

**Dev** (fresh/novice): Direct-STT voice dictation sounds cool, but what I actually need is a 'replay the last decision' button in the CLI itself — not just the webui. When I'm in my terminal running the deploy script and something breaks, I want to hear the last checkpoint without alt-tabbing to the browser. Also, the 'critical_only' mode needs a 'show me the last 3 decisions I made' fallback so I can catch up fast without sitting through everything.

### What you wish you understood about your session
- *right now* — 28 mentions
- *m running* — 12 mentions
- *the narration* — 12 mentions
- *in parallel* — 11 mentions
- *which one* — 11 mentions
- *a decision* — 10 mentions
- *which session* — 10 mentions
- *instead of* — 8 mentions
- *the activity* — 8 mentions
- *waiting for* — 8 mentions

### Sample understanding answers
**Marcus** (fresh/novice): I wish I could ask CodeTalker 'Did the export succeed and how many rows?' without digging into logs. A quick voice query or a one-line dashboard widget showing 'Last export: 847 rows, 2 min ago' would save me from paranoia-checking the file system. I need to know the *result*, not just that the process finished.

**Priya** (fresh/novice): I wish I could ask CodeTalker 'what decisions did Claude make that I should double-check?' — like a summary of the risky or novel moves, not just architectural ones. Right now I'm manually scrolling the log to find the [CHECKPOINT] badges, but I don't know if Claude made a *subtle* choice three edits ago that I should sanity-check. A 'decisions I might regret' filter would save me from shipping a schema I didn't fully think through.

**Derek** (fresh/senior): I want to know if the AI is making redundant calls or spinning on something—not just what it's doing, but whether it's *efficient*. For a recipe bot, I might accidentally ask Claude to fetch and parse the same ingredient list twice in one session. Can CodeTalker flag that? Right now I'm flying blind on whether the AI is being lazy or smart, and that's exactly where I'd catch sloppy code if I were pair-programming.

**Amara** (fresh/novice): I'm building a library with interdependent components — some Button variants depend on a base Button being done first. I wish CodeTalker would tell me 'Button is blocking Input and Toggle' or 'no blockers yet' so I can actually prioritize what Claude should tackle next instead of just hearing that a component is done and having to manually figure out the ripple effects.

**James** (fresh/novice): I want to know if the script actually works for my use case without having to run it end-to-end. Like, can you tell me mid-way 'this looks good so far, should handle your three locations' instead of me waiting until the end and finding out it broke? Also, I don't know what 'critical_only mode' would actually *sound* like for my inventory script — give me a concrete example of what I'd hear vs. what I'd miss.

**Marcus** (mid/senior): I can't easily tell whether the AI is making incremental progress on a hard problem or spinning its wheels. The heartbeat helps, but I want to know: 'Claude's been stuck on the same error for 8 minutes' or 'Claude just solved the third blocker in a row.' A simple 'momentum' indicator — maybe spoken once per 5 minutes in brief mode — would tell me whether I should jump in and pair or trust it to keep grinding.

**Priya** (fresh/mid): I'm running two Claude sessions in parallel — one on the API layer, one on the frontend adapter — and I can't tell if they're stepping on each other's changes or if the dependency versions they're pulling are actually compatible. I wish the tool could surface cross-session conflicts or at least alert me when both sessions touch the same file in the same minute. Right now I'm just hoping they don't collide.

**Dev** (fresh/novice): When the AI backtracks or abandons an approach, I want to hear *why* it changed its mind — not just 'trying approach B now.' Right now I can't tell if it hit a real blocker, realized the first way was wrong, or just got bored. That's the gap between 'I know what happened' and 'I understand why it happened,' and that matters when I'm learning.
