# {{AGENT_ATTRIBUTION}}
"""v1.7 tests for x_monitor.list_drift: startup sanity check + 3-cycle drift.

v1.7's Call A uses `(list:<x_monitor_list_id>)` to pull tweets from all
curated list members in one go. Two failure modes must be guarded:

1. **Startup sanity check** (memory feedback
   `feedback_twitterapi_unknown_list_silent_fallback.md`): if the
   list_id is wrong/fake, TwitterAPI.io silently returns "Latest"
   tweets — no error code, no msg. A typo in `x_monitor_list_id`
   would pollute the dashboard for as long as it takes an operator
   to notice. Defense: after the first Call A response, assert at
   least one expected author_handle (from the union of
   `brands_accounts` official+staff) is in the response. If not,
   write `degraded:list_id_invalid` to the run summary and refuse
   to attribute.

2. **List-drift detection** (3-cycle soft warning, plan §"x.com
   mega-list is curated manually"): if a DB-listed handle is
   absent from Call A's response for 3 consecutive cycles, write
   `degraded:list_drift: [...]` to the summary. Soft warning, not
   a hard fail — the x.com API doesn't expose list membership, so
   "missing" can only be inferred from the response. State
   persists across runs in `data/_list_drift_state.json` (atomic
   write).

These tests verify:
  - collect_expected_handles returns the union of official+staff
    (read from `brands_accounts WHERE role_id IN (2, 3)`)
  - check_startup_sanity returns True if ≥1 expected handle in
    response, False otherwise; writes the right summary field
  - update_drift_state increments per missing handle, resets on
    seen, emits the right warning list when threshold hit
  - The state file is JSON, atomic, recoverable on first run

Plan 2026-07-11-002 (U4): data/accounts/*.yaml retired; collect_expected_handles
now reads from the live DB via Store.read_brand_official_staff_handles.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _seed_brands_accounts(store, fixtures: list[tuple[str, str, str]]) -> None:
    """Seed `brands_accounts` edges for testing.

    `fixtures` is a list of (brand_id, handle, role_key) tuples. The
    helper inserts the brand row (if missing), the account row (if
    missing), and the edge row in one go."""
    for brand_id, handle, role_key in fixtures:
        store._conn.execute(
            "INSERT OR IGNORE INTO brands(nickname, is_sentinel) VALUES (?, 0)",
            (brand_id,),
        )
        store._conn.execute(
            "INSERT OR IGNORE INTO accounts(author_id, handle) VALUES (?, ?)",
            (f"handle:{handle}", handle),
        )
        account_id = store._conn.execute(
            "SELECT id FROM accounts WHERE handle=?",
            (handle,),
        ).fetchone()["id"]
        role_id = store._conn.execute(
            "SELECT id FROM roles WHERE key=?", (role_key,)
        ).fetchone()["id"]
        brand_pk = store._conn.execute(
            "SELECT id FROM brands WHERE nickname=?", (brand_id,)
        ).fetchone()["id"]
        store._conn.execute(
            "INSERT INTO brands_accounts(brand_id, accounts_id, role_id, added_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (brand_pk, account_id, role_id),
        )
    store._conn.commit()


# --- v1.7 collect_expected_handles --------------------------------------


def test_collect_expected_handles_unions_official_and_staff(tmp_path):
    """For 2 enabled models, the union of official+staff handles is
    the set. Plan 2026-07-11-002 (U4): the helper reads from
    `brands_accounts WHERE role_id IN (2, 3)`."""
    from x_monitor.list_drift import collect_expected_handles
    from x_monitor.store import Store

    p = tmp_path / "drift.db"
    s = Store(p, auto_migrate=True)
    try:
        _seed_brands_accounts(s, [
            ("minimax", "MiniMaxAI", "official"),
            ("minimax", "MiniMax_AI", "staff"),
            ("qwen", "Alibaba_Qwen", "staff"),
        ])
        handles = collect_expected_handles(
            s, enabled_models=["minimax", "qwen"]
        )
        assert handles == {"MiniMaxAI", "MiniMax_AI", "Alibaba_Qwen"}
    finally:
        s.close()


def test_collect_expected_handles_skips_brand_with_no_handles(tmp_path):
    """An enabled brand with no DB handles contributes nothing to the
    set — no error, just an absent brand."""
    from x_monitor.list_drift import collect_expected_handles
    from x_monitor.store import Store

    p = tmp_path / "no_brand.db"
    s = Store(p, auto_migrate=True)
    try:
        _seed_brands_accounts(s, [
            ("minimax", "MiniMaxAI", "official"),
        ])
        handles = collect_expected_handles(
            s, enabled_models=["minimax", "no_such_brand"]
        )
        assert handles == {"MiniMaxAI"}
    finally:
        s.close()


# --- v1.7 startup sanity check -----------------------------------------


def test_check_startup_sanity_returns_true_when_expected_handle_present(tmp_path):
    """If response_authors contains at least one expected handle (casefolded),
    check_startup_sanity returns True and writes nothing."""
    from x_monitor.list_drift import check_startup_sanity

    response_authors = [
        {"author_handle": "minimax_ai"},
        {"author_handle": "OtherHandle"},
    ]
    expected = {"MiniMaxAI", "MiniMax_AI"}
    summary: dict = {}
    assert check_startup_sanity(
        response_authors, expected, write_summary_field=True, summary=summary
    ) is True
    assert "degraded" not in summary


def test_check_startup_sanity_returns_false_when_no_overlap(tmp_path):
    """If response_authors has zero overlap with expected, returns False and
    writes `degraded:list_id_invalid` (when write_summary_field=True)."""
    from x_monitor.list_drift import check_startup_sanity

    response_authors = [{"author_handle": "stranger1"}, {"author_handle": "stranger2"}]
    expected = {"MiniMaxAI", "MiniMax_AI"}
    summary: dict = {}
    assert check_startup_sanity(
        response_authors, expected, write_summary_field=True, summary=summary
    ) is False
    assert "degraded" in summary
    assert "list_id_invalid" in summary["degraded"]


def test_check_startup_sanity_case_insensitive_match(tmp_path):
    """Match is casefolded so 'minimaxai' equals 'MiniMaxAI' (same
    string after casefold; underscores are not normalized)."""
    from x_monitor.list_drift import check_startup_sanity

    response_authors = [{"author_handle": "MiniMaxAI"}]
    expected = {"minimaxai"}
    assert check_startup_sanity(response_authors, expected) is True


def test_check_startup_sanity_no_write_when_disabled(tmp_path):
    """`write_summary_field=False` does NOT mutate the summary even on failure."""
    from x_monitor.list_drift import check_startup_sanity

    response_authors = [{"author_handle": "stranger"}]
    expected = {"MiniMaxAI"}
    summary = {"existing_field": 42}
    assert check_startup_sanity(
        response_authors, expected, write_summary_field=False, summary=summary
    ) is False
    assert "degraded" not in summary


def test_check_startup_sanity_writes_once_per_summary(tmp_path):
    """A second failure does not duplicate the message — the existing entry is kept."""
    from x_monitor.list_drift import check_startup_sanity

    response_authors = [{"author_handle": "stranger"}]
    expected = {"MiniMaxAI"}
    summary: dict = {}
    check_startup_sanity(response_authors, expected, write_summary_field=True, summary=summary)
    first_msg = summary["degraded"]["list_id_invalid"]
    # Second call — already-present key is preserved (no overwrite).
    check_startup_sanity(response_authors, expected, write_summary_field=True, summary=summary)
    assert summary["degraded"]["list_id_invalid"] == first_msg


# --- v1.7 update_drift_state --------------------------------------------


def _make_response(*handles: str) -> list[dict]:
    return [{"author_handle": h} for h in handles]


def test_update_drift_state_no_drifts_when_all_present(tmp_path):
    """All expected handles appear in the response — drift list is empty,
    and the state file's counters are reset to 0."""
    from x_monitor.list_drift import update_drift_state

    state = tmp_path / "state.json"
    response = _make_response("MiniMaxAI", "MiniMax_AI", "OtherHandle")
    expected = {"MiniMaxAI", "MiniMax_AI"}
    drifted = update_drift_state(state, response, expected, threshold=3)
    assert drifted == []
    # State file reflects the reset (counters at 0, not deleted).
    state_after = json.loads(state.read_text(encoding="utf-8"))
    assert state_after == {"MiniMaxAI": 0, "MiniMax_AI": 0}


def test_update_drift_state_increments_per_missing_handle(tmp_path):
    """Each missing handle increments its counter; the threshold-crossing
    handle emits exactly once."""
    from x_monitor.list_drift import update_drift_state

    state = tmp_path / "state.json"
    expected = {"A", "B", "C"}
    # First call: response has A; A resets to 0, B and C increment to 1.
    drifted1 = update_drift_state(
        state, _make_response("A"), expected, threshold=3,
    )
    assert drifted1 == []
    state_after_1 = json.loads(state.read_text(encoding="utf-8"))
    assert state_after_1 == {"A": 0, "B": 1, "C": 1}

    # Second call: response still has A; A resets to 0, B and C increment to 2.
    drifted2 = update_drift_state(
        state, _make_response("A"), expected, threshold=3,
    )
    assert drifted2 == []
    state_after = json.loads(state.read_text(encoding="utf-8"))
    assert state_after == {"A": 0, "B": 2, "C": 2}


def test_update_drift_state_emits_drift_on_threshold_cross(tmp_path):
    """A handle crossing threshold=3 for the first time emits ONCE."""
    from x_monitor.list_drift import update_drift_state

    state = tmp_path / "state.json"
    expected = {"Z"}
    # Three cycles of "Z" missing.
    update_drift_state(state, _make_response(), expected, threshold=3)
    update_drift_state(state, _make_response(), expected, threshold=3)
    drifted3 = update_drift_state(state, _make_response(), expected, threshold=3)
    assert drifted3 == ["Z"]
    # Fourth call — already at threshold; does NOT re-emit.
    drifted4 = update_drift_state(state, _make_response(), expected, threshold=3)
    assert drifted4 == []


def test_update_drift_state_resets_on_seen(tmp_path):
    """A missing handle that appears in the response gets its counter reset to 0."""
    from x_monitor.list_drift import update_drift_state

    state = tmp_path / "state.json"
    expected = {"X", "Y"}
    update_drift_state(state, _make_response(), expected, threshold=3)  # X=1, Y=1
    update_drift_state(state, _make_response("X"), expected, threshold=3)  # X=0, Y=2
    update_drift_state(state, _make_response(), expected, threshold=3)  # X=1, Y=3 → emit Y
    update_drift_state(state, _make_response("Y"), expected, threshold=3)  # X=2, Y=0
    state_after = json.loads(state.read_text(encoding="utf-8"))
    assert state_after == {"X": 2, "Y": 0}


def test_update_drift_state_cleans_stale_entries(tmp_path):
    """Handles no longer in `expected` are removed from state (so a stale
    handle doesn't trigger a drift warning after removal)."""
    from x_monitor.list_drift import update_drift_state

    state = tmp_path / "state.json"
    expected_initial = {"A", "B"}
    update_drift_state(state, _make_response(), expected_initial, threshold=3)  # A=1, B=1
    # Operator removes A from enabled_models (or its DB row); second call uses
    # an updated expected set without A.
    expected_after = {"B"}
    update_drift_state(state, _make_response(), expected_after, threshold=3)  # B=2; A is dropped
    state_after = json.loads(state.read_text(encoding="utf-8"))
    assert "A" not in state_after
    assert state_after == {"B": 2}


def test_update_drift_state_handles_missing_state_file(tmp_path):
    """A first run with no state file starts fresh — no exception,
    no drift emission, file is written."""
    from x_monitor.list_drift import update_drift_state

    state = tmp_path / "fresh_state.json"
    expected = {"A", "B"}
    drifted = update_drift_state(state, _make_response(), expected, threshold=3)
    assert drifted == []
    assert state.exists()
    body = json.loads(state.read_text(encoding="utf-8"))
    assert body == {"A": 1, "B": 1}


def test_update_drift_state_recovers_from_corrupt_json(tmp_path):
    """A corrupt state file is recovered by treating it as empty —
    the next write overwrites it with valid JSON."""
    from x_monitor.list_drift import update_drift_state

    state = tmp_path / "corrupt.json"
    state.write_text("this is not valid json{", encoding="utf-8")
    expected = {"A"}
    drifted = update_drift_state(state, _make_response(), expected, threshold=3)
    assert drifted == []
    # State file was rewritten with valid JSON.
    body = json.loads(state.read_text(encoding="utf-8"))
    assert body == {"A": 1}