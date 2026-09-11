from __future__ import annotations

import json

import pytest

from scripts.u18_runtime_classifier_candidate import FrozenRuntimeClient
from x_monitor.attribution import (
    _PRAGMATICS_BASE_SYSTEM_PROMPT,
    _PRAGMATICS_FULL_REPAIR_SYSTEM_PROMPT,
    _PRAGMATICS_FULL_SYSTEM_PROMPT,
    _PRAGMATICS_RARE_REPAIR_SYSTEM_PROMPT,
    _PRAGMATICS_RARE_SYSTEM_PROMPT,
    _PRAGMATICS_REVIEW_SYSTEM_PROMPT,
    _PRAGMATICS_SECONDARY_SYSTEM_PROMPT,
)


class _Delegate:
    def __init__(self):
        self.calls = 0

    def messages_create(self, **_kwargs):
        self.calls += 1
        return {"results": []}


def _budget(tmp_path):
    import hashlib

    path = tmp_path / "budget.json"
    systems = (
        _PRAGMATICS_BASE_SYSTEM_PROMPT,
        _PRAGMATICS_SECONDARY_SYSTEM_PROMPT,
        _PRAGMATICS_FULL_SYSTEM_PROMPT,
        _PRAGMATICS_FULL_REPAIR_SYSTEM_PROMPT,
        _PRAGMATICS_REVIEW_SYSTEM_PROMPT,
        _PRAGMATICS_RARE_SYSTEM_PROMPT,
        _PRAGMATICS_RARE_REPAIR_SYSTEM_PROMPT,
    )
    path.write_text(
        json.dumps(
            {
                "lanes": {
                    "test": {
                        "model": "deepseek-v4-flash",
                        "max_tokens_per_attempt": 4096,
                        "temperature": 0,
                        "maximum_requests": 2,
                        "maximum_transport_attempts": 2,
                        "maximum_retries_per_request": 0,
                        "maximum_input_tokens": 100000,
                        "maximum_output_tokens": 8192,
                        "maximum_cost_usd": "1",
                        "input_usd_per_million": "0.44",
                        "output_usd_per_million": "1.32",
                        "allowed_system_sha256": [
                            hashlib.sha256(value.encode()).hexdigest()
                            for value in systems
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _kwargs():
    return {
        "model": "deepseek-v4-flash",
        "max_tokens": 4096,
        "temperature": 0,
        "thinking": {"type": "disabled"},
        "system": _PRAGMATICS_REVIEW_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": "[]"}],
    }


def test_budgeted_runtime_keeps_independent_passes_and_replays_without_spend(tmp_path):
    delegate = _Delegate()
    budget = _budget(tmp_path)
    private = tmp_path / "private"
    first = FrozenRuntimeClient(
        budget_path=budget,
        lane="test",
        private_dir=private,
        delegate=delegate,
    )
    first.messages_create(**_kwargs())
    first.messages_create(**_kwargs())
    assert delegate.calls == 2
    assert first.state["transport_attempts"] == 2

    replay_delegate = _Delegate()
    replay = FrozenRuntimeClient(
        budget_path=budget,
        lane="test",
        private_dir=private,
        delegate=replay_delegate,
    )
    replay.messages_create(**_kwargs())
    replay.messages_create(**_kwargs())
    assert replay_delegate.calls == 0
    assert replay.state["transport_attempts"] == 2

    with pytest.raises(RuntimeError, match="request cap"):
        replay.messages_create(**_kwargs())
