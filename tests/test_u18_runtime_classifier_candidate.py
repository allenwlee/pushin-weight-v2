from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import u18_runtime_base_batch_probe
from scripts.u18_runtime_base_batch_probe import _run_base_batches
from scripts import u18_runtime_review_model_probe
from scripts.u18_runtime_classifier_candidate import (
    DEFAULT_BUDGET,
    DEFAULT_COHORT,
    FrozenRuntimeClient,
    _candidate_row,
    _response_manifest_sha256,
    _runtime_trace_provenance,
)
from scripts.u18_runtime_grouped_label_probe import _merge_group_decisions
from scripts.u18_runtime_review_model_probe import DirectAnthropicDelegate
from x_monitor.attribution import (
    _PRAGMATICS_BASE_SYSTEM_PROMPT,
    _PRAGMATICS_COMPLETENESS_REVIEW_REPAIR_PROMPT_VERSION,
    _PRAGMATICS_COMPLETENESS_REVIEW_REPAIR_SYSTEM_PROMPT,
    _PRAGMATICS_COMPLETENESS_REVIEW_PROMPT_VERSION,
    _PRAGMATICS_COMPLETENESS_REVIEW_SYSTEM_PROMPT,
    _PRAGMATICS_COMPLETENESS_SELECTOR_VERSION,
    _PRAGMATICS_FULL_REPAIR_SYSTEM_PROMPT,
    _PRAGMATICS_FULL_REPAIR_PROMPT_VERSION,
    _PRAGMATICS_FULL_SYSTEM_PROMPT,
    _PRAGMATICS_RARE_REPAIR_SYSTEM_PROMPT,
    _PRAGMATICS_RARE_SYSTEM_PROMPT,
    _PRAGMATICS_REVIEW_SYSTEM_PROMPT,
    _PRAGMATICS_PRIMARY_PROMPT_VERSION,
    _PRAGMATICS_PRIMARY_SYSTEM_PROMPT,
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


def test_base_batch_probe_freezes_five_post_batches(monkeypatch):
    calls = []

    def classify(batch, *_args, **_kwargs):
        calls.append([row["tweet_id"] for row in batch])
        return [{"tweet_id": row["tweet_id"]} for row in batch]

    monkeypatch.setattr(
        u18_runtime_base_batch_probe,
        "_classify_stage1_base_batch",
        classify,
    )
    client = type(
        "Client",
        (),
        {"budget": {"model": "deepseek-v4-flash", "max_tokens_per_attempt": 4096}},
    )()
    tweets = [{"tweet_id": str(index)} for index in range(12)]

    results = _run_base_batches(
        tweets,
        client=client,
        batch_size=5,
        max_workers=1,
    )

    assert calls == [["0", "1", "2", "3", "4"], ["5", "6", "7", "8", "9"], ["10", "11"]]
    assert [row["tweet_id"] for row in results] == [str(index) for index in range(12)]


def test_grouped_probe_replaces_only_its_common_labels():
    base = {
        "outcome": "classified",
        "post_types": ["events", "opinions_reactions", "releases_updates"],
        "product_labels": ["testimonial"],
        "sentiment": "positive",
    }

    merged = _merge_group_decisions(
        base,
        {
            "releases_updates": False,
            "business_finance": True,
            "research_explanations": False,
            "hands_on_usage": True,
            "results_evaluations": True,
            "opinions_reactions": True,
            "questions_requests": False,
            "advertising_marketing": False,
        },
    )

    assert set(merged["post_types"]) == {
        "business_finance",
        "events",
        "hands_on_usage",
        "opinions_reactions",
        "results_evaluations",
    }
    assert merged["product_labels"] == ["testimonial"]


def test_direct_anthropic_delegate_omits_proxy_thinking_field():
    class Delegate:
        def messages_create(self, **kwargs):
            return kwargs

    delegate = DirectAnthropicDelegate("unused", delegate=Delegate())

    result = delegate.messages_create(
        model="claude-haiku-4-5-20251001",
        thinking={"type": "disabled"},
        messages=[],
    )

    assert "thinking" not in result
    assert result["model"] == "claude-haiku-4-5-20251001"


def test_candidate_row_preserves_primary_review_final_trace():
    primary = {"outcome": "classified", "post_types": ["opinions_reactions"]}
    review = {"outcome": "classified", "post_types": ["releases_updates"]}
    source = {
        "example_id": "example-1",
        "brand_id": "minimax",
        "source_language": "en",
        "context_provenance": {},
        "input_context_fingerprint": "fingerprint",
        "stratum": "common",
        "source_role": "official",
        "source_hint": "hint",
    }
    result = {
        "valid": True,
        "by_brand": {"minimax": review},
        "classification_trace": {
            "selector_version": _PRAGMATICS_COMPLETENESS_SELECTOR_VERSION,
            "primary": {
                "valid": True,
                "by_brand": {"minimax": primary},
                "prompt_version": _PRAGMATICS_PRIMARY_PROMPT_VERSION,
            },
            "review": {
                "valid": True,
                "by_brand": {"minimax": review},
                "metadata_by_brand": {
                    "minimax": {
                        "decision": "replace",
                        "change_reasons": ["missing_post_type"],
                        "evidence": [{"source": "source", "quote": "launch"}],
                    }
                },
                "prompt_version": _PRAGMATICS_COMPLETENESS_REVIEW_PROMPT_VERSION,
            },
            "final": {
                "valid": True,
                "by_brand": {"minimax": review},
            },
        },
    }

    row = _candidate_row(source, result)

    assert row["classification"] == review
    assert row["classification"] == row["classification_trace"]["final"]["classification"]
    assert row["classification_trace"]["primary"]["classification"] == primary
    assert row["classification_trace"]["review"]["classification"] == review
    assert row["classification_trace"]["review"]["metadata"]["decision"] == "replace"


def test_runtime_trace_provenance_pins_current_prompts_and_selector():
    provenance = _runtime_trace_provenance()

    assert provenance == {
        "primary_prompt_version": _PRAGMATICS_PRIMARY_PROMPT_VERSION,
        "primary_prompt_sha256": hashlib.sha256(
            _PRAGMATICS_PRIMARY_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "primary_repair_prompt_version": _PRAGMATICS_FULL_REPAIR_PROMPT_VERSION,
        "primary_repair_prompt_sha256": hashlib.sha256(
            _PRAGMATICS_FULL_REPAIR_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "review_prompt_version": _PRAGMATICS_COMPLETENESS_REVIEW_PROMPT_VERSION,
        "review_prompt_sha256": hashlib.sha256(
            _PRAGMATICS_COMPLETENESS_REVIEW_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "review_repair_prompt_version": (
            _PRAGMATICS_COMPLETENESS_REVIEW_REPAIR_PROMPT_VERSION
        ),
        "review_repair_prompt_sha256": hashlib.sha256(
            _PRAGMATICS_COMPLETENESS_REVIEW_REPAIR_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "selector_version": _PRAGMATICS_COMPLETENESS_SELECTOR_VERSION,
    }


def test_default_v24_budget_pins_zero_transport_replay_and_current_selector():
    budget = json.loads(DEFAULT_BUDGET.read_text(encoding="utf-8"))
    lane = budget["lanes"][budget["lane"]]
    provenance = _runtime_trace_provenance()

    assert DEFAULT_COHORT.name == "thinking-probe-cohort.json"
    assert budget["cohort"] == {
        "bytes": 248569,
        "cohort_id": "u18-development-thinking-probe-v1",
        "development_only": True,
        "rows": 120,
        "selection": (
            "fixed-seed 40 each en/zh-cn/ja from the consumed 500-row development "
            "cohort; unchanged from v18 and v23"
        ),
        "sha256": "54f86b329475a87dfd1dc64e5aeec9fed83053b452a8e4456c884df83b3cb908",
    }
    assert {
        provenance["primary_prompt_sha256"],
        provenance["primary_repair_prompt_sha256"],
        provenance["review_prompt_sha256"],
        provenance["review_repair_prompt_sha256"],
    } == set(lane["allowed_system_sha256"])
    assert budget["prompt"]["selector_version"] == (
        _PRAGMATICS_COMPLETENESS_SELECTOR_VERSION
    )
    assert budget["replay"]["network_transport_allowed"] is False
    assert lane["maximum_requests"] == 0
    assert lane["maximum_transport_attempts"] == 0
    assert lane["maximum_output_tokens"] == (
        lane["maximum_transport_attempts"] * lane["max_tokens_per_attempt"]
    )


def test_runtime_replays_external_frozen_response_with_transport_disabled(
    tmp_path, monkeypatch
):
    budget = _budget(tmp_path)
    document = json.loads(budget.read_text(encoding="utf-8"))
    lane = document["lanes"]["test"]
    lane.update(
        {
            "maximum_requests": 0,
            "maximum_transport_attempts": 0,
            "maximum_input_tokens": 0,
            "maximum_output_tokens": 0,
            "maximum_cost_usd": "0",
        }
    )
    budget.write_text(json.dumps(document), encoding="utf-8")
    response_dir = tmp_path / "source-responses"
    response_dir.mkdir()
    request_id = FrozenRuntimeClient._signature(_kwargs())
    (response_dir / f"{request_id}_00.json").write_text(
        json.dumps({"results": [{"cached": True}]}), encoding="utf-8"
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    local_response_dir = tmp_path / "replay-state" / "responses"
    local_response_dir.mkdir(parents=True)
    (local_response_dir / f"{request_id}_00.json").write_text(
        json.dumps({"results": [{"cached": False}]}), encoding="utf-8"
    )

    client = FrozenRuntimeClient(
        budget_path=budget,
        lane="test",
        private_dir=tmp_path / "replay-state",
        replay_response_dirs=(response_dir,),
    )

    assert client.messages_create(**_kwargs()) == {"results": [{"cached": True}]}
    assert client.state["replay_hits"] == 1
    assert client.state["transport_attempts"] == 0

    missed = {**_kwargs(), "messages": [{"role": "user", "content": "miss"}]}
    with pytest.raises(RuntimeError, match="cap exhausted"):
        client.messages_create(**missed)


def test_response_manifest_detects_cached_response_tampering(tmp_path):
    response_dir = tmp_path / "responses"
    response_dir.mkdir()
    response = response_dir / "request_00.json"
    response.write_text('{"results":[]}', encoding="utf-8")

    original = _response_manifest_sha256(response_dir)
    response.write_text('{"results":[{}]}', encoding="utf-8")

    assert _response_manifest_sha256(response_dir)[0] == original[0]
    assert _response_manifest_sha256(response_dir)[1] != original[1]


def test_retired_v18_review_probe_requires_explicit_acknowledgement():
    with pytest.raises(RuntimeError, match="retired historical v18 experiment"):
        u18_runtime_review_model_probe.run(
            budget_path=Path("unused-budget.json"),
            cohort_path=Path("unused-cohort.json"),
            output_path=Path("unused-output.json"),
            private_dir=Path("unused-private"),
        )
