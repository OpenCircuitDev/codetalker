# Market Analysis — CodeTalker
_Generated 2026-05-21_ · _50 virtual users_ · _Model: anthropic/claude-haiku-4.5_

## Methodology

50 vibe-developer personas generated in 10 batches of 5 (each batch focused on a different archetype — beginners, power users, non-CS founders, etc.). Each persona was shown the product description, webui description, cadence behavior, and 10 real narrations sampled from `~/.claude/scripts/codetalker/narration-log.jsonl`. They scored 7 dimensions on a 1-5 scale and answered 4 open-ended questions, in character.

## Executive summary

- **NPS score: -22.0** (0 promoters · 39 passives · 11 detractors)
- **Would subscribe to Pro: 10/50 (20%)**
- **Strongest dimension**: freshness (mean 4.24/5)
- **Weakest dimension**: feature_completeness (mean 3.18/5)

## Dimension scores

| Dimension | Mean | Median | Stdev | Min-Max | n |
|---|---:|---:|---:|---:|---:|
| clarity | 4 | 4.0 | 0.0 | 4-4 | 50 |
| decision_helpfulness | 3.46 | 3.0 | 0.79 | 3-5 | 50 |
| cadence | 4.02 | 4.0 | 0.25 | 3-5 | 50 |
| freshness | 4.24 | 4.0 | 0.43 | 4-5 | 50 |
| relatability | 3.84 | 4.0 | 0.37 | 3-4 | 50 |
| ui_usability | 3.86 | 4.0 | 0.35 | 3-4 | 50 |
| feature_completeness | 3.18 | 3.0 | 0.52 | 2-5 | 50 |

## Cohort breakdown (mean by vibe-experience tier)

| Tier (n) | clarity | decision_helpfulness | cadence | freshness | relatability | ui_usability | feature_completeness |
|---|---:|---:|---:|---:|---:|---:|---:|
| fresh (19) | 4 | 3.26 | 4.05 | 4.11 | 3.95 | 3.79 | 3.16 |
| mid (14) | 4 | 3.93 | 3.93 | 4.43 | 3.86 | 3.79 | 3.36 |
| veteran (8) | 4 | 3.12 | 4.12 | 4.12 | 3.88 | 4 | 2.88 |
| power (9) | 4 | 3.44 | 4 | 4.33 | 3.56 | 4 | 3.22 |

## Recurring themes

### Top bigrams in 'what surprised you'
- *live stream* — 32 mentions
- *stream summaries* — 21 mentions
- *expect the* — 18 mentions
- *summaries are* — 14 mentions
- *genuinely useful* — 14 mentions
- *are genuinely* — 12 mentions
- *i expected* — 12 mentions
- *the narration* — 11 mentions

### Top bigrams in 'one feature you'd remove'
- *feels like* — 31 mentions
- *like feature* — 19 mentions
- *tab feels* — 16 mentions
- *the character* — 14 mentions
- *character avatars* — 14 mentions
- *feature creep* — 12 mentions
- *avatars and* — 12 mentions
- *feel like* — 11 mentions

### Top bigrams in 'one feature you'd add'
- *mode that* — 21 mentions
- *right now* — 13 mentions
- *a confidence* — 9 mentions
- *the narration* — 8 mentions
- *that only* — 7 mentions
- *only speaks* — 6 mentions
- *speaks when* — 6 mentions
- *when claude* — 6 mentions

## Voice highlights — extreme reactions

### Loudest detractors

**Derek** · Warehouse supervisor learning tech on the side · fresh/novice · NPS 6
> Yeah, I'd use this. The Basic tier is free and it solves the problem of me having to stare at my screen during breaks. But it needs to dial back the fancy narration for someone like me who just wants 'query executed' or 'error on line 42' — not a TED talk about what the AI is thinking.
> Would remove: Cut the character avatars and voice cloning stuff — that's cool for streaming, but I'm listening in a break room on my phone trying not to look weird; I don't need a 3D person staring at me.
> Would add: Give me a 'bug spotter' mode that specifically flags common mistakes in Python or SQL — like missing error handling, SQL injection risks, or uninitialized variables — narrated as warnings before I even have to run the code. That's what would actually save me time debugging.

**Marcus** · Senior Frontend Engineer transitioning to Node.js · mid/senior · NPS 6
> I'd use it, but not because it's polished—because the live-stream narration actually lets me context-switch without losing the thread. For a backend engineer building real-time systems though, it needs domain-specific smarts around concurrency and data consistency, or it's just a fancy status ticker.
> Would remove: The character avatars and XREAL glasses integration feel like feature creep for my use case—I'm on a train half-reading Hacker News, not running a podcast studio.
> Would add: A 'risk flag' mode that interrupts narration when the agent is about to do something architecturally sketchy—like spawning unbounded parallel queries or missing transaction boundaries in PostgreSQL writes. That's the refactoring debt I actually care about catching early.

**Jennifer** · Principal Architect, Fintech · mid/expert · NPS 6
> I'd try the Basic tier for a week on my next prototype sprint, but I'd only go Pro if the Android app lets me pipe alerts to my watch and the risk filter actually works. For C++ I'd trust my instincts alone; for Python + gRPC I need a second pair of ears, and CodeTalker could be it — but only if it's smart enough to know what matters in fintech.
> Would remove: The 'Buddy mode' talk-back feature feels like a distraction for my use case — I'm on a treadmill to stay away from the keyboard, not to have a conversation with Claude through my phone.
> Would add: A 'risk filter' mode that *only* speaks when the AI touches concurrency primitives, transaction boundaries, or state mutations — give me a silent hum otherwise, and interrupt hard when something smells wrong.

**Rajesh** · Economist · mid/mid · NPS 6
> I'd use this, but only on Brief mode and only after the first week of tuning. For someone like me—economist half-listening between meetings—the value is real, but it only clicks if I can configure it to *not* talk unless something actually matters. Pro tier doesn't justify the cost yet.
> Would remove: The 'Direct mode' for raw tool outputs feels like developer noise I'd never use; Brief mode alone would cover 95% of my actual needs.
> Would add: A 'statistical anomaly alert' mode that only speaks when something genuinely unexpected happens in my data pipeline—right now I'd still get narration during routine ingestion, which defeats the point of half-listening.

**Sofia** · Literary Scholar · veteran/novice · NPS 6
> Cautiously yes, but only for the Basic tier and only if you're willing to treat it as a *transparency layer*, not a convenience tool. The narration is thoughtful enough that I could actually interrogate the AI's reasoning while I'm cooking dinner, which is the whole point. But it doesn't yet do what I most need: surface the *assumptions embedded in my own search queries and annotations*. That's on me to build, but CodeTalker gives me the listening infrastructure to do it.
> Would remove: The 'Buddy mode' (talking to your agent through the phone) feels like a distraction—I need to *listen and interrogate*, not chat; if I'm doing that, I should be at the computer anyway.
> Would add: A 'decision log' that explicitly surfaces every heuristic, threshold, or classification rule the AI applied during a session—not just what it did, but *why it decided that way*. For my use case, that's the whole ballgame.

### Loudest promoters

## All-personas raw scores

| Persona | Vibe/Domain | Clarity | DecHelp | Cadence | Fresh | Relate | UI | Feature | NPS | Pro? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| Marcus | fresh/novice | 4 | 5 | 4 | 5 | 4 | 3 | 4 | 7 | — |
| Yuki | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| James | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Priya | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Derek | fresh/novice | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 6 | — |
| Marcus | mid/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |
| Priya | fresh/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Derek | veteran/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Sophie | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| James | power/senior | 4 | 5 | 4 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Marcus | fresh/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Jennifer | mid/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |
| David | fresh/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Priya | mid/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Robert | fresh/expert | 4 | 5 | 5 | 5 | 4 | 4 | 5 | 8 | ✓ |
| Marcus | veteran/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Priya | mid/mid | 4 | 5 | 4 | 5 | 4 | 3 | 4 | 8 | ✓ |
| Dev | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Sarah | power/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Kai | mid/senior | 4 | 4 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Maya | fresh/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Rajesh | mid/mid | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 6 | — |
| Sofia | veteran/novice | 4 | 3 | 4 | 4 | 3 | 4 | 2 | 6 | — |
| Dmitri | power/senior | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 7 | ✓ |
| Priya | fresh/mid | 4 | 4 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Marcus | veteran/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Priya | mid/senior | 4 | 3 | 4 | 4 | 4 | 4 | 2 | 6 | — |
| Jamal | fresh/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Chen | power/expert | 4 | 3 | 4 | 5 | 3 | 4 | 3 | 7 | — |
| Sophia | mid/novice | 4 | 4 | 3 | 4 | 4 | 4 | 3 | 7 | — |
| Marcus | veteran/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |
| Priya | mid/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Derek | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Yuki | power/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |
| Ahmed | mid/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 7 | — |
| Marcus | mid/senior | 4 | 5 | 4 | 5 | 4 | 3 | 4 | 8 | ✓ |
| Priya | veteran/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Dev | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| James | power/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |
| Yuki | mid/senior | 4 | 5 | 4 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Marcus | mid/mid | 4 | 4 | 4 | 4 | 4 | 3 | 4 | 7 | ✓ |
| Priya | veteran/senior | 4 | 4 | 5 | 5 | 4 | 4 | 3 | 8 | ✓ |
| James | fresh/novice | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 7 | — |
| Yuki | fresh/novice | 4 | 3 | 4 | 4 | 4 | 3 | 3 | 6 | — |
| Dev | power/expert | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Marcus | power/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Priya | mid/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| David | veteran/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Zoe | fresh/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Jamal | power/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |

## Delta vs baseline

| Dimension | Baseline | Current | Δ |
|---|---:|---:|---:|
| clarity | 4 | 4 | — +0.00 |
| decision_helpfulness | 4.18 | 3.46 | ↓ -0.72 |
| cadence | 4.1 | 4.02 | — -0.08 |
| freshness | 4.78 | 4.24 | ↓ -0.54 |
| relatability | 3.92 | 3.84 | — -0.08 |
| ui_usability | 3.84 | 3.86 | — +0.02 |
| feature_completeness | 3.44 | 3.18 | ↓ -0.26 |

**NPS**: -6.0 → -22.0 (Δ -16.0)
