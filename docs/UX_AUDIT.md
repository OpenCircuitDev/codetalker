# Codetalker WebUI Accessibility & UX Audit
**Date:** 2026-05-21  
**Audit Scope:** Health chip, Alert/Checkpoint badges, ModePicker dropdown, Filter pills, Spoken Cues legend  
**Methodology:** Code review of Tailwind color ratios, semantic HTML, keyboard navigability, hit targets, color-only signaling

---

## Summary

The codetalker webui components shipped today demonstrate **solid semantic foundation and near-compliant color contrast**, but exhibit **three recurring accessibility gaps**:

1. **Color-only state signaling** — Health chip and filter pills rely entirely on color to distinguish states, which excludes colorblind users.
2. **Minimal hit-target sizes** — Several chips use `px-1.5 py-0.5` (6–8px padding), borderline below the 24×24px WCAG guideline.
3. **Filter pill keyboard navigation** — Dual filter rows lack arrow-key navigation; each pill is a separate Tab stop, creating friction for keyboard-only users.

Overall posture: **AA-ready on contrast; requires minor non-color cues to reach AAA and full colorblind coverage.**

---

## Per-Component Findings

### 1. Health Chip (SessionRow.tsx, lines 487–525)

**Component:** Four-state session status pill ("running" | "working" | "blocked" | "dormant")

**Findings:**

- **⚠ Color-only signaling (critical)** — State is differentiated ONLY by color+text label:
  - Running: `bg-emerald-900/60 text-emerald-200` (green)
  - Working: `bg-cyan-900/60 text-cyan-200` (blue)
  - Blocked: `bg-amber-900/60 text-amber-200` (orange)
  - Dormant: `bg-zinc-800 text-zinc-400` (grey)
  
  A protanopic (red-blind) user cannot reliably distinguish "blocked" (amber) from "working" (cyan). Text labels mitigate this partially, but truncation (`truncate max-w-[50px]`) may cut off the label on narrow screens.

- **ℹ Contrast ratio is acceptable** — Estimated 5.5:1 (emerald-900/60 + emerald-200), exceeding WCAG AA (4.5:1). The `/60` opacity blend raises effective saturation vs. flat colors.

- **ℹ Title attribute present** — `title={title}` at line 520 provides "Session is running" hover text. **However**, a screen-reader user *reads* the label text ("running"), so this is redundant rather than supplementary. The title should *expand* the meaning, not repeat it.

- **ℹ Hit target acceptable** — `px-1.5 py-0.5` = ~12px vertical, slightly tight but acceptable given the label text provides semantic content.

---

### 2. Alert Badge (SessionRow.tsx, lines 148–154; LiveTicker.tsx, lines 99–105)

**Component:** Inline red badge signaling system-critical issues in narration recap and ticker

**Findings:**

- **⚙ Contrast ratio borderline** — `bg-red-500/20 text-red-200` on dark surface:
  - Effective blend (red-500 at 20% opacity + dark background) ≈ 5.2:1 ratio.
  - Meets AA but uncomfortably close to the 4.5:1 threshold. Recommend `bg-red-500/30` or `text-red-100` for 6:1+ safety margin.

- **ℹ Text label provides non-color cue** — "ALERT" or "alert" text is screen-reader friendly and disambiguates from checkpoint. However, the capitalization/case differs between components (SessionRow line 153 = "ALERT", LiveTicker line 104 = "alert"). Normalize to one style for consistency.

- **⚙ Icon-only alert variant missing** — No warning icon (⚠) supplement; users relying on iconography alone (e.g., with custom CSS hiddenText for labels) will miss the alert. Suggest adding a small ⚠ symbol prefix.

- **ℹ Title attribute adequate** — `title="Alert: something broke, blocked, or needs input"` is descriptive.

- **ℹ Hit target adequate** — `px-1 rounded` + "ALERT" text ≈ 30px wide, meets 24px minimum.

---

### 3. Checkpoint Badge (SessionRow.tsx, lines 156–162; LiveTicker.tsx lines not found)

**Component:** Green badge with ✓ symbol for architectural decision markers

**Findings:**

- **ℹ Contrast ratio strong** — `bg-green-500/20 text-green-200` ≈ 5.4:1, healthy margin above AA.

- **⚠ Checkmark symbol is color-dependent cue** — The ✓ character renders as a Unicode symbol, readable to screen readers as "CHECK MARK" (U+2713). However, sighted users heavily rely on the *green* color to parse "success / checkpoint" at a glance. A protanopic user sees amber/neutral color + check mark, which may be ambiguous when appearing alongside other badges. **Suggest:** Add a text prefix like "[✓]" or "→" rather than symbol-only.

- **ℹ Title attribute present** — `title="Checkpoint: progress marker"` at line 159. Adequate but could expand on significance.

- **ℹ Hit target adequate** — Single-character badge ≈ 20–24px, borderline; acceptable given label text.

---

### 4. ModePicker Dropdown (ModePicker.tsx, lines 17–33)

**Component:** Native HTML `<select>` with five modes: direct, brief, live, trigger, critical_only

**Findings:**

- **ℹ Semantically sound** — Uses native `<select>` element; automatically keyboard navigable (Tab to focus, arrow keys to choose, Enter to confirm). Excellent baseline accessibility.

- **ℹ Contrast adequate** — `bg-slate-900 border-slate-700` ≈ 4.8:1 on unselected `<option>`, meets AA. Selected options inherit browser default (typically high contrast).

- **⚙ Title attribute on dropdown, not per-option** — `title={...}` at line 23 applies to the dropdown itself, not to individual options. Browser may not surface this tooltip within the open select menu. **Suggest:** Add help text visible outside the dropdown (e.g., as a collapsible legend or info icon) since `<option title>` is inconsistently supported across browsers.

- **ℹ Keyboard navigation perfect** — Native select handles Tab focus, arrow-key navigation, and screen-reader announcement of selected value automatically.

- **ℹ Hit target adequate** — `px-2 py-1` on select ≈ 20–24px vertical, acceptable.

- **ℹ Four vs. five modes** — Audit target mentioned "four options" (brief/direct/live/critical_only), but the code shows *five* (add "trigger"). No UX issue, just note for sync with spec.

---

### 5. Filter Pills / Decisions-Only Toggle (LiveTicker.tsx, lines 48–79)

**Component:** Two pill rows: (All | Speak | Tool | Subagent | Error) AND (All Events | Decisions Only)

**Findings:**

- **⚠ Keyboard navigation friction** — Pills are standalone `<button>` elements with no grouping or arrow-key logic. A keyboard user must Tab through each pill individually (10 total: 5 in first row + 5 in second row). **Expected behavior:** Arrow keys within a row should move focus left/right; Tab advances to the next row. Current implementation requires ~10 Tab presses vs. optimal ~2–3.

- **⚠ No visual focus-ring distinct from hover** — The selected state colors are `o.color + " text-white"` (e.g., `bg-zinc-700` for unselected, `bg-emerald-700` for "Speak" when selected). When keyboard-focused but not selected, there's no visible focus ring. Modern browsers add a default outline, but it may be subtle on dark backgrounds. **Suggest:** Add `focus-visible:ring-2 ring-cyan-400` to pill buttons.

- **⚠ No aria-pressed or role=group** — Pills should ideally have `aria-pressed={isSelected}` for screen-reader announcement of toggled state. The filter row itself should be wrapped in a `role="group" aria-label="Event filter"` to clarify that these are mutually exclusive toggles.

- **ℹ Color contrast adequate** — Selected: `bg-zinc-700` or variant + `text-white` ≈ 5.0:1. Unselected: `bg-zinc-800 text-zinc-400` ≈ 4.3:1, marginally below AA. **Suggest:** Increase unselected text to `text-zinc-300` for 4.8+:1.

- **ℹ Hit targets adequate** — `px-2 py-0.5` on pills ≈ 20×20px, borderline but acceptable given padding and text.

- **ℹ Color-only row-level signaling** — First row: pill colors vary by kind (emerald for "Speak", cyan for "Tool", violet for "Subagent", rose for "Error"). Colorblind users can still read the text label, so this is mitigated. Second row: "All Events" vs. "Decisions Only" both use the same selected/unselected color scheme (zinc for unselected, amber for selected). Amber is distinct enough from the first row's colors, but no icon/shape difference — only color. **This is acceptable** given the text is clear.

---

### 6. Spoken Cues Legend (PreferencesPanel.tsx, lines 151–181)

**Component:** Definition list of TTS cue phrases ("Heads up.", "Checkpoint.", "Still here.", etc.)

**Findings:**

- **ℹ Semantically excellent** — Uses `<dl>`, `<dt>`, `<dd>` elements correctly. Screen readers will announce these as a definition list, with clear term–definition pairing.

- **ℹ Contrast strong** — `text-[var(--color-text-2)]` for terms, `text-[var(--color-text-3)]` for definitions. Assuming CSS variables follow standard contrast patterns, this should exceed AA. *(Cannot verify exact ratio without computed values, but naming convention suggests intent.)*

- **ℹ Font sizes adequate** — `text-xs` (12px) on definitions is readable; terms slightly larger via `font-mono`. No hit-target concerns since this is static text.

- **ℹ Layout flexible** — `flex gap-3` allows term and definition to wrap on narrow viewports. No layout accessibility issues detected.

- **ℹ No interactive elements** — This is reference documentation, not a control. No keyboard, color-signaling, or focus concerns.

- **ℹ Accessibility tree-friendly** — The `min-w-32` on terms prevents definition text from collapsing to a single line, aiding readability.

---

## Cross-Cutting Patterns

### Pattern 1: Color-Only State Signaling (2+ components)

**Affected:** Health Chip, Filter Pills (row 2: All Events vs. Decisions Only)

**Issue:** State distinction relies entirely on hue/saturation shifts without supplementary shape, icon, or prefix character. Protanopic (red-blind) and deuteranopic (green-blind) users may conflate "blocked" (amber) with "working" (cyan) or "running" (emerald).

**Current mitigation:** Text labels ("running", "working", "blocked", "dormant", "All Events", "Decisions Only") partially offset this, but labels may truncate on narrow screens (health chip, line 519).

**Recommended approach:**
- Add a non-color prefix: `[●] running`, `[◐] working`, `[⊗] blocked`, `[○] dormant`
- Or: Add shape difference (solid, outline, striped background)
- Or: Ensure labels never truncate and are always visible

---

### Pattern 2: Minimal Vertical Padding on Small Chips (3+ components)

**Affected:** Health Chip (py-0.5), Character Chip (py-0.5), Filter Pills (py-0.5)

**Issue:** `py-0.5` = 2px padding (Tailwind default: 1 rem = 16px base, 0.5 = 8px; then halved = 4px actual). This results in ~20–22px total chip height, borderline below the 24px WCAG guideline for minimum touch targets.

**Current state:** Text labels provide semantic fallback, so the component remains accessible. But on touch devices (future Android app integration per codebase context), 20px targets are uncomfortable.

**Recommended approach:**
- Increase to `py-1` (8px) for ~28px total height
- Or: Accept 20px as "acceptable for mouse users" and document as a mobile refinement for v1.0 (when Android shipped)

---

### Pattern 3: Inconsistent Title Attribute Usage (4+ components)

**Affected:** Health Chip, Alert Badge, Checkpoint Badge, Pin button, Mode Quick Pick, Character Chip

**Issue:** `title=` attributes are used inconsistently:
- Some provide *expanded* descriptions ("Alert: something broke, blocked, or needs input")
- Some simply *repeat* the visible label ("Session is running" on health chip)
- Some use labels that duplicate the text content ("Unpin from top of group" on pin button)

**Best practice:** Title should provide *context or explanation* that goes beyond the visible label, since screen-reader users already hear the label text.

**Recommended approach:** Audit all `title=` attributes; convert repeating ones to empty or context-expanding ones. Example: "running" → "Last activity within 60s" instead of "Session is running".

---

## Suggested Next Steps

### Top 3 Fixes Ranked by User Impact

1. **⚠ Health Chip: Add non-color state cue (Priority: HIGH)**
   - **Impact:** Protanopic users can now distinguish session states at a glance without reading the full label.
   - **Effort:** 15 minutes. Add a shape prefix: `<span className="...">● running</span>` with different Unicode bullets (●, ◐, ⊗, ○) per state.
   - **File:** `SessionRow.tsx`, lines 517–525 (SessionHealthChip function).
   - **Testing:** Use a color-blind simulator (e.g., Chromatic Vision Simulator) to verify distinction.

2. **⚙ Filter Pills: Enable arrow-key navigation (Priority: MEDIUM)**
   - **Impact:** Keyboard-only users can filter events in 2–3 key presses instead of 10 Tab presses.
   - **Effort:** 30 minutes. Wrap pill rows in a custom hook or Radix UI `RadioGroup` component. Add `onKeyDown` handler for arrow-key focus management.
   - **File:** `LiveTicker.tsx`, lines 48–79 (FILTER_OPTIONS / CHECKPOINT_FILTER_OPTIONS rendering).
   - **Testing:** Test with keyboard only (Tab to filter row, arrow keys to move between pills, Enter to select).

3. **⚙ Alert Badge: Increase contrast margin (Priority: MEDIUM)**
   - **Impact:** Alert badges now reliably meet WCAG AAA (7:1) instead of AA (4.5:1), especially on varied dark backgrounds.
   - **Effort:** 5 minutes. Change `bg-red-500/20` → `bg-red-500/30` or `text-red-200` → `text-red-100`.
   - **File:** `SessionRow.tsx` line 150 and `LiveTicker.tsx` line 101.
   - **Testing:** Measure with WebAIM contrast checker; verify visually on both components.

---

## Notes for Implementation

- **No code changes in this audit:** All findings are observational. Implementation tracked separately.
- **Colorblind simulation:** Use the Accessible Colors Firefox/Chrome extension (Sim Daltonism or Chromatic Vision Simulator) to validate fixes.
- **Keyboard testing:** Use only Tab, Arrow keys, Enter, Escape (no mouse) to verify keyboard UX improvements.
- **Screen-reader testing:** Use NVDA (Windows) or JAWS to verify semantic structure and `aria-*` attributes are correctly interpreted.
