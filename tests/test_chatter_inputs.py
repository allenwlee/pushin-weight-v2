"""Selector model context stays separate from its full saved retrieval ledger."""

import json
from copy import deepcopy
from datetime import timedelta

import pytest

from core.models import OriginalContent, Post
from monitor.editorial.chatter_accounting import call_once
from monitor.editorial.chatter_discovery import request
from monitor.editorial.chatter_inputs import (
    _selection_packet,
    _selection_request,
    reconstruct_selection_request,
)
from monitor.editorial.providers import json_call, request_fingerprint, request_payload
from tests.test_chatter_chain import wire
from tests.test_chatter_gathering import (
    ranked as ranked,  # noqa: PLC0414 - pytest fixture export
)
from tests.test_original_content_consideration import producer

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def gathered(ranked, count):
    from monitor.editorial.chatter_gathering import gather_trends

    run, cfg = ranked
    Post.objects.bulk_create([
        Post(tweet_id=str(9000000000000000000 + index),
             text="Original headline 1 " + "source passage " * 40,
             author_handle="reporter", lang="en",
             created_at=run.facts_as_of - timedelta(minutes=1))
        for index in range(count)
    ])
    result = gather_trends(run.pk, cfg=cfg, enqueue=lambda *args: None)
    assert result["status"] == "discovered", result
    run.refresh_from_db()
    return run, cfg


@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_large_saved_retrieval_ledger_does_not_block_the_real_selector_send(
    ranked, monkeypatch
):
    run, cfg = gathered(ranked, 178)
    monkeypatch.setenv(cfg.chatter.selector.key_env, "fixture-only")
    lead = run.outcome["gathering"]["leads"][0]
    lead["raw_ids"] = [str(8000000000000000000 + index) for index in range(10000)]
    run.save(update_fields=["outcome"])
    payload = _selection_packet(run, cfg)
    legacy = request_payload(cfg.chatter.selector, request("selection", payload, cfg))
    limit = cfg.max_packet_bytes + cfg.max_schema_bytes + 30000
    assert len(request_fingerprint(legacy)[0]) > limit
    before = deepcopy(payload)
    built, full = _selection_request(run, "selector:0", payload, cfg)
    rendered = json.loads(built["user"])
    sent = []

    def transport(endpoint, key, body, **kwargs):
        sent.append(body)
        return wire({"fixture": True}, cfg.chatter.selector.model)

    reply = json_call(run, "selector:0", cfg.chatter.selector, built, cfg,
                      transport=transport, reservation=call_once)
    assert reply["data"] == {"fixture": True}
    assert len(sent) == 1 and len(request_fingerprint(sent[0])[0]) <= limit
    assert rendered["candidates"] == before["candidates"]
    assert sum(len(row["evidence"]) for row in rendered["candidates"]) == 178
    for key in before.keys() - {"coverage"}:
        assert rendered[key] == before[key]
    summary = rendered["coverage"]["gathering"]["leads"][0]
    for key in ("rank", "headline_ids", "coverage", "query_state", "error_code",
                "matched_count", "qualified_count", "context_clipped",
                "context_omitted_count", "source_observed_at"):
        assert summary[key] == lead[key]
    assert summary["raw_count"] == 10000
    assert summary["source_gaps"] == lead["source_gaps"]
    assert "raw_ids" not in summary and "captured_request_ids" not in summary
    run.refresh_from_db()
    assert run.outcome["gathering"]["leads"][0] == lead
    assert run.outcome["selection_inputs"]["selector:0"]["payload"]["coverage"] == before["coverage"]
    assert full == before
    full["history_expansion_complete"] = True
    followup, expanded = _selection_request(run, "selector:1", full, cfg)
    assert expanded["coverage"] == before["coverage"]
    assert len(request_fingerprint(request_payload(cfg.chatter.selector, followup))[0]) <= limit
    run.refresh_from_db()
    assert run.outcome["selection_inputs"]["selector:1"]["payload"]["coverage"] == before["coverage"]


@pytest.mark.parametrize("ranked", [1], indirect=True)
@pytest.mark.parametrize("builder", ["chatter-selection-v1", "chatter-selection-v2", "chatter-selection-v3"])
def test_saved_selector_request_keeps_its_builder_and_reconstructs_after_lease(
    ranked, builder
):
    run, cfg = gathered(ranked, 1)
    payload = _selection_packet(run, cfg)
    built, full = _selection_request(run, "selector:0", payload, cfg)
    if builder.endswith("v1"):
        built = request("selection", payload, cfg)
    reference = {"run_id": run.pk, "stage": "selector:0", "builder": builder}
    if builder.endswith("v3"):
        from monitor.editorial.chatter_inputs import (
            _render_selection_input,
            _selector_request,
        )

        _, rendered = _render_selection_input(
            run, "selector:0", run.outcome["selection_inputs"]["selector:0"], reference
        )
        built = _selector_request(rendered, cfg, builder)
    body = request_payload(cfg.chatter.selector, built)
    content = OriginalContent.objects.filter(run=run).first()
    call = producer(content, "en")
    call.stage = "selector:0"
    call.request_hash = request_fingerprint(body)[1]
    call.request_packet = {"input_reference": reference}
    call.save(update_fields=["stage", "request_hash", "request_packet"])
    replay, actual = _selection_request(run, "selector:0", payload, cfg)
    assert replay["input_reference"] == reference
    assert request_payload(cfg.chatter.selector, replay) == body
    assert actual == full
    run.lease_until = run.facts_as_of - timedelta(minutes=1)
    run.save(update_fields=["lease_until"])
    assert reconstruct_selection_request(call) == body
    call.request_hash = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        reconstruct_selection_request(call)

@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_rolling_selector_uses_short_prompt_and_reconstructs_exactly(ranked, monkeypatch):
    from monitor.editorial.chatter_inputs import _ROLLING_SELECTOR_SYSTEM
    from monitor.editorial.chatter_trends import DECISION_SCOPE

    run, cfg = gathered(ranked, 3)
    run.scope_key = DECISION_SCOPE
    run.save(update_fields=["scope_key"])
    monkeypatch.setenv(cfg.chatter.selector.key_env, "fixture-only")
    payload = _selection_packet(run, cfg)
    built, full = _selection_request(run, "selector:0", payload, cfg)
    assert built["system"] == _ROLLING_SELECTOR_SYSTEM
    assert built["input_reference"]["builder"] == "chatter-selection-v4"
    assert json.loads(built["user"])["candidates"] == payload["candidates"]
    sent = []

    def transport(endpoint, key, body, **kwargs):
        sent.append(body)
        return wire({"fixture": True}, cfg.chatter.selector.model)

    json_call(run, "selector:0", cfg.chatter.selector, built, cfg,
              transport=transport, reservation=call_once)
    call = run.provider_calls.get(stage="selector:0")
    assert len(sent) == 1
    assert reconstruct_selection_request(call) == sent[0]
    assert full == payload


def test_selector_v4_bounds_excerpts_without_changing_saved_sources(monkeypatch):
    from types import SimpleNamespace

    from monitor.editorial.chatter_inputs import _render_selection_input

    sources = {
        str(i): {"id": str(i), "original_text": "long text " * 600,
                 "stored_quote": "quote " * 600, "excerpt_truncated": False}
        for i in range(74)
    }
    saved = deepcopy(sources)
    monkeypatch.setattr("monitor.editorial.chatter_inputs.resolved_sources", lambda _: sources)
    run = SimpleNamespace(pk=100, snapshot={})
    payload = {"candidates": [{"post_ids": list(sources)}], "coverage": {}}
    reference = {"run_id": 100, "stage": "selector:0", "builder": "chatter-selection-v4"}
    full, rendered = _render_selection_input(run, "selector:0", {"schema_version": 1, "payload": payload}, reference)
    assert sources == saved
    assert len(full["candidates"][0]["evidence"][0]["original_text"]) == 6000
    assert len(rendered["candidates"][0]["evidence"]) == 74
    assert all(len(row["original_text"]) == 1200 and len(row["stored_quote"]) == 1200
               and row["excerpt_truncated"] for row in rendered["candidates"][0]["evidence"])
    reference["builder"] = "chatter-selection-v3"
    _, legacy = _render_selection_input(run, "selector:0", {"schema_version": 1, "payload": payload}, reference)
    assert len(legacy["candidates"][0]["evidence"][0]["original_text"]) == 6000


def test_selector_excerpt_limit_counts_utf8_bytes(monkeypatch):
    from types import SimpleNamespace

    from monitor.editorial.chatter_inputs import _render_selection_input

    source = {"id": "1", "original_text": "汉" * 1000, "stored_quote": "", "excerpt_truncated": False}
    monkeypatch.setattr("monitor.editorial.chatter_inputs.resolved_sources", lambda _: {"1": source})
    payload = {"candidates": [{"post_ids": ["1"]}], "coverage": {}}
    ref = {"run_id": 1, "stage": "selector:0", "builder": "chatter-selection-v4"}
    full, rendered = _render_selection_input(SimpleNamespace(pk=1, snapshot={}), "selector:0", {"schema_version": 1, "payload": payload}, ref)
    excerpt = rendered["candidates"][0]["evidence"][0]
    assert len(excerpt["original_text"].encode("utf-8")) == 1200
    assert excerpt["excerpt_truncated"]
    assert full["candidates"][0]["evidence"][0]["original_text"] == "汉" * 1000


@pytest.mark.parametrize("language,number,count", [("ja", 6, 12), ("en", 8, 20)])
@pytest.mark.parametrize("ranked", [1], indirect=True)
def test_global_event_history_budget_preserves_evidence_and_reconstructs(ranked, monkeypatch, language, number, count):
    run, cfg = gathered(ranked, 3)
    from monitor.editorial.chatter_trends import DECISION_SCOPE
    run.scope_key = DECISION_SCOPE
    run.save(update_fields=["scope_key"])
    payload = _selection_packet(run, cfg)
    candidate = payload["candidates"][0]
    phrase = ("量子開発者会議で報告された出来事" if language == "ja" else "Reported previously at the conference. ") * 160
    payload["candidates"] = []
    for pos in range(number):
        editions = [{"edition_id": f"{pos}-{n}", "dossier_id": None, "story_id": f"story-{pos}",
            "published": run.facts_as_of.isoformat(), "locale": language, "headline": f"Headline {n}",
            "angle": phrase[:350], "article": phrase[:1600], "cited_passages": [{"excerpt": phrase[:300]}] * 3}
            for n in range(count)]
        payload["candidates"].append({**candidate, "candidate_ref": str(pos),
                                      "event_history": {"editions": editions, "dossiers": []}})
    built, full = _selection_request(run, "selector:0", payload, cfg)
    route = cfg.chatter.selector
    sent = []
    monkeypatch.setenv(route.key_env, "fixture")
    json_call(run, "selector:0", route, built, cfg, transport=lambda _url, _key, body, **kw:
              (sent.append(body) or wire({"fixture": True}, route.model)), reservation=call_once)
    run.refresh_from_db()
    assert reconstruct_selection_request(run.provider_calls.get(stage="selector:0")) == sent[0]
    assert len(request_fingerprint(sent[0])[0]) <= cfg.max_packet_bytes + cfg.max_schema_bytes + 30000
    retained = [c["event_history"]["editions"] for c in full["candidates"]]
    assert all(r and r[0]["edition_id"] == f"{i}-0" for i, r in enumerate(retained))
    assert sum(map(len, retained)) < number * count
    assert all(c["evidence"] == candidate["evidence"] for c in full["candidates"])


@pytest.mark.parametrize("source_language,excerpt,source_detail", [
    ("zh", "员工高呼欢迎他归来", "高呼"), ("fr", "Les employés l'ont accueilli avec une ovation.", "ovation"),
    ("und", "Los empleados lo recibieron con aplausos.", "aplausos"),
])
def test_translated_followup_checks_source_detail_in_its_original_language(source_language, excerpt, source_detail):
    from monitor.editorial.chatter_coverage import decisions_for

    edition = {"edition_id": "old", "story_id": "story", "dossier_id": None, "locale": "en",
               "headline": "Old headline", "angle": "The board reversed its decision.", "article": "He was rehired.",
               "published": "2026-11-24T02:00:00+00:00"}
    candidate = {"candidate_ref": "candidate", "event_history": {"editions": [edition], "dossiers": []},
                 "source_usages": {"source": "consideration"}, "evidence": [{"id": "source", "author_handle": "witness",
                 "original_text": excerpt, "source_language": source_language}]}
    passage = {"source_id": "source", "excerpt": excerpt}
    assignment = {"support": passage, "source_detail": source_detail, "reader_gets": "Employees welcomed him back.",
                  "detail_words": {"en": ["welcome"]}}
    compare = {"candidate_ref": "candidate", "kind": "personnel_change", "participants": ["Jensen Huang"],
               "action": "reinstated", "occasion": "2026-11-23", "same_editions": ["old"], "same_dossier": None,
               "passages": [passage], "assignment": assignment}
    assert decisions_for([compare], [candidate], ["en"])["candidate"]["assignment"]["source_detail"] == source_detail
    assignment.update(source_detail="meme", reader_gets="There is an AI meme.", detail_words={"en": ["meme"]})
    assert decisions_for([compare], [candidate], ["en"])["candidate"]["assignment"] is None
