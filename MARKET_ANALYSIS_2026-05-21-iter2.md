# Market Analysis — CodeTalker
_Generated 2026-05-21_ · _50 virtual users_ · _Model: anthropic/claude-haiku-4.5_

## Methodology

50 vibe-developer personas generated in 10 batches of 5 (each batch focused on a different archetype — beginners, power users, non-CS founders, etc.). Each persona was shown the product description, webui description, cadence behavior, and 10 real narrations sampled from `~/.claude/scripts/codetalker/narration-log.jsonl`. They scored 7 dimensions on a 1-5 scale and answered 4 open-ended questions, in character.

## Executive summary

- **NPS score: -6.0** (0 promoters · 47 passives · 3 detractors)
- **Would subscribe to Pro: 24/50 (48%)**
- **Strongest dimension**: freshness (mean 4.78/5)
- **Weakest dimension**: feature_completeness (mean 3.44/5)

## Dimension scores

| Dimension | Mean | Median | Stdev | Min-Max | n |
|---|---:|---:|---:|---:|---:|
| clarity | 4 | 4.0 | 0.0 | 4-4 | 50 |
| decision_helpfulness | 4.18 | 4.0 | 0.87 | 3-5 | 50 |
| cadence | 4.1 | 4.0 | 0.3 | 4-5 | 50 |
| freshness | 4.78 | 5.0 | 0.42 | 4-5 | 50 |
| relatability | 3.92 | 4.0 | 0.27 | 3-4 | 50 |
| ui_usability | 3.84 | 4.0 | 0.42 | 3-5 | 50 |
| feature_completeness | 3.44 | 3.0 | 0.54 | 2-4 | 50 |

## Cohort breakdown (mean by vibe-experience tier)

| Tier (n) | clarity | decision_helpfulness | cadence | freshness | relatability | ui_usability | feature_completeness |
|---|---:|---:|---:|---:|---:|---:|---:|
| fresh (17) | 4 | 4 | 4 | 4.88 | 3.94 | 3.59 | 3.18 |
| mid (15) | 4 | 3.6 | 4.07 | 4.53 | 3.87 | 4 | 3.2 |
| veteran (9) | 4 | 4.67 | 4.22 | 4.78 | 4 | 3.78 | 3.78 |
| power (9) | 4 | 5 | 4.22 | 5 | 3.89 | 4.11 | 4 |

## Recurring themes

### Top bigrams in 'what surprised you'
- *live stream* — 25 mentions
- *multi session* — 15 mentions
- *expect the* — 14 mentions
- *the multi* — 14 mentions
- *session fan* — 13 mentions
- *stream summaries* — 13 mentions
- *the activity* — 13 mentions
- *i expected* — 12 mentions

### Top bigrams in 'one feature you'd remove'
- *feels like* — 37 mentions
- *direct mode* — 15 mentions
- *like feature* — 13 mentions
- *tab feels* — 12 mentions
- *the direct* — 12 mentions
- *mode feels* — 11 mentions
- *the characters* — 10 mentions
- *feature creep* — 10 mentions

### Top bigrams in 'one feature you'd add'
- *right now* — 16 mentions
- *mode that* — 11 mentions
- *the narration* — 9 mentions
- *the webui* — 7 mentions
- *the activity* — 7 mentions
- *instead of* — 5 mentions
- *that lets* — 5 mentions
- *last seconds* — 4 mentions

## Voice highlights — extreme reactions

### Loudest detractors

**Jade** · Freelance writer dabbling in side projects · fresh/novice · NPS 6
> It's clever and I'd probably use the free tier while building my blog, but it feels built for engineers who already speak code fluently. For me, it's a nice-to-have, not a must-have—I'd rather just check Slack or GitHub occasionally than try to parse narration about things I don't fully understand anyway.
> Would remove: The CHARACTERS tab feels like overkill for me—I don't need 3D avatars or voice cloning; I just want to know if my Medium sync broke while I'm on the train.
> Would add: A super-dumb "plain English" narration mode that translates tech stuff into actual human language—like 'your code is still thinking' instead of 'running the performance suite' so I can actually understand what's happening without Googling.

**James** · Analytics Engineer · mid/mid · NPS 6
> Yeah, I'd try it for a month on the free tier. It's solid for catching what's happening without staring at the screen, and the Activity feed could save me from missing a silent failure. But I'd need that red-flag mode before I'd actually trust it on a production pipeline—right now it feels like it'd be too chatty to be useful when I'm actually busy.
> Would remove: Cut the 'still hunting' / 'still working through' filler—just tell me what changed or what's blocked, not a play-by-play of the AI thinking.
> Would add: A quick 'red flag' alert mode that only speaks when the AI hits an error, throws a deprecation warning, or detects something that looks like it'll bite me in the dbt DAG later—I don't need narration every 8 seconds, I need warnings before I have to debug.

**Kai** · Skeptical Contractor · mid/senior · NPS 6
> It's solid for *awareness*—I can genuinely cook dinner and stay in the loop on progress. But for my use case (not trusting AI code), it's a 60% solution. I need it to narrate *risks*, not just *activities*. If you add aggressive code-smell detection to the live feed, I'm in.
> Would remove: The 'Buddy mode' phone-to-Claude dictation feels like feature creep when what I actually need is the daemon to *flag* suspicious patterns in the code it's generating—not chat with it.
> Would add: A 'code-audit' narration mode that specifically calls out SQL injection risks, unhandled errors, or antipatterns as they're written—line numbers, severity, and the exact problem. Right now I'm still stopping to read the screen anyway.

### Loudest promoters

## All-personas raw scores

| Persona | Vibe/Domain | Clarity | DecHelp | Cadence | Fresh | Relate | UI | Feature | NPS | Pro? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| Marcus | fresh/novice | 4 | 5 | 4 | 5 | 4 | 3 | 4 | 7 | — |
| Priya | fresh/novice | 4 | 3 | 4 | 5 | 4 | 3 | 3 | 7 | — |
| Derek | fresh/novice | 4 | 4 | 4 | 5 | 3 | 4 | 3 | 7 | — |
| Jade | fresh/novice | 4 | 3 | 4 | 5 | 4 | 3 | 2 | 6 | — |
| Vincent | fresh/novice | 4 | 4 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Marcus | mid/senior | 4 | 4 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Priya | fresh/mid | 4 | 4 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Derek | veteran/expert | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | ✓ |
| Yuki | fresh/mid | 4 | 3 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Jamal | power/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Marcus | fresh/expert | 4 | 5 | 4 | 5 | 4 | 3 | 4 | 8 | ✓ |
| Priya | mid/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| David | veteran/expert | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Sarah | fresh/mid | 4 | 5 | 4 | 5 | 4 | 3 | 4 | 8 | — |
| James | power/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Maya | mid/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Jordan | fresh/novice | 4 | 4 | 4 | 5 | 4 | 3 | 3 | 7 | — |
| Priya | veteran/expert | 4 | 5 | 5 | 4 | 4 | 4 | 4 | 8 | ✓ |
| Alex | power/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Sam | mid/mid | 4 | 4 | 5 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | fresh/expert | 4 | 5 | 4 | 5 | 4 | 4 | 3 | 8 | ✓ |
| Marcus | mid/novice | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 7 | — |
| Yuki | veteran/mid | 4 | 5 | 4 | 5 | 4 | 3 | 4 | 8 | ✓ |
| James | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Sofia | power/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Marcus | veteran/expert | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | mid/senior | 4 | 3 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Jake | fresh/novice | 4 | 5 | 4 | 5 | 4 | 4 | 3 | 8 | — |
| Devon | power/expert | 4 | 5 | 5 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Aaron | mid/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Marcus | veteran/expert | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | fresh/novice | 4 | 3 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Diego | mid/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| Kenji | power/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Sophia | mid/senior | 4 | 4 | 4 | 5 | 4 | 4 | 3 | 7 | ✓ |
| Marcus | veteran/expert | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | fresh/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |
| James | mid/mid | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |
| Yuki | power/expert | 4 | 5 | 5 | 5 | 3 | 4 | 4 | 8 | ✓ |
| Derek | mid/mid | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 7 | ✓ |
| Maya | fresh/novice | 4 | 4 | 4 | 5 | 4 | 3 | 3 | 7 | — |
| Derek | mid/mid | 4 | 4 | 4 | 5 | 4 | 4 | 3 | 7 | — |
| Priya | veteran/senior | 4 | 4 | 4 | 5 | 4 | 3 | 3 | 7 | — |
| Kai | mid/senior | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 6 | — |
| Zara | power/expert | 4 | 5 | 4 | 5 | 4 | 5 | 4 | 8 | ✓ |
| Marcus | veteran/senior | 4 | 5 | 5 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Priya | mid/expert | 4 | 4 | 4 | 5 | 3 | 4 | 3 | 7 | — |
| Jake | fresh/mid | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| Elena | power/senior | 4 | 5 | 4 | 5 | 4 | 4 | 4 | 8 | ✓ |
| David | mid/novice | 4 | 3 | 4 | 4 | 4 | 4 | 3 | 7 | — |

## Delta vs baseline

| Dimension | Baseline | Current | Δ |
|---|---:|---:|---:|
| clarity | 3.96 | 4 | — +0.04 |
| decision_helpfulness | 4.16 | 4.18 | — +0.02 |
| cadence | 3.98 | 4.1 | ↑ +0.12 |
| freshness | 4.8 | 4.78 | — -0.02 |
| relatability | 4.32 | 3.92 | ↓ -0.40 |
| ui_usability | 3.58 | 3.84 | ↑ +0.26 |
| feature_completeness | 3.6 | 3.44 | ↓ -0.16 |

**NPS**: -12.0 → -6.0 (Δ +6.0)
