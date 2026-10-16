"""Corrected inputs retain paid history and use the real shared publishers."""

import copy
import json
from uuid import uuid4

import pytest

from core.models import OriginalContentCall, Post, PostBrandClassificationState
from core.provider_batches import BatchAdmissionError, digest, post_snapshot
from tests.test_backfill_cached_replay import _paid_history, _rejected_packet
from tests.test_backfill_direct_enrichment import DirectProvider
from tests.test_backfill_native_enrichment import native as native_fixture
from tests.test_backfill_verify import accepted as accepted_fixture

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
native = native_fixture
accepted = accepted_fixture


def _spec(native, ids):
    return {
        "version": "canonical-contract-recovery-v1", "job_id": str(native[0].pk),
        "post_id": "native-1", "phase": "base", "prior_call_ids": ids,
        "source_snapshot": post_snapshot(Post.objects.prefetch_related("brands").get(pk="native-1")),
        "feedback": "Correct the prior schema violation. Keep exact decision IDs and exclude tracked brands from untracked subjects.",
    }


def _advance(native, spec, provider):
    from monitor.backfill_recovery import advance_contract_recovery

    return advance_contract_recovery(
        native[0].pk, specs=[spec], cfg=native[1], api_key="test", delegates=native[2],
        client_factory=provider.factory, direct_concurrency=2,
    )


def test_corrected_input_publishes_after_three_old_failures_without_erasing_them(native):
    _, ids = _rejected_packet(native)
    spec = _spec(native, ids)
    before = _paid_history()
    sibling = Post.objects.filter(pk="native-2").values().get()
    sibling_state = PostBrandClassificationState.objects.filter(post_id="native-2").values().get()
    provider = DirectProvider()
    for _ in range(8):
        result = _advance(native, spec, provider)
        if result["pending_posts"] == 0:
            break
    assert result["pending_posts"] == 0 and provider.sent == 2
    assert _paid_history()[:len(before)] == before
    assert Post.objects.filter(pk="native-2").values().get() == sibling
    assert PostBrandClassificationState.objects.filter(post_id="native-2").values().get() == sibling_state
    calls = OriginalContentCall.objects.exclude(pk__in=[r["pk"] for r in before])
    for call in calls:
        assert call.import_state == "applied"
        context = call.provenance["context"]["recovery"]
        assert context["spec_sha256"] == digest(spec) and context["prior_call_ids"] == ids
        assert "canonical-contract-recovery-v1" in json.dumps(call.request_packet)
    assert _advance(native, spec, provider)["pending_posts"] == 0 and provider.sent == 2


def test_corrected_unknown_is_held_and_never_automatically_resent(native):
    from x_monitor.deepinfra import DeepInfraRetryableError

    _, ids = _rejected_packet(native)
    spec = _spec(native, ids)

    class Unknown(DirectProvider):
        def transport(self, body, timeout):
            self.sent += 1
            raise DeepInfraRetryableError("outcome_unknown")

    provider = Unknown()
    _advance(native, spec, provider)
    sent = provider.sent
    result = _advance(native, spec, provider)
    assert result["deferred"] == {"native-1": "corrected_request_outcome_unknown"}
    assert provider.sent == sent and sent == 2


def test_bad_corrected_replies_do_not_create_new_input_on_every_retry(native):
    _, ids = _rejected_packet(native)
    spec = _spec(native, ids)

    class Invalid(DirectProvider):
        def transport(self, body, timeout):
            reply = super().transport(body, timeout)
            if "CONTENT ROLE:" in body["messages"][0]["content"]:
                data = json.loads(reply["choices"][0]["message"]["content"])
                data["decisions"]["D01"]["outcome"] = "invalid_outcome"
                reply["choices"][0]["message"]["content"] = json.dumps(data)
            return reply

    provider = Invalid()
    for _ in range(10):
        result = _advance(native, spec, provider)
    calls = list(OriginalContentCall.objects.filter(provenance__context__recovery__spec_sha256=digest(spec)))
    assert len(calls) == 6 and len({c.request_hash for c in calls}) == 2
    assert result["deferred"] == {"native-1": "corrected_request_allowance_exhausted"}
    assert provider.sent == 6


def test_corrected_source_change_rejects_before_any_paid_start(native):
    _, ids = _rejected_packet(native)
    spec = _spec(native, ids)
    Post.objects.filter(pk="native-1").update(text="Changed source")
    before = _paid_history()
    provider = DirectProvider()
    with pytest.raises(BatchAdmissionError, match="source_changed"):
        _advance(native, spec, provider)
    assert _paid_history() == before and provider.sent == 0


def test_corrected_preparation_reserves_and_sends_nothing(native):
    from monitor.backfill_recovery import advance_contract_recovery

    _, ids = _rejected_packet(native)
    before = _paid_history()
    provider = DirectProvider()
    result = advance_contract_recovery(
        native[0].pk, specs=[_spec(native, ids)], cfg=native[1], api_key="test",
        delegates=native[2], client_factory=provider.factory, prepare_only=True,
    )
    assert len(result["requests"]) == 2 and provider.sent == 0 and _paid_history() == before


def test_targeted_recovery_keeps_canonical_identity_and_publishes_through_shared_writer(accepted, native):
    from core.models import Event, PostBrandSignal, TargetedExtractionState
    from monitor.backfill_recovery import advance_contract_recovery
    from scripts.backfill_targeted import advance_targeted, requirements
    from tests.test_backfill_targeted import ExtractionProvider

    ids, cfg = accepted
    cfg.targeted_extraction.enabled = True
    PostBrandSignal.objects.create(post_id=ids[0], brand_id="qwen", post_type_id="events", sentiment_id="neutral")
    provider = ExtractionProvider()
    for _ in range(4):
        advance_targeted(native[0].pk, cfg=cfg, api_key="test", delegate=native[2]["classification"], client_factory=provider.factory)
        if TargetedExtractionState.objects.filter(post_id=ids[0], status="succeeded").exists():
            break
    original = OriginalContentCall.objects.get(provenance__context__operation="post_targeted_extraction")
    previous = []
    for index in range(3):
        call = original if index == 0 else copy.deepcopy(original)
        if index:
            call.pk = None
            call.request_identity = uuid4().hex
            call.batch_key = uuid4().hex
        call.import_state = "error"
        call.import_evidence = {"validation": "canonical_targeted_validation_failed"}
        call.save()
        previous.append(call.pk)
    TargetedExtractionState.objects.filter(post_id=ids[0]).update(status="failed", result_hash="")
    before = _paid_history()
    post = Post.objects.prefetch_related("brands").get(pk=ids[0])
    expected = requirements(post, cfg)
    spec = _spec(native, previous) | {
        "phase": "targeted", "output_tokens": 8192,
        "feedback": "organization_name and title are required source-supported strings. Use full timezone ISO values for datetime precision.",
    }
    for _ in range(4):
        result = advance_contract_recovery(
            native[0].pk, specs=[spec], cfg=cfg, api_key="test", delegates=native[2],
            targeted_delegate=native[2]["classification"], client_factory=provider.factory,
        )
        if result["pending_posts"] == 0:
            break
    assert result["pending_posts"] == 0 and Event.objects.count() == 1
    state = TargetedExtractionState.objects.get(post=post)
    assert state.status == "succeeded" and state.content_identity == expected[state.role]
    assert _paid_history()[:len(before)] == before
    corrected = OriginalContentCall.objects.get(provenance__context__recovery__spec_sha256=digest(spec))
    assert corrected.import_state == "applied" and corrected.request_packet["max_tokens"] == 8192


def test_literal_recovery_reuses_healthy_locale_and_existing_classification(native):
    from core.models import PostEnrichmentState, PostTranslationArtifact
    from tests.test_backfill_direct_enrichment import run_direct

    provider = DirectProvider()
    for turn in range(8):
        if run_direct(native, provider, initial=turn == 0)["status"] == "completed":
            break
    original = OriginalContentCall.objects.get(
        stage="translation", member_post_ids=["native-1"],
        provenance__context__target_language="zh-Hans",
    )
    previous = []
    for index in range(3):
        call = original if index == 0 else copy.deepcopy(original)
        if index:
            call.pk = None
            call.request_identity = uuid4().hex
            call.batch_key = uuid4().hex
        call.response_payload = copy.deepcopy(call.response_payload)
        call.response_payload["choices"][0]["finish_reason"] = "length"
        call.response_hash = digest(call.response_payload)
        call.import_state = "error"
        call.import_evidence = {"validation": "failed"}
        call.save()
        previous.append(call.pk)
    PostTranslationArtifact.objects.filter(post_id="native-1").delete()
    PostEnrichmentState.objects.filter(pk="native-1").update(translation_status="pending")
    spec = _spec(native, previous)
    before = _paid_history()
    provider = DirectProvider()
    for _ in range(8):
        result = _advance(native, spec, provider)
        if result["pending_posts"] == 0:
            break
    assert result["pending_posts"] == 0 and provider.sent == 1
    assert _paid_history()[:len(before)] == before
    corrected = OriginalContentCall.objects.get(provenance__context__recovery__spec_sha256=digest(spec))
    assert corrected.stage == "translation" and corrected.provenance["context"]["target_language"] == "zh-Hans"


def test_old_failure_does_not_replace_later_valid_pending_translation(native):
    from core.models import PostEnrichmentState, PostTranslationArtifact
    from tests.test_backfill_direct_enrichment import run_direct

    provider = DirectProvider()
    for turn in range(8):
        if run_direct(native, provider, initial=turn == 0)["status"] == "completed":
            break
    good = OriginalContentCall.objects.get(
        stage="translation", member_post_ids=["native-1"],
        provenance__context__target_language="zh-Hans",
    )
    old = copy.deepcopy(good)
    old.pk = None
    old.request_identity = uuid4().hex
    old.batch_key = uuid4().hex
    old.response_payload = copy.deepcopy(old.response_payload)
    old.response_payload["choices"][0]["finish_reason"] = "length"
    old.response_hash = digest(old.response_payload)
    old.import_state = "error"
    old.save()
    good.import_state = "pending"
    good.save(update_fields=["import_state"])
    failed = OriginalContentCall.objects.get(
        stage="translation", member_post_ids=["native-1"],
        provenance__context__target_language="ja",
    )
    failed.response_payload = copy.deepcopy(failed.response_payload)
    failed.response_payload["choices"][0]["finish_reason"] = "length"
    failed.response_hash = digest(failed.response_payload)
    failed.import_state = "error"
    failed.save()
    PostTranslationArtifact.objects.filter(post_id="native-1").delete()
    PostEnrichmentState.objects.filter(pk="native-1").update(translation_status="pending")
    before = _paid_history()
    provider = DirectProvider()
    spec = _spec(native, [old.pk, failed.pk])
    for _ in range(8):
        result = _advance(native, spec, provider)
        if result["pending_posts"] == 0:
            break
    assert result["pending_posts"] == 0 and provider.sent == 1
    assert _paid_history()[:len(before)] == before
    corrected = OriginalContentCall.objects.get(provenance__context__recovery__spec_sha256=digest(spec))
    assert corrected.provenance["context"]["target_language"] == "ja"
