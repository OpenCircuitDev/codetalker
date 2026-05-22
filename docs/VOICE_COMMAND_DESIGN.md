# Voice Command Design Spec
## "Hey CodeTalker, status?" — Query Sessions Without Unlocking

**Feature**: On-demand voice query to check session status, active decisions, and blocked sessions without opening the webui or unlocking the phone.

**Scope**: Pro feature (Android companion + optional XREAL glasses).

**Status**: Design phase. No code. Outlines infrastructure reuse, question shapes, and hard trade-offs.

---

## Context

Across market iterations 6–7 (100 personas), 9 repeated asks for a way to query session status by voice:

- "I need to know which session is blocking me without opening the webui" (Marcus, iter7)
- "Can I ask CodeTalker which session just broke?" (James, iter7)
- "I wish I could ask 'what did I miss while I was sketching?' and get a recap instead of scrolling" (Zara, iter7)

Today's app offers Buddy mode dictation for Q&A (vol-DOWN hold → type question → get LLM-generated answer), but it's conversational and requires the user to phrase their question as natural language. A status-query feature would support predefined shapes ("Is Claude stuck?", "What's happening?") that map to quick structured API calls, keeping latency under 2 seconds and avoiding a round-trip to the LLM.

---

## 1. Wake Word vs Push-to-Talk

### Decision: **Push-to-Talk (PTT) only in v1**

**Why**: Wake-word detection is a licensing / CPU burden tradeoff. The Android `SpeechRecognizer` already supports on-device recognition (Pixel 7+), but adding always-on mic capture for "Hey CodeTalker" triggers:

- Battery drain from continuous audio processing
- Microphone permission complexity (users must grant always-on mic, not just on-demand)
- False positives (saying "code talker" while cooking triggers a query)
- Privacy concerns (always-listening device in pocket)

**v1 UX**: Long-press a new action button or use an existing hold-to-talk gesture (e.g., extended vol-DOWN hold; v1 borrows from Buddy mode's vol-DOWN for consistency). The UI hints "Ask CodeTalker" to signal it's listening for a question shape, not free-form Buddy dictation.

**v2 consideration**: If user testing shows friction from "how do I invoke it without looking?", revisit wake-word with a first-run battery/privacy consent dialog.

---

## 2. STT Infrastructure Reuse

### Existing Path (Buddy Mode)

The companion app already ships `STTRecorder` + `AndroidSTTRecorder` (commit CCT-31 Phase 6). This handles:

- Audio capture via Android `SpeechRecognizer` (on-device + graceful fallback to cloud STT on older devices)
- Partial results (interim transcription for visual feedback)
- Final results and error handling
- Timeout management and recognizer state cleanup (critical fix in commit 2026-05-17)

**Reuse approach**:

1. Create a new state path in `CompanionViewModel`:
   - New `SttMode.QUERY` (parallel to existing `BUDDY` and `DIRECT_CC`)
   - New `sttPhase` substates: `QUERY_RECORDING` → `QUERY_REVIEW` → `QUERY_DISPATCHING`

2. Bind to same `STTRecorder` instance:
   ```kotlin
   // In CompanionViewModel.handleButtonState
   when (newState) {
       ButtonState.QueryListening -> {
           sttMode.value = SttMode.QUERY
           sttRecorder.start()  // Reuse existing start() logic
       }
   }
   ```

3. On final transcription, route to a new dispatcher:
   ```kotlin
   // In CompanionViewModel.onRecognitionComplete
   when (sttMode.value) {
       SttMode.BUDDY -> inject(sessionId, text)  // Existing path
       SttMode.QUERY -> dispatchQuery(sessionId, text)  // New
       SttMode.DIRECT_CC -> directStt(sessionId, text)  // Existing
   }
   ```

4. Keep the REVIEW phase (send / re-record / cancel) so users verify the recognized text before dispatching.

**Gap identified**: The `STTRecorder` abstraction is sound, but the `CompanionViewModel` constructor currently hardcodes `maxRecordingMs = 30_000L`. For status queries, 15 seconds is more appropriate (a question like "which session is blocking?" is short). Make `maxRecordingMs` injectable per `SttMode` or add a second parameter.

---

## 3. Question Shapes (v1 Scope)

Pick **5–8 shapes**; each maps to a single API call or log tail. Recognize via substring match (not NLU) to keep latency <200ms. Fallback to Buddy mode if the query doesn't match a known shape.

### Proposed v1 Shapes

| Shape | Example utterance | API call | Response |
|-------|-------------------|----------|----------|
| **Active summary** | "What's happening?" / "Status" | `GET /api/narration-log?session_id={active}&limit=1` | Read the most recent narration entry; speak its text |
| **Session stuck?** | "Is Claude stuck?" / "Is it blocked?" | `GET /api/sessions/{active}` → check `last_hook_at` age + `lifecycle` | "Session X is blocked. Last activity was 47 seconds ago." |
| **Blocking session** | "Which session is blocking?" / "Which one is stuck?" | `GET /api/sessions` → sort by health state + last_hook_at | "The OCR session is blocked." (or "None are blocked.") |
| **Time since quiet** | "How long has it been quiet?" | Check `last_modified` vs now | "Silent for 23 seconds." |
| **Last decision** | "What was the last decision?" / "Replay the decision" | `GET /api/narration-log?session_id={active}&limit=50` → find last `checkpoint=true` entry | Speak the text of the last checkpoint narration |
| **Session count** | "How many sessions?" | `GET /api/sessions?lifecycle=RUNNING` → count | "Two sessions active." |
| **Active session name** | "What session am I on?" | Return `activeSessionId` from app state | "The design-system session." |

### Pattern Matching (Client-Side)

Implement a simple keyword-based matcher in Kotlin (no cloud call). Each shape has a trigger regex:

```kotlin
data class QueryShape(
    val name: String,
    val triggerRegex: Regex,
    val apiCall: suspend (daemonClient: DaemonClient, sessionId: String) -> String
)

val queryShapes = listOf(
    QueryShape(
        "active_summary",
        Regex("what.*happening|status|update", IGNORE_CASE),
        { client, sid ->
            val log = client.getNarrationLog(sessionId = sid, limit = 1)
            log.firstOrNull()?.text ?: "Nothing yet."
        }
    ),
    QueryShape(
        "is_stuck",
        Regex("stuck|block|is.*hang|frozen", IGNORE_CASE),
        { client, sid ->
            val session = client.getSession(sid)
            val ageSeconds = (System.currentTimeMillis() / 1000) - session.last_hook_at
            if (ageSeconds > 30) "Blocked. Last activity ${ageSeconds}s ago."
            else "Still running."
        }
    ),
    // ... more shapes
)
```

**Ambiguity on match**: If the query matches multiple shapes, prefer the most specific (fewest wildcard segments in the regex). If tied, use the first match in the list.

---

## 4. Response Shape

### Playback

Route to existing audio infrastructure: **priority="alert"** in the daemon's audio queue. This ensures the response interrupts any running narration long enough for the user to hear it, then resumes.

**Pro**: Reuses `TTSPlayer` dispatch logic and priority handling (no new audio paths).

**Con**: A simultaneous narration gets paused/resumed, which may feel jarring. Alternative: mute ongoing narration for the duration of the response, then unmute (softer UX but requires a new mute signal).

**v1 choice**: Use `priority="alert"`. Keep the response short so the pause is brief.

### Length

Cap at **15–20 words** (max ~3 seconds of speech). Examples:

- "The OCR session is blocked. Last activity 47 seconds ago." (10 words)
- "Silent for 23 seconds." (4 words)
- "Two sessions active. OCR is deciding." (6 words)

If the real answer is longer, choose one: (a) truncate and append "…ask the companion app for details", or (b) offer a follow-up prompt like "Want the full activity log?" (requires Buddy mode round-trip).

**v1 choice**: Truncate with "Ask the companion app for details." Keep it snappy.

### Ducking vs Interrupting

**Option A (interrupt)**: Stop the running narration, play the response, resume narration. Simple, but jarring if narration is mid-clause.

**Option B (duck)**: Reduce the volume of running narration, mix in the response on top, then restore volume. Smoother but requires ExoPlayer audio focus manipulation.

**Option C (queue)**: Append to the audio queue with high priority, so it plays as soon as the current narration ends. Delays the response by up to 10 seconds but never interrupts.

**v1 choice**: Option A (interrupt). Latency is critical for a voice query; users expect <2 second response time.

---

## 5. Multi-Session Disambiguation

If the user has 3 active sessions, which one does "What's happening?" refer to?

### Options

| Strategy | Pro | Con |
|----------|-----|-----|
| **Most-recently-active** (last_hook_at) | Simple, often correct | Wrong if user switched context 2 min ago |
| **Currently-narrating session** | Obvious intent when a session is mid-narration | Ambiguous during silence |
| **Last marked-active by user** | Explicit user choice | Requires a UI control |
| **Only-session** (fallback) | Default when exactly 1 is running | Error message when 2+ are running |
| **Voice-disambiguated** ("on the OCR session?") | User is explicit | Requires second utterance |

**v1 choice**: **Most-recently-active, with a voice fallback**. Implement as:

1. On query match, check the app's `activeSessionId` StateFlow.
2. If set and in the most-recent 60 seconds, use it.
3. If ambiguous, respond: "Which session? The OCR one, or the design-system one?" and remain listening for a re-record.
4. If the user says a session name, fuzzy-match against known sessions' display names.

This keeps the modal interaction short while staying under 2 seconds for the common case.

---

## 6. Hard Questions to Flag

### 6.1 Privacy: Always-On Microphone (if v2 adds wake-word)

**The problem**: If v2 adds "Hey CodeTalker" wake-word detection, the app must request `android.permission.RECORD_AUDIO` with continuous capture or a native service listening in the background.

**Impact**:
- Users see "CodeTalker is always listening" in permissions, creating privacy friction.
- Battery drain from continuous audio processing (10–30% on older chips).
- Potential false positives if a third party says "code talker" or a voice assistant conflict.

**Mitigation**:
- v1: PTT only (no always-on mic).
- v2 (if shipped): Offer an opt-in toggle. Require explicit battery/privacy consent on first launch. Disable wake-word on low-battery.
- Future: Partner with device OEM (Pixel, Samsung) for co-processor offload (always-listening without battery drain).

**Decision needed**: Is wake-word a dealbreaker for Gen 1 release, or can v1 ship with PTT and iterate?

### 6.2 Pro Feature: STT + Voice Cloning Already Pro

Asking "what's happening?" and hearing a response in the user's cloned voice is part of the Pro experience. Status queries are Pro-only.

**Implementation gate**:
```kotlin
if (account.tier != AccountTier.PRO) {
    showAlert("Status queries are a Pro feature. Upgrade to use voice commands.")
    return
}
```

**Marketing**: "Get instant session status by voice — no unlocking your phone." (Pro differentiator vs. Basic webui).

### 6.3 Offline Behavior: STT Requires Internet

Android's `SpeechRecognizer` defaults to cloud STT on older devices (pre-Pixel 7); v1 assumes internet connectivity.

**On no internet**:
- `SpeechRecognizer` fires `onError(ERROR_NETWORK)`.
- Current `CompanionViewModel` handles this and shows an error caption.
- App can show toast: "Offline. Try again when connected." and return to IDLE.

**v2 option**: Ship Whisper.cpp for fully offline on-device recognition (larger APK, lower latency, battery trade-off). The `STTRecorder` abstraction already supports swapping engines.

**v1 choice**: Require internet. Document as a limitation.

### 6.4 Latency: Query → STT → API Call → TTS Response

**Target**: <2 seconds end-to-end.

**Breakdown**:
- STT capture + recognition: 1–3s (user dependency; recognizer auto-stops on silence or max time)
- API call (single query): 50–200ms (local daemon, not cloud)
- TTS synthesis: 500–1500ms (depends on response length; cached if re-asked)
- Audio queue dispatch: 100–500ms

**v1 approach**:
- Cache frequent responses (e.g., "Two sessions active. Both idle.") so re-asking plays from cache.
- Use the existing TTS cache layer (`state.tts_cache` in daemon).
- Return short responses (<20 words) so synthesis is fast.
- Prioritize the audio queue so alert-priority responses jump ahead.

**Benchmark**: Ship with simple timer logging in `CompanionViewModel` so we can measure real user latency and tune.

### 6.5 Ambiguous Queries: Fuzzy Session Matching

If the user says "What's happening on the auth session?" but the display name is "auth-middleware", we need fuzzy matching.

**Simple v1**: Exact substring match of display_name against recognized text (case-insensitive).

```kotlin
val query = "what's happening on the auth session"
val sessions = getActiveSessions()
val matched = sessions.firstOrNull {
    it.display_name.contains("auth", ignoreCase = true)
}
```

**Upgrade**: Levenshtein distance or Jaro-Winkler for typo tolerance (e.g., "oder" → "order").

**Decision needed**: How many sessions do we expect the user to name in one utterance? If typically 1–3, exact match + toast on no-match is fine. If 5+, invest in fuzzy matching.

### 6.6 Session Health State Definition

What does it mean for a session to be "blocked"?

**Current model** (from `schemas/session.py` + memory):
- `last_hook_at`: Epoch seconds of last hook fire.
- `lifecycle`: One of DORMANT, LISTENING, NARRATING, DECIDING, QUIET.
- `last_modified`: Transcript file mtime.

**Proposed "blocked" heuristic**:
- `lifecycle == "DECIDING"` OR `last_hook_at` is older than 60 seconds AND `lifecycle != "DORMANT"`.

**Alternative**: Introduce a new `Session.health_state` enum:
```python
class SessionHealthState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    BLOCKED = "blocked"  # No hook activity in >60s while lifecycle != DORMANT
    STUCK = "stuck"  # ERROR lifecycle or health check failed
```

Then the query "Which session is blocking?" becomes:
```python
GET /api/sessions → [s for s in sessions if s.health_state == "blocked"]
```

**v1 choice**: Use the heuristic above (no new schema field). If it's inaccurate, v2 adds `health_state` to the Session model and the narration logs.

### 6.7 Test Coverage: Dialog Flow vs API Accuracy

The REVIEW phase UI (send / re-record / cancel) requires a test matrix:

| Scenario | Result |
|----------|--------|
| User says "what's happening" → recognizer returns "what's happening" → send | ✓ Dispatch the query |
| User says "what's happening" → recognizer returns "watch it snowing" → send | ✗ No match; offer Buddy or re-record |
| User says "which session is blocking" → recognizer returns "which session is locked in" → review → re-record | ✓ UX flow OK |
| User says a short query; recognizer timeout before max_recording_ms | ✓ Auto-transition to REVIEW |

**v1 approach**: Add unit tests to `CompanionViewModelTest` covering query shape matching. Add integration tests with mock `DaemonClient` that verify end-to-end dispatch.

---

## 7. Multi-Iteration Roadmap

### v1 (Current Release)
- [x] Reuse `STTRecorder` for PTT-based query capture
- [x] Implement 5–7 simple question shapes (text match only, no NLU)
- [x] Route to existing audio queue with alert priority
- [x] Keep responses <20 words
- [x] Multi-session fallback: most-recently-active + voice disambiguation
- [x] Pro-only feature gate
- [x] Documentation + help text in UI

### v2 (Iter+1)
- [ ] Wake-word "Hey CodeTalker" (if user research shows PTT friction)
- [ ] Fuzzy session name matching (Levenshtein)
- [ ] Session health_state schema addition + health badge in narration
- [ ] Whisper.cpp for offline STT
- [ ] Caching of common responses (e.g., "Two sessions active")
- [ ] Telemetry: latency histogram + shape distribution

### v3+ (Future)
- [ ] Natural-language queries via Buddy LLM fallback ("What's the latest design decision?" → LLM reads logs and summarizes)
- [ ] Cross-session queries ("Which session made the most progress?" → LLM analyzes all narration logs)
- [ ] Scheduled status reports ("Check on my sessions every 10 minutes and alert me if any are stuck")

---

## 8. Validation Checklist

- [x] Five design sections: wake word, STT reuse, question shapes, response shape, multi-session disambiguation
- [x] Hard questions flagged: privacy (always-on mic), Pro gating, offline fallback, latency, fuzzy matching, health definition, testing
- [x] Memory reconciliation: Pro feature aligns with `pro_vs_basic_differentiation.md` (Pro = Android + exclusive features)
- [x] Infrastructure audit: STT reuse path identified (CompanionViewModel + STTRecorder), gap flagged (maxRecordingMs injection)
- [x] No code written
- [x] No images or SVG
- [x] No release timing promised

---

## 9. Next Steps

1. **Personas review**: Show 2–3 persona quotes to stakeholder review + validate question shapes match real asks.
2. **Latency benchmark**: Measure current daemon API response times on common queries (`GET /api/narration-log`, `GET /api/sessions`).
3. **Prototype v1 shapes**: Implement the 5 shapes above; measure STT accuracy on a test cohort.
4. **UX review**: Iterate the "Ask CodeTalker" hint text, REVIEW phase button labels, and error messaging.
5. **Ship v1**: PTT only, 5 shapes, <20 word responses, Pro-only.
6. **Measure v1**: Collect latency histogram, shape frequency, Buddy fallback rate. Use data to rank v2 features.

---

## Appendix: Example Persona Quotes (Iter 6–7)

> "I need to know which session is blocking me without opening the webui." — Marcus, iter7

> "Right now I have to unlock my phone or check the webui to see if a session is actually still running or if it just went quiet. A simple audio heartbeat every 60 seconds would let me know the daemon didn't crash." — Marcus, iter7

> "I'm running multiple design-system prototype branches in parallel, and I can't tell from the Activity feed which session a decision came from. I need a way to see 'which ones have architectural decisions I should know about?' without hunting through the log." — Priya, iter7

> "I wish I could ask CodeTalker 'what did I miss while I was sketching?' and get a 30-second recap instead of scrolling the Activity feed." — Zara, iter7

> "I want a quick way to ask CodeTalker 'which session just broke?' without opening the webui. Right now I have to guess or tab over." — James, iter7
