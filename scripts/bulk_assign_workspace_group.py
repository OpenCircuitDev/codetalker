#!/usr/bin/env python3
"""Bulk-assign workspace_group to codetalker sessions.

Matches the user's mental categorization (OCR / CodeTalker / OCDev) without
clicking into each of the 86 sessions individually. Edit the RULES below
to fit your projects, dry-run first, then commit with --apply.

Usage:
    python scripts/bulk_assign_workspace_group.py            # dry-run preview
    python scripts/bulk_assign_workspace_group.py --apply    # commit
    python scripts/bulk_assign_workspace_group.py --clear    # remove ALL workspace_group assignments

Predicates run in order — first match wins. To leave a session unassigned,
make sure no rule matches it (it will land in the "Ungrouped" group on the
webui Sessions list).
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DAEMON_BASE = "http://127.0.0.1:17832"


# ---------------------------------------------------------------------------
# RULES — edit these to fit your projects.
#
# Each rule is (predicate, group_label). Predicates take a session dict
# (the row shape returned by GET /api/sessions) and return True/False.
# The first matching rule wins; non-matching sessions stay unassigned.
#
# Useful fields on the session dict:
#   display_name  e.g. "OCRGame", "Pickng Up From A Steady Sonnet"
#   cwd           e.g. r"C:\Users\brand\Dropbox\OCR\Open_Circuit\BF_Workspace"
#                 (empty string for dormant sessions — restart daemon for full coverage)
#   project_slug  e.g. "Workspace", "codetalker"
#   project_dir   e.g. "C--Users-brand-Dropbox-OCR-Open-Circuit-codetalker"
#                 (only available after daemon restart picks up the v0.1.0 fix)
# ---------------------------------------------------------------------------

def _name(s: dict) -> str:
    return (s.get("display_name") or "").lower()


def _cwd(s: dict) -> str:
    return (s.get("cwd") or "").lower()


def _project_dir(s: dict) -> str:
    return (s.get("project_dir") or "").lower()


def _project_slug(s: dict) -> str:
    return (s.get("project_slug") or "").lower()


RULES: list[tuple] = [
    # 1. CodeTalker — most specific repo match. Anything explicitly named
    #    CodeTalker / CT... or in the codetalker repo path.
    (
        lambda s: (
            "codetalker" in _name(s)
            or _name(s).startswith("ct")
            or "codetalker" in _cwd(s)
            or "codetalker" in _project_dir(s)
            or _project_slug(s) == "codetalker"
        ),
        "CodeTalker",
    ),
    # 2. OCDev — dev tooling for OCR (memory palace, forge, dev infra).
    #    MUST come BEFORE OCR because cwds like `ocr-memory-palace`
    #    would otherwise be claimed by OCR's broader "ocr in cwd" match.
    (
        lambda s: (
            "ocdev" in _name(s)
            or "ocr-memory-palace" in _cwd(s)
            or "memory-palace" in _cwd(s)
            or "ocr-forge" in _cwd(s)
            or "ocr-forge" in _project_dir(s)
            or "ocr-memory-palace" in _project_dir(s)
            or "ocdev" in _project_dir(s)
        ),
        "OCDev",
    ),
    # 3. OCR — broadest catch-all for OCR-flavored work that isn't dev tooling.
    #    "OCR" in name, BF_Workspace, BlueprintForge, or any other Open_Circuit
    #    cwd that didn't already get claimed by OCDev above.
    (
        lambda s: (
            "ocr" in _name(s)
            or "bf_workspace" in _cwd(s)
            or "blueprintforge" in _cwd(s)
            or "open_circuit" in _cwd(s)
            or "open-circuit" in _project_dir(s)
        ),
        "OCR",
    ),
]


# ---------------------------------------------------------------------------
# Rule precedence note
# ---------------------------------------------------------------------------
# Rules fire in the order they're declared. The first match wins, then later
# rules are skipped for that session. Current order prioritizes specificity:
#   1. CodeTalker (specific repo)
#   2. OCDev (specific dev-tooling subdirs of OCR — must come before OCR)
#   3. OCR (broad catch-all for OCR-flavored work)
# Reorder if your mental model differs.


# ---------------------------------------------------------------------------
# Rule precedence note
# ---------------------------------------------------------------------------
# Rules fire in the order they're declared. The first match wins, then later
# rules are skipped for that session. So if you want OCDev to claim a session
# that ALSO matches OCR's rule (e.g. `ocr-memory-palace` cwd contains "ocr"),
# move the OCDev rule above the OCR rule. The current order prioritizes:
#   1. CodeTalker (most specific repo match)
#   2. OCR (broad — anything with "OCR" in name or in OCR-rooted cwds)
#   3. OCDev (dev tooling subset of OCR-rooted)
# Reorder if your mental model differs.


def fetch_sessions() -> list[dict]:
    with urllib.request.urlopen(f"{DAEMON_BASE}/api/sessions", timeout=3) as r:
        return json.load(r)


def put_workspace_group(sid: str, group: str | None) -> None:
    body = json.dumps({"workspace_group": group}).encode()
    req = urllib.request.Request(
        f"{DAEMON_BASE}/api/sessions/{sid}/overlay",
        method="PUT",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read()


def plan_assignments(sessions: list[dict]) -> list[tuple]:
    """Return list of (sid, display_name, target_group, current_group)."""
    out = []
    for s in sessions:
        sid = s["session_id"]
        current = s.get("workspace_group")
        target = None
        for pred, label in RULES:
            try:
                if pred(s):
                    target = label
                    break
            except Exception:
                continue
        if target is not None and current != target:
            out.append((sid, s.get("display_name") or sid[:8], target, current))
    return out


def summarize_distribution(sessions: list[dict]) -> dict[str, dict[str, int]]:
    """Return per-group counts: how many sessions already match each rule
    target vs how many would migrate vs how many have no matching rule.
    Used by --dry-run to show the full picture, not just the pending diff."""
    summary: dict[str, dict[str, int]] = {}
    no_rule = 0
    for s in sessions:
        current = s.get("workspace_group")
        target = None
        for pred, label in RULES:
            try:
                if pred(s):
                    target = label
                    break
            except Exception:
                continue
        if target is None:
            no_rule += 1
            continue
        bucket = summary.setdefault(target, {"already": 0, "will_change": 0})
        if current == target:
            bucket["already"] += 1
        else:
            bucket["will_change"] += 1
    summary["(no rule matched)"] = {"already": no_rule, "will_change": 0}
    return summary


def main() -> int:
    apply = "--apply" in sys.argv
    clear = "--clear" in sys.argv

    if clear:
        sessions = fetch_sessions()
        targets = [s for s in sessions if s.get("workspace_group")]
        print(f"--clear: {len(targets)} sessions currently have workspace_group set.")
        if not apply:
            for s in targets[:20]:
                print(f"  would clear: {s.get('display_name'):50s} (was {s.get('workspace_group')!r})")
            if len(targets) > 20:
                print(f"  ... and {len(targets) - 20} more")
            print("\nRe-run with --apply --clear to commit.")
            return 0
        for s in targets:
            put_workspace_group(s["session_id"], None)
        print(f"Cleared workspace_group on {len(targets)} sessions.")
        return 0

    sessions = fetch_sessions()
    plan = plan_assignments(sessions)
    summary = summarize_distribution(sessions)

    print(f"=== bulk_assign_workspace_group ===")
    print(f"Total sessions: {len(sessions)}")
    print()
    print("Distribution after rules apply:")
    for target in sorted(summary.keys()):
        b = summary[target]
        total = b["already"] + b["will_change"]
        print(
            f"  {target:30s} {total:3d} total  ({b['already']:3d} already, {b['will_change']:3d} to migrate)"
        )
    print()
    print(f"Pending changes: {len(plan)}")
    print()

    by_target: dict[str, list[tuple]] = {}
    for sid, name, target, cur in plan:
        by_target.setdefault(target, []).append((name, cur))
    for target in sorted(by_target.keys()):
        rows = by_target[target]
        print(f"  -> {target} ({len(rows)} sessions)")
        for name, cur in rows[:8]:
            cur_str = f"  (was {cur!r})" if cur else ""
            print(f"      - {name}{cur_str}")
        if len(rows) > 8:
            print(f"      ... and {len(rows) - 8} more")
        print()

    if not apply:
        print("Dry run. Re-run with --apply to commit.")
        return 0

    failed = []
    for sid, name, target, _ in plan:
        try:
            put_workspace_group(sid, target)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            failed.append((name, e))
    print(f"Committed {len(plan) - len(failed)} assignments.")
    if failed:
        print(f"Failures ({len(failed)}):")
        for name, err in failed[:10]:
            print(f"  • {name}: {err}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
