import pytest
from django.db import transaction

from core import models

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def finding(name="Model A", key="a" * 64):
    return {
        "finding_key": key,
        "observed_name": name,
        "version": None,
        "variant": None,
        "novelty": "new_release",
        "category": "model-llm",
        "brand_id": None,
        "brand_candidate_id": None,
        "candidate_repo_id": None,
        "assertions": [
            {
                "claim_kind": "announcement",
                "assertion_text": "Released Model A",
                "source_excerpt": "Released Model A",
                "source_locator": None,
                "access_channel": None,
                "effective_precision": "unknown",
                "event_timezone": None,
                "effective_at": None,
                "effective_date": None,
                "effective_year": None,
                "effective_month": None,
                "not_before": None,
                "not_after": None,
            }
        ],
    }


def test_saved_findings_replay_and_read_without_creating_products():
    from core.product_release_dossiers import (
        persist_classified_release_findings,
        read_saved_release_findings,
    )

    post = models.Post.objects.create(tweet_id="pulse-p2-1", text="Released Model A")
    args = {
        "source": {"kind": "post", "id": post.pk},
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "classifier-v1",
        "findings": [finding()],
    }
    first = persist_classified_release_findings(**args)
    second = persist_classified_release_findings(**args)
    assert (
        first["findings"][0]["anchor_claim_id"]
        == second["findings"][0]["anchor_claim_id"]
    )
    assert (
        len(
            read_saved_release_findings(
                source=args["source"], revision_id=args["revision_id"]
            )
        )
        == 1
    )
    assert models.EventDossier.objects.count() == 1
    assert models.EventDossierClaim.objects.count() == 3
    assert not models.Product.objects.exists()


def test_single_finding_resource_observation_and_replay():
    from time import perf_counter

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from core.product_release_dossiers import persist_classified_release_findings

    post = models.Post.objects.create(tweet_id="pulse-measurement", text="Released Model A")
    args = {
        "source": {"kind": "post", "id": post.pk}, "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64, "extraction_version": "test", "findings": [finding()],
    }
    observations = []
    for _ in range(2):
        start = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            persist_classified_release_findings(**args)
        observations.append((len(queries), round((perf_counter() - start) * 1000, 2)))
    archive = models.CollectionEvidenceArchive.objects.get(capture_kind="product_release_intake")
    assert models.EventDossier.objects.count() == 1
    assert models.EventDossierSource.objects.count() == 1
    assert models.EventDossierClaim.objects.count() == 3
    assert models.CollectionEvidenceArchive.objects.count() == 1
    assert not models.Product.objects.exists()
    print(f"first/replay query counts and ms: {observations}; archive bytes: {archive.byte_count}")


def test_lineage_evidence_is_preserved_without_guessing_a_product():
    from core.product_release_dossiers import (
        persist_classified_release_findings,
        read_saved_release_findings,
    )

    post = models.Post.objects.create(tweet_id="pulse-lineage", text="Model A succeeds Model 0")
    item = finding()
    item["lineage_evidence"] = [{
        "relationship_kind": "new_version", "parent_observed_name": "Model 0",
        "source_excerpt": post.text, "source_locator": None,
    }]
    args = {"source": {"kind": "post", "id": post.pk}, "revision_id": "b" * 64,
                "content_fingerprint": "c" * 64, "extraction_version": "test", "findings": [item]}
    result = persist_classified_release_findings(**args)
    assert persist_classified_release_findings(**args)["findings"][0]["anchor_claim_id"] == result["findings"][0]["anchor_claim_id"]
    claim = models.EventDossierClaim.objects.get(scope_key__startswith="pulse-lineage-v1:")
    assert claim.source_excerpt == post.text and claim.reported_product_id is None
    assert read_saved_release_findings(source=args["source"], revision_id=args["revision_id"])[0]["finding"]["lineage_evidence"] == item["lineage_evidence"]
    assert not models.ProductRelationship.objects.exists()


def test_lineage_evidence_requires_both_names_in_excerpt():
    from core.product_release_dossiers import persist_classified_release_findings

    post = models.Post.objects.create(tweet_id="pulse-bad-lineage", text="Model A released")
    item = finding()
    item["lineage_evidence"] = [{
        "relationship_kind": "new_version", "parent_observed_name": "Model 0",
        "source_excerpt": post.text, "source_locator": None,
    }]
    with pytest.raises(ValueError, match="lineage"):
        persist_classified_release_findings(
            source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
            content_fingerprint="c" * 64, extraction_version="test", findings=[item],
        )
    assert not models.EventDossier.objects.exists()


def test_invalid_second_finding_rolls_back_first_and_empty_creates_no_dossier():
    from core.product_release_dossiers import persist_classified_release_findings

    post = models.Post.objects.create(tweet_id="pulse-p2-2", text="Released Model A")
    args = {
        "source": {"kind": "post", "id": post.pk},
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "classifier-v1",
    }
    invalid = finding(key="d" * 64)
    invalid["assertions"][0]["access_channel"] = "not-a-channel"
    with pytest.raises(ValueError), transaction.atomic():
        persist_classified_release_findings(**args, findings=[finding(), invalid])
    assert not models.EventDossier.objects.exists()
    assert (
        persist_classified_release_findings(**args, findings=[])["outcome"]
        == "no_findings"
    )
    assert not models.EventDossier.objects.exists()


def test_unnamed_finding_is_recoverable_and_changed_replay_is_rejected():
    from core.product_release_dossiers import (
        persist_classified_release_findings,
        read_saved_release_findings,
    )

    post = models.Post.objects.create(tweet_id="pulse-p2-3", text="Released Model A")
    args = {
        "source": {"kind": "post", "id": post.pk},
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "classifier-v1",
    }
    item = finding(name=None)
    result = persist_classified_release_findings(**args, findings=[item])
    anchor = models.EventDossierClaim.objects.get(
        pk=result["findings"][0]["anchor_claim_id"]
    )
    assert anchor.claim_kind_reference.code == "release_signal"
    assert (
        read_saved_release_findings(
            source=args["source"], revision_id=args["revision_id"]
        )[0]["finding"]["observed_name"]
        is None
    )
    item["category"] = "other"
    with pytest.raises(ValueError, match="changed evidence"):
        persist_classified_release_findings(**args, findings=[item])
    assert models.EventDossierClaim.objects.count() == 3


def test_different_offerings_share_post_but_keep_separate_evidence():
    from core.product_release_dossiers import persist_classified_release_findings

    post = models.Post.objects.create(tweet_id="pulse-p2-4", text="Released Model A")
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="classifier-v1",
        findings=[finding(), finding(key="e" * 64)],
    )
    assert len({row["dossier_id"] for row in result["findings"]}) == 2
    assert models.EventDossierSource.objects.filter(post=post).count() == 2


def test_merged_finding_replays_and_reads_once_from_canonical_dossier():
    from core.event_dossiers import (
        add_claim,
        attach_source,
        create_dossier,
        identity_key,
    )
    from core.product_release_dossiers import (
        persist_classified_release_findings,
        read_saved_release_findings,
    )
    from core.product_release_pipeline import merge_dossiers

    post = models.Post.objects.create(
        tweet_id="pulse-p2-merge", text="Released Model A"
    )
    args = {
        "source": {"kind": "post", "id": post.pk},
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "classifier-v1",
        "findings": [finding()],
    }
    original = persist_classified_release_findings(**args)["findings"][0]
    target = create_dossier(
        event_kind="product_release", identity_key=identity_key("test", "merge-target")
    )
    other = models.Post.objects.create(tweet_id="pulse-p2-other", text="Other evidence")
    linked = attach_source(target.pk, post_id=other.pk)
    add_claim(
        linked.pk,
        claim_kind="announcement",
        scope_key="other",
        assertion_text=other.text,
        source_excerpt=other.text,
        extraction_version="test",
    )
    merge_dossiers(
        original["dossier_id"], target.pk, actor="test", reason="Same release"
    )
    saved = read_saved_release_findings(
        source=args["source"], revision_id=args["revision_id"]
    )
    assert len(saved) == 1
    assert saved[0]["dossier_id"] == str(target.pk)
    replay = persist_classified_release_findings(**args)
    assert replay["findings"][0]["dossier_id"] == str(target.pk)


def test_assertion_order_does_not_change_saved_evidence():
    from core.product_release_dossiers import persist_classified_release_findings

    post = models.Post.objects.create(
        tweet_id="pulse-p2-order", text="Released Model A"
    )
    item = finding()
    other = dict(item["assertions"][0], claim_kind="availability", access_channel="api")
    item["assertions"].append(other)
    args = {
        "source": {"kind": "post", "id": post.pk},
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "test",
    }
    first = persist_classified_release_findings(**args, findings=[item])
    item["assertions"].reverse()
    second = persist_classified_release_findings(**args, findings=[item])
    assert (
        first["findings"][0]["anchor_claim_id"]
        == second["findings"][0]["anchor_claim_id"]
    )
    assert models.EventDossierClaim.objects.count() == 4


def test_observation_origin_and_post_canonicalization_keep_source_lineage():
    from core.product_release_dossiers import (
        persist_classified_release_findings,
        read_saved_release_findings,
    )
    from tests.test_benchmark_download_db_models import measurement

    _, _, observation = measurement()
    source = {"kind": "observation", "id": observation.pk}
    args = {
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "test",
        "findings": [finding()],
    }
    result = persist_classified_release_findings(source=source, **args)
    link = models.EventDossierSource.objects.get(pk=result["findings"][0]["source_id"])
    assert link.collection_observation_id == observation.pk and link.post_id is None
    assert (
        len(read_saved_release_findings(source=source, revision_id=args["revision_id"]))
        == 1
    )

    post = models.Post.objects.create(
        tweet_id="pulse-observed-post", text="Released Model A"
    )
    models.CollectionObservation.objects.filter(pk=observation.pk).update(
        source_subject_kind="post",
        post=post,
        source_identifier=post.pk,
        product=None,
        mapping=None,
    )
    result = persist_classified_release_findings(
        source=source, **{**args, "revision_id": "d" * 64}
    )
    link = models.EventDossierSource.objects.get(pk=result["findings"][0]["source_id"])
    assert result["source"] == {"kind": "post", "id": post.pk}
    assert link.post_id == post.pk and link.collection_observation_id is None


def test_issuer_report_is_preserved_with_source_without_assigning_ownership():
    from core.product_release_dossiers import (
        persist_classified_release_findings,
        read_saved_release_findings,
    )

    post = models.Post.objects.create(
        tweet_id="issuer-report", text="We released Model A"
    )
    item = finding()
    item["issuer_evidence"] = {
        "relation": "source_author",
        "source_locator": None,
        "source_excerpt": "We released Model A",
        "observed_name": None,
    }
    args = {
        "source": {"kind": "post", "id": post.pk},
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "test",
        "findings": [item],
    }
    result = persist_classified_release_findings(**args)
    saved = read_saved_release_findings(
        source=args["source"], revision_id=args["revision_id"]
    )
    assert saved[0]["finding"]["issuer_evidence"] == item["issuer_evidence"]
    claim = models.EventDossierClaim.objects.get(
        scope_key__startswith="pulse-reported-issuer-v1:"
    )
    assert claim.reported_brand_id is None and claim.reported_product_id is None
    assert result["findings"][0]["identity"] == "unresolved"


def test_attributed_issuer_must_be_named_in_its_source_excerpt():
    from core.product_release_dossiers import persist_classified_release_findings

    post = models.Post.objects.create(
        tweet_id="invalid-issuer", text="Someone released Model A"
    )
    item = finding()
    item["issuer_evidence"] = {
        "relation": "attributed_party",
        "source_locator": None,
        "source_excerpt": "Someone released Model A",
        "observed_name": "Unrelated",
    }
    with pytest.raises(ValueError, match="issuer"):
        persist_classified_release_findings(
            source={"kind": "post", "id": post.pk},
            revision_id="b" * 64,
            content_fingerprint="c" * 64,
            extraction_version="test",
            findings=[item],
        )
    assert not models.EventDossier.objects.exists()


def test_source_qualified_hf_repository_is_queued_from_saved_finding(monkeypatch, settings):
    from core.product_release_dossiers import persist_classified_release_findings

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    models.DataSource.objects.get_or_create(pk='hf', defaults={'name':'Hugging Face', 'source_type':'model_adoption'})
    post = models.Post.objects.create(tweet_id='pulse-exact-hf', text='Released Model A https://huggingface.co/acme/Model-A')
    item = finding()
    item['candidate_repo_id'] = 'acme/Model-A'
    persist_classified_release_findings(source={'kind':'post', 'id':post.pk}, revision_id='b' * 64,
        content_fingerprint='c' * 64, extraction_version='test', findings=[item])
    job = models.CollectionJob.objects.get(targets__target_role='exact_model')
    assert job.targets.get().native_identifier == 'acme/Model-A'
    assert job.dossier_claim_links.count() == 2


def test_finding_cannot_queue_repo_absent_from_saved_source(settings):
    from core.product_release_dossiers import persist_classified_release_findings

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    models.DataSource.objects.get_or_create(pk='hf', defaults={'name':'Hugging Face', 'source_type':'model_adoption'})
    post = models.Post.objects.create(tweet_id='pulse-wrong-hf', text='Released Model A https://huggingface.co/other/Model-A')
    item = finding()
    item['candidate_repo_id'] = 'acme/Model-A'
    persist_classified_release_findings(source={'kind':'post', 'id':post.pk}, revision_id='b' * 64,
        content_fingerprint='c' * 64, extraction_version='test', findings=[item])
    assert not models.CollectionJob.objects.filter(operation='release_acquisition').exists()


def test_multiple_findings_do_not_guess_which_offering_owns_hf_link(settings):
    from core.product_release_dossiers import persist_classified_release_findings

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    models.DataSource.objects.get_or_create(pk='hf', defaults={'name':'Hugging Face', 'source_type':'model_adoption'})
    post = models.Post.objects.create(tweet_id='pulse-ambiguous-hf', text='Released Model A https://huggingface.co/acme/Model-A')
    first, second = finding(), finding(name='Model B', key='d' * 64)
    persist_classified_release_findings(source={'kind':'post', 'id':post.pk}, revision_id='b' * 64,
        content_fingerprint='c' * 64, extraction_version='test', findings=[first, second])
    assert not models.CollectionJob.objects.filter(operation='release_acquisition').exists()


def test_exact_hf_lead_survives_dossier_merge_before_registration(monkeypatch, settings):
    from core.event_dossiers import create_dossier, identity_key
    from core.product_release_acquisition import queue_hf_name_search
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_pipeline import merge_dossiers

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    monkeypatch.setattr('core.product_release_acquisition.queue_after_commit', lambda *args, **kwargs: None)
    models.DataSource.objects.get_or_create(pk='hf', defaults={'name':'Hugging Face', 'source_type':'model_adoption'})
    post = models.Post.objects.create(tweet_id='pulse-merged-hf', text='Released Model A https://huggingface.co/acme/Model-A')
    item = finding()
    item['candidate_repo_id'] = 'acme/Model-A'
    saved = persist_classified_release_findings(source={'kind':'post', 'id':post.pk}, revision_id='b' * 64,
        content_fingerprint='c' * 64, extraction_version='test', findings=[item])
    original = saved['findings'][0]
    target = create_dossier(event_kind='product_release', identity_key=identity_key('test', 'merged-hf-target'))
    merge_dossiers(original['dossier_id'], target.pk, actor='fixture', reason='same release')
    job = queue_hf_name_search(original['anchor_claim_id'], exact_only=True)
    lead = job.dossier_claim_links.get(claim__scope_key__startswith='pulse-hf-source-link-v1:').claim
    assert lead.event_dossier_source.event_dossier_id == target.pk
    assert lead.event_dossier_source.post_id == post.pk


def test_hf_registration_and_dossier_merge_do_not_deadlock(monkeypatch, settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import connections
    from core import product_release_acquisition as acquisition
    from core.event_dossiers import create_dossier, identity_key
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_pipeline import merge_dossiers

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    monkeypatch.setattr(acquisition, 'queue_after_commit', lambda *args, **kwargs: None)
    models.DataSource.objects.get_or_create(pk='hf', defaults={'name':'Hugging Face', 'source_type':'model_adoption'})
    post = models.Post.objects.create(tweet_id='pulse-concurrent-hf', text='Released Model A https://huggingface.co/acme/Model-A')
    item = finding()
    item['candidate_repo_id'] = 'acme/Model-A'
    saved = persist_classified_release_findings(source={'kind':'post', 'id':post.pk}, revision_id='b' * 64,
        content_fingerprint='c' * 64, extraction_version='test', findings=[item])['findings'][0]
    target = create_dossier(event_kind='product_release', identity_key=identity_key('test', 'concurrent-hf-target'))
    locked, resume = Event(), Event()
    original = acquisition._retain_pulse_hf_lead
    def pause_after_post_lock(*args, **kwargs):
        locked.set()
        assert resume.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(acquisition, '_retain_pulse_hf_lead', pause_after_post_lock)
    def register():
        try:
            return acquisition.queue_hf_name_search(saved['anchor_claim_id'], exact_only=True).pk
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(register)
        try:
            assert locked.wait(10)
            merge_dossiers(saved['dossier_id'], target.pk, actor='fixture', reason='same release')
        finally:
            resume.set()
        job = models.CollectionJob.objects.get(pk=future.result(timeout=10))
    lead = job.dossier_claim_links.get(claim__scope_key__startswith='pulse-hf-source-link-v1:').claim
    assert lead.event_dossier_source.event_dossier_id == target.pk


def test_saved_pulse_sweep_does_not_expand_unverified_hf_name(settings):
    from core.product_release_acquisition import queue_saved_release_claims
    from core.product_release_dossiers import persist_classified_release_findings

    settings.PRODUCT_RELEASE_BACKGROUND_ENABLED = False
    models.DataSource.objects.get_or_create(pk='hf', defaults={'name':'Hugging Face', 'source_type':'model_adoption'})
    post = models.Post.objects.create(tweet_id='pulse-sweep-no-hf', text='Released Qwen3.5')
    item = finding(name='Qwen3.5')
    item['assertions'][0]['source_excerpt'] = 'Released Qwen3.5'
    item['assertions'][0]['assertion_text'] = 'Released Qwen3.5'
    persist_classified_release_findings(source={'kind':'post', 'id':post.pk}, revision_id='b' * 64,
        content_fingerprint='c' * 64, extraction_version='test', findings=[item])
    outcome = queue_saved_release_claims(limit=100, persist=True)
    assert outcome['queued'] == 0
    assert not models.CollectionJob.objects.filter(operation='release_acquisition').exists()


def test_duplicate_identical_assertions_are_saved_once_and_remain_replayable():
    from core.product_release_dossiers import persist_classified_release_findings, read_saved_release_findings

    post = models.Post.objects.create(tweet_id="duplicate-finding", text="Released Model A")
    value = finding()
    value["assertions"].append(dict(value["assertions"][0]))
    args = {
        "source": {"kind": "post", "id": post.pk},
        "revision_id": "d" * 64,
        "content_fingerprint": "e" * 64,
        "extraction_version": "classifier-v1",
        "findings": [value],
    }
    first = persist_classified_release_findings(**args)
    second = persist_classified_release_findings(**args)
    assert first["findings"][0]["anchor_claim_id"] == second["findings"][0]["anchor_claim_id"]
    saved = read_saved_release_findings(source=args["source"], revision_id=args["revision_id"])
    assert saved[0]["finding"]["assertions"] == value["assertions"]
    assert models.EventDossierClaim.objects.filter(scope_key__startswith="pulse-assertion-v1:").count() == 1
