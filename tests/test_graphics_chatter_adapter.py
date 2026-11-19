"""Frozen Chatter evidence reaches the one real C1 request without another writer."""

import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from core.models import OriginalContentCall, Post
from monitor.editorial import chatter_history as history
from monitor.editorial.config import load_editorial_config
from monitor.editorial.graphics_contracts import load_pack
from monitor.editorial.graphics_entry import prepare_selected_story, run_selected_story
from monitor.editorial.graphics_packages import materialize_package
from monitor.editorial.voices import load_bound_voices
from monitor.original_content import digest
from tests.test_original_content_consideration import consideration

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def frozen_chatter():
    physical = consideration(consideration_state="selected")
    row = consideration(consideration_state="selected")
    first = Post.objects.create(tweet_id="98001", text="A later mutable edit.", created_at=physical.run.facts_as_of)
    second = Post.objects.create(tweet_id="98002", text="Another mutable edit.", created_at=physical.run.facts_as_of)
    sources = []
    for post, passage, author in [
        (first, "The reporter calls this a limited preview, quoting its maker.", "reporter"),
        (second, "Last year the maker described a different prototype.", "historian"),
    ]:
        source = history.project_post(post)
        source.update(original_text=passage, author_handle=author,
                      created_at=(physical.run.facts_as_of - timedelta(days=1)).isoformat())
        sources.append(source)
    sources[0].update(stored_quote="Maker: testing only; no general release yet.",
                      quoted_author_handle="maker", quoted_post_id="97001", is_quote=True,
                      local_parent="Earlier parent says access remains invitation-only.",
                      parent_author_handle="parent_author", parent_post_id="96001", is_reply=True)
    history.freeze_sources(physical.run, sources, fence=physical.run.fence)
    history.attach_sources(physical, [first.pk, second.pk], fence=physical.run.fence)
    history.reference_sources(row.run, physical, fence=row.run.fence)
    history.attach_sources(row, [first.pk], fence=row.run.fence)
    history.attach_sources(row, [second.pk], usage="background", fence=row.run.fence)
    cfg = load_editorial_config(ROOT / "config/editorial-chatter-staging.yaml")
    voices = {key: voice.model_dump(mode="json") for key, voice in load_bound_voices(cfg).items()}
    row.run.config_snapshot = {"schema_version": 1, "editorial": cfg.model_dump(mode="json"), "voices": voices}
    row.run.save(update_fields=["config_snapshot"])
    row.run.refresh_from_db()
    return row, physical, sources


def prepared(row, locale="en"):
    return prepare_selected_story(content_id=row.pk, run_id=row.run_id, locale=locale)


def copy_result(locale="en", used=("F01-Q",)):
    return {"schema_version": "copy-proposals/v3", "locale": locale,
            "article": "The maker says this is testing only.", "used_fact_ids": list(used),
            "evidence_gaps": [], "candidates": [
                {"id": label, "headline": title, "byline": "The maker describes a preview.",
                 "wordplay_meaning": "A preview pun.", "cultural_reference": None,
                 "used_fact_ids": list(used)}
                for label, title in [("A", "Testing Times"), ("B", "Preview View")]]}


def decode_handoff(body):
    task = body["messages"][1]["content"]
    return json.JSONDecoder().raw_decode(task.split("\n\nSUPPLIED INPUTS:\n", 1)[1])[0]


def test_frozen_quote_parent_background_and_ownership_survive_materialization(frozen_chatter):
    row, physical, _ = frozen_chatter
    request = prepared(row)
    run, _ = materialize_package(request)
    assert materialize_package(prepared(row))[0].pk == run.pk
    assert run.snapshot["request"] == request
    facts = {fact["fact_id"]: fact for fact in request["handoff"]["fact_items"]}
    assert set(facts) == {"F01", "F01-Q", "F01-P", "F02"}
    assert facts["F01-Q"]["supporting_passage"] == "Maker: testing only; no general release yet."
    assert facts["F01-Q"]["speaker"] == "maker"
    assert facts["F01-P"]["speaker"] == "parent_author"
    assert facts["F01-Q"]["source_role"] == "quoted"
    assert facts["F01-P"]["source_role"] == "parent"
    assert facts["F02"]["source_role"] == "background"
    assert facts["F01"]["created_at"] == request["sources"][0]["created_at"]
    assert facts["F01-Q"]["created_at"] is None
    assert facts["F01-Q"]["carrier_created_at"] == facts["F01"]["created_at"]
    assert facts["F01-Q"]["source_post_id"] == "98001"
    assert facts["F01-Q"]["attributed_post_id"] == "97001"
    assert facts["F01-Q"]["snapshot_hash"] == digest(request["sources"][0])
    assert facts["F01-Q"]["qualifiers"]["is_quote"] is True
    assert request["chatter"]["development_id"] == str(row.development_id)
    assert (request["chatter"]["source_locale"], request["chatter"]["editorial_group"]) == ("en", "rest")
    assert [source["snapshot_run_id"] for source in request["chatter"]["source_identities"]] == [physical.run_id] * 2
    assert prepared(row) == request  # live Post edits never enter this boundary


@pytest.mark.parametrize("locale", ["en", "ja", "zh-cn"])
def test_final_c1_wire_uses_saved_native_voice_locale_route_and_actual_citations(frozen_chatter, locale):
    from monitor.editorial.graphics_contracts import bind_copy_contract
    from monitor.editorial.graphics_pipeline import advance_step
    from monitor.editorial.graphics_publication import publish_primary

    row, _, _ = frozen_chatter
    request = prepared(row, locale)
    run, output = materialize_package(request)
    voice = row.run.config_snapshot["voices"][f"chatter:{locale}"]
    cfg = row.run.config_snapshot["editorial"]
    route = cfg["locale_routes"].get(f"chatter:{locale}") or cfg["routes"]["chatter"]
    captures = []

    def transport(endpoint, key, body, **kwargs):
        captures.append((endpoint, key, deepcopy(body), kwargs))
        return 200, json.dumps({"model": route["model"], "usage": {}, "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(copy_result(locale))}}]}).encode()

    result = advance_step(run.pk, keys={route["key_env"]: "fake-configured-key"}, transport=transport)
    assert result["state"] == "completed"
    assert len(captures) == 1
    endpoint, key, body, kwargs = captures[0]
    assert (endpoint, key, body["model"], kwargs["timeout"]) == (
        route["endpoint"], "fake-configured-key", route["model"], route["timeout_seconds"])
    assert body["max_completion_tokens"] == route["max_output_tokens"]
    assert body["reasoning_effort"] == route["reasoning"]
    assert voice["instructions"] in body["messages"][0]["content"]
    assert f"({locale})" in body["messages"][0]["content"]
    if locale != "en":
        assert "Write the complete publication copy in English (en)." not in body["messages"][0]["content"]
    handoff = decode_handoff(body)
    assert handoff == request["handoff"]
    assert [fact["speaker"] for fact in handoff["fact_items"]] == ["reporter", "maker", "parent_author", "historian"]
    schema = json.JSONDecoder().raw_decode(body["messages"][1]["content"].split("OUTPUT JSON SCHEMA FOR THIS REQUEST:\n", 1)[1])[0]
    assert schema["properties"]["locale"] == {"const": locale}
    assert body["messages"][1]["content"].count("OUTPUT JSON SCHEMA FOR THIS REQUEST:") == 1
    call = OriginalContentCall.objects.get(run=run, stage=f"gfx:{run.pk}:C1")
    assert call.provider == "openai" and call.model == route["model"]
    assert call.actual_usd is None  # direct-provider token counts are not billed receipts
    pack = bind_copy_contract(load_pack(ROOT / "config/editorial_prompts/editorial-creative-roles-v1.json"), request["handoff"])
    text = publish_primary(content=output, producer=call, pack=pack, sources=request["sources"])
    assert text.locale == locale
    assert list(text.sources.values_list("post_id", "source_hash")) == [("98001", digest(request["sources"][0]))]
    assert advance_step(run.pk, keys={})["stage"] == "G0"
    assert OriginalContentCall.objects.filter(run=run).count() == 1


@pytest.mark.parametrize("fault", ["hash", "owner", "future", "missing", "not_selected", "voice", "route"])
def test_invalid_chatter_evidence_or_binding_fails_before_dispatch(frozen_chatter, fault):
    row, physical, _ = frozen_chatter
    if fault == "hash":
        row.consideration_sources.filter(post_id="98001").update(source_hash="0" * 64)
    elif fault == "owner":
        row.consideration_sources.filter(post_id="98001").update(snapshot_run_id=None)
    elif fault in {"future", "missing"}:
        physical.run.refresh_from_db()
        if fault == "future":
            source = physical.run.snapshot["sources"]["98001"]
            source["created_at"] = (row.run.facts_as_of + timedelta(seconds=1)).isoformat()
            row.run.snapshot["source_refs"]["98001"]["sha256"] = digest(source)
            row.run.save(update_fields=["snapshot"])
            row.consideration_sources.filter(post_id="98001").update(source_hash=digest(source))
        else:
            del physical.run.snapshot["sources"]["98001"]
        physical.run.save(update_fields=["snapshot"])
    elif fault == "not_selected":
        row.consideration_state = "passed_over"
        row.save(update_fields=["consideration_state"])
    else:
        row.run.config_snapshot["voices" if fault == "voice" else "editorial"] = {}
        row.run.save(update_fields=["config_snapshot"])
    dispatched = []
    with pytest.raises(ValueError):
        run_selected_story(content_id=row.pk, run_id=row.run_id, locale="en", advance=lambda value: dispatched.append(value))
    assert not dispatched and not OriginalContentCall.objects.exists()


def test_materialization_rechecks_chatter_source_and_voice_instead_of_trusting_caller(frozen_chatter):
    row, _, _ = frozen_chatter
    request = prepared(row)
    request["handoff"]["fact_items"][1]["speaker"] = "invented"
    with pytest.raises(ValueError, match="differs"):
        materialize_package(request)
    request = prepared(row)
    row.consideration_sources.filter(post_id="98001").update(source_hash="0" * 64)
    with pytest.raises(ValueError, match="snapshot"):
        materialize_package(request)


def test_document_evidence_remains_a_typed_document_through_the_c1_wire(frozen_chatter, tmp_path):
    from core.event_dossiers import create_dossier, identity_key
    from core.models import CollectionObservation, EventDossierSource
    from monitor.editorial.graphics_generation import build_text_request
    from tests.test_product_release_documents import captured_document

    row, _, _ = frozen_chatter
    receipt, _, options = captured_document(tmp_path)
    event = create_dossier(event_kind="product_release", identity_key=identity_key("test", "graphics-doc"))
    document = EventDossierSource.objects.create(event_dossier=event,
        collection_observation=CollectionObservation.objects.get(pk=receipt["observation_id"]))
    source = {"kind": "dossier_source", "id": f"dossier-source:{document.pk}",
              "dossier_source_id": document.pk, "url": options["url"],
              "original_text": "The publisher says it is a preview, with access by invitation.",
              "created_at": None, "observed_at": row.run.facts_as_of.isoformat(),
              "author_handle": "document publisher"}
    history.freeze_sources(row.run, [source], fence=row.run.fence)
    history.attach_sources(row, [source["id"]], usage="background", fence=row.run.fence)
    request = prepared(row)
    run, _ = materialize_package(request)
    pack = load_pack(ROOT / "config/editorial_prompts/editorial-creative-roles-v1.json")
    wire = build_text_request(pack, "C1", run.snapshot["request"]["handoff"], writer_route=request["writer_route"])
    document_fact = decode_handoff(wire["body"])["fact_items"][-1]
    assert document_fact["dossier_source_id"] == document.pk
    assert "source_post_id" not in document_fact
    assert document_fact["source_role"] == "background" and document_fact["source_kind"] == "dossier_source"
    assert document_fact["created_at"] is None
    assert document_fact["snapshot_hash"] == digest(request["sources"][-1])
    assert request["chatter"]["source_identities"][-1]["post_id"] is None
    assert not Post.objects.filter(pk=source["id"]).exists()


def test_unknown_used_fact_ids_cannot_attach_other_chatter_support(frozen_chatter):
    from monitor.editorial.graphics_contracts import validate_copy_fact_ids
    from monitor.editorial.graphics_publication import _used_citations

    row, _, _ = frozen_chatter
    request = prepared(row)
    facts = request["handoff"]["fact_items"]
    assert [value["post_id"] for value in _used_citations(request["sources"], facts, ["F02"])] == ["98002"]
    with pytest.raises(ValueError, match="Unknown fact"):
        validate_copy_fact_ids(copy_result(used=("unknown",)), facts)
    with pytest.raises(ValueError, match="used facts"):
        _used_citations(request["sources"], facts, ["unknown"])


def test_missing_quote_attribution_is_explicit_and_never_assigned_to_the_reporter(frozen_chatter):
    row, physical, _ = frozen_chatter
    physical.run.refresh_from_db()
    source = physical.run.snapshot["sources"]["98001"]
    source["quoted_author_handle"] = ""
    physical.run.save(update_fields=["snapshot"])
    row.run.snapshot["source_refs"]["98001"]["sha256"] = digest(source)
    row.run.save(update_fields=["snapshot"])
    row.consideration_sources.filter(post_id="98001").update(source_hash=digest(source))
    quote = prepared(row)["handoff"]["fact_items"][1]
    assert quote["speaker"] == "" and quote["speaker_id"] is None
    assert quote["attribution_gaps"] == ["passage_date_unavailable", "speaker_unavailable"]


@pytest.mark.parametrize("conflict", ["passage", "speaker"])
def test_conflicting_frozen_quote_does_not_invent_a_resolved_identity(frozen_chatter, conflict):
    row, _, _ = frozen_chatter
    post = Post.objects.create(tweet_id="97001", text="Mutable quote source",
                               created_at=row.run.facts_as_of - timedelta(days=2))
    source = history.project_post(post)
    source.update(original_text=("A different passage." if conflict == "passage" else "Maker: testing only; no general release yet."),
                  author_handle="different_speaker" if conflict == "speaker" else "maker")
    history.freeze_sources(row.run, [source], fence=row.run.fence)
    history.attach_sources(row, [post.pk], usage="background", fence=row.run.fence)
    quoted = next(fact for fact in prepared(row)["handoff"]["fact_items"] if fact["source_role"] == "quoted")
    assert quoted["source_post_id"] == "98001"
    assert quoted["created_at"] is None and quoted["speaker"] == "maker"
    assert "linked_source_conflict" in quoted["attribution_gaps"]


def test_saved_writer_voice_and_route_do_not_reload_current_profiles(frozen_chatter, monkeypatch):
    row, _, _ = frozen_chatter
    expected = prepared(row, "ja")

    def current_profile_is_not_evidence(*args, **kwargs):
        pytest.fail("Selected Chatter input must use the saved profile.")

    monkeypatch.setattr("monitor.editorial.voices.load_voice", current_profile_is_not_evidence)
    monkeypatch.setattr("monitor.editorial.config.load_editorial_config", current_profile_is_not_evidence)
    assert prepared(row, "ja") == expected
