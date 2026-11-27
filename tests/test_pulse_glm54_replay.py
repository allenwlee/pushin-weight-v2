"""Replay the saved Z.ai announcement through P2 and the Pulse chart endpoint."""

import json
from datetime import date
from pathlib import Path

import pytest
from django.utils import timezone

from core import models
from core.classified_product_releases import read_publication_findings
from core.product_release_detection_queue import drain_posts, enqueue_posts
from core.product_release_dossiers import persist_classified_release_findings
from core.pulse_readers import release_page
from core.release_chart_handoff import resolve_release

POST = "2124805514722771349"


def replay_announcement():
    packet = json.loads(
        (Path(__file__).parent / "fixtures/pulse-glm-54-announcement.json").read_text()
    )
    author = models.Account.objects.create(**packet["author"])
    for brand in packet["brands"]:
        models.Brand.objects.get_or_create(
            nickname=brand["nickname"], defaults={"display_name": brand["display_name"]}
        )
    for link in packet["links"]:
        models.Role.objects.get_or_create(key=link["role_id"])
        models.BrandAccount.objects.create(**link, account=author)
    post = models.Post.objects.create(**packet["post"], author=author)
    for brand in packet["brands"]:
        models.PostBrand.objects.create(post=post, brand_id=brand["nickname"])
    models.PostEnrichmentState.objects.create(
        post=post, classification_status="succeeded"
    )
    models.PostBrandClassificationJudgment.objects.create(**packet["marker"])
    doc = packet["packet"]
    persist_classified_release_findings(
        **{
            key: doc[key]
            for key in (
                "source",
                "revision_id",
                "content_fingerprint",
                "extraction_version",
            )
        },
        findings=[doc["finding"]],
    )
    for _ in range(2):
        enqueue_posts([post.pk])
        assert read_publication_findings(post.pk)[0]["finding"] == doc["finding"]
        result = drain_posts(classified_only=True, post_ids=[post.pk])
        assert result["processed"] == 1 and result["failed"] == 0
    entries = [
        entry for entry in release_page()["entries"] if entry["name"] == "GLM-5.4"
    ]
    assert len(entries) == 1
    entry = entries[0]
    release = resolve_release(entry["id"], cutoff=timezone.now())
    assert entry["product_key"] == str(release.product_key)
    assert entry["brand"]["id"] == release.brand_id == "glm"
    assert entry["novelty"] == "new_release"
    assert release.date == date(2026, 11, 23)
    return release


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_real_glm54_without_provider_mapping_still_has_pulse_chart(client, settings, monkeypatch):
    from django.core.cache.backends.locmem import LocMemCache

    from monitor import single_brand_chart

    monkeypatch.setattr(single_brand_chart, "cache", LocMemCache("glm54-release-chart", {}))
    monkeypatch.setattr(single_brand_chart, "_LAST_BUILD_FINISHED", float("-inf"))
    settings.SECURE_SSL_REDIRECT = False
    release = replay_announcement()
    assert not models.SourceSubjectMapping.objects.filter(
        subject__product_id=release.product_key
    ).exists()
    page = client.get("/pulse", {"release": release.dossier_id, "locale": "en"})
    assert page.status_code == 200 and b"GLM-5.4" in page.content
    response = client.get(
        "/general/chart/", {"release": release.dossier_id, "locale": "en"}
    )
    assert response.status_code == 200, response.content
    chart = response.json()
    assert chart["product"]["key"] == str(release.product_key)
    lines = {line["key"]: line for line in chart["lines"]}
    for key in ("discussion:posts", "discussion:product_posts"):
        assert [
            (p["date"], p["raw"]) for p in lines[key]["points"] if p["raw"] is not None
        ] == [("2026-11-23", "1")]
    external = [line for line in lines.values() if line["source"] != "discussion"]
    assert external and all(
        p["raw"] is None for line in external for p in line["points"]
    )
    assert not models.SourceSubjectMapping.objects.filter(
        subject__product_id=release.product_key
    ).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_later_reviewed_listing_reuses_glm54_without_inventing_measurements():
    """A hypothetical OpenCode listing exercises recovery; no such listing was observed."""
    from core.benchmark_metric_identity import register_definitions
    from core.collection_identity import review_catalog_mapping
    from core.measurement_taxonomy import configure_taxonomy, resolve_subject_id
    from core.release_chart_collection import _metric_mappings

    release = replay_announcement()
    assert _metric_mappings(release) == []
    register_definitions(sources=["opencode"])
    source = models.DataSource.objects.get(pk="opencode")
    source.enabled = True
    source.save(update_fields=["enabled"])
    configure_taxonomy(
        {
            "reviewed_by": "fixture",
            "subjects": [{"kind": "product", "key": str(release.product_key)}],
        }
    )
    subject = models.MeasurementSubject.objects.get(
        pk=resolve_subject_id("product", release.product_key)
    )
    path = "/data/fixture/glm-5-4.json"
    attributes = {
        "source": source,
        "subject": subject,
        "external_identifier": "fixture/glm-5-4",
        "identifier_scope": "model_id",
        "source_subject_kind": "model",
        "publisher_account": models.Post.objects.get(pk=POST).author,
        "role": "dedicated_model",
        "version_selector": None,
        "evidence_url": "https://opencode.ai" + path,
        "reviewed_by": "hypothetical listing",
        "identity_snapshot": {},
        "identifier_metadata": {"endpoint_path": path},
    }
    catalog = review_catalog_mapping(**attributes)
    first = _metric_mappings(release)
    assert [m.source_id for m in first] == ["opencode"]
    assert review_catalog_mapping(**attributes).pk == catalog.pk
    assert [m.pk for m in _metric_mappings(release)] == [first[0].pk]
    assert models.SourceSubjectMapping.objects.filter(subject=subject).count() == 2
    assert models.MetricValue.objects.count() == 0
    assert resolve_release(release.dossier_id).product_key == release.product_key


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_discovery_enabled_worker_finds_glm54_with_zero_provider_rows(settings):
    import httpx

    from core.release_chart_collection import collect_due_release_metrics

    release = replay_announcement()
    settings.BENCHMARK_COLLECTION_ENABLED = True
    checked = []

    def check_saved_evidence(qualified, cutoff):
        assert qualified.product_key == release.product_key
        assert not models.SourceSubjectMapping.objects.filter(
            subject__product_id=qualified.product_key
        ).exists()
        checked.append(qualified.dossier_id)

    def unexpected_fetch(request):
        pytest.fail(f"Unmapped release requested a metric at {request.url.path}")

    with httpx.Client(transport=httpx.MockTransport(unexpected_fetch)) as client:
        result = collect_due_release_metrics(
            client=client, discover_saved_endpoints=check_saved_evidence
        )
    assert checked == [release.dossier_id]
    assert result["qualified"] == 1 and result["linked_jobs"] == result["requests"] == 0


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_verified_hf_repository_reuses_catalog_product_from_release():
    from core.product_verification import _prior_dossier_product

    release = replay_announcement()
    product = models.Product.objects.get(product_key=release.product_key)
    assert _prior_dossier_product(
        dossier_id=release.dossier_id, brand=product.brand,
        observed_name=product.display_name, repo_id="zai-org/GLM-5.4",
    ) == product.pk


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_release_with_only_demo_link_avoids_model_metadata_request():
    from core.release_provider_identity import discover_verified_hf_model

    release = replay_announcement()
    from core.event_dossiers import add_claim

    anchor = models.EventDossierClaim.objects.get(pk=release.claim_id)
    demo = "https://huggingface.co/spaces/WANG-XIXI/ViDiHand2"
    add_claim(anchor.event_dossier_source_id, claim_kind="release_context",
              scope_key="official-hf-model:spaces/WANG-XIXI/ViDiHand2",
              source_locator=demo, assertion_text=demo, source_excerpt=demo,
              extraction_version="pulse-publisher-source-v1",
              reported_product_id=models.Product.objects.get(product_key=release.product_key).pk)
    assert discover_verified_hf_model(release, budget=None) is False
