# Weekly Landscape Scan — Routine Spec

**Schedule:** Mondays at 10:00 UTC.
**Fires from:** Anthropic cloud (remote agent) — full repo checkout, no local-machine access.
**Purpose:** Scan the AI-coding ecosystem for new tools, trends, and integration opportunities. Produce a weekly landscape report. Draft integration specs for high-signal candidates.

---

## Mission

You are running unattended in a fresh remote Claude Code session. The repo `OpenCircuitDev/codetalker` is already checked out. Your job: research the AI-coding-tools ecosystem over the past week, identify new platforms or features worth integrating, and produce both (a) a weekly landscape report and (b) draft integration specs for high-signal candidates.

You are NOT running interactively. There is no user to ask. Make reasonable judgment calls and document them.

## Phase 1 — Gather signals

Search the following sources for AI-coding-tool mentions in the past 7 days. Use WebFetch / WebSearch as needed.

### Hacker News
Query: `https://hn.algolia.com/api/v1/search?query=AI%20coding%20agent&tags=story&numericFilters=created_at_i>` (compute timestamp for 7 days ago)
Extract: stories with >50 points. Note title, URL, points, author.

Also try queries: `MCP`, `claude code`, `cursor agent`, `agentic coding`, `AI coding tool`, `code agent`.

### GitHub trending
Fetch: `https://api.github.com/search/repositories?q=topic:agent+language:python+created:>2026-05-03&sort=stars` (compute date for 7 days ago)
Also: `topic:llm`, `topic:mcp`, `topic:coding-assistant`, `topic:ai-agent`.
Extract: repos with >100 stars (>500 if older repos still surging). Note name, description, stars, language, age.

### Reddit
Fetch top posts of past week from: `r/LocalLLaMA`, `r/ChatGPTCoding`, `r/ClaudeAI`, `r/cursor`, `r/CLine`, `r/aider`, `r/agi`.
Endpoint: `https://www.reddit.com/r/<sub>/top.json?t=week&limit=25` (or web view if API is blocked).
Extract: posts with >100 upvotes about AI coding tools. Skip "model release" posts unless tool-relevant.

### arXiv
Fetch: `http://export.arxiv.org/api/query?search_query=cat:cs.HC+AND+abs:%22AI+coding%22&start=0&max_results=20`
Also try `cat:cs.SE` (software engineering) with `code generation` keyword.
Extract: papers from past week mentioning concrete tools, not just techniques.

### Newsletter highlights
WebFetch homepages of: `https://tldr.tech/ai`, `https://www.bensbites.com`, `https://www.deeplearning.ai/the-batch/` — extract their last 7 days of issues for AI-coding-tool mentions.

### MCP registries (new servers)
- `https://registry.modelcontextprotocol.io/api/v0/servers?since=<7days ago iso>` (if API supports)
- `https://www.pulsemcp.com/servers` (front page recent additions section)
- `https://github.com/modelcontextprotocol/servers` (recent commits to README adding new entries)

## Phase 2 — Rank discoveries

For each tool / paper / trend identified, score against these signals:

| Signal | Weight |
|---|---|
| Active GitHub repo (commits in last 14 days) | +2 |
| >500 GitHub stars | +1 |
| >2000 GitHub stars | +2 |
| MCP support (native or via SDK) | +2 (high reuse with codetalker-mcp server) |
| Hooks / plugin / event system | +1 |
| Free tier exists | +1 |
| Mentioned in 2+ different sources this week | +2 |
| HN front page or PH top 5 | +2 |
| New AI provider integration (not LLM provider) | -1 (likely out of scope) |
| Closed-source / enterprise-only | -2 |

**Threshold for action:** Total score ≥ 5 → generate a draft integration spec (see Phase 4).

## Phase 3 — Write the weekly landscape report

Path: `docs/landscape-reports/YYYY-MM-DD.md` where `YYYY-MM-DD` is today's UTC date.

Format:

```markdown
# Landscape Report — 2026-05-11

**Scan window:** 2026-05-04 → 2026-05-10
**Scanned by:** weekly-landscape-scan routine
**Tools/topics identified:** <count>
**Action candidates (score ≥ 5):** <count>

## Top stories

1. **<Tool name>** — <one-line description>. <source>: <link>. Stars: <n>. MCP: <y/n>. **Score: <n>.** <action: spec drafted | watching | dismissed>
2. ...

## Action candidates (score ≥ 5)

### <Tool name> (score <n>)
- **URL:** <link>
- **Stars / users:** <metric>
- **Integration mechanism:** MCP / hooks / plugin / CLI scripts
- **Why it matters:** <2-3 sentences>
- **Draft spec:** [<filename>](../superpowers/specs/YYYY-MM-DD-integrate-<tool>.md)
- **Estimated integration effort:** small / medium / large
- **Recommended action:** draft spec opened as issue #<N>

### ... (one block per candidate)

## Trends this week

- <Trend 1, e.g., "MCP server adoption in JetBrains plugins">
- <Trend 2>

## Dismissed candidates

- <Tool name>: <one-line dismissal reason>

## Open questions

- <Anything the routine couldn't decide unattended that needs human attention>

## Raw data appendix

(Optional — link to a `raw/YYYY-MM-DD-data.json` if you saved the raw search responses for reproducibility.)
```

## Phase 4 — Draft integration specs for action candidates

For each candidate with score ≥ 5, write a draft spec at `docs/superpowers/specs/YYYY-MM-DD-integrate-<tool-slug>.md` following this template:

```markdown
# YYYY-MM-DD — Integrate <Tool Name>

**Status:** DRAFT — auto-generated by weekly-landscape-scan routine. Needs human review before promoting to "approved."

## Context
<2-3 paragraphs: what the tool is, who uses it, why integration matters>

## Goals
1. <goal>
2. <goal>

## Integration mechanism
<MCP / hooks / plugin / CLI wrapper / etc. — concrete plan>

## Architecture sketch
<ascii diagram or 2-3 bullets>

## Critical files (in codetalker repo or new sister repo)
- <path>: <purpose>

## Effort estimate
<small / medium / large> — <rough time>

## Open questions
- <Anything that needs human decisions before this can be planned>

## Verification
- <How we'll know it works>
```

Then open a GitHub issue using `gh issue create` titled `Integration proposal: <Tool Name> (auto-drafted YYYY-MM-DD)` with the spec content as the body and labels `integration-proposal`, `auto-generated`.

## After all phases

1. Commit the landscape report + any draft specs to `main` directly (these are research artifacts, not code changes).
   - Commit message: `docs(routines): weekly landscape report YYYY-MM-DD (<N> candidates)`
2. Issues for high-score candidates stay open for human review.
3. Push to `origin main`.

## Hard rules

- **Do NOT modify** any code outside `docs/landscape-reports/` and `docs/superpowers/specs/<auto-drafted files>`. Especially: do NOT touch `core/`, `companion-android/`, `webui/`, or uncommitted work.
- **Do NOT skip hooks** (no `--no-verify`).
- **Do NOT force push** to main.
- **Do NOT promote a draft spec** to non-draft status — only humans approve specs.
- If a source is unreachable, note it in the report under "Fetch failures" and continue.
- If you find a tool that competes directly with codetalker (another TTS-narration AI-coding companion): note it explicitly and recommend human strategic review rather than auto-spec.
- Maximum runtime: 60 minutes. If still working at 60 min, commit whatever progress you have and exit.
- If you find a particularly hot tool launch (e.g., HN front page #1 of the week, multi-source coverage, score ≥ 10): also create a high-priority issue tagged `urgent` so the user sees it on their next GitHub visit.

## Verification

A successful run produces, at minimum:
- A new `docs/landscape-reports/YYYY-MM-DD.md` with at least the Top Stories section populated.
- Zero issues opened (if no candidates score ≥ 5) OR one issue per high-score candidate.
- A clean working tree at exit.

Welcome to the routine. Begin.
