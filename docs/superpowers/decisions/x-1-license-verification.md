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

## Open questions for the implementer

The following decisions remain open and should be answered when wiring
the code. Each is small (5-10 lines) and shapes the user experience.

### Q1 — `is_pro_feature(feature: str) -> bool`

Which features actually require Pro? Suggested list, but the operator
should confirm:

```python
PRO_FEATURES = {
    "character_attach",       # attach a cloned-voice character to a session
    "voice_clone_create",     # /api/clone-voice endpoint
    "android_companion",      # POST /api/companion/active-session
    "buddy_mode",             # /api/companion/inject (buddy LLM)
    "ar_pairing",             # XREAL glasses pairing flow
    # multi_session_fanin?    # uncertain — currently free in webui
}
```

The "uncertain" entries need a call. The webui can already fan-in
multiple active sessions to desktop speakers; the question is whether
fan-in *to phone* is Pro-only or whether having any phone routing is
Pro-only.

### Q2 — Machine_id binding policy

Stripe issues one subscription per user; the license key is bound to
that subscription. But subscription holders may use Pro on multiple
machines (desktop + laptop + a CI box for tests).

Options:

- **Single-machine**: license activates on first daemon, refuses
  subsequent. Customer must use a "deactivate this machine" UI to
  move.
- **N-machine**: allow up to N (e.g., 3) concurrent activations per
  subscription. Webui shows which machines are active.
- **Unlimited but tracked**: allow any number, but show recent
  activations in the account dashboard so the customer can spot abuse.

Recommendation: **unlimited-but-tracked** for v1 (lowest friction),
revisit if abuse becomes real.

### Q3 — Refund window vs immediate revocation

Stripe refunds emit `charge.refunded`. Currently the website webhook
only handles `customer.subscription.deleted` (cancellations). Refunds
mid-period: should they revoke the license immediately, or honor the
period the customer paid for?

Recommendation: honor the paid period (don't revoke on refund).
Aligns with how SaaS typically handles this.

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
