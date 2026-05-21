# Decision X-1 · License verification

**Status**: Decided · 2026-05-18
**Owner**: Brand
**Scope**: Distribution gate for codetalker-pro
**Touches**: `codetalker` (daemon), `codetalker-pro` (Pro modules), `codetalker-website` (entitlement source of truth)

## The question

How do paying customers prove they're entitled to Pro features?

Two paths were on the table in [the vNext release design](../specs/2026-05-11-vNext-release-design.md#X-1):

- **A · Lemonsqueezy + GitHub repo membership** — invite the user to a private
  `OpenCircuitDev/codetalker-pro` GitHub repo on purchase. Daemon checks repo
  membership via the user's GitHub OAuth token.
- **B · Stripe + HMAC license keys** — Stripe subscription drives entitlement.
  Webhook on `customer.subscription.*` issues a per-user HMAC-signed license key.
  Daemon validates the key against the website at boot and periodically.

## The decision

**B — Stripe subscriptions with HMAC license keys.**

License is checked at daemon launch, then re-polled at a configurable
interval (default 6 hours) so a cancelled or refunded subscription
revokes Pro features without requiring a restart.

## Why

- The [codetalker-website](https://github.com/OpenCircuitDev/codetalker-website)
  was scaffolded earlier this session with Stripe subscription mode +
  `license_keys` table + `/api/licenses/validate` endpoint — option B is
  half-built already.
- Self-serve sign-up doesn't depend on the customer having a GitHub
  account (OAuth via GitHub OR Google OR email/password, all flow
  through the same `users` table).
- HMAC signing gives forgery resistance without a database round-trip
  for the first-layer check; the second-layer DB lookup gates on
  subscription status, machine_id, and revocation flag.
- Stripe's cancellation/refund/dispute machinery is well-trodden;
  Lemonsqueezy's is fine but less battle-tested for our specific shape
  (subscription with per-machine activation).

## The poll-and-fail model

The daemon's licensing client behaves as a **cached online validator**:

| Condition | Behavior |
|---|---|
| First launch, license file present, validate succeeds | `pro_active=True`, cache `last_validated_at=now` |
| First launch, license file absent | `pro_active=False`, no further action |
| First launch, license file present, validate fails (network or 401) | `pro_active=False`, log warning, retry next poll |
| Subsequent poll succeeds | refresh `last_validated_at`, update `pro_active` from response |
| Subsequent poll fails, last success within **grace window** | keep current `pro_active`, log warning |
| Subsequent poll fails, last success **beyond grace window** | force `pro_active=False`, log error |

**Grace window**: default 24 hours (configurable via
`cfg.licensing.grace_window_seconds`). Long enough to ride out Wi-Fi
outages, ISP failures, or a brief website outage. Short enough that a
genuine revocation takes effect within a day.

**Poll interval**: default 6 hours (`cfg.licensing.poll_interval_seconds`).
Lower for faster revocation response; higher to reduce daemon→website
traffic.

## Ratified answers (2026-05-18)

The three open questions from the original draft have been decided by
the operator. Captured here in their final form.

### Q1 — Pro feature inventory · **DECIDED**

```python
PRO_FEATURES = frozenset({
    "character_attach",       # attach a cloned-voice character to a session
    "voice_clone_create",     # /api/characters/{id}/clone-voice (XTTS)
    "buddy_mode",             # /api/companion/inject (OpenRouter buddy LLM)
    "direct_stt",             # /api/companion/direct-stt (voice → SendKeys)
    "ar_pairing",             # /api/companion/pair (XREAL + Android tokens)
    "multi_session_fanin",    # phone receiving N parallel session streams
})
```

Six features, all gated. Notes:

- **`ar_pairing`** sits at `/api/companion/pair`. Existing tokens keep
  working — only the issuance of new tokens is gated. A Basic user
  cannot pair a new device, but a previously-paired device whose
  customer downgrades continues to function until the token expires.
  This is intentional: it avoids ripping audio mid-session away from a
  user who just cancelled.
- **`multi_session_fanin`** has no dedicated endpoint. It's the
  emergent capability of having multiple sessions with
  `audio_outputs=["phone"]`. Today this is transitively gated by
  `ar_pairing` (no pair → no phone → no fan-in). Listed explicitly so
  a future tier split ("phone-basic = 1 session, phone-pro = N") has
  a name to gate on.
- Free users can still BROWSE the character library + voice list +
  fleet UI. Only the **action** (attach, clone, inject, dictate,
  pair) is Pro.

### Q2 — Machine binding · **DECIDED · unlimited-but-tracked**

License activates on every machine that POSTs to
`/api/license/activate`. The webui's `/account` dashboard surfaces
recent `machine_id` activations (already in `license_keys.machine_id`
+ `last_validated_at`) so the customer can spot abuse and contact us
to revoke. No per-machine cap.

Implementation: no daemon-side change needed; the website's
`/api/licenses/validate` already accepts the machine_id, stamps it on
the row, and serves it to the account page.

### Q3 — Refund / cancellation behavior · **DECIDED · honor paid period**

Stripe webhook only revokes the license when the subscription
genuinely ends. Mid-period refunds (`charge.refunded`) do **not**
revoke; the customer keeps Pro until the period they paid for runs
out. This matches the existing
`customer.subscription.updated/deleted` handling in
`webhook.ts` — `status='active'` → keep Pro, anything else
(`cancelled`, `incomplete`) → revoke.

No additional webhook event needs to be handled; the
`charge.refunded` event simply continues to be ignored.

## Implementation order (proving slice)

1. **Decision doc landed.** ✓
2. **Daemon `licensing.py`** — module with `LicenseClient` class, polls
   on a thread, exposes `state.licensing.pro_active`.
3. **Wire one Pro-feature gate** — `character_attach` is the highest-value
   one and the cleanest gate point. Other features follow the same
   pattern in a separate sprint.
4. **Website Stripe webhook** — on `checkout.session.completed`,
   create `subscriptions` row + issue HMAC key + update `users.tier='pro'`.
   On `customer.subscription.deleted`, set `subscriptions.status='cancelled'`.
5. **Tests** — `licensing.py` decision functions (pure), and a fast
   roundtrip integration test using the website's `/api/licenses/validate`.

## Out of scope (this decision)

- The character library UI — currently shown to Basic users with a "PRO" badge.
  Gating the *attach* action is the entitlement check; browsing the library
  stays free.
- Trial period (Stripe `trial_period_days`). Easy to add later;
  the entitlement check naturally treats `status='trialing'` as active.
- Annual billing. Same — Stripe handles it; the daemon doesn't care.
