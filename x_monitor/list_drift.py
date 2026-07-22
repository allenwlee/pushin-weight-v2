# {{AGENT_ATTRIBUTION}}
"""v1.7 list-drift detection + startup sanity check for the list: operator.

v1.7's Call A uses `(list:<x_monitor_list_id>)` to pull tweets from
all curated list members in one go. Two failure modes need explicit
guards (the v1.6 design had no list, so neither was a concern):

1. **Startup sanity check** (memory feedback
   `feedback_twitterapi_unknown_list_silent_fallback.md`): if the
   list_id is wrong/fake, TwitterAPI.io silently returns "Latest"
   tweets — no error code, no msg. A typo in `x_monitor_list_id`
   would pollute the dashboard for as long as it takes an operator
   to notice. Defense: after the first Call A response, assert at
   least one expected author_handle (from the union of accounts +
   staff) is in the response. If not, write
   `degraded:list_id_invalid` to the run summary and refuse to
   attribute.

2. **List-drift detection** (3-cycle soft warning, plan §"x.com
   mega-list is curated manually"): if a yaml-listed handle is
   absent from Call A's response for 3 consecutive cycles, write
   `degraded:list_drift: [...]` to the summary. Soft warning, not
   a hard fail — the x.com API doesn't expose list membership, so
   "missing" can only be inferred from the response. State persists
   across runs in `data/_list_drift_state.json` (atomic write).

These functions are pure helpers called by `RunPipeline.execute`.
The state file format is `{handle: consecutive_cycles_missing}` and
is intentionally human-inspectable for the operator.

See docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
§"x.com mega-list is curated manually, on a documented cadence"
(Decision 7) and §"List-drift detection" (Unit 1's Approach).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def collect_expected_handles(
    store,
    enabled_models: list[str],
) -> set[str]:
    """Return the union of `accounts + staff` handles across enabled models.

    Plan 2026-07-11-002 (U4): the yaml read path
    (`data/accounts/<model>.yaml`) is retired. The DB's
    `brands_accounts WHERE role_id IN (2, 3)` is canonical; the
    helper reads from the live DB once via
    `Store.read_brand_official_staff_handles`. The `role` field is
    ignored — every handle in the result is considered "expected"
    for the sanity check (a `staff` handle not in the list is also
    a drift).

    Brands with no DB rows (no yaml equivalent) silently contribute
    nothing. The function never raises.
    """
    expected: set[str] = set()
    try:
        seeded = store.read_brand_official_staff_handles(enabled_models)
    except Exception:
        # Defensive — a corrupt DB or missing brands_accounts table
        # shouldn't crash the drift check. The startup sanity check
        # sees an empty expected set; the list_id_invalid flag fires
        # immediately. Operator catches it on the first cycle.
        return expected
    for m in enabled_models:
        for handle, _role in seeded.get(m, []):
            expected.add(handle)
    return expected


def check_startup_sanity(
    response_authors: list[dict[str, Any]],
    expected: set[str],
    *,
    write_summary_field: bool = False,
    summary: dict[str, Any] | None = None,
) -> bool:
    """Verify the first Call A response contains ≥1 expected author.

    The x.com mega-list and the `accounts + staff` yaml are the two
    sources of truth for which handles should appear in Call A's
    response. If 0 expected handles are present, the list_id is
    almost certainly wrong (TwitterAPI.io silently returns Latest
    tweets for unknown list IDs — see
    `feedback_twitterapi_unknown_list_silent_fallback.md`).

    Args:
        response_authors: list of dicts each with at least
            `author_handle` (the field name TwitterAPI.io uses).
        expected: set of author_handles from collect_expected_handles.
        write_summary_field: if True, write `degraded:list_id_invalid`
            into the supplied `summary` dict on failure.
        summary: target dict to mutate (only when write_summary_field).

    Returns:
        True if ≥1 expected handle appears in response_authors
        (casefolded comparison). False otherwise.
    """
    response_handles_cf = {
        (a.get("author_handle") or "").casefold()
        for a in response_authors
        if a.get("author_handle")
    }
    expected_cf = {h.casefold() for h in expected}
    ok = bool(response_handles_cf & expected_cf)
    if not ok and write_summary_field and summary is not None:
        degraded = summary.setdefault("degraded", {})
        if "list_id_invalid" not in degraded:
            n_expected = len(expected_cf)
            n_response = len(response_handles_cf)
            degraded["list_id_invalid"] = (
                f"first Call A response has 0 expected author_handles "
                f"({n_expected} yaml-listed handles, {len(response_handles_cf)} "
                f"distinct authors in response) — list_id is likely wrong. "
                f"Check config.yaml::x_monitor_list_id and the x.com list "
                f"membership. This is a soft warning; the run continues but "
                f"Call A results are not attributed."
            )
    return ok


def _read_state(state_path: Path) -> dict[str, int]:
    """Read the drift state file; return {} on missing or corrupt JSON."""
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Corrupt or unreadable: start fresh. The next write will
        # overwrite with valid JSON. Don't crash — this is a
        # monitoring file, not a critical artifact.
        return {}


def _write_state_atomic(state_path: Path, state: dict[str, int]) -> None:
    """Write the state file atomically (write-temp-then-rename).

    Avoids partial writes that could leave the operator with a
    corrupt file mid-cycle (especially relevant for the
    `corrupt_json_recovery` test).
    """
    state_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(state_path.parent),
        prefix=f".{state_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp_path, state_path)
    except Exception:
        # Best-effort cleanup; surface the original error.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def update_drift_state(
    state_path: Path,
    response_authors: list[dict[str, Any]],
    expected: set[str],
    threshold: int = 3,
) -> list[str]:
    """Update the per-handle missing counter; return handles that drifted.

    For each expected handle:
      - If the handle appears in `response_authors` (casefolded match),
        reset its counter to 0.
      - Otherwise, increment its counter. If the counter reaches
        `threshold`, add the handle to the returned `drifted` list.

    The state file at `state_path` is a JSON dict
    `{handle: consecutive_cycles_missing}`. Atomic write.

    Args:
        state_path: path to the JSON state file
            (e.g. `data/_list_drift_state.json`).
        response_authors: list of dicts with `author_handle`.
        expected: set of expected author_handles (from
            collect_expected_handles).
        threshold: cycles-missing before a handle is considered
            drifted. Default 3 (per the plan).

    Returns:
        List of handles that crossed the threshold THIS call. May
        be empty. (A handle that was drifted in a previous call but
        is not in the response this call still increments, but is
        only re-emitted if it crosses the threshold again — i.e.
        the function emits each drift ONCE per threshold crossing.)
    """
    state = _read_state(state_path)
    seen_cf = {
        (a.get("author_handle") or "").casefold()
        for a in response_authors
        if a.get("author_handle")
    }
    drifted_this_call: list[str] = []
    for h in expected:
        if h.casefold() in seen_cf:
            # Reset on seen.
            state[h] = 0
            continue
        prev = int(state.get(h, 0))
        new_val = prev + 1
        if new_val >= threshold and prev < threshold:
            # Crossed the threshold this call. Emit.
            drifted_this_call.append(h)
        state[h] = new_val
    # Handles no longer in `expected` (e.g. operator removed the
    # yaml entry): clean up by deleting them from state. This
    # prevents a stale entry from triggering a drift warning after
    # the handle has been intentionally removed.
    stale = [h for h in list(state) if h not in expected]
    for h in stale:
        del state[h]
    _write_state_atomic(state_path, state)
    return drifted_this_call
