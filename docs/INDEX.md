# CodeTalker Documentation

A single-page directory of all CodeTalker docs, organized by audience and use case.

---

## For Users

### [User Guide](USER_GUIDE.md)
The first stop after install. Walks you through the webui (Sessions, Activity, Analysis, Preferences tabs), explains the four narration modes (brief / live / direct / critical_only) and when to pick each, and teaches the audible vocabulary ("Heads up." = alert, "Checkpoint." = decision, "Still here." = heartbeat).

**Read this if:** You just installed CodeTalker and want to understand what you're hearing and how to switch modes to match your workflow.

---

## For Operators & Debugging

### [API Reference](API_QUICKREF.md)
Complete HTTP endpoint reference for the CodeTalker daemon. Lists health checks, session queries, audio control (play, skip, rewind), mode switching, character attachment, and configuration endpoints. Includes curl examples for each.

**Read this if:** You're building a client, integrating with another tool, scripting session state, or troubleshooting the daemon via HTTP.

### [UX Audit](UX_AUDIT.md)
Accessibility and usability deep-dive on the webui health chips, alert/checkpoint badges, mode picker, filter pills, and spoken-cues legend. Reports on color contrast, hit targets, keyboard navigation, and colorblind-user coverage. Posts findings by component with WCAG guidance.

**Read this if:** You're improving webui accessibility, planning a design refresh, or need to justify a11y work to stakeholders (audit includes before/after patterns).

---

## For Contributors & Product

### [Persona Insights](PERSONA_INSIGHTS.md)
Synthesis of 8 market-analysis iterations spanning 400+ personas. Tracks NPS trajectory (-12 → -3.3), break down by dimension (clarity, decision_helpfulness, freshness, etc.), and interprets inflection points. Shows how shipping decision-awareness features ([CHECKPOINT], [UNSURE], why-clause prompts) recovered personas from a mid-run valley and tied it to Pro conversion rates.

**Read this if:** You're making roadmap decisions, tuning the narrator, evaluating feature scope, or understanding why certain ships moved the needle (or didn't).

### [Voice Command Design](VOICE_COMMAND_DESIGN.md)
Design spec for the "Hey CodeTalker" status-query feature (Pro only, Android + optional XREAL). Justifies push-to-talk over wake-word in v1, details STT infrastructure reuse from Buddy mode, and sketches the query shapes ("Is Claude stuck?", "What happened?") and latency targets (<2s).

**Read this if:** You're building the voice command feature, planning Pro-exclusive infrastructure, or reviewing the design trade-offs for always-on listening (battery, privacy, permissions).

### [Release Notes (2026-05-21)](../CHANGELOG_2026_05_21.md)
One-day feature burst driven by an in-day market loop. Summarizes the NPS climb, lists new features (critical-only mode, [ALERT] cue, [CHECKPOINT] marker, decision log filter, session health badge, hearbeat escalation), UI ships (Analysis tab, lazy-load Characters tab), and points to commit hashes for diffs.

**Read this if:** You're reviewing what shipped in this release, understanding the feature diff for a version bump, or backporting a fix to an earlier release.

---

## Navigation & Cross-References

- **Just installed?** Start with [User Guide](USER_GUIDE.md), then explore the webui tabs.
- **Building on CodeTalker?** See [API Reference](API_QUICKREF.md) and the [integrations](integrations/README.md) folder.
- **Tuning narration quality?** Read [Persona Insights](PERSONA_INSIGHTS.md) first; the NPS data will guide your next sprint.
- **Accessibility fixes?** [UX Audit](UX_AUDIT.md) catalogs the gaps and has before/after examples.

---

*Last updated: 2026-05-21. Docs ship with the latest release.*
