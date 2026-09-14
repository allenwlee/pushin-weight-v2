from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.u18_openrouter_two_role_pilot import (
    BRAND_SYSTEM_PROMPT,
    CONTENT_SYSTEM_PROMPT,
    FrozenCaps,
    PilotCapExceeded,
    PilotInputError,
    TwoRolePilot,
    _client_factory,
    _floor_report,
    _quality_release_gates,
    attest_provider,
    batches,
    build_public_packets,
    catalog_preflight,
    load_budget,
    merge_role_rows,
    preflight,
    request_signature,
    score_candidate,
)
from x_monitor.attribution import (
    _TWO_ROLE_BRAND_REVISION,
    _TWO_ROLE_CONTENT_REVISION,
    _two_role_fingerprint,
    _two_role_payload,
)
from x_monitor.provider_telemetry import ProviderResponse

VALID_CANDIDATE = {
    "candidate_id": "fixture",
    "model": "fixture/model",
    "provider": "fixture-slug",
    "response_provider": "Fixture Provider",
    "endpoint_aliases": ["Fixture Provider"],
    "quantization": "bf16",
    "data_collection": "allow",
    "zdr": False,
    "reasoning_enabled": False,
    "allow_fallbacks": False,
    "input_usd_per_million": "0.1",
    "output_usd_per_million": "0.2",
    "max_input_price": "0.1",
    "max_output_price": "0.2",
}


def _manifest(count: int = 45) -> dict:
    rows = []
    for index in range(count):
        brand = "qwen" if index % 2 else "deepseek"
        tweet_id = str(1000 + index)
        rows.append(
            {
                "case_id": f"H{index:012d}",
                "example_id": f"example-{index}",
                "brand_id": brand,
                "source_language": ("en", "ja", "zh-cn")[index % 3],
                "selection_evidence": {"secret": "owner answer"},
                "source_row": {
                    "author_handle": "private-handle",
                    "author_name": "private-name",
                    "source_role": "official" if index == 0 else "third_party",
                    "source_hint": "private selection hint",
                    "stratum": "rare_positive",
                    "input_context_fingerprint": "private-fingerprint",
                    "input": {
                        "tweet_id": tweet_id,
                        "text": f"Visible post {index}",
                        "context": [{"kind": "stored_quote", "text": "Visible quote"}],
                        "brand_ids": [brand],
                    },
                },
            }
        )
    return {"rows": rows}


def _reference(manifest: dict) -> dict:
    return {
        "status": "owner_accepted_unblinded",
        "human_grounded": False,
        "human_gate_status": "waived_by_owner",
        "rows": [
            {
                "example_id": row["example_id"],
                "brand_id": row["brand_id"],
                "classification": {
                    "outcome": "classified",
                    "post_types": ["events"],
                    "product_labels": [],
                    "sentiment": "neutral",
                    "china_nationalism": "none",
                    "us_nationalism": "none",
                },
            }
            for row in manifest["rows"]
        ],
    }


def _response(packets, role, *, request_id="req-1", provider="Fixture Provider"):
    payload = _two_role_payload([dict(packet) for packet in packets], role)
    results = []
    for item in payload:
        values = []
        for brand in item["brand_ids"]:
            if role == "content":
                values.append({"brand_id": brand, "outcome": "classified", "post_types": ["events"]})
            else:
                values.append({"brand_id": brand, "product_labels": [], "sentiment": "neutral", "china_nationalism": "none", "us_nationalism": "none"})
        value = {
            "tweet_id": item["tweet_id"],
            "input_context_fingerprint": item["input_context_fingerprint"],
            "role_revision": _TWO_ROLE_CONTENT_REVISION if role == "content" else _TWO_ROLE_BRAND_REVISION,
            "classifications": values,
        }
        if role == "content":
            value["unsanctioned_flags"] = []
        results.append(value)
    return ProviderResponse({"results": results}, usage={"provider": provider, "model": VALID_CANDIDATE["model"], "provider_request_id": request_id, "selected_endpoint": provider, "input_tokens": 10, "output_tokens": 10, "cost_usd": 0})


def test_privacy_packet_and_manifest_order():
    packets, local = build_public_packets(_manifest())
    assert [local[_two_role_fingerprint(packet)]["example_id"] for packet in packets] == [f"example-{i}" for i in range(45)]
    encoded = json.dumps(packets)
    for forbidden in ("case_id", "example_id", "selection_evidence", "author_handle", "author_name", "owner answer", "private-name"):
        assert forbidden not in encoded
    assert packets[0]["affiliations"] == [{"brand_id": "deepseek", "role": "official", "reviewed": True}]
    assert packets[1]["affiliations"] == []
    assert len(local) == 45


def test_exact_batches_and_production_role_payloads():
    packets, _ = build_public_packets(_manifest())
    assert [len(batch) for batch in batches(packets)] == [20, 20, 5]
    assert "Exact envelope" in CONTENT_SYSTEM_PROMPT
    assert "Exact envelope" in BRAND_SYSTEM_PROMPT
    assert _two_role_payload(packets[:1], "content")[0]["role_revision"] == _TWO_ROLE_CONTENT_REVISION


def test_pair_cap_is_checked_before_any_transport():
    packets, _ = build_public_packets(_manifest())
    pilot = TwoRolePilot(VALID_CANDIDATE, caps=FrozenCaps(maximum_logical_requests=0, maximum_transport_attempts=36, maximum_input_tokens=10_000_000, maximum_output_tokens=10_000_000, maximum_reasoning_tokens=0, maximum_spend_usd=100, maximum_cost_per_1000_posts_usd=100))
    calls = []
    with pytest.raises(PilotCapExceeded):
        pilot.run_candidate(packets, lambda _candidate: calls.append(True))
    assert calls == []


def test_retry_envelope_allows_two_attempts_but_no_third():
    packets, _ = build_public_packets(_manifest())
    class Client:
        def __init__(self): self.calls = 0
        def messages_create(self, **kwargs):
            self.calls += 1
            from x_monitor.openrouter import OpenRouterRetryableError
            raise OpenRouterRetryableError("timeout")
    # Exercise the per-role bound directly; a retryable transport fails closed
    # after two attempts and does not call a semantic repair path.
    pilot = TwoRolePilot(VALID_CANDIDATE, max_transport_attempts_per_role=2)
    client = Client()
    with pytest.raises(PilotInputError, match="after 2"):
        pilot._call(role="content", packets=packets[:1], client=client)
    assert client.calls == 2


def test_permanent_semantic_failure_is_counted_once_without_retry():
    from x_monitor.openrouter import OpenRouterPermanentError

    packets, _ = build_public_packets(_manifest())

    class Client:
        calls = 0

        def messages_create(self, **kwargs):
            self.calls += 1
            raise OpenRouterPermanentError(
                "openrouter_response_content_invalid",
                provider_usage={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "reasoning_tokens": 0,
                    "cost_usd": 0.000002,
                    "provider_request_id": "failed-1",
                },
            )

    pilot = TwoRolePilot(VALID_CANDIDATE)
    client = Client()
    with pytest.raises(OpenRouterPermanentError, match="content_invalid"):
        pilot._call(role="content", packets=packets[:1], client=client)
    assert client.calls == 1
    assert pilot.ledger.transport_attempts == 1
    assert pilot.ledger.input_tokens == 10
    assert pilot.ledger.output_tokens == 5
    assert pilot.measurements[0]["failure_code"] == "openrouter_response_content_invalid"


def test_runner_makes_exactly_two_role_calls_per_ordered_batch(tmp_path: Path):
    packets, _local = build_public_packets(_manifest())
    calls = []

    class Client:
        def messages_create(self, **kwargs):
            payload = json.loads(kwargs["messages"][0]["content"])
            role = "content" if kwargs["system"] == CONTENT_SYSTEM_PROMPT else "brand_interpretation"
            calls.append((role, len(payload)))
            return _response(payload, role, request_id=f"req-{len(calls)}")

    result = TwoRolePilot(VALID_CANDIDATE, private_dir=tmp_path).run_candidate(
        packets, lambda _candidate: Client()
    )
    assert len(calls) == 6
    assert sorted(size for _role, size in calls) == [5, 5, 20, 20, 20, 20]
    assert [len(batch["merged"]) for batch in result["batches"]] == [20, 20, 5]
    assert result["ledger"]["logical_requests"] == 6


def test_replay_signature_and_missing_rows_are_deterministic(tmp_path: Path):
    packets, local = build_public_packets(_manifest())
    signature_a = request_signature(candidate=VALID_CANDIDATE, role="content", packets=_two_role_payload(packets[:1], "content"), max_tokens=4096)
    signature_b = request_signature(candidate=VALID_CANDIDATE, role="content", packets=_two_role_payload(packets[:1], "content"), max_tokens=4096)
    assert signature_a == signature_b
    reference = _reference(_manifest())
    result = {"batches": [{"merged": [], "failed_row_keys": []}]}
    score = score_candidate(result, reference, local)
    assert score["source_posts"] == score["post_brand_rows"] == 45
    assert score["coverage_failures"] == 45
    assert score["agreement"] == 0


def test_provider_attestation_requires_pinned_identity():
    response = _response([], "content")
    assert attest_provider(response, VALID_CANDIDATE)["selected_endpoint"] == "Fixture Provider"
    bad = _response([], "content", provider="Other Provider")
    with pytest.raises(PilotInputError, match="attestation"):
        attest_provider(bad, VALID_CANDIDATE)


def test_frozen_budget_and_source_receipts_are_enforced():
    root = Path(__file__).resolve().parents[1]
    budget_path = root / "docs/analysis/2026-09-14-190649-u18-r97-two-role-pilot-contract.json"
    caps, candidates, attempts = load_budget(budget_path)
    assert attempts == 2
    assert caps.maximum_logical_requests == 18
    assert caps.maximum_transport_attempts == 36
    assert sum(caps.per_model[model]["maximum_input_tokens"] for model in caps.per_model) == 522554
    assert [candidate["input_tokens_by_batch"] for candidate in candidates] == [
        [14543, 22071, 9568], [48129, 80325, 38768], [15100, 23152, 9621]
    ]
    assert candidates[2]["maximum_spend_usd"] == "0.0255809750"
    assert all(candidate["response_provider"] in candidate["endpoint_aliases"] for candidate in candidates)
    checked = preflight(budget_path=budget_path)
    assert len(checked["verified_source_receipts"]) >= 9
    assert checked["initial_logical_requests"] == 18


def test_catalog_preflight_checks_exact_route_price_and_parameters():
    candidate = {
        **VALID_CANDIDATE,
        "endpoint_receipt": "https://openrouter.ai/api/v1/models/fixture/model/endpoints",
        "response_model": "fixture/model-build",
        "input_tokens_by_batch": [100, 100, 50],
    }
    fixture = {
        "data": {
            "id": "fixture/model",
            "endpoints": [{
                "name": "Fixture Provider | fixture/model-build",
                "model_id": "fixture/model",
                "provider_name": "Fixture Provider",
                "quantization": "bf16",
                "pricing": {"prompt": "0.0000001", "completion": "0.0000002"},
                "supported_parameters": ["max_tokens", "response_format", "temperature", "reasoning"],
                "max_completion_tokens": 4096,
                "context_length": 8192,
                "status": 0,
            }],
        },
    }
    result = catalog_preflight([candidate], fetch=lambda _url: fixture)
    assert result[0]["provider"] == "Fixture Provider"
    assert all(result[0]["checks"].values())
    fixture["data"]["endpoints"][0]["pricing"]["completion"] = "0.0000003"
    with pytest.raises(PilotInputError, match="completion_price"):
        catalog_preflight([candidate], fetch=lambda _url: fixture)


def test_gemma_unknown_quantization_is_omitted(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    budget_path = root / "docs/analysis/2026-09-14-190649-u18-r97-two-role-pilot-contract.json"
    _caps, candidates, _attempts = load_budget(budget_path)
    gemma = candidates[1]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    client = _client_factory(gemma)
    request = client.build_request(max_tokens=4096, messages=[])
    assert "quantizations" not in request["provider"]


def test_missing_floor_path_fails_except_frozen_support_zero():
    score = {"quality": {}}
    floors = {"all.post_types.labels.other.f1": 0.55, "all.typo.accuracy": 0.5}
    report = _floor_report(score, floors, ["all.post_types.labels.other.f1"])
    assert report["checks"]["all.post_types.labels.other.f1"]["status"] == "unmeasured"
    assert report["checks"]["all.post_types.labels.other.f1"]["passed"] is True
    assert report["checks"]["all.typo.accuracy"]["status"] == "missing"
    assert report["checks"]["all.typo.accuracy"]["passed"] is False
    assert report["passed"] is False


def test_all_61_floors_and_release_gates_are_measured_on_perfect_result():
    root = Path(__file__).resolve().parents[1]
    budget = json.loads((root / "docs/analysis/2026-09-14-190649-u18-r97-two-role-pilot-contract.json").read_text())
    manifest = json.loads((root / ".context/u18/human-ambiguity-study-v1/selection-manifest.json").read_text())
    reference = json.loads((root / ".context/u18/human-ambiguity-study-v1/owner-accepted-reference.json").read_text())
    _packets, local = build_public_packets(manifest)
    reference_by_pair = {
        (row["example_id"], row["brand_id"]): row["classification"]
        for row in reference["rows"]
    }
    merged = []
    for row_key, metadata in local.items():
        classification = reference_by_pair[(metadata["example_id"], metadata["brand_id"])]
        merged.append({"row_key": row_key, "target_brand": metadata["brand_id"], **classification})
    unsupported = budget["baseline_metrics"]["per_label_support_and_f1"]["unsupported"]
    score = score_candidate(
        {"batches": [{"merged": merged, "failed_row_keys": []}]},
        reference,
        local,
        budget["quality_floors"]["floors"],
        unsupported,
    )
    floor_gate = score["floor_gate"]
    assert len(floor_gate["checks"]) == 61
    assert floor_gate["passed"] is True
    assert {name for name, item in floor_gate["checks"].items() if item.get("status") == "unmeasured"} == set(unsupported)
    release = _quality_release_gates(score, budget)
    assert release["improvement_composite"]["passed"] is True
    assert release["axis_regression"]["passed"] is True
    assert release["per_label_regression"]["passed"] is True


def test_multibrand_merge_joins_by_brand_without_cross_transfer():
    packet = {
        "tweet_id": "opaque",
        "text": "DeepSeek says its model beats MiniMax. Subscribe to DeepSeek.",
        "context": [],
        "brand_ids": ["deepseek", "minimax"],
        "affiliations": [{"brand_id": "deepseek", "role": "official", "reviewed": True}],
        "source_language": "en",
    }
    fingerprint = _two_role_fingerprint(packet)
    content = {"results": [{
        "tweet_id": "opaque", "input_context_fingerprint": fingerprint,
        "role_revision": _TWO_ROLE_CONTENT_REVISION, "unsanctioned_flags": [],
        "classifications": [
            {"brand_id": "minimax", "outcome": "classified", "post_types": ["results_evaluations", "opinions_reactions"]},
            {"brand_id": "deepseek", "outcome": "classified", "post_types": ["advertising_marketing", "results_evaluations", "opinions_reactions"]},
        ],
    }]}
    brand = {"results": [{
        "tweet_id": "opaque", "input_context_fingerprint": fingerprint,
        "role_revision": _TWO_ROLE_BRAND_REVISION,
        "classifications": [
            {"brand_id": "deepseek", "product_labels": [], "sentiment": "positive", "china_nationalism": "none", "us_nationalism": "none"},
            {"brand_id": "minimax", "product_labels": [], "sentiment": "negative", "china_nationalism": "none", "us_nationalism": "none"},
        ],
    }]}
    merged, failures = merge_role_rows(content, brand, [packet])
    by_brand = {row["target_brand"]: row for row in merged}
    assert failures == set()
    assert "advertising_marketing" in by_brand["deepseek"]["post_types"]
    assert "advertising_marketing" not in by_brand["minimax"]["post_types"]
    assert by_brand["deepseek"]["sentiment"] == "positive"
    assert by_brand["minimax"]["sentiment"] == "negative"


def test_replay_reads_signed_artifacts_without_transport(tmp_path: Path):
    packets, _local = build_public_packets(_manifest())
    for batch in batches(packets):
        for role in ("content", "brand_interpretation"):
            payload = _two_role_payload(batch, role)
            signature = request_signature(candidate=VALID_CANDIDATE, role=role, packets=payload, max_tokens=4096)
            response = _response(payload, role, request_id=f"replay-{signature[:8]}")
            path = tmp_path / "responses" / f"{signature}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"signature": signature, "response": dict(response), "usage": response.provider_usage}))
    result = TwoRolePilot(VALID_CANDIDATE, private_dir=tmp_path).run_candidate(
        packets,
        client_factory=lambda _candidate: pytest.fail("replay constructed a transport"),
        replay=True,
    )
    assert [len(batch["merged"]) for batch in result["batches"]] == [20, 20, 5]
    assert all(item["replay"] is True for item in result["measurements"])
