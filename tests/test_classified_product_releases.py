"""Exercise the real harvester/classifier/publisher with offline transports."""

import json
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from core import models, product_release_dossiers
from core.classified_product_releases import (
    read_publication_findings,
    selected_release_revision,
)
from monitor import cycle
from tests.test_compressed_classifier import answers, case, extraction
from tests.test_post_enrichment_queue import _cfg

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


class CombinedTransport:
    request_profile = "compressed8_pulse_v1"
    request_identity = "fixture-combined"
    release_channels = ("api", "weights")
    model = "deepseek-ai/DeepSeek-V4-Flash-0731"

    def __init__(self, *, empty=False):
        self.calls = []
        self.document = extraction()
        if empty:
            self.document["release_findings"]["findings"] = []

    def messages_create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model"].startswith("deepseek"):
            return deepcopy(self.document)
        response = answers(json.loads(kwargs["messages"][0]["content"]))
        for index, finding in enumerate(self.document["release_findings"]["findings"]):
            if finding.get("issuer_evidence") is not None:
                response["answers"][f"release:{index}:issuer_supported"]["noul"] = 0.9
        return response


def setup_cycle(monkeypatch, *, empty=False, sentinel=False, official=False):
    call_command("seed_i18n_labels", verbosity=0)
    sample = case()
    if official:
        sample["state"]["source_text"] = "We released Qwen4 weights today."
    post = models.Post.objects.create(
        tweet_id="combined-cycle", text=sample["state"]["source_text"],
        lang="en", lang_detected="en", author_handle="QwenOfficial",
    )
    brand = models.Brand.objects.create(
        nickname="_unattributed" if sentinel else "qwen",
        display_name="Unattributed" if sentinel else "Qwen", is_sentinel=sentinel,
    )
    cycle._persist_attribution(post, [brand.pk], [], allow_unattributed=sentinel)
    if not sentinel:
        models.PostBrand.objects.create(post=post, brand=brand)
    if official:
        account = models.Account.objects.create(author_id="123456789", handle="QwenOfficial")
        role, _ = models.Role.objects.get_or_create(key="official")
        models.BrandAccount.objects.create(brand=brand, account=account, role=role)
        post.author = account
        post.save(update_fields=["author"])
    state = models.PostEnrichmentState.objects.create(post=post, translation_status="succeeded")
    monkeypatch.setattr(cycle, "_requeue_recent_incomplete_translations", lambda **kwargs: 0)
    monkeypatch.setattr(cycle, "_classification_tracked_brand_catalog", lambda: sample["state"]["tracked_brands"])
    cfg = _cfg()
    cfg.llm.classifier_pipeline = "compressed8_pulse_v1"
    cfg.llm.classifier_model = CombinedTransport.model
    transport = CombinedTransport(empty=empty)
    if official:
        transport.document["entities"][0]["evidence"] = post.text
        finding = transport.document["release_findings"]["findings"][0]
        finding["assertions"][0]["source_excerpt"] = post.text
        finding["issuer_evidence"] = {
            "relation": "source_author", "source_locator": "post",
            "source_excerpt": post.text, "observed_name": None,
        }
    runner = cycle.CycleRunner(
        cfg=cfg, _post_fetch_clients={"translation": None, "classification": transport},
    )
    return state, runner, transport


def stub_saved_findings(monkeypatch):
    """Keep control-flow fixtures bound to the real publisher's complete output."""
    saved = []

    def write(**kwargs):
        saved[:] = [{"anchor_claim_id": 7 + index, "finding": finding}
                    for index, finding in enumerate(kwargs["findings"])]
        return ()

    monkeypatch.setattr(product_release_dossiers, "persist_classified_release_findings", write)
    monkeypatch.setattr(product_release_dossiers, "read_saved_release_findings", lambda **kwargs: tuple(saved))


@pytest.mark.parametrize("empty,sentinel", [(False, False), (True, False), (False, True)])
def test_cycle_publishes_findings_and_queues_atomically(monkeypatch, empty, sentinel):
    state, runner, transport = setup_cycle(monkeypatch, empty=empty, sentinel=sentinel)
    writes = []

    def write(**kwargs):
        assert connection.in_atomic_block
        assert selected_release_revision(state.pk)["revision_id"] == kwargs["revision_id"]
        writes.append(kwargs)
        return ()

    monkeypatch.setattr(product_release_dossiers, "persist_classified_release_findings", write, raising=False)
    runner._run_post_fetch([], run_id="combined-cycle")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    assert len(transport.calls) == runner._llm_call_count == 2
    assert len(writes) == 1
    assert len(writes[0]["findings"]) == (0 if empty else 1)
    assert writes[0]["source"] == {"kind": "post", "id": state.pk}
    assert models.ProductReleaseDetectionState.objects.get(post=state.post).completed_at is None
    selected = models.PostBrandClassificationState.objects.get(post_id=state.pk)
    assert selected.model.endswith("+jev-1.14.0")
    assert len(selected_release_revision(state.pk)["revision_id"]) == 64
    if not empty:
        assert models.PostBrandSignal.objects.filter(post_id=state.pk, post_type_id="releases_updates").exists()
    assert not models.Product.objects.exists()
    assert not models.CollectionRequest.objects.exists()


def test_failed_evidence_write_rolls_back_classification_and_outbox(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)

    def fail(**kwargs):
        raise ValueError("classification_fixture_evidence_failure")

    monkeypatch.setattr(product_release_dossiers, "persist_classified_release_findings", fail, raising=False)
    runner._run_post_fetch([], run_id="combined-cycle")
    state.refresh_from_db()
    assert len(transport.calls) == 2
    assert state.classification_status == "pending"
    assert not models.PostBrandClassificationState.objects.filter(post_id=state.pk).exists()
    assert not models.PostBrandClassificationJudgment.objects.filter(post_id=state.pk).exists()
    assert not models.ProductReleaseDetectionState.objects.filter(post_id=state.pk).exists()
    assert selected_release_revision(state.pk) is None


def test_failed_release_enqueue_rolls_back_real_saved_evidence(monkeypatch):
    from core import product_release_detection_queue

    state, runner, transport = setup_cycle(monkeypatch)

    def fail(post_id):
        assert connection.in_atomic_block
        assert models.EventDossierClaim.objects.filter(
            scope_key__startswith="pulse-finding-v1:",
        ).exists()
        raise ValueError("fixture_outbox_failure")

    monkeypatch.setattr(product_release_detection_queue, "enqueue_saved_post", fail)
    runner._run_post_fetch([], run_id="combined-outbox-rollback")
    state.refresh_from_db()
    assert len(transport.calls) == 2 and state.classification_status == "pending"
    assert not models.EventDossierClaim.objects.filter(scope_key__startswith="pulse-finding-v1:").exists()
    assert not models.CollectionEvidenceArchive.objects.exists()
    assert not models.PostBrandClassificationJudgment.objects.filter(post_id=state.pk).exists()
    assert not models.ProductReleaseDetectionState.objects.filter(post_id=state.pk).exists()


def test_missing_classification_is_pending_not_an_empty_release_answer(monkeypatch):
    state, _runner, _transport = setup_cycle(monkeypatch)
    assert selected_release_revision(state.pk) is None


def test_targeted_release_extraction_does_not_repeat_combined_classifier(monkeypatch):
    _state, runner, transport = setup_cycle(monkeypatch)
    writes = []
    monkeypatch.setattr(product_release_dossiers, "persist_classified_release_findings", lambda **kw: writes.append(kw), raising=False)
    runner.cfg.targeted_extraction.enabled = True
    calls = []
    runner._targeted_extraction_calls = {"model_release_extraction": lambda *a: calls.append(a)}
    runner._run_post_fetch([], run_id="combined-cycle")
    assert len(transport.calls) == 2
    assert len(writes) == 1
    assert calls == []


def test_identity_stop_preserves_evidence_and_resume_never_reclassifies(monkeypatch, tmp_path, settings):
    from core.product_release_detection_queue import enqueue_posts
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = True
    pulse_control.initialize(directory=tmp_path, state="stopped", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch)
    stub_saved_findings(monkeypatch)
    calls = []
    monkeypatch.setattr(product_release_dossiers, "resolve_saved_release_finding", lambda **kw: calls.append(kw) or {"status": "unresolved"}, raising=False)
    runner._run_post_fetch([], run_id="combined-cycle")
    assert process_saved_findings()["status"] == "stopped"
    assert calls == []
    assert len(transport.calls) == 2
    assert models.ProductReleaseDetectionState.objects.get(post_id=state.pk).completed_at is None
    pulse_control.request_state("running", expected_revision=1, actor="fixture", reason="resume")
    result = process_saved_findings()
    assert result["status"] == "running"
    assert result["processed"] == result["unresolved"] == 1
    assert result["queries"] > 0 and result["affected_rows"] > 0
    assert result["provider_calls"] == 0
    assert calls == [{"claim_id": 7}]
    enqueue_posts([state.pk])
    assert process_saved_findings()["processed"] == 1
    assert len(transport.calls) == 2


def test_missing_classifier_does_not_complete_or_consume_identity_retry(monkeypatch, tmp_path, settings):
    from core.product_release_detection_queue import enqueue_posts
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, _runner, _transport = setup_cycle(monkeypatch)
    monkeypatch.setattr(product_release_dossiers, "resolve_saved_release_finding", lambda **kw: pytest.fail("unexpected identity write"), raising=False)
    enqueue_posts([state.pk])
    result = process_saved_findings()
    assert result["waiting_for_classification"] == 1
    assert result["processed"] == result["failed"] == 0
    work = models.ProductReleaseDetectionState.objects.get(post_id=state.pk)
    assert work.attempts == 0 and work.completed_at is None


@pytest.mark.parametrize("request_limit,expected_calls", [(1, 0), (20, 2)])
def test_combined_pair_uses_existing_durable_budget_before_dispatch(monkeypatch, request_limit, expected_calls):
    from monitor.enrichment_budget import config_fingerprint

    state, runner, transport = setup_cycle(monkeypatch)
    monkeypatch.setattr(product_release_dossiers, "persist_classified_release_findings", lambda **kw: (), raising=False)
    now = timezone.now()
    window = models.EnrichmentBudgetWindow.objects.create(
        enrichment_window_kind="scheduled", starts_at=now, ends_at=now + timedelta(hours=1),
        request_limit=request_limit, usd_limit=Decimal(1),
        config_fingerprint=config_fingerprint(runner.cfg),
    )
    runner.cfg.harvest.enrichment.budget_window_id = str(window.pk)
    result = runner._run_post_fetch([], run_id="combined-budget")
    state.refresh_from_db()
    window.refresh_from_db()
    assert len(transport.calls) == result["provider_requests"] == expected_calls
    if expected_calls:
        from x_monitor.attribution import _MAX_RETRIES

        assert window.reserved_requests == 2 * _MAX_RETRIES
        assert window.reserved_usd > 0
        assert state.classification_status == "succeeded"
    else:
        assert window.reserved_requests == window.reserved_usd == 0
        assert state.classification_attempts == 0
        assert state.classification_status == "pending"
        assert result["enrichment_stop_reason"] == "enrichment_budget_exhausted"


def test_classification_backlog_cannot_starve_saved_release_identity(monkeypatch, tmp_path, settings):
    from core.product_release_detection_queue import enqueue_posts
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    old = models.Post.objects.create(tweet_id="older-unclassified", text="Pending translation")
    models.PostEnrichmentState.objects.create(post=old)
    enqueue_posts([old.pk])
    state, runner, _transport = setup_cycle(monkeypatch)
    stub_saved_findings(monkeypatch)
    monkeypatch.setattr(product_release_dossiers, "resolve_saved_release_finding", lambda **kw: {"status": "unresolved"}, raising=False)
    runner._run_post_fetch([], run_id="combined-priority")
    result = process_saved_findings(limit=1)
    assert result["processed"] == 1 and result["waiting_for_classification"] == 0
    assert models.ProductReleaseDetectionState.objects.get(post_id=state.pk).completed_at is not None
    assert models.ProductReleaseDetectionState.objects.get(post_id=old.pk).completed_at is None


def test_real_dossier_writer_and_identity_reader_from_scheduled_publication(monkeypatch, tmp_path, settings):
    from pathlib import Path

    from core.collection_capture import read_document
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch)
    runner._run_post_fetch([], run_id="combined-real-dossier")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    findings = read_publication_findings(state.pk)
    assert len(findings) == 1
    assert findings[0]["finding"]["observed_name"] == "Qwen4"
    assert findings[0]["finding"]["category"] == "model-llm"
    assert models.EventDossier.objects.count() == 1
    assert models.EventDossierSource.objects.get().post_id == state.pk
    claim = models.EventDossierClaim.objects.get(claim_kind_reference__code="availability")
    assert claim.release_access_channel_reference.code == "weights"
    assert claim.source_excerpt == "Qwen4 weights are available today."
    artifact = Path(settings.BASE_DIR) / ".local/p1-classified-example.json"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(json.dumps({
        "evidence_kind": "synthetic provider responses through real classifier/publication/archive writer",
        "packet": read_document(claim.source_archive),
    }, indent=2))
    counts = (models.EventDossier.objects.count(), models.EventDossierClaim.objects.count())
    outcome = process_saved_findings()
    assert outcome["processed"] == outcome["unresolved"] == 1
    assert len(transport.calls) == 2
    assert not models.Product.objects.exists()  # A release mention alone does not identify its issuer.
    assert (models.EventDossier.objects.count(), models.EventDossierClaim.objects.count()) == counts


def test_official_source_author_creates_product_through_real_cycle_and_saved_evidence(monkeypatch, tmp_path, settings):
    from core.product_release_detection_queue import enqueue_posts
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch, official=True)
    company = models.Company.objects.create(nickname="alibaba")
    models.BrandCompany.objects.create(brand_id="qwen", company=company)
    runner._run_post_fetch([], run_id="combined-official-source")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    saved = read_publication_findings(state.pk)
    assert saved[0]["finding"]["issuer_evidence"] == {
        "relation": "source_author", "source_locator": None,
        "source_excerpt": "We released Qwen4 weights today.", "observed_name": None,
    }
    outcome = process_saved_findings()
    assert outcome["processed"] == 1
    assert outcome["unresolved"] == outcome["failed"] == 0
    product = models.Product.objects.get()
    assert product.display_name == "Qwen4"
    assert product.product_type.code == "model-llm"
    assert product.brand_id == "qwen"
    assert models.PostBrandProduct.objects.get(post_id=state.pk).product_id == product.pk
    from core.measurement_taxonomy import resolve_subject_id
    from core.pulse_readers import release_page

    subject = models.MeasurementSubject.objects.get(pk=resolve_subject_id("product", str(product.product_key)))
    assert subject.product_id == product.product_key
    row = release_page()["entries"][0]
    assert row["product_key"] == str(product.product_key)
    assert row["brand"]["id"] == "qwen"
    assert [owner["id"] for owner in row["companies"]] == ["alibaba"]
    assert row["category"] == "model-llm"
    assert not row["provider_mapping_present"]
    enqueue_posts([state.pk])
    assert process_saved_findings()["processed"] == 1
    assert models.Product.objects.count() == 1
    assert read_publication_findings(state.pk) == saved
    assert len(transport.calls) == 2


def captured_publication(monkeypatch, *, count=1):
    """Capture the real selected producer result for same-generation replay."""
    state, runner, transport = setup_cycle(monkeypatch, empty=count == 0)
    if count == 2:
        extra = deepcopy(transport.document["release_findings"]["findings"][0])
        extra["observed_name"] = None
        transport.document["release_findings"]["findings"].append(extra)
    captured = []
    publisher = cycle._publish_stage1_classification

    def publish(**kwargs):
        captured.append(deepcopy({key: value for key, value in kwargs.items() if key != "cfg"}))
        return publisher(**kwargs)

    monkeypatch.setattr(cycle, "_publish_stage1_classification", publish)
    runner._run_post_fetch([], run_id="combined-manifest")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    assert len(captured) == 1
    # Reacquire the existing generation's claim, without calling a provider again.
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(
        claim_run_id="combined-manifest", claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    return state, captured[0]


@pytest.mark.parametrize("initial_count,change", [(0, "extra"), (1, "empty"), (2, "subset"), (1, "extra")])
def test_same_revision_cannot_change_complete_release_output(monkeypatch, initial_count, change):
    from core.product_release_findings import FindingLimits, parse_release_findings

    state, publication = captured_publication(monkeypatch, count=initial_count)
    before = read_publication_findings(state.pk)
    findings = list(publication["result"]["release_findings"])
    if change == "empty":
        findings = []
    elif change == "subset":
        findings = findings[:1]
    else:
        document = extraction()["release_findings"]
        if initial_count:
            document["findings"][0]["observed_name"] = None
        findings.extend(parse_release_findings(document, source={"kind": "post", "id": state.pk},
            passages={"post": state.post.text}, allowed_channels=("weights",), limits=FindingLimits(8, 8, 4096)))
    publication["result"]["release_findings"] = findings
    with pytest.raises(ValueError, match="classification_trace_revision_conflict"):
        cycle._publish_stage1_classification(**publication)
    assert read_publication_findings(state.pk) == before
    assert models.PostBrandClassificationJudgment.objects.filter(post_id=state.pk).count() == 3


@pytest.mark.parametrize("count", [0, 1, 2])
def test_complete_output_manifest_replay_is_idempotent_and_ignores_trace_metadata(monkeypatch, count):
    state, publication = captured_publication(monkeypatch, count=count)
    before = read_publication_findings(state.pk)
    counts = (models.EventDossier.objects.count(), models.EventDossierClaim.objects.count(),
              models.CollectionEvidenceArchive.objects.count())
    # Untrusted trace envelopes cannot replace the manifest derived by the publisher.
    publication["result"]["classification_trace"]["final"]["changes_json"] = {"release_output": {"forged": True}}
    publication["result"]["release_findings"] = list(reversed(publication["result"]["release_findings"]))
    cycle._publish_stage1_classification(**publication)
    assert read_publication_findings(state.pk) == before
    assert (models.EventDossier.objects.count(), models.EventDossierClaim.objects.count(),
            models.CollectionEvidenceArchive.objects.count()) == counts
    assert models.PostBrandClassificationJudgment.objects.filter(post_id=state.pk).count() == 3


def test_empty_output_is_final_but_missing_manifest_is_pending(monkeypatch):
    state, _publication = captured_publication(monkeypatch, count=0)
    assert read_publication_findings(state.pk) == ()
    assert not models.EventDossier.objects.exists()
    final = models.PostBrandClassificationJudgment.objects.get(post_id=state.pk, stage="final")
    assert final.changes_json["release_output"]["finding_keys"] == []
    final.changes_json.pop("release_output")
    final.save(update_fields=["changes_json"])
    assert selected_release_revision(state.pk) is None
    assert read_publication_findings(state.pk) is None


@pytest.mark.parametrize("tamper", ["missing", "extra", "digest"])
def test_reader_rejects_actual_saved_output_tampering(monkeypatch, tamper):
    from django.db import IntegrityError

    from core.product_release_findings import finding_identity

    state, _publication = captured_publication(monkeypatch)
    saved = read_publication_findings(state.pk)
    anchor = models.EventDossierClaim.objects.get(pk=saved[0]["anchor_claim_id"])
    if tamper == "missing":
        with pytest.raises(IntegrityError, match="immutable"):
            anchor.delete()
        assert read_publication_findings(state.pk) == saved
        # The DB guard prevents deletion; independently prove the reader's
        # complete-output check rejects an incomplete storage response.
        monkeypatch.setattr(product_release_dossiers, "read_saved_release_findings", lambda **kwargs: ())
    elif tamper == "extra":
        extra = deepcopy(saved[0]["finding"])
        extra["observed_name"] = None
        extra["finding_key"] = finding_identity({"kind": "post", "id": state.pk},
            observed_name=None, version=extra["version"], variant=extra["variant"], assertions=extra["assertions"])
        product_release_dossiers.persist_classified_release_findings(
            source={"kind": "post", "id": state.pk}, **selected_release_revision(state.pk),
            findings=[extra], extraction_version="test-tampered-extra",
        )
    else:
        with pytest.raises(IntegrityError, match="immutable"):
            models.EventDossierClaim.objects.filter(pk=anchor.pk).update(source_archive=None)
        assert read_publication_findings(state.pk) == saved
        altered = deepcopy(saved)
        altered[0]["finding"]["category"] = "other"
        monkeypatch.setattr(product_release_dossiers, "read_saved_release_findings", lambda **kwargs: altered)
    with pytest.raises(ValueError, match="classification_release_output_mismatch"):
        read_publication_findings(state.pk)


@pytest.mark.parametrize("manifest", [
    None, {}, {"schema": "unknown", "finding_keys": [], "sha256": "a" * 64},
    {"schema": "pulse-classified-release-output-v1", "finding_keys": [], "sha256": "a" * 64, "extra": True},
    {"schema": "pulse-classified-release-output-v1", "finding_keys": ["b" * 64, "a" * 64], "sha256": "a" * 64},
    {"schema": "pulse-classified-release-output-v1", "finding_keys": ["a" * 64] * 2, "sha256": "a" * 64},
    {"schema": "pulse-classified-release-output-v1", "finding_keys": [str(n) * 64 for n in range(9)], "sha256": "a" * 64},
    {"schema": "pulse-classified-release-output-v1", "finding_keys": [], "sha256": "bad"},
])
def test_selected_trace_writer_requires_strict_manifest_even_for_direct_callers(monkeypatch, manifest):
    state, publication = captured_publication(monkeypatch)
    selected = models.PostBrandClassificationState.objects.get(post_id=state.pk)
    trace = publication["result"]["classification_trace"]
    trace["final"]["changes_json"] = selected.selected_final_judgment.changes_json
    with pytest.raises(ValueError, match="classification_release_manifest_invalid"):
        cycle._persist_classification_trace(
            post_id=state.pk, brand_ids={"qwen"}, trace=trace,
            final_by_brand=cycle._parse_published_classifications(publication["result"]["by_brand"], {"qwen"}),
            model=publication["model"], run_id="new-untrusted-run",
            fingerprint=selected.input_context_fingerprint, release_manifest=manifest,
        )
    assert models.PostBrandClassificationJudgment.objects.filter(post_id=state.pk).count() == 3


@pytest.mark.parametrize("saved_url", [None, "https://x.com/QwenOfficial/status/quoted-source"])
def test_publication_maps_only_saved_source_urls_and_preserves_finding_key(saved_url):
    from core.classified_product_releases import _source_bound_findings
    from core.product_release_findings import FindingLimits, parse_release_findings

    quoted = models.Post.objects.create(tweet_id="quoted-source", text=case()["state"]["source_text"],
                                        tweet_url=saved_url)
    post = models.Post.objects.create(tweet_id="quoting-post", text="Interesting release", quoted_status_id=quoted)
    document = extraction()["release_findings"]
    document["findings"][0]["assertions"][0]["source_locator"] = "context_0"
    findings = parse_release_findings(document, source={"kind": "post", "id": post.pk},
        passages={"context_0": quoted.text}, allowed_channels=("weights",),
        limits=FindingLimits(8, 8, 4096))
    saved = _source_bound_findings(post, {"text": post.text,
        "context": [{"text": quoted.text, "provenance": "stored_quote"}]}, findings)
    assert saved[0]["assertions"][0]["source_locator"] == saved_url
    assert saved[0]["finding_key"] == findings[0]["finding_key"]


@pytest.mark.parametrize("forged_issuer", [False, True])
def test_publication_rechecks_passage_evidence_before_writing(forged_issuer):
    from core.classified_product_releases import _source_bound_findings
    from core.product_release_findings import FindingLimits, parse_release_findings

    text = case()["state"]["source_text"]
    post = models.Post.objects.create(tweet_id="source-recheck", text=text)
    findings = parse_release_findings(extraction()["release_findings"],
        source={"kind": "post", "id": post.pk}, passages={"post": text},
        allowed_channels=("weights",), limits=FindingLimits(8, 8, 4096))
    if forged_issuer:
        findings[0]["issuer_evidence"] = {"relation": "source_author", "source_locator": "post",
            "source_excerpt": "We release Qwen4", "observed_name": None}
        supplied = text
    else:
        supplied = "Different source content"
    with pytest.raises(ValueError, match="evidence_not_supplied"):
        _source_bound_findings(post, {"text": supplied}, findings)


@pytest.mark.parametrize("saved_url", [None, "https://x.com/QwenOfficial/status/lineage"])
def test_lineage_survives_real_publication_as_source_evidence_without_product_relationships(monkeypatch, saved_url):
    state, runner, transport = setup_cycle(monkeypatch)
    excerpt = "Qwen4 is the successor to Qwen3."
    state.post.text += " " + excerpt
    state.post.tweet_url = saved_url
    state.post.save(update_fields=["text", "tweet_url"])
    relation = {"relationship_kind": "new_version", "parent_observed_name": "Qwen3",
                "source_locator": "post", "source_excerpt": excerpt}
    transport.document["release_findings"]["findings"][0]["lineage_evidence"] = [relation]
    respond = transport.messages_create

    def supported(**kwargs):
        response = respond(**kwargs)
        if not kwargs["model"].startswith("deepseek"):
            response["answers"]["release:0:lineage:0:supported"]["noul"] = 0.9
        return response

    monkeypatch.setattr(transport, "messages_create", supported)
    runner._run_post_fetch([], run_id="combined-lineage")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    saved = read_publication_findings(state.pk)
    assert saved[0]["finding"]["lineage_evidence"] == [{**relation, "source_locator": saved_url}]
    claim = models.EventDossierClaim.objects.get(scope_key__startswith="pulse-lineage-v1:")
    assert claim.source_excerpt == excerpt
    assert claim.source_locator == saved_url
    assert claim.claim_kind_reference.code == "release_context"
    assert not models.ProductRelationship.objects.exists()
    assert len(transport.calls) == 2


@pytest.mark.parametrize("mutation", ["excerpt", "locator"])
def test_publication_rechecks_lineage_source_binding(mutation):
    from core.classified_product_releases import _source_bound_findings
    from core.product_release_findings import FindingLimits, parse_release_findings

    text = case()["state"]["source_text"] + " Qwen4 replaces Qwen3."
    post = models.Post.objects.create(tweet_id="lineage-recheck", text=text)
    document = extraction()["release_findings"]
    document["findings"][0]["lineage_evidence"] = [{
        "relationship_kind": "new_version", "parent_observed_name": "Qwen3",
        "source_locator": "post", "source_excerpt": "Qwen4 replaces Qwen3.",
    }]
    findings = parse_release_findings(document, source={"kind": "post", "id": post.pk},
        passages={"post": text}, allowed_channels=("weights",), limits=FindingLimits(8, 8, 4096))
    findings[0]["lineage_evidence"][0]["source_" + mutation] = "invented"
    with pytest.raises(ValueError, match="classification_lineage_evidence_not_supplied"):
        _source_bound_findings(post, {"text": text}, findings)


@pytest.mark.parametrize("novelty,channel", [("historical_release", "weights"), ("availability_update", "api")])
def test_qualified_recap_or_availability_post_joins_original_release_without_reclassification(
    monkeypatch, tmp_path, settings, novelty, channel,
):
    from core.product_release_detection_queue import enqueue_posts
    from core.pulse_readers import release_page, release_sources
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    original, runner, transport = setup_cycle(monkeypatch, official=True)
    runner._run_post_fetch([], run_id="original-launch")
    assert process_saved_findings()["processed"] == 1
    product = models.Product.objects.get()
    original_packet = read_publication_findings(original.pk)
    later_text = ("Recap: Qwen4 weights were released on 2026-11-16." if novelty == "historical_release"
                  else "Qwen4 API access became available on 2026-11-17.")
    effective_day = "2026-11-16" if novelty == "historical_release" else "2026-11-17"
    post = models.Post.objects.create(tweet_id="later-qualified-source", text=later_text,
                                     lang="en", lang_detected="en", author_handle="independent-commentator")
    cycle._persist_attribution(post, ["qwen"], [])
    models.PostBrand.objects.create(post=post, brand_id="qwen")
    # Existing independently qualified identity evidence is the input here;
    # neither the classifier's brand topic nor a matching name creates it.
    models.PostBrandProduct.objects.create(
        post=post, brand_id="qwen", product=product, observed_name="Qwen4",
        source_evidence={"original_release_claim": str(original_packet[0]["anchor_claim_id"])},
        verification_policy_version="fixture-qualified-source-v1",
    )
    models.PostEnrichmentState.objects.create(post=post, translation_status="succeeded")
    transport.document = extraction()
    transport.document["entities"][0]["evidence"] = later_text
    finding = transport.document["release_findings"]["findings"][0]
    finding["novelty"] = novelty
    finding["assertions"][0]["source_excerpt"] = later_text
    finding["assertions"][0]["assertion_text"] = later_text
    finding["assertions"][0]["access_channel"] = channel
    finding["assertions"][0]["effective"] = {"precision": "day", "value": effective_day, "timezone": None}
    respond = transport.messages_create

    def milestone(**kwargs):
        answer = respond(**kwargs)
        if not kwargs["model"].startswith("deepseek"):
            question = answer["answers"]["release:0:novelty"]
            question["choice"] = novelty
            question["probabilities"] = {key: float(key == novelty) for key in question["probabilities"]}
        return answer

    monkeypatch.setattr(transport, "messages_create", milestone)
    runner._run_post_fetch([], run_id="later-release-source")
    before = read_publication_findings(post.pk)
    assert models.EventDossier.objects.filter(merged_into__isnull=True).count() == 2
    outcome = process_saved_findings(limit=1)
    assert outcome["failed"] == 0 and outcome["merged"] == 1
    assert models.Product.objects.count() == 1
    page = release_page()["entries"]
    assert len(page) == 1 and page[0]["product_key"] == str(product.product_key)
    assert page[0]["sources_count"] == 2
    sources = release_sources(page[0]["id"])["entries"]
    assert {source["post_id"] for source in sources} == {original.pk, post.pk}
    after = read_publication_findings(post.pk)
    assert after[0]["finding"] == before[0]["finding"]
    assert after[0]["finding"]["assertions"][0]["access_channel"] == channel
    assert after[0]["finding"]["assertions"][0]["effective_date"] == effective_day
    assert read_publication_findings(original.pk)[0]["finding"] == original_packet[0]["finding"]
    counts = (models.EventDossier.objects.count(), models.EventDossierSource.objects.count(),
              models.EventDossierClaim.objects.count(), models.CollectionEvidenceArchive.objects.count())
    enqueue_posts([original.pk, post.pk])
    assert process_saved_findings()["failed"] == 0
    assert counts == (models.EventDossier.objects.count(), models.EventDossierSource.objects.count(),
                      models.EventDossierClaim.objects.count(), models.CollectionEvidenceArchive.objects.count())
    assert len(transport.calls) == 4
    from pathlib import Path

    receipt_path = Path(settings.BASE_DIR) / ".local/p1-association-growth.json"
    receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    receipt[novelty] = {
        "posts": 2, "products": models.Product.objects.count(), "canonical_events": 1,
        "stored_dossiers": counts[0], "stored_source_links": counts[1],
        "stored_claims": counts[2], "stored_archives": counts[3],
        "canonical_source_links": page[0]["sources_count"], "unchanged_replay_growth": 0,
        "physical_provider_calls": 0, "synthetic_transport_requests": 4,
        "storage_note": "Existing merge preserves retired dossier/source/claim history and copies claims to the canonical event.",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2))


@pytest.mark.parametrize("limited", [False, True])
def test_association_progress_is_pending_without_retry_charge_or_model_calls(monkeypatch, tmp_path, settings, limited):
    from core import product_identity
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch, official=True)
    runner._run_post_fetch([], run_id="association-progress")
    models.ProductReleaseDetectionState.objects.filter(post_id=state.pk).update(attempts=2)
    calls = []

    def reconcile(**kwargs):
        assert not connection.in_atomic_block
        assert kwargs["max_merges"] == 1
        assert kwargs["candidate_limit"] == 50
        assert kwargs["claim_limit"] == 50
        assert 0 < kwargs["max_seconds"] <= 5
        calls.append(kwargs)
        return {"status": "candidate_limit" if limited and len(calls) == 1 else "ready",
                "merged_ids": [], "more_remaining": len(calls) == 1}

    monkeypatch.setattr(product_identity, "reconcile_product_release_events", reconcile, raising=False)
    first = process_saved_findings()
    pending = models.ProductReleaseDetectionState.objects.get(post_id=state.pk)
    assert first["association_pending"] == 1 and first["due_remaining"]
    assert first["association_limited"] == int(limited)
    if limited:
        assert pulse_control.read_status()["diagnostics"][-1]["code"] == "association_candidate_limit"
    assert pending.completed_at is None and pending.attempts == 2 and pending.error_code == ""
    second = process_saved_findings()
    pending.refresh_from_db()
    assert second["processed"] == 1 and not second["due_remaining"]
    assert pending.completed_at == pending.requested_at and pending.attempts == 0
    assert len(transport.calls) == 2


@pytest.mark.parametrize("interruption", ["failure", "new_generation"])
def test_association_recovery_preserves_committed_identity_and_fences_queue_completion(
    monkeypatch, tmp_path, settings, interruption,
):
    from core import product_identity
    from core.product_release_detection_queue import enqueue_posts
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    state, runner, transport = setup_cycle(monkeypatch, official=True)
    runner._run_post_fetch([], run_id="association-recovery")
    calls = []

    def reconcile(**kwargs):
        assert not connection.in_atomic_block
        calls.append(kwargs)
        if len(calls) == 1:
            if interruption == "failure":
                raise ValueError("injected merge failure")
            enqueue_posts([state.pk])
        return {"merged_ids": [], "more_remaining": False}

    monkeypatch.setattr(product_identity, "reconcile_product_release_events", reconcile, raising=False)
    first = process_saved_findings()
    pending = models.ProductReleaseDetectionState.objects.get(post_id=state.pk)
    assert pending.completed_at is None
    assert pending.attempts == int(interruption == "failure")
    assert first["failed"] == int(interruption == "failure")
    product_key = models.Product.objects.get().product_key
    if interruption == "failure":
        assert pending.retry_at is not None
        models.ProductReleaseDetectionState.objects.filter(pk=pending.pk).update(retry_at=None)
    second = process_saved_findings()
    pending.refresh_from_db()
    assert second["processed"] == 1 and not second["due_remaining"]
    assert pending.completed_at == pending.requested_at and pending.attempts == 0
    assert models.Product.objects.get().product_key == product_key
    assert len(transport.calls) == 2


def test_nonprogressing_association_cannot_starve_later_ready_post(monkeypatch, tmp_path, settings):
    from core import product_identity
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    original, runner, transport = setup_cycle(monkeypatch, official=True)
    runner._run_post_fetch([], run_id="first-association-request")
    later = models.Post.objects.create(tweet_id="later-no-new-product", text="Qwen usage discussion.",
                                       lang="en", lang_detected="en")
    cycle._persist_attribution(later, ["qwen"], [])
    models.PostBrand.objects.create(post=later, brand_id="qwen")
    models.PostEnrichmentState.objects.create(post=later, translation_status="succeeded")
    transport.document = {"entities": [], "release_findings": {"schema": "pulse-release-findings-v1", "findings": []}}
    runner._run_post_fetch([], run_id="later-association-request")
    monkeypatch.setattr(product_identity, "reconcile_product_release_events", lambda **kwargs: {
        "status": "busy", "merged_ids": [], "more_remaining": True,
    }, raising=False)
    first = process_saved_findings(limit=1)
    old_work = models.ProductReleaseDetectionState.objects.get(post_id=original.pk)
    later_work = models.ProductReleaseDetectionState.objects.get(post_id=later.pk)
    assert first["association_pending"] == 1 and old_work.completed_at is None
    assert old_work.requested_at > later_work.requested_at
    second = process_saved_findings(limit=1)
    later_work.refresh_from_db()
    old_work.refresh_from_db()
    assert second["processed"] == 1 and second["association_pending"] == 0
    assert later_work.completed_at == later_work.requested_at
    assert old_work.completed_at is None and old_work.attempts == 0
    assert len(transport.calls) == 4


def test_cycle_supplies_saved_profile_to_jev_without_an_extra_call(monkeypatch):
    from x_monitor.attribution import _two_role_fingerprint

    state, runner, transport = setup_cycle(monkeypatch, official=True)
    account = state.post.author
    other = models.Brand.objects.create(nickname="otherpublisher")
    models.BrandAccount.objects.create(brand=other, account=account, role_id="official")
    account.bio = "We build Qwen models."
    account.save(update_fields=["bio"])
    state.post.author_profile_bio = {
        "description": "We build Qwen models.",
        "entities": {"url": {"urls": [{"expanded_url": "https://qwen.example"}]}},
    }
    state.post.save(update_fields=["author_profile_bio"])
    runner._run_post_fetch([], run_id="pulse-profile-fallback")
    assert len(transport.calls) == 2
    request = json.loads(transport.calls[1]["messages"][0]["content"])
    assert "otherpublisher" in [a["brand_id"] for a in request["state"]["author_affiliations"]]
    profile = request["state"]["author_profile_evidence"]
    assert "qwen.example" in profile["domains"]
    assert any(source["text"] == "We build Qwen models." for source in profile["sources"])
    assert not any(source["id"] == f"post:{state.post_id}" for source in profile["sources"])
    tweet = {"tweet_id": "fixture", "text": "Post", "_classification_pipeline": "compressed8_pulse_v1"}
    before = _two_role_fingerprint(tweet)
    tweet["author_profile_evidence"] = profile
    assert _two_role_fingerprint(tweet) != before


def test_classifier_supported_third_party_creates_product_without_official_author(monkeypatch, tmp_path, settings):
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state='running', actor='fixture', reason='test')
    state, runner, transport = setup_cycle(monkeypatch)
    statement = 'Qwen released Qwen4 weights today, says reporter.'
    state.post.text = statement
    state.post.save(update_fields=['text'])
    transport.document['entities'][0]['evidence'] = statement
    finding = transport.document['release_findings']['findings'][0]
    finding['assertions'][0]['source_excerpt'] = statement
    finding['issuer_evidence'] = {'relation': 'attributed_party', 'source_locator': 'post',
                                  'source_excerpt': statement, 'observed_name': 'Qwen'}
    call = transport.messages_create

    def affirmative_publisher(**kwargs):
        result = call(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['release:0:publisher:qwen']['noul'] = 0.9
        return result

    transport.messages_create = affirmative_publisher
    runner._run_post_fetch([], run_id='third-party-publisher')
    state.refresh_from_db()
    assert state.classification_status == 'succeeded'
    assert read_publication_findings(state.pk)[0]['finding']['brand_id'] == 'qwen'
    outcome = process_saved_findings()
    assert outcome['processed'] == 1 and outcome['unresolved'] == outcome['failed'] == 0
    product = models.Product.objects.get()
    assert (product.display_name, product.brand_id) == ('Qwen4', 'qwen')
    assert models.PostBrandProduct.objects.get(post_id=state.pk).source_evidence['issuer_claim'] == 'attributed_party'
    assert not models.BrandAccount.objects.exists()


def test_classifier_supported_third_party_creates_new_publisher_without_company(monkeypatch, tmp_path, settings):
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state='running', actor='fixture', reason='test')
    state, runner, transport = setup_cycle(monkeypatch, sentinel=True)
    statement = 'Acme Labs released Qwen4 weights today, says reporter.'
    state.post.text = statement
    state.post.save(update_fields=['text'])
    transport.document['entities'][0]['evidence'] = statement
    finding = transport.document['release_findings']['findings'][0]
    finding['assertions'][0]['source_excerpt'] = statement
    finding['issuer_evidence'] = {'relation': 'attributed_party', 'source_locator': 'post',
                                  'source_excerpt': statement, 'observed_name': 'Acme Labs'}
    runner._run_post_fetch([], run_id='third-party-new-publisher')
    state.refresh_from_db()
    assert state.classification_status == 'succeeded'
    assert read_publication_findings(state.pk)[0]['finding']['issuer_evidence']['observed_name'] == 'Acme Labs'
    outcome = process_saved_findings()
    assert outcome['processed'] == 1 and outcome['unresolved'] == outcome['failed'] == 0
    product = models.Product.objects.get()
    assert product.brand.display_name == 'Acme Labs'
    assert not models.Company.objects.exists()
    assert not models.BrandAccount.objects.exists()
    assert len(transport.calls) == 2


def test_source_author_profile_can_identify_new_publisher_without_worker(monkeypatch, tmp_path, settings):
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state='running', actor='fixture', reason='test')
    state, runner, transport = setup_cycle(monkeypatch, sentinel=True)
    author = models.Account.objects.create(author_id='88123480', handle='acmelabs',
                                           display_name='Acme Labs', bio='We build AI models at Acme Labs.')
    statement = 'We released Qwen4 weights today.'
    state.post.author = author
    state.post.text = statement
    state.post.save(update_fields=['author', 'text'])
    transport.document['entities'][0]['evidence'] = statement
    finding = transport.document['release_findings']['findings'][0]
    finding['assertions'][0]['source_excerpt'] = statement
    finding['issuer_evidence'] = {'relation': 'source_author', 'source_locator': 'post',
                                  'source_excerpt': statement, 'observed_name': None}
    call = transport.messages_create

    def affirmative_profile(**kwargs):
        result = call(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['release:0:profile_publisher_supported']['noul'] = 0.9
        return result

    transport.messages_create = affirmative_profile
    runner._run_post_fetch([], run_id='source-author-new-publisher')
    state.refresh_from_db()
    assert state.classification_status == 'succeeded'
    saved = read_publication_findings(state.pk)[0]['finding']
    assert saved['issuer_evidence']['observed_name'] == 'Acme Labs'
    assert saved['publisher_profile']['display_name'] == 'Acme Labs'
    assert any('Acme Labs' in source['text'] for source in saved['publisher_profile']['sources'])
    outcome = process_saved_findings()
    assert outcome['processed'] == 1 and outcome['unresolved'] == outcome['failed'] == 0
    assert models.Product.objects.get().brand.display_name == 'Acme Labs'
    assert not models.Company.objects.exists()
    assert not models.BrandAccount.objects.exists()
    assert len(transport.calls) == 2


def test_unconfirmed_author_profile_does_not_create_publisher(monkeypatch, tmp_path, settings):
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state='running', actor='fixture', reason='test')
    state, runner, transport = setup_cycle(monkeypatch, sentinel=True)
    author = models.Account.objects.create(author_id='88123481', handle='reporter',
                                           display_name='Acme Reporter', bio='Reporting about AI.')
    statement = 'We released Qwen4 weights today.'
    state.post.author = author
    state.post.text = statement
    state.post.save(update_fields=['author', 'text'])
    transport.document['entities'][0]['evidence'] = statement
    finding = transport.document['release_findings']['findings'][0]
    finding['assertions'][0]['source_excerpt'] = statement
    finding['issuer_evidence'] = {'relation': 'source_author', 'source_locator': 'post',
                                  'source_excerpt': statement, 'observed_name': None}
    runner._run_post_fetch([], run_id='source-author-unclear-publisher')
    saved = read_publication_findings(state.pk)[0]['finding']
    assert saved['issuer_evidence']['observed_name'] is None
    assert 'publisher_profile' not in saved
    outcome = process_saved_findings()
    assert outcome['unresolved'] == 1
    assert not models.Product.objects.exists()
    assert not models.Brand.objects.exclude(is_sentinel=True).exists()


def test_classifier_family_name_reaches_product_and_pulse(monkeypatch, tmp_path, settings):
    from core.pulse_readers import release_page
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state='running', actor='fixture', reason='test')
    state, runner, transport = setup_cycle(monkeypatch)
    statement = 'Qwen released Qwen4 in the Qwen Nova family.'
    state.post.text = statement
    state.post.save(update_fields=['text'])
    transport.document['entities'][0]['evidence'] = statement
    finding = transport.document['release_findings']['findings'][0]
    finding['assertions'][0]['source_excerpt'] = statement
    finding['issuer_evidence'] = {'relation': 'attributed_party', 'source_locator': 'post',
                                  'source_excerpt': statement, 'observed_name': 'Qwen'}
    finding['family_evidence'] = {'name': 'Qwen Nova', 'source_locator': 'post', 'source_excerpt': statement}
    call = transport.messages_create

    def supported_family(**kwargs):
        result = call(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['release:0:publisher:qwen']['noul'] = 0.9
            result['answers']['release:0:family_supported']['noul'] = 0.9
        return result

    transport.messages_create = supported_family
    runner._run_post_fetch([], run_id='explicit-family')
    saved = read_publication_findings(state.pk)[0]['finding']
    assert saved['family_evidence']['name'] == 'Qwen Nova'
    outcome = process_saved_findings()
    assert outcome['processed'] == 1 and outcome['unresolved'] == outcome['failed'] == 0
    assert release_page()['entries'][0]['family']['name'] == 'Qwen Nova'
    assert len(transport.calls) == 2


def test_legacy_combined_publication_remains_readable_after_classifier_revision(monkeypatch):
    from core import classification_contract
    from monitor import classification_persistence
    from x_monitor import attribution, compressed_classifier

    old = classification_contract.COMPRESSED_CLASSIFIER_LEGACY_REVISIONS
    with monkeypatch.context() as legacy:
        legacy.setattr(classification_contract, 'COMPRESSED_CLASSIFIER_REVISIONS', old)
        legacy.setattr(classification_persistence, 'COMPRESSED_CLASSIFIER_REVISIONS', old)
        legacy.setattr(attribution, 'COMPRESSED_CLASSIFIER_REVISIONS', old)
        legacy.setattr(compressed_classifier, 'REVISIONS', old)
        legacy.setattr(cycle, '_TWO_ROLE_ALLOWED_REVISION_TRIPLETS',
                       cycle._TWO_ROLE_ALLOWED_REVISION_TRIPLETS | {old})
        state, runner, transport = setup_cycle(legacy)
        runner._run_post_fetch([], run_id='legacy-release-generation')
        state.refresh_from_db()
        assert state.classification_status == 'succeeded'
        assert len(transport.calls) == 2
    assert selected_release_revision(state.pk) is not None
    findings = read_publication_findings(state.pk)
    assert len(findings) == 1 and findings[0]['finding']['observed_name'] == 'Qwen4'
    assert models.ProductReleaseDetectionState.objects.filter(post_id=state.pk).exists()


def test_release_survives_unrelated_classifier_answer_failure(monkeypatch, tmp_path, settings):
    from monitor import pulse_control
    from monitor.pulse_processing import process_saved_findings

    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state='running', actor='fixture', reason='test')
    state, runner, transport = setup_cycle(monkeypatch)
    call = transport.messages_create

    def broken_unrelated_answer(**kwargs):
        result = call(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers'].pop('relevant')
        return result

    transport.messages_create = broken_unrelated_answer
    runner._run_post_fetch([], run_id='partial-release')
    state.refresh_from_db()
    assert state.classification_status == 'pending'
    assert not models.PostBrandClassificationState.objects.filter(post_id=state.pk).exists()
    partial = models.PostBrandClassificationJudgment.objects.get(post_id=state.pk, validation_state='release_only')
    assert partial.canonical_judgment == {}
    saved = read_publication_findings(state.pk)
    assert len(saved) == 1 and saved[0]['finding']['observed_name'] == 'Qwen4'
    outcome = process_saved_findings()
    assert outcome['processed'] == 1 and outcome['failed'] == 0
    assert len(transport.calls) == 2


def test_invalid_release_answer_is_not_published_as_release_only(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    call = transport.messages_create

    def broken_release_answer(**kwargs):
        result = call(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers'].pop('release:0:category')
        return result

    transport.messages_create = broken_release_answer
    runner._run_post_fetch([], run_id='invalid-release-answer')
    state.refresh_from_db()
    assert state.classification_status == 'pending'
    assert not models.PostBrandClassificationJudgment.objects.filter(post_id=state.pk, validation_state='release_only').exists()
    assert read_publication_findings(state.pk) is None
    assert not models.EventDossier.objects.exists()


def test_later_complete_classification_supersedes_release_only(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    call = transport.messages_create

    def broken_unrelated_answer(**kwargs):
        result = call(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers'].pop('relevant')
        return result

    transport.messages_create = broken_unrelated_answer
    runner._run_post_fetch([], run_id='partial-first')
    partial = selected_release_revision(state.pk)
    assert partial is not None
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    transport.messages_create = call
    runner._run_post_fetch([], run_id='complete-next')
    state.refresh_from_db()
    assert state.classification_status == 'succeeded'
    complete = selected_release_revision(state.pk)
    assert complete is not None and complete != partial
    assert len(read_publication_findings(state.pk)) == 1
    assert models.EventDossier.objects.count() == 1
    assert len(transport.calls) == 4


def test_release_only_replay_is_idempotent_and_cannot_change_same_generation(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    call = transport.messages_create

    def broken_unrelated_answer(**kwargs):
        result = call(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers'].pop('relevant')
        return result

    transport.messages_create = broken_unrelated_answer
    captured = []
    publish = cycle._publish_stage1_classification

    def capture(**kwargs):
        captured.append({key: deepcopy(value) if key != 'cfg' else value for key, value in kwargs.items()})
        return publish(**kwargs)

    monkeypatch.setattr(cycle, '_publish_stage1_classification', capture)
    runner._run_post_fetch([], run_id='partial-replay')
    before = read_publication_findings(state.pk)
    assert len(before) == 1 and len(captured) == 1
    claim_count = models.EventDossierClaim.objects.count()
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(
        claim_run_id='partial-replay', claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    cycle._publish_stage1_classification(**captured[0])
    assert read_publication_findings(state.pk) == before
    assert models.EventDossierClaim.objects.count() == claim_count
    changed = deepcopy(captured[0])
    changed['result']['release_findings'] = list(changed['result']['release_findings'])
    changed['result']['release_findings'][0]['novelty'] = 'historical_release'
    with pytest.raises(ValueError, match='classification_release_only_generation_conflict'):
        cycle._publish_stage1_classification(**changed)
    assert read_publication_findings(state.pk) == before


def test_classifier_publication_queues_single_exact_hf_link_without_provider_calls(monkeypatch, settings):
    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    models.DataSource.objects.get_or_create(pk='hf', defaults={'name':'Hugging Face', 'source_type':'model_adoption'})
    state, runner, transport = setup_cycle(monkeypatch)
    state.post.text += ' https://huggingface.co/Qwen/Qwen4'
    state.post.save(update_fields=['text'])
    runner._run_post_fetch([], run_id='classifier-hf-handoff')
    saved = read_publication_findings(state.post_id)
    assert len(saved) == 1 and saved[0]['finding']['candidate_repo_id'] is None
    job = models.CollectionJob.objects.get(targets__target_role='exact_model')
    assert job.targets.get().native_identifier == 'Qwen/Qwen4'
    assert job.dossier_claim_links.count() == 2
    lead = job.dossier_claim_links.get(claim__scope_key__startswith='pulse-hf-source-link-v1:').claim
    from core.collection_capture import read_document
    models.Post.objects.filter(pk=state.post_id).update(text='changed after capture', entities={})
    assert 'https://huggingface.co/Qwen/Qwen4' in read_document(lead.source_archive)['matched_urls']
    assert not models.CollectionRequest.objects.exists()
    assert len(transport.calls) == 2  # Both responses are local fixtures.


def test_pulse_backfill_reuses_a_saved_empty_decision(monkeypatch):
    from monitor.management.commands.backfill_pulse_candidates import saved_result

    state, runner, transport = setup_cycle(monkeypatch, empty=True)
    assert saved_result(state.post_id) == ("missing", ())
    runner._process_enrichment_claim_batch([], run_id="pulse-history-test",
        post_ids={state.post_id}, pulse_backfill=True)
    assert saved_result(state.post_id) == ("selected", ())
    assert len(transport.calls) == 2


def test_invalid_release_finding_publishes_feed_and_keeps_release_unresolved(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    transport.document["release_findings"] = {"schema": "invalid", "findings": []}
    runner._run_post_fetch([], run_id="partial-feed")
    state.refresh_from_db()
    assert state.classification_status == "pending"
    assert len(transport.calls) == 2
    assert models.PostBrandClassificationState.objects.filter(post_id=state.pk).exists()
    assert selected_release_revision(state.pk) is None
    assert read_publication_findings(state.pk) is None
    assert not models.EventDossier.objects.exists()
    from monitor.views import _enrich_posts_with_classifications

    rows = _enrich_posts_with_classifications(models.Post.objects.filter(pk=state.pk))
    assert rows[0]["classifications_by_brand"]["qwen"]["classification_status"] == "classified"
    assert rows[0]["classifications_by_brand"]["qwen"]["post_types"]
    assert rows[0]["enrichment_stages"]["classification"][0] == "succeeded"
    final = models.PostBrandClassificationState.objects.get(post_id=state.pk).selected_final_judgment
    final.changes_json.pop('feed_axes_complete')
    final.save(update_fields=['changes_json'])
    rows = _enrich_posts_with_classifications(models.Post.objects.filter(pk=state.pk))
    assert rows[0]["enrichment_stages"]["classification"][0] == "succeeded"


def test_fast_classification_is_saved_before_slow_sibling_finishes(monkeypatch):
    import threading
    import time
    from django.db import close_old_connections
    from x_monitor import compressed_classifier

    state, runner, _ = setup_cycle(monkeypatch)
    other = models.Post.objects.create(
        tweet_id="slow-sibling", text=state.post.text, lang="en", lang_detected="en",
    )
    models.PostBrand.objects.create(post=other, brand_id="qwen")
    models.PostEnrichmentState.objects.create(post=other, translation_status="succeeded")
    release = threading.Event()
    slow_started = threading.Event()
    original = compressed_classifier._run_prepared_case

    def delayed(sample, request, call, *, release_channels):
        if sample["case_id"] == "slow-sibling":
            slow_started.set()
            assert release.wait(10)
        return original(sample, request, call, release_channels=release_channels)

    monkeypatch.setattr(compressed_classifier, "_run_prepared_case", delayed)
    errors = []

    def run():
        close_old_connections()
        try:
            runner._run_post_fetch([], run_id="streaming-test")
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert slow_started.wait(10)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if models.PostBrandClassificationState.objects.filter(post_id=state.pk).exists():
                break
            time.sleep(.05)
        assert models.PostBrandClassificationState.objects.filter(post_id=state.pk).exists()
        assert not models.PostBrandClassificationState.objects.filter(post_id=other.pk).exists()
    finally:
        release.set()
        thread.join(timeout=15)
    assert not thread.is_alive()
    assert not errors
    assert models.PostBrandClassificationState.objects.filter(post_id=other.pk).exists()


@pytest.mark.parametrize("ambiguous", [False, True])
def test_source_named_existing_hf_product_resolves_only_when_unique(monkeypatch, ambiguous):
    from core.product_identity import resolve_saved_release_finding

    state, runner, _ = setup_cycle(monkeypatch)
    product = models.Product.objects.create(
        display_name="Qwen4", brand_id="qwen", repo_id="Qwen/Qwen4", hf_type="model",
    )
    if ambiguous:
        other = models.Brand.objects.create(nickname="other")
        models.Product.objects.create(
            display_name="Qwen4", brand=other, repo_id="other/Qwen4", hf_type="model",
        )
    runner._run_post_fetch([], run_id="hf-exact-identity")
    rows = read_publication_findings(state.pk)
    assert rows and len(rows) == 1
    outcome = resolve_saved_release_finding(claim_id=rows[0]["anchor_claim_id"])
    if ambiguous:
        assert outcome["status"] == "unresolved"
    else:
        assert outcome["status"] == "matched"
        assert outcome["product_id"] == product.pk
        from core.pulse_readers import release_page

        entry = next(row for row in release_page()["entries"] if row["id"] == outcome["dossier_id"])
        assert entry["product_key"] == str(product.product_key)
        assert entry["brand"]["id"] == "qwen"


def test_unresolved_release_retry_preserves_previous_selected_release(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    runner._run_post_fetch([], run_id="first-complete")
    previous = selected_release_revision(state.pk)
    before = read_publication_findings(state.pk)
    assert previous and before
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(
        classification_status="pending", classification_next_attempt_at=None,
    )
    transport.document["release_findings"] = {"schema": "invalid", "findings": []}
    runner._run_post_fetch([], run_id="incomplete-retry")
    assert selected_release_revision(state.pk) == previous
    assert read_publication_findings(state.pk) == before


def test_feed_only_retry_preserves_prior_release_only(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create

    def missing_feed_answer(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers'].pop('relevant')
        return result

    transport.messages_create = missing_feed_answer
    runner._run_post_fetch([], run_id='release-only-first')
    previous = selected_release_revision(state.pk)
    assert previous and read_publication_findings(state.pk)
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    transport.messages_create = original
    transport.document['release_findings'] = {'schema': 'invalid', 'findings': []}
    runner._run_post_fetch([], run_id='feed-only-next')
    assert models.PostBrandClassificationState.objects.filter(post_id=state.pk).exists()
    assert selected_release_revision(state.pk) == previous
    assert read_publication_findings(state.pk)


def test_missing_release_answer_still_publishes_feed(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create

    def missing_release_answer(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers'].pop('release:0:category')
        return result

    transport.messages_create = missing_release_answer
    runner._run_post_fetch([], run_id='missing-release-answer')
    state.refresh_from_db()
    assert state.classification_status == 'pending'
    assert models.PostBrandClassificationState.objects.filter(post_id=state.pk).exists()
    assert selected_release_revision(state.pk) is None


def test_hf_name_match_does_not_override_named_publisher(monkeypatch):
    from core.product_identity import resolve_saved_release_finding

    state, runner, transport = setup_cycle(monkeypatch)
    product = models.Product.objects.create(display_name='Qwen4', brand_id='qwen', repo_id='Qwen/Qwen4', hf_type='model')
    statement = 'OtherCorp released Qwen4 weights today.'
    state.post.text = statement
    state.post.save(update_fields=['text'])
    transport.document['entities'][0]['evidence'] = statement
    finding = transport.document['release_findings']['findings'][0]
    finding['assertions'][0]['source_excerpt'] = statement
    finding['issuer_evidence'] = {'relation': 'attributed_party', 'source_locator': 'post',
                                  'source_excerpt': statement, 'observed_name': 'OtherCorp'}
    runner._run_post_fetch([], run_id='different-publisher')
    row = read_publication_findings(state.pk)[0]
    assert row['finding']['issuer_evidence']['observed_name'] == 'OtherCorp'
    outcome = resolve_saved_release_finding(claim_id=row['anchor_claim_id'])
    assert outcome.get('product_id') != product.pk


def test_hf_name_match_does_not_override_nonmodel_category(monkeypatch):
    from core.product_identity import resolve_saved_release_finding

    state, runner, transport = setup_cycle(monkeypatch)
    models.Product.objects.create(display_name='Qwen4', brand_id='qwen', repo_id='Qwen/Qwen4', hf_type='model')
    original = transport.messages_create

    def app_category(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['release:0:category'] = answers(
                json.loads(kwargs['messages'][0]['content']),
                choices={'release:0:category': 'other'},
            )['answers']['release:0:category']
        return result

    transport.messages_create = app_category
    runner._run_post_fetch([], run_id='nonmodel-category')
    row = read_publication_findings(state.pk)[0]
    assert row['finding']['category'] == 'other'
    assert resolve_saved_release_finding(claim_id=row['anchor_claim_id'])['status'] == 'unresolved'


def test_hf_name_match_preserves_conflicting_prior_identity(monkeypatch):
    from core.event_dossiers import add_claim
    from core.product_identity import resolve_saved_release_finding

    state, runner, _ = setup_cycle(monkeypatch)
    models.Product.objects.create(display_name='Qwen4', brand_id='qwen', repo_id='Qwen/Qwen4', hf_type='model')
    previous = models.Product.objects.create(display_name='Earlier model', brand_id='qwen')
    runner._run_post_fetch([], run_id='prior-identity-conflict')
    row = read_publication_findings(state.pk)[0]
    anchor = models.EventDossierClaim.objects.get(pk=row['anchor_claim_id'])
    add_claim(
        anchor.event_dossier_source_id, claim_kind='release_context',
        scope_key='pulse-self-identity-v1:' + row['finding']['finding_key'],
        assertion_text='Previously selected product', source_excerpt=anchor.source_excerpt,
        source_locator=anchor.source_locator, extraction_version='pulse-product-identity-v1',
        source_archive_id=anchor.source_archive_id, reported_brand_id='qwen', reported_product_id=previous.pk,
    )
    outcome = resolve_saved_release_finding(claim_id=anchor.pk)
    assert outcome['status'] == 'unresolved'
    assert models.EventDossierClaim.objects.filter(
        event_dossier_source=anchor.event_dossier_source,
        scope_key='pulse-self-identity-v1:' + row['finding']['finding_key'],
    ).count() == 1


def test_unresolved_promotion_saves_sentiment_without_changing_existing_promotion(monkeypatch, client):
    state, runner, transport = setup_cycle(monkeypatch)
    prior = models.PostUntrackedBrandPromotion.objects.create(
        post=state.post, promotion_keys=['general'], evidence={'source': 'previous'},
        contract_version='previous', taxonomy_version='previous', prompt_version='previous',
        model='previous', provider_role='previous',
    )
    original = transport.messages_create

    def uncertain_promotion(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.9
        return result

    transport.messages_create = uncertain_promotion
    runner._run_post_fetch([], run_id='uncertain-promotion')
    state.refresh_from_db()
    assert state.classification_status == 'pending'
    selected = models.PostBrandClassificationState.objects.get(post_id=state.pk, brand_id='qwen')
    assert selected.sentiment_id == 'neutral'
    assert models.PostBrandSignal.objects.filter(post_id=state.pk, post_type_id='releases_updates').exists()
    prior.refresh_from_db()
    assert prior.promotion_keys == ['general'] and prior.evidence == {'source': 'previous'}
    assert read_publication_findings(state.pk)
    from monitor.views import _enrich_posts_with_classifications

    row = _enrich_posts_with_classifications(models.Post.objects.filter(pk=state.pk))[0]
    assert row['classifications_by_brand']['qwen']['sentiments'] == ['neutral']
    assert row['enrichment_stages']['classification'][0] == 'succeeded'
    response = client.post('/api/v2/post-synthesis-demands/', data=json.dumps({
        'post_ids': [state.pk], 'poll_only': True, 'locale': 'en',
    }), content_type='application/json', secure=True)
    assert response.status_code == 200
    assert not any('analysis pending' in badge['message'].lower()
                   for badge in response.json()['results'][0]['processing_badges'])
    other = models.Brand.objects.create(nickname='unclassified-brand')
    models.PostBrand.objects.create(post=state.post, brand=other)
    row = _enrich_posts_with_classifications(models.Post.objects.filter(pk=state.pk))[0]
    assert row['enrichment_stages']['classification'][0] == 'pending'


def test_unresolved_combined_release_is_owned_by_pulse_during_targeted_replay(monkeypatch):
    from core.targeted_extraction import run_targeted_extractions
    state, runner, transport = setup_cycle(monkeypatch)
    transport.document["release_findings"]["schema"] = "invalid"
    runner.cfg.targeted_extraction.enabled = True
    calls = []
    runner._targeted_extraction_calls = {"model_release_extraction": lambda *args: calls.append(args)}
    runner._run_post_fetch([], run_id="partial-release-with-targeted")
    state.refresh_from_db()
    assert state.classification_status == "pending"
    assert selected_release_revision(state.pk) is None
    run_targeted_extractions(post=state.post, post_types={"releases_updates"},
        config=runner.cfg.targeted_extraction, calls=runner._targeted_extraction_calls, max_calls=1)
    assert len(transport.calls) == 2
    assert calls == []


def test_continuous_worker_completes_targeted_and_requested_translation_after_pair(monkeypatch, settings):
    from monitor.enrichment_worker import process_enrichment_batch
    from tests.test_literal_translation_plaintext import PlaintextClient, TextResponse
    from x_monitor import reattribute
    from x_monitor.provider_telemetry import ProviderResponse

    settings.X_MONITOR_LLM_PAUSE_SECONDS = 0
    state, runner, transport = setup_cycle(monkeypatch, empty=True)
    state.post.text += " Join the live Qwen workshop."
    state.post.save(update_fields=["text"])
    state.translation_status = "pending"
    state.translation_requested = True
    state.save(update_fields=("translation_requested", "translation_status"))
    runner.cfg.harvest.enrichment.max_calls_per_batch = 6
    runner.cfg.harvest.enrichment.classifier_reserved_calls = 2
    runner.cfg.targeted_extraction.enabled = True
    runner.cfg.llm.literal_translation_v2_enabled = True
    runner.cfg.llm.translator_model = "google/gemma-4-31B-it-turbo"
    translator = PlaintextClient([TextResponse("今天可以使用通义千问四代权重。"), TextResponse("今日からモデルの重みを利用できます。")])
    runner._post_fetch_clients["translation"] = translator
    dispatch = transport.messages_create

    def classify(**kwargs):
        response = dispatch(**kwargs)
        if "answers" in response:
            response["answers"]["type:events"]["noul"] = 0.9
        return response

    monkeypatch.setattr(transport, "messages_create", classify)
    class TargetedProvider:
        def messages_create(self, **kwargs):
            return ProviderResponse({"records": [{
                "brand_id": "qwen", "organization_name": "Qwen", "title": "Live Qwen workshop",
                "attendance_mode": "online_live", "start_value": None, "start_precision": "unknown",
                "end_value": None, "end_precision": "unknown", "source_status": "scheduled",
            }]})

    monkeypatch.setattr(reattribute, "build_relevancy_client_from_env", lambda *a, **kw: TargetedProvider())
    result = process_enrichment_batch(runner, [], scope="continuous", run_id="release-unused", fair_queue=True)
    state.refresh_from_db()
    assert state.translation_status == state.classification_status == "succeeded"
    assert result["n_targeted_extraction_calls"] == 1
    assert models.TargetedExtractionState.objects.get(post=state.post).status == "succeeded"
    assert models.EventEvidence.objects.get(source_post=state.post).event.title == "Live Qwen workshop"
    assert len(transport.calls) == len(translator.calls) == 2
    assert result["reserved_dispatches"] == result["provider_requests"] == 5


def test_cycle_publishes_sibling_when_release_brand_identity_is_disputed(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    deepseek = models.Brand.objects.create(nickname="deepseek", display_name="DeepSeek")
    models.PostBrand.objects.create(post=state.post, brand=deepseek)
    catalog = [
        {"brand_id": "qwen", "aliases": ["Qwen"], "products": [], "accounts": []},
        {"brand_id": "deepseek", "aliases": ["DeepSeek"], "products": [], "accounts": []},
    ]
    monkeypatch.setattr(cycle, "_classification_tracked_brand_catalog", lambda: catalog)
    original = transport.messages_create

    def disputed(**kwargs):
        response = original(**kwargs)
        if kwargs["model"].startswith("deepseek"):
            return response
        request = json.loads(kwargs["messages"][0]["content"])
        brands = request["state"]["target_brands"]
        qwen = brands.index("qwen")
        sibling = brands.index("deepseek")
        for key in (
            f"b{qwen}:identity_namesake_only",
            f"b{sibling}:relevant",
            f"b{sibling}:type:hands_on_usage",
            f"b{sibling}:negative",
            f"b{sibling}:product:bug",
            "release:0:concerns:qwen",
        ):
            response["answers"][key]["noul"] = 0.9
        return response

    transport.messages_create = disputed
    runner._run_post_fetch([], run_id="disputed-brand")
    state.refresh_from_db()
    assert state.classification_status == "succeeded"
    selected = models.PostBrandClassificationState.objects.get(post=state.post, brand=deepseek)
    assert selected.sentiment_id == "negative"
    assert models.PostBrandSignal.objects.filter(
        post=state.post, brand=deepseek, post_type_id="hands_on_usage", sentiment_id="negative",
    ).exists()
    assert models.PostBrandProductLabel.objects.filter(post=state.post, brand=deepseek, product_label_id="bug").exists()
    assert models.PostBrandClassificationState.objects.get(post=state.post, brand_id="qwen").outcome == "context_missing"
    assert read_publication_findings(state.pk)[0]["finding"]["brand_id"] is None
    assert not models.PostBrandClassificationJudgment.objects.filter(post=state.post, validation_state="release_only").exists()


def test_promotion_retry_preserves_completed_feed_when_later_vote_loses_context(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.9
            if retry:
                result['answers']['identity_namesake_only']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='promotion-first')
    first = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    assert first.outcome == 'classified'
    selected_id = first.selected_final_judgment_id
    before = list(models.PostBrandSignal.objects.filter(post=state.post).values_list('post_type_id', 'sentiment_id'))
    release = read_publication_findings(state.pk)
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='promotion-retry')
    first.refresh_from_db()
    assert first.outcome == 'classified'
    assert first.selected_final_judgment_id == selected_id
    assert list(models.PostBrandSignal.objects.filter(post=state.post).values_list('post_type_id', 'sentiment_id')) == before
    assert read_publication_findings(state.pk) == release


def test_completed_promotion_retry_keeps_prior_feed_and_records_reason(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.1 if retry else 0.9
            if retry:
                result['answers']['identity_namesake_only']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='promotion-unresolved')
    first = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    selected_id = first.selected_final_judgment_id
    original_signals = list(models.PostBrandSignal.objects.filter(post=state.post).values_list('post_type_id', 'sentiment_id'))
    original_release = read_publication_findings(state.pk)
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='promotion-resolved')
    first.refresh_from_db()
    state.refresh_from_db()
    assert state.classification_status == 'succeeded'
    assert first.selected_final_judgment_id == selected_id
    assert list(models.PostBrandSignal.objects.filter(post=state.post).values_list('post_type_id', 'sentiment_id')) == original_signals
    assert read_publication_findings(state.pk) == original_release
    assert models.PostBrandClassificationJudgment.objects.filter(
        post=state.post, stage='final', changes_json__promotion_retry_reason='fill_unresolved_promotion',
    ).exists()


def test_promotion_retry_reassesses_when_source_text_materially_changes(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.9
            if retry:
                result['answers']['identity_namesake_only']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='material-first')
    first = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    assert first.outcome == 'classified'
    selected_id = first.selected_final_judgment_id
    state.post.text += ' The quoted context has changed.'
    state.post.save(update_fields=['text'])
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='material-retry')
    first.refresh_from_db()
    assert first.selected_final_judgment_id != selected_id
    assert first.outcome == 'context_missing'
    assert first.selected_final_judgment.changes_json['feed_replacement_reason'] == 'feed_material_source_changed'


def test_ambiguous_legacy_promotion_retry_keeps_feed_and_fills_release(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create
    document = deepcopy(transport.document)
    transport.document['release_findings'] = {'schema': 'invalid', 'findings': []}
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.1 if retry else 0.9
            if retry:
                result['answers']['identity_namesake_only']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='ambiguous-first')
    first = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    selected_id = first.selected_final_judgment_id
    assert first.outcome == 'classified'
    assert read_publication_findings(state.pk) is None
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    transport.document = document
    retry = True
    runner._run_post_fetch([], run_id='ambiguous-retry')
    first.refresh_from_db()
    state.refresh_from_db()
    assert state.classification_status == 'succeeded'
    assert first.selected_final_judgment_id == selected_id
    assert first.outcome == 'classified'
    assert read_publication_findings(state.pk)[0]['finding']['observed_name'] == 'Qwen4'
    assert models.PostBrandClassificationJudgment.objects.filter(
        post=state.post, stage='final', changes_json__promotion_retry_reason='fill_unresolved_promotion',
    ).exists()


def test_promotion_retry_keeps_completed_brand_while_other_brand_improves(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    deepseek = models.Brand.objects.create(nickname='deepseek', display_name='DeepSeek')
    models.PostBrand.objects.create(post=state.post, brand=deepseek)
    catalog = [
        {'brand_id': 'qwen', 'aliases': ['Qwen'], 'products': [], 'accounts': []},
        {'brand_id': 'deepseek', 'aliases': ['DeepSeek'], 'products': [], 'accounts': []},
    ]
    monkeypatch.setattr(cycle, '_classification_tracked_brand_catalog', lambda: catalog)
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            request = json.loads(kwargs['messages'][0]['content'])
            brands = request['state']['target_brands']
            qwen, other = brands.index('qwen'), brands.index('deepseek')
            result['answers']['binding:missing_subject']['noul'] = 0.9
            result['answers'][f'b{qwen}:relevant']['noul'] = 0.9
            result['answers'][f'b{other}:relevant']['noul'] = 0.9
            result['answers'][f'b{qwen if retry else other}:identity_namesake_only']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='mixed-first')
    qwen = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    other = models.PostBrandClassificationState.objects.get(post=state.post, brand=deepseek)
    assert qwen.outcome == 'classified' and other.outcome == 'context_missing'
    selected_id = qwen.selected_final_judgment_id
    release_fingerprint = selected_release_revision(state.pk)['content_fingerprint']
    catalog[0]['aliases'].append('Additional Qwen alias')
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='mixed-retry')
    qwen.refresh_from_db()
    other.refresh_from_db()
    assert qwen.outcome == 'classified' and qwen.selected_final_judgment_id == selected_id
    assert other.outcome == 'classified'
    assert other.selected_final_judgment.changes_json['feed_replacement_reason'] == 'unresolved_feed_improved'
    assert read_publication_findings(state.pk)
    assert selected_release_revision(state.pk)['content_fingerprint'] == release_fingerprint


def test_promotion_retry_does_not_reclassify_completed_feed_from_identity_vote(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.9
            if retry:
                result['answers']['identity_namesake_only']['noul'] = 0.9
                result['answers']['relevant']['noul'] = 0.1
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='identity-first')
    prior = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    assert prior.outcome == 'classified'
    selected_id = prior.selected_final_judgment_id
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='identity-exclusion')
    prior.refresh_from_db()
    assert prior.outcome == 'classified'
    assert prior.selected_final_judgment_id == selected_id


def test_promotion_retry_preserves_legacy_completed_feed_without_partial_marker(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.9
            if retry:
                result['answers']['identity_namesake_only']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='legacy-promotion-first')
    selected = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    final = selected.selected_final_judgment
    selected_id = final.pk
    final.changes_json.pop('feed_axes_complete')
    final.changes_json.pop('feed_input_fingerprint')
    final.save(update_fields=['changes_json'])
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='legacy-promotion-retry')
    selected.refresh_from_db()
    assert selected.outcome == 'classified'
    assert selected.selected_final_judgment_id == selected_id


def test_promotion_retry_new_brand_does_not_replace_completed_brand(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.9
            if retry:
                request = json.loads(kwargs['messages'][0]['content'])
                brands = request['state']['target_brands']
                qwen = brands.index('qwen')
                other = brands.index('deepseek')
                result['answers'][f'b{qwen}:identity_namesake_only']['noul'] = 0.9
                result['answers'][f'b{other}:relevant']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='new-brand-first')
    qwen = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    selected_id = qwen.selected_final_judgment_id
    deepseek = models.Brand.objects.create(nickname='deepseek', display_name='DeepSeek')
    models.PostBrand.objects.create(post=state.post, brand=deepseek)
    catalog = [
        {'brand_id': 'qwen', 'aliases': ['Qwen'], 'products': [], 'accounts': []},
        {'brand_id': 'deepseek', 'aliases': ['DeepSeek'], 'products': [], 'accounts': []},
    ]
    monkeypatch.setattr(cycle, '_classification_tracked_brand_catalog', lambda: catalog)
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='new-brand-retry')
    qwen.refresh_from_db()
    assert qwen.outcome == 'classified'
    assert qwen.selected_final_judgment_id == selected_id
    assert models.PostBrandClassificationState.objects.get(post=state.post, brand=deepseek).outcome == 'classified'


def test_resolved_positive_promotion_retains_audit_judgment(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    state.post.text += ' Try OrbitChat today!'
    state.post.save(update_fields=['text'])
    transport.document['entities'].append({
        'name': 'OrbitChat', 'source': 'post', 'evidence': 'Try OrbitChat today!',
    })
    original = transport.messages_create
    retry = False

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.1 if retry else 0.9
            if retry:
                result['answers']['untracked_pitch']['noul'] = 0.9
                result['answers']['binding:S0:pitch']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='positive-promotion-first')
    previous = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    selected_id = previous.selected_final_judgment_id
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    retry = True
    runner._run_post_fetch([], run_id='positive-promotion-retry')
    previous.refresh_from_db()
    assert previous.selected_final_judgment_id == selected_id
    promotion = models.PostUntrackedBrandPromotion.objects.get(post=state.post)
    assert promotion.final_judgment_id is not None
    assert promotion.final_judgment.changes_json['promotion_retry_reason'] == 'fill_unresolved_promotion'


def test_replaying_old_generation_without_feed_fingerprint_is_idempotent(monkeypatch):
    state, publication = captured_publication(monkeypatch)
    selected = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    final = selected.selected_final_judgment
    final.changes_json.pop('feed_input_fingerprint')
    final.save(update_fields=['changes_json'])
    previous = read_publication_findings(state.pk)
    cycle._publish_stage1_classification(**publication)
    selected.refresh_from_db()
    assert selected.selected_final_judgment_id == final.pk
    assert read_publication_findings(state.pk) == previous


def test_retry_does_not_replace_an_unimproved_context_missing_judgment(monkeypatch):
    state, runner, transport = setup_cycle(monkeypatch)
    original = transport.messages_create

    def responses(**kwargs):
        result = original(**kwargs)
        if not kwargs['model'].startswith('deepseek'):
            result['answers']['binding:missing_subject']['noul'] = 0.9
            result['answers']['identity_namesake_only']['noul'] = 0.9
        return result

    transport.messages_create = responses
    runner._run_post_fetch([], run_id='missing-first')
    selected = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    assert selected.outcome == 'context_missing'
    selected_id = selected.selected_final_judgment_id
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(classification_next_attempt_at=None)
    runner._run_post_fetch([], run_id='missing-retry')
    selected.refresh_from_db()
    assert selected.outcome == 'context_missing'
    assert selected.selected_final_judgment_id == selected_id


def test_explicit_reassessment_can_replace_completed_feed_and_records_reason(monkeypatch):
    state, publication = captured_publication(monkeypatch)
    selected = models.PostBrandClassificationState.objects.get(post=state.post, brand_id='qwen')
    prior_id = selected.selected_final_judgment_id
    models.PostEnrichmentState.objects.filter(pk=state.pk).update(
        claim_run_id='explicit-reassessment', claim_expires_at=timezone.now() + timedelta(minutes=5),
    )
    publication['run_id'] = 'explicit-reassessment'
    publication['force_feed_reassessment'] = True
    cycle._publish_stage1_classification(**publication)
    selected.refresh_from_db()
    assert selected.selected_final_judgment_id != prior_id
    assert selected.selected_final_judgment.changes_json['feed_replacement_reason'] == 'explicit_reassessment'
    assert read_publication_findings(state.pk)
