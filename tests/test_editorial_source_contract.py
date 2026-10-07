"""Replay observed ownership failures against both the wire schema and parser."""

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from monitor.editorial import providers
from monitor.editorial.config import load_editorial_config
from monitor.editorial.contracts import Event
from monitor.editorial.grounding import normalize_reply
from monitor.editorial.voices import load_voice
from monitor.editorial.writing import editor_request, validate_copy, writer_request


@pytest.fixture
def setup_contract():
    packet = json.loads(
        Path("tests/fixtures/editorial_source_ownership.json").read_text()
    )
    packet.pop("provenance")
    cfg = load_editorial_config(Path("config/editorial-english-launch.yaml"))
    return packet, cfg, editor_request(packet, cfg)


def support_for(req, canonical_id, field="original_text"):
    label = next(k for k, v in req["source_ids"].items() if v == canonical_id)
    option = next(
        o
        for o in req["source_bindings"]
        if o["post_id"] == label and o["source_field"] == field
    )
    return {
        **{
            k: copy.deepcopy(option[k])
            for k in ("post_id", "source_field", "brand_keys")
        },
        "span_ids": option["span_ids"][:1],
    }


def event_wire(supports):
    event = Event(
        key="source-ownership",
        summary="Source-grounded development",
        reason="Evidence",
        occurred_at="2026-10-04T00:00:00Z",
        post_ids=[s["post_id"] for s in supports],
        chatter=True,
        pulse=True,
        importance=70,
    ).model_dump(mode="json")
    event.pop("brand_keys")
    event.pop("post_ids")
    event["source_check"] = [
        {
            "support": s,
            "action": "reports",
            "target": "model",
            "status": "source_report",
            "number_ownership": "none",
        }
        for s in supports
    ]
    return {"events": [event]}


@pytest.mark.parametrize(
    "post_id,wrong_brand",
    [
        ("2106503895375851947", "glm"),  # GLM claim attached to a Qwen reply.
        (
            "2106398475558482342",
            "qwen",
        ),  # Qwen appears in prose, but is not a collected match here.
    ],
)
def test_observed_brand_mix_rejected_by_schema_and_local_parser(
    setup_contract, post_id, wrong_brand
):
    _, _, req = setup_contract
    support = support_for(req, post_id)
    support["brand_keys"].append(wrong_brand)
    data = event_wire([support])
    validator = Draft202012Validator(req["response_schema"])
    assert not validator.is_valid(data)
    with pytest.raises(ValueError, match="ownership mismatch"):
        normalize_reply(data, req, editor=True)


def test_grouped_story_keeps_each_brand_attached_to_its_own_source(setup_contract):
    _, _, req = setup_contract
    data = event_wire(
        [
            support_for(req, pid)
            for pid in ("2106503895375851947", "2106383170857791527")
        ]
    )
    Draft202012Validator.check_schema(req["response_schema"])
    Draft202012Validator(req["response_schema"]).validate(data)
    result = normalize_reply(data, req, editor=True)["events"][0]
    assert result["brand_keys"] == ["glm", "qwen"]
    assert result["post_ids"] == ["2106503895375851947", "2106383170857791527"]
    assert [c["brand_keys"] for c in result["source_check"]] == [["qwen"], ["glm"]]
    assert "brand_keys" not in data["events"][0]  # No mutation of the receipt.


def test_quote_cannot_borrow_original_authors_comparison_passage(setup_contract):
    _, _, req = setup_contract
    support = support_for(req, "2106398475558482342", "stored_quote")
    support["span_ids"] = support_for(req, "2106398475558482342")["span_ids"]
    data = event_wire([support])
    assert not Draft202012Validator(req["response_schema"]).is_valid(data)
    with pytest.raises(ValueError, match="ownership mismatch"):
        normalize_reply(data, req, editor=True)


@pytest.mark.parametrize(
    "defect", ["legacy_brands", "extra_source", "flat_support", "guessed_id"]
)
def test_local_parser_rejects_bypasses_even_without_provider_schema_enforcement(
    setup_contract, defect
):
    _, _, req = setup_contract
    data = event_wire([support_for(req, "2106398475558482342")])
    event = data["events"][0]
    if defect == "legacy_brands":
        event["brand_keys"] = ["qwen"]
    elif defect == "extra_source":
        event["post_ids"] = [support_for(req, "2106503895375851947")["post_id"]]
    elif defect == "flat_support":
        claim = event["source_check"][0]
        claim.update(claim.pop("support"))
    else:
        event["source_check"][0]["support"]["post_id"] = "2106398475558482342"
    with pytest.raises(ValueError):
        normalize_reply(data, req, editor=True)


def test_writer_receives_sources_without_editor_prose_and_checks_final_copy(
    setup_contract,
):
    packet, cfg, req = setup_contract
    event = Event.model_validate(
        normalize_reply(
            event_wire([support_for(req, "2106383170857791527")]), req, editor=True
        )["events"][0]
    )
    event.summary = "TAINTED EDITOR SUMMARY"
    event.reason = "TAINTED EDITOR REASON"
    event.source_check[0].target = "TAINTED EDITOR CLAIM"
    writer = writer_request(event, packet, load_voice("pulse-en-v1"), cfg)
    assert "TAINTED" not in writer["user"]
    assert set(json.loads(writer["user"])["event"]) == {"post_ids", "brand_keys"}
    assert list(writer["response_schema"]["properties"])[:2] == [
        "source_check",
        "supported_copy",
    ]
    support = support_for(writer, "2106383170857791527")
    checked = {
        "headline": "GLM model available on platform",
        "byline": "A source reports availability",
        "article": "A platform advertises access to GLM-5.3-FlashX.",
    }
    raw = {
        **checked,
        "supported_copy": checked.copy(),
        "locale": "en",
        "visual_brief": "",
        "source_check": event_wire([support])["events"][0]["source_check"],
    }
    raw["source_check"][0]["number_ownership"] = (
        "GLM-5.3-FlashX is the model version named by the source."
    )
    Draft202012Validator(writer["response_schema"]).validate(raw)
    normalized = normalize_reply(raw, writer, editor=False)
    validate_copy(normalized, event, "en", packet=packet)
    normalized["headline"] = "Developer launches new model"
    with pytest.raises(ValueError, match="differs from supported copy"):
        validate_copy(normalized, event, "en", packet=packet)
    raw.pop("supported_copy")
    with pytest.raises(ValueError, match="missing supported copy"):
        normalize_reply(raw, writer, editor=False)


def test_schema_budget_rejects_before_any_provider_send(setup_contract, monkeypatch):
    _, cfg, req = setup_contract
    cfg = cfg.model_copy(update={"max_schema_bytes": 4000})
    assert len(json.dumps(req["response_schema"]).encode()) > cfg.max_schema_bytes

    def unexpected(*args, **kwargs):
        pytest.fail("Over-budget schema must not reserve or send")

    monkeypatch.setattr(providers, "call_once", unexpected)
    with pytest.raises(ValueError, match="schema cap"):
        providers.json_call(
            None, "editor", cfg.routes["editor"], req, cfg, transport=unexpected
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("chart_support", "not_supported"),
        ("chart_support", "supported"),
        ("chart_fact_ids", ["invented"]),
        ("change", "unchanged"),
        ("story_id", "00000000-0000-0000-0000-000000000001"),
        ("person_ids", ["00000000-0000-0000-0000-000000000001"]),
    ],
)
def test_empty_context_cannot_select_measurements_or_existing_identities(
    setup_contract, field, value
):
    from monitor.editorial.selection import validate_decisions

    packet, _, req = setup_contract
    packet.update(people=[], stories=[])
    data = event_wire([support_for(req, "2106383170857791527")])
    data["events"][0][field] = value
    assert not Draft202012Validator(req["response_schema"]).is_valid(data)
    with pytest.raises(ValueError):
        validate_decisions(normalize_reply(data, req, editor=True), packet)


def test_available_context_preserves_valid_existing_story_and_measurement(
    setup_contract,
):
    packet, cfg, _ = setup_contract
    story_id = "00000000-0000-0000-0000-000000000001"
    packet.update(
        stories=[{"id": story_id}],
        people=[{"id": story_id}],
        chart_context=[{"brand_key": "glm", "facts": [{"fact_id": "glm-volume"}]}],
    )
    req = editor_request(packet, cfg)
    data = event_wire([support_for(req, "2106383170857791527")])
    data["events"][0].update(
        change="update",
        story_id=story_id,
        person_ids=[story_id],
        chart_fact_ids=["glm-volume"],
        chart_support="supported",
    )
    Draft202012Validator(req["response_schema"]).validate(data)
    from monitor.editorial.selection import validate_decisions

    validate_decisions(normalize_reply(data, req, editor=True), packet)


def test_speaker_is_derived_from_source_field_not_model_claim(setup_contract):
    _, _, req = setup_contract
    original = support_for(req, "2106398475558482342")
    quote = support_for(req, "2106398475558482342", "stored_quote")
    data = event_wire([original, quote])
    normalized = normalize_reply(data, req, editor=True)
    assert [c["actor"] for c in normalized["events"][0]["source_check"]] == [
        "trawasthi_ai",
        "Aleph__Alpha",
    ]
    data["events"][0]["source_check"][0]["actor"] = "Aleph__Alpha"
    assert not Draft202012Validator(req["response_schema"]).is_valid(data)
    with pytest.raises(ValueError, match="code-owned"):
        normalize_reply(data, req, editor=True)


@pytest.mark.parametrize(
    "summary,code",
    [
        (
            "Multiple independent reports confirm the partnership.",
            "unverified source independence",
        ),
        ("The model has 78B parameters.", "numeric copy without number ownership"),
    ],
)
def test_observed_audit_contradictions_hold_before_writing(
    setup_contract, summary, code
):
    from monitor.editorial.selection import validate_decisions

    packet, _, req = setup_contract
    packet.update(people=[], stories=[])
    data = normalize_reply(
        event_wire([support_for(req, "2106398475558482342")]), req, editor=True
    )
    data["events"][0]["summary"] = summary
    with pytest.raises(ValueError, match=code):
        validate_decisions(data, packet)


def test_numeric_audit_and_attributed_report_are_allowed(setup_contract):
    from monitor.editorial.selection import validate_decisions

    packet, _, req = setup_contract
    packet.update(people=[], stories=[])
    data = normalize_reply(
        event_wire([support_for(req, "2106398475558482342", "stored_quote")]),
        req,
        editor=True,
    )
    event = data["events"][0]
    event["summary"] = (
        "The quoted developer describes Kolibri as a 78B-parameter model; no independent confirmation is supplied."
    )
    event["source_check"][0]["number_ownership"] = (
        "Kolibri: 78B total parameters, as stated by Aleph__Alpha in the supplied quote."
    )
    validate_decisions(data, packet)


def test_repeated_author_groups_do_not_establish_independence():
    from monitor.editorial.grounding import source_provenance

    assert source_provenance(
        [
            {"id": "S001", "author_id": "a"},
            {"id": "S002", "author_id": "a"},
            {"id": "S003", "author_id": "b"},
            {"id": "S004"},
        ]
    )["same_author_post_groups"] == [["S001", "S002"]]
