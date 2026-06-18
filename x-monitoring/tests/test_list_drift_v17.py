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
   `accounts + staff`) is in the response. If not, write
   `degraded:list_id_invalid` to the run summary and refuse to
   attribute.

2. **List-drift detection** (3-cycle soft warning, plan §"x.com
   mega-list is curated manually"): if a yaml-listed handle is
   absent from Call A's response for 3 consecutive cycles, write
   `degraded:list_drift: [...]` to the summary. Soft warning, not
   a hard fail — the x.com API doesn't expose list membership, so
   "missing" can only be inferred from the response. State
   persists across runs in `data/_list_drift_state.json`.

These tests verify:
  - collect_expected_handles returns the union of accounts + staff
  - check_startup_sanity returns True if ≥1 expected handle in
    response, False otherwise; writes the right summary field
  - update_drift_state increments per missing handle, resets on
    seen, emits the right warning list when threshold hit
  - The state file is JSON, atomic, recoverable on first run
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# --- v1.7 collect_expected_handles --------------------------------------


def test_collect_expected_handles_unions_accounts_and_staff(tmp_path):
    """For 2 enabled models, the union of accounts+staff is the set."""
    from x_monitor.list_drift import collect_expected_handles

    data = tmp_path / "data"
    accounts = data / "accounts"
    accounts.mkdir(parents=True)
    (accounts / "minimax.yaml").write_text(
        "accounts:\n"
        "  - handle: MiniMaxAI\n    role: official\n"
        "  - handle: MiniMax_AI\n    role: staff\n",
        encoding="utf-8",
    )
    (accounts / "qwen.yaml").write_text(
        "accounts:\n"
        "  - handle: Alibaba_Qwen\n    role: staff\n",
        encoding="utf-8",
    )
    handles = collect_expected_handles(
        data, enabled_models=["minimax", "qwen"]
    )
    # Union: 3 handles total
    assert handles == {"MiniMaxAI", "MiniMax_AI", "Alibaba_Qwen"}


def test_collect_expected_handles_skips_missing_yaml(tmp_path):
    """Missing yaml for an enabled model is silently skipped (not an error)."""
    from x_monitor.list_drift import collect_expected_handles

    data = tmp_path / "data"
    (data / "accounts").mkdir(parents=True)
    (data / "accounts" / "minimax.yaml").write_text(
        "accounts:\n  - handle: MiniMaxAI\n    role: official\n",
        encoding="utf-8",
    )
    handles = collect_expected_handles(
        data, enabled_models=["minimax", "no_such_brand"]
    )
    assert handles == {"MiniMaxAI"}


# --- v1.7 startup sanity check -----------------------------------------


def test_check_startup_sanity_returns_true_when_expected_handle_present(tmp_path):
    """The first Call A response has at least one expected handle → OK."""
    from x_monitor.list_drift import check_startup_sanity

    expected = {"MiniMaxAI", "Alibaba_Qwen"}
    response_authors = [
        {"author_handle": "random_user", "text": "hi"},
        {"author_handle": "MiniMaxAI", "text": "release announcement"},
    ]
    ok = check_startup_sanity(
        response_authors, expected, write_summary_field=False
    )
    assert ok is True


def test_check_startup_sanity_returns_false_when_no_expected_handle(tmp_path):
    """All response authors are unknown → list_id is wrong, mark degraded."""
    from x_monitor.list_drift import check_startup_sanity

    expected = {"MiniMaxAI", "Alibaba_Qwen"}
    response_authors = [
        {"author_handle": "satyaXBT", "text": "random"},
        {"author_handle": "karandarda", "text": "another random"},
    ]
    # No expected author in the response → sanity check fails.
    ok = check_startup_sanity(
        response_authors, expected, write_summary_field=False
    )
    assert ok is False


def test_check_startup_sanity_empty_response_is_failure(tmp_path):
    """An empty first response is treated as 'list not found'."""
    from x_monitor.list_drift import check_startup_sanity

    ok = check_startup_sanity(
        [], {"MiniMaxAI"}, write_summary_field=False
    )
    assert ok is False


def test_check_startup_sanity_writes_summary_field_on_failure(tmp_path):
    """On failure, check_startup_sanity writes 'degraded:list_id_invalid'
    to the summary dict (mutates the input)."""
    from x_monitor.list_drift import check_startup_sanity

    summary: dict = {"degraded": {}}
    ok = check_startup_sanity(
        [{"author_handle": "random"}],
        {"MiniMaxAI"},
        write_summary_field=True,
        summary=summary,
    )
    assert ok is False
    assert "list_id_invalid" in summary["degraded"]
    assert "no expected author_handle" in summary["degraded"]["list_id_invalid"].lower() or \
           "expected" in summary["degraded"]["list_id_invalid"].lower()


# --- v1.7 list-drift state (3-cycle soft warning) ----------------------


def test_update_drift_state_increments_missing_handles(tmp_path):
    """Handles absent from the response get their counter incremented."""
    from x_monitor.list_drift import update_drift_state

    state_path = tmp_path / "_list_drift_state.json"
    # First cycle: MiniMaxAI present, Alibaba_Qwen absent.
    drifted = update_drift_state(
        state_path,
        response_authors=[{"author_handle": "MiniMaxAI"}],
        expected={"MiniMaxAI", "Alibaba_Qwen"},
        threshold=3,
    )
    # No drift yet (Alibaba_Qwen has counter=1, threshold=3)
    assert drifted == []
    # Verify state file
    state = json.loads(state_path.read_text())
    assert state.get("Alibaba_Qwen", 0) >= 1
    assert state.get("MiniMaxAI", 0) == 0  # seen, reset to 0


def test_update_drift_state_emits_warning_at_threshold(tmp_path):
    """A handle absent for 3 consecutive cycles is in the warning list."""
    from x_monitor.list_drift import update_drift_state

    state_path = tmp_path / "_list_drift_state.json"
    # 3 cycles with Alibaba_Qwen absent.
    for _ in range(3):
        drifted = update_drift_state(
            state_path,
            response_authors=[{"author_handle": "MiniMaxAI"}],
            expected={"MiniMaxAI", "Alibaba_Qwen"},
            threshold=3,
        )
    # After 3 cycles, Alibaba_Qwen should be in the drift list.
    assert "Alibaba_Qwen" in drifted
    assert "MiniMaxAI" not in drifted


def test_update_drift_state_resets_on_seen_handle(tmp_path):
    """A handle that reappears in the response has its counter reset."""
    from x_monitor.list_drift import update_drift_state

    state_path = tmp_path / "_list_drift_state.json"
    # Cycle 1: absent
    update_drift_state(
        state_path, [{"author_handle": "MiniMaxAI"}],
        {"MiniMaxAI", "Alibaba_Qwen"}, threshold=3,
    )
    state = json.loads(state_path.read_text())
    assert state.get("Alibaba_Qwen", 0) >= 1
    # Cycle 2: reappears
    update_drift_state(
        state_path, [{"author_handle": "Alibaba_Qwen"}],
        {"MiniMaxAI", "Alibaba_Qwen"}, threshold=3,
    )
    state = json.loads(state_path.read_text())
    # Counter reset to 0
    assert state.get("Alibaba_Qwen", 0) == 0


def test_update_drift_state_atomic_writes(tmp_path):
    """The state file is written atomically (write-temp-then-rename)."""
    from x_monitor.list_drift import update_drift_state

    state_path = tmp_path / "_list_drift_state.json"
    update_drift_state(
        state_path, [{"author_handle": "MiniMaxAI"}],
        {"MiniMaxAI", "Alibaba_Qwen"}, threshold=3,
    )
    # File exists, is valid JSON, has the expected key
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert "Alibaba_Qwen" in state


def test_update_drift_state_creates_file_on_first_run(tmp_path):
    """No pre-existing state file → create a fresh one (no crash)."""
    from x_monitor.list_drift import update_drift_state

    state_path = tmp_path / "_list_drift_state.json"
    assert not state_path.exists()
    update_drift_state(
        state_path, [], {"MiniMaxAI"}, threshold=3,
    )
    assert state_path.exists()


def test_update_drift_state_corrupt_json_recovery(tmp_path):
    """A corrupt state file is treated as empty (no crash, fresh start)."""
    from x_monitor.list_drift import update_drift_state

    state_path = tmp_path / "_list_drift_state.json"
    state_path.write_text("{this is not valid json", encoding="utf-8")
    # Must not raise
    drifted = update_drift_state(
        state_path, [{"author_handle": "MiniMaxAI"}],
        {"MiniMaxAI", "Alibaba_Qwen"}, threshold=3,
    )
    assert drifted == []  # cycle 1, threshold not hit
    # File is now valid JSON
    state = json.loads(state_path.read_text())
    assert isinstance(state, dict)


def test_update_drift_state_handles_all_handles_seen(tmp_path):
    """All expected handles present → empty state, no drift."""
    from x_monitor.list_drift import update_drift_state

    state_path = tmp_path / "_list_drift_state.json"
    for _ in range(5):
        drifted = update_drift_state(
            state_path,
            response_authors=[
                {"author_handle": "MiniMaxAI"},
                {"author_handle": "Alibaba_Qwen"},
            ],
            expected={"MiniMaxAI", "Alibaba_Qwen"},
            threshold=3,
        )
    assert drifted == []
    state = json.loads(state_path.read_text())
    # All counters at 0 (or absent)
    for h in ("MiniMaxAI", "Alibaba_Qwen"):
        assert state.get(h, 0) == 0
