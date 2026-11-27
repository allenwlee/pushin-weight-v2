from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from core.event_dossiers import ProductReleaseInput
from core.models import (
    CollectionJob,
    CollectionRun,
    EventDossierClaimCollectionJob,
    MetricValue,
)
from tests.test_collection_scheduling import scheduled
from tests.test_event_dossiers import claim, dossier, review
from tests.test_geolocation_access import (
    serving_login,  # noqa: F401 -- restricted PostgreSQL role
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def release_for(product, *, key="model", days_ago=1, exact_date=True):
    event = dossier(key)
    day = timezone.now().date() - timedelta(days=days_ago)
    fields = {"effective_precision": "day", "effective_date": day} if exact_date else {}
    evidence = claim(event, key=key, **fields)
    review(
        event,
        evidence,
        review_state="confirmed",
        product_release=ProductReleaseInput(
            observed_name="Model",
            product_key=product.product_key,
            disclosure_state="announced",
            availability_state="available",
        ),
    )
    return event, evidence


def test_scheduled_release_reuses_metric_job_and_recovers_without_fresh_posts(
    settings, monkeypatch
):
    from core.collection_scheduling import take_metric_authority
    from core.release_chart_collection import collect_due_release_metrics

    job = scheduled(settings)
    # The registered schedule is immutable. Pick a time after its real 10:00 UTC slot.
    product = job.contract.mappings.get().subject.product
    event, evidence = release_for(product)
    now = timezone.now()
    later = now.replace(hour=12) if now.hour < 12 else now
    monkeypatch.setattr(timezone, "now", lambda: later)
    seen = []

    def respond(request):
        seen.append(request.url.path)
        return httpx.Response(
            200, json={"id": "lab/Model", "downloads": 0, "downloadsAllTime": 100}
        )

    take_metric_authority(job.pk)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = collect_due_release_metrics(client=client, cutoff=later)
        second = collect_due_release_metrics(client=client, cutoff=later)
    assert first["applied"] == 1 and second["applied"] == 0
    assert len(seen) == 1 and "lab/Model" in seen[0]
    assert (
        EventDossierClaimCollectionJob.objects.filter(claim=evidence, job=job).count()
        == 1
    )
    assert CollectionRun.objects.filter(job=job, status="success").count() == 1
    value = MetricValue.objects.get(source_metric__metric_key="downloads")
    assert (
        value.integer_value == 0
        and value.observation.mapping.subject.product == product
    )
    assert value.observation.inputs.get().input_request.archive_id
    assert event.sources.filter(claims=evidence).exists()


def test_closed_chart_window_and_unresolved_date_make_no_requests(settings):
    from core.release_chart_collection import collect_due_release_metrics

    job = scheduled(settings)
    product = job.contract.mappings.get().subject.product
    release_for(product, key="old", days_ago=50)
    release_for(product, key="undated", exact_date=False)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected request"))
    ) as client:
        result = collect_due_release_metrics(client=client)
    assert result["applied"] == 0
    assert not CollectionRun.objects.exists()
    assert not EventDossierClaimCollectionJob.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_catalog_only_product_collects_through_the_existing_writer_and_honors_revoked_publisher(
    settings,
    monkeypatch,
    request,
):
    from unittest.mock import patch

    from django.core.cache.backends.locmem import LocMemCache
    from django.db import connections

    from core.collection_identity import review_catalog_mapping
    from core.collection_scheduling import due_job
    from core.measurement_taxonomy import resolve_subject_id
    from core.models import (
        CompanyAccount,
        DataSource,
        MeasurementSubject,
        SourceSubjectMapping,
    )
    from core.release_chart_collection import collect_due_release_metrics
    from tests.test_benchmark_download_db_identity import setup_spec
    from tests.test_benchmark_opencode import SELECTED, endpoint

    product, _ = setup_spec()
    source = DataSource.objects.get(pk="opencode")
    source.enabled = True
    source.save(update_fields=["enabled"])
    settings.BENCHMARK_COLLECTION_ENABLED = True
    entry = SELECTED[0]
    from core.chart_engine import (
        ChartRequest,
        ReleaseAnchor,
        build_single_brand_chart,
        single_brand_dates,
    )
    from core.models import (
        Account,
        BrandAccount,
        EventDossier,
        Post,
        PostBrand,
        PostBrandProduct,
        Role,
    )
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from core.release_chart_handoff import resolve_release
    from core.release_chart_history import midnight
    from monitor import single_brand_chart
    from tests.test_pulse_finding_persistence import finding

    day = timezone.now().date() - timedelta(days=1)
    product.display_name = "Lab Model"
    product.save(update_fields=["display_name"])
    author = Account.objects.create(author_id="19701", handle="labfixture")
    role, _ = Role.objects.get_or_create(key="official")
    BrandAccount.objects.create(account=author, brand=product.brand, role=role)
    text = f"We released Lab Model on {day}."
    post = Post.objects.create(
        tweet_id="lab-release", author=author, text=text, created_at=midnight(day)
    )
    PostBrand.objects.create(post=post, brand=product.brand)
    PostBrandProduct.objects.create(
        post=post,
        brand=product.brand,
        product=product,
        observed_name=product.display_name,
        verification_policy_version="fixture",
        source_evidence={},
    )
    item = finding(name=product.display_name)
    item.update(
        brand_id=product.brand_id,
        issuer_evidence={
            "relation": "source_author",
            "source_locator": None,
            "source_excerpt": text,
            "observed_name": None,
        },
    )
    item["assertions"][0].update(
        assertion_text=text,
        source_excerpt=text,
        effective_precision="day",
        effective_date=day.isoformat(),
    )
    saved = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        findings=[item],
        extraction_version="fixture",
    )["findings"][0]
    matched = resolve_saved_release_finding(claim_id=saved["anchor_claim_id"])
    assert matched["product_key"] == str(product.product_key)
    event = EventDossier.objects.get(pk=saved["dossier_id"])
    catalog = review_catalog_mapping(
        source=source,
        subject=MeasurementSubject.objects.get(
            pk=resolve_subject_id("product", product.product_key)
        ),
        external_identifier=entry["external_identifier"],
        identifier_scope="model_id",
        source_subject_kind="model",
        publisher_account=product.publisher_account,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://opencode.ai" + entry["endpoint_path"],
        reviewed_by="test publisher review",
        identity_snapshot={},
        identifier_metadata={"endpoint_path": entry["endpoint_path"]},
    )
    seen = []

    def respond(request):
        seen.append(request.url.path)
        payload = endpoint(tokens=0, updated=timezone.now().isoformat())
        payload["usage"]["daily"][0]["date"] = (
            timezone.now().date() - timedelta(days=1)
        ).isoformat()
        payload["usage"]["daily"][1]["date"] = timezone.now().date().isoformat()
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = collect_due_release_metrics(client=client)
        again = collect_due_release_metrics(client=client)
        assert first["applied"] == 1 and again["applied"] == 0
        job = CollectionJob.objects.get(
            dossier_claim_links__claim__event_dossier_source__event_dossier=event
        )
        assert (
            job.contract.mappings.get().identifier_metadata["release_catalog"][
                "mapping_hash"
            ]
            == catalog.mapping_hash
        )
        assert job.last_success_id and job.last_success.status == "success"
        assert (
            len(seen) == 1
            and MetricValue.objects.filter(
                source_metric__metric_key="tokens", integer_value=0
            ).exists()
        )
        qualified = resolve_release(event.pk)
        assert qualified.source == "p2-qualified" and qualified.date == day
        first_date, last_date = single_brand_dates(day)
        chart = build_single_brand_chart(
            ChartRequest(
                target=ReleaseAnchor.from_qualified(qualified),
                start=midnight(first_date),
                end=midnight(last_date + timedelta(days=1)),
                cutoff=timezone.now(),
                history_mode="hindsight",
            ),
            cache_catalog_states=True,
        )
        lines = {line["key"]: line for line in chart["lines"]}
        points = {
            k: next(
                point
                for point in lines[k]["points"]
                if point["date"] == day.isoformat()
            )
            for k in ["opencode:tokens", "discussion:posts"]
        }
        assert points["discussion:posts"]["raw"] == 1
        numeric = MetricValue.objects.get(
            source_metric__metric_key="tokens", integer_value=0
        )
        assert points["opencode:tokens"]["raw"] == numeric.integer_value
        assert points["opencode:tokens"]["evidence"] == {
            "value_id": numeric.pk,
            "observation_id": numeric.observation_id,
        }
        cache = LocMemCache("release-chart-revocation", {})
        monkeypatch.setattr(single_brand_chart, "cache", cache)
        cache.set(str(event.pk), chart)
        serving, *_ = request.getfixturevalue("serving_login")
        with patch.object(connections["default"], "connection", serving):
            assert single_brand_chart._cached_chart(str(event.pk)) == chart
        CompanyAccount.objects.filter(account=product.publisher_account).update(
            ownership_confirmed=False
        )
        with patch.object(connections["default"], "connection", serving):
            assert single_brand_chart._cached_chart(str(event.pk)) is None
        assert collect_due_release_metrics(client=client)["linked_jobs"] == 0
        # An ordinary shared scheduler also honors revocation, independent of Pulse.
        assert (
            due_job(job, now=timezone.now() + timedelta(hours=1))["reason"]
            == "release_scope_unavailable"
        )
        assert (
            len(seen) == 1
            and SourceSubjectMapping.objects.filter(contract=job.contract).count() == 1
        )


def test_failed_direct_fetch_cools_down_and_siblings_do_not_get_a_fabricated_zero(
    settings, monkeypatch
):
    from core.collection_scheduling import take_metric_authority
    from core.release_chart_collection import collect_due_release_metrics

    job = scheduled(settings)
    product = job.contract.mappings.get().subject.product
    release_for(product)
    now = timezone.now().replace(hour=13)
    monkeypatch.setattr(timezone, "now", lambda: now)
    take_metric_authority(job.pk)
    seen = []

    def unavailable(request):
        seen.append(request.url.path)
        return httpx.Response(503, text="unavailable")

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as client:
        first = collect_due_release_metrics(client=client, max_seconds=2)
        prior = len(seen)
        repeated = collect_due_release_metrics(client=client, max_seconds=2)
        assert first["requests"] == prior > 0 and repeated["requests"] == 0
        assert len(seen) == prior and not MetricValue.objects.exists()


def test_old_release_fills_only_missing_publication_window_and_replay_is_inert(
    settings,
):
    from core.chart_engine import single_brand_dates
    from core.collection_identity import review_catalog_mapping
    from core.measurement_taxonomy import resolve_subject_id
    from core.models import DataSource, MeasurementSubject
    from core.release_chart_collection import collect_due_release_metrics
    from tests.test_benchmark_download_db_identity import setup_spec
    from tests.test_benchmark_opencode import SELECTED, endpoint

    product, _ = setup_spec()
    source = DataSource.objects.get(pk="opencode")
    source.enabled = True
    source.save(update_fields=["enabled"])
    settings.BENCHMARK_COLLECTION_ENABLED = True
    today = timezone.now().date()
    release_day = today - timedelta(days=60)
    first, last = single_brand_dates(release_day)
    entry = SELECTED[0]
    event, _ = release_for(product, key="closed", days_ago=60)
    review_catalog_mapping(
        source=source,
        subject=MeasurementSubject.objects.get(
            pk=resolve_subject_id("product", product.product_key)
        ),
        external_identifier=entry["external_identifier"],
        identifier_scope="model_id",
        source_subject_kind="model",
        publisher_account=product.publisher_account,
        role="dedicated_model",
        version_selector=None,
        evidence_url="https://opencode.ai" + entry["endpoint_path"],
        reviewed_by="test publisher review",
        identity_snapshot={},
        identifier_metadata={"endpoint_path": entry["endpoint_path"]},
    )
    seen = []

    def respond(request):
        seen.append(request.url.path)
        report = endpoint(updated=timezone.now().isoformat())
        report["usage"]["daily"] = [
            {
                "date": (first + timedelta(days=i)).isoformat(),
                "tokens": i + 1,
                "uniqueUsers": 0,
                "sessions": 0,
            }
            for i in range(-1, (last - first).days + 2)
        ]
        return httpx.Response(200, json=report)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first_run = collect_due_release_metrics(client=client)
        again = collect_due_release_metrics(client=client, dossier_ids=[event.pk])
    assert first_run["history_applied"] == 1 and again["history_applied"] == 0
    assert len(seen) == 1
    assert set(
        MetricValue.objects.filter(source_metric__metric_key="tokens").values_list(
            "period_label_date", flat=True
        )
    ) == {first + timedelta(days=i) for i in range((last - first).days + 1)}
    scope_job = CollectionJob.objects.get(
        mode="historical", operation="collect_metrics"
    )
    assert scope_job.state == "completed" and scope_job.targets.count() == 1
    from core.collection_capture import read_document
    from core.models import CollectionRequest

    selected = read_document(scope_job.last_success.payload_archive)
    check = selected["endpoint_checks"][0]
    assert "native_payload" not in check and len(check["dates"]) == 43
    wire = CollectionRequest.objects.get(attempt__run=scope_job.last_success)
    assert len(read_document(wire.archive)["usage"]["daily"]) == 45



def test_real_saved_deepseek_0813_price_update_cannot_supply_a_launch_date(settings):
    import json
    from pathlib import Path

    from core.event_dossiers import ProductReleaseInput
    from core.models import EventDossier, EventDossierClaim
    from core.product_release_dossiers import persist_classified_release_findings
    from core.release_chart_collection import collect_due_release_metrics
    from core.release_chart_handoff import resolve_release
    from tests.test_event_dossiers import post

    # Real saved P1 intake for November 21 (JST). Its model name resembles
    # a date, but its only assertion describes a price change on OpenRouter.
    packet = json.loads(
        (
            Path(__file__).parent / "fixtures/pulse-deepseek-0813-price-update.json"
        ).read_text()
    )
    finding = packet["finding"]
    source = post(packet["source"]["id"], finding["assertions"][0]["source_excerpt"])
    from core.benchmark_metric_identity import configure_collection
    from core.benchmark_metric_store import persist_source
    from core.measurement_taxonomy import configure_taxonomy, subject_id
    from core.models import Brand, Product
    from tests.product_factory import product_type_fields
    from tests.test_benchmark_download_db_identity import setup_spec

    _, spec = setup_spec()
    product = Product.objects.create(
        product_key="20d66250-db05-40bf-8fda-94b610bed0c7",
        repo_id="deepseek-ai/DeepSeek-V4-Pro-0813",
        display_name="DeepSeek-V4-Pro-0813",
        brand=Brand.objects.create(nickname="deepseek"),
        **product_type_fields(Product, "model-llm"),
        private=False,
        disabled=False,
    )
    native = "deepseek/deepseek-v4-pro-20260813"
    taxonomy = configure_taxonomy(
        {
            "reviewed_by": "offline fixture",
            "subjects": [{"kind": "product", "key": str(product.product_key)}],
        }
    )
    mapping = {
        "source": "openrouter",
        "source_subject_kind": "model",
        "identifier_scope": "",
        "external_identifier": native,
        "subject_id": str(subject_id("product", product.product_key)),
        "evidence_url": "https://openrouter.ai/" + native,
    }
    contract = configure_collection(
        {
            **spec,
            "taxonomy_version": str(taxonomy.pk),
            "mappings": [mapping],
            "source_configuration": {"openrouter": {"metrics": ["total_tokens"]}},
        }
    )
    # Selected row from archive b5189608-009f-4b8b-b05a-28bc834c1f15,
    # observation 2341944 / value 611568. Fixture writes get their own local IDs.
    source_row = {
        "date": "2026-08-13",
        "model_permaslug": native,
        "total_tokens": "142872896552",
    }
    run = persist_source(
        contract,
        "openrouter",
        "8" * 64,
        {
            "status": "ok",
            "coverage": "top_50_public_models",
            "as_of": "2026-10-07T02:05:43.707Z",
            "meta": {"version": "v1"},
            "rows": [source_row],
        },
    )
    assert run.observations.get().values.get().integer_value == 142872896552
    settings.BENCHMARK_COLLECTION_ENABLED = True
    saved = persist_classified_release_findings(
        source={"kind": "post", "id": source.pk},
        revision_id=packet["revision_id"],
        content_fingerprint=packet["content_fingerprint"],
        extraction_version=packet["extraction_version"],
        findings=[finding],
    )["findings"][0]
    event = EventDossier.objects.get(pk=saved["dossier_id"])
    update = EventDossierClaim.objects.get(pk=saved["assertion_claim_ids"][0])
    assert (
        update.claim_kind_reference.code == "availability"
        and update.effective_precision == "unknown"
    )
    # Even a reviewed exact Product with a registered measurement job does
    # not turn this saved price evidence into a new launch.
    review(
        event,
        update,
        review_state="confirmed",
        product_release=ProductReleaseInput(
            observed_name=finding["observed_name"],
            product_key=product.product_key,
            disclosure_state="announced",
            availability_state="available",
        ),
    )
    with pytest.raises(ValueError, match="no qualified day"):
        resolve_release(event.pk)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected request"))
    ) as client:
        result = collect_due_release_metrics(client=client)
    assert result["qualified"] == result["requests"] == 0
    assert not EventDossierClaimCollectionJob.objects.exists()
    assert (
        MetricValue.objects.count() == 1
    )  # the already attributed source point survives


def test_stale_dispatch_decision_cannot_collect_an_already_completed_slot(
    settings, monkeypatch
):
    from django.core.management import CommandError

    from core.collection_budgets import invocation_budget
    from core.collection_scheduling import (
        due_job,
        execute_due_job,
        take_metric_authority,
    )

    job = scheduled(settings)
    current = timezone.now().replace(hour=14)
    monkeypatch.setattr(timezone, "now", lambda: current)
    take_metric_authority(job.pk)
    decision = due_job(job)
    assert decision["due"]
    paths = []

    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(
            200, json={"id": "lab/Model", "downloads": 0, "downloadsAllTime": 100}
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        budget = invocation_budget(client)
        execute_due_job(job, decision, budget)
        with pytest.raises(CommandError, match="slot"):
            execute_due_job(job, decision, budget)
    assert len(paths) == 1
    assert CollectionRun.objects.filter(job=job).count() == 1


def test_closed_arena_window_fetches_exact_dates_and_stays_off_latest(settings):
    from core.benchmark_metric_identity import configure_collection
    from core.chart_engine import single_brand_dates
    from core.models import DataSource
    from core.release_chart_collection import collect_due_release_metrics
    from tests.test_benchmark_download_db_identity import setup_spec
    from tests.test_benchmark_download_sources import arena_page, arena_row

    product, spec = setup_spec()
    spec["mappings"][0].update(
        source="arena",
        identifier_scope="",
        source_subject_kind="model",
        external_identifier="lab/model",
    )
    spec["source_configuration"] = {
        "arena": {"metrics": ["rating"], "config": "text", "scheduling_enabled": True}
    }
    configure_collection(spec)
    DataSource.objects.filter(pk="arena").update(enabled=True)
    settings.BENCHMARK_COLLECTION_ENABLED = True
    event, _ = release_for(product, key="old-arena", days_ago=60)
    first, _ = single_brand_dates(timezone.now().date() - timedelta(days=60))
    seen = []

    def respond(request):
        seen.append(request.url)
        assert request.url.params["where"].find(first.isoformat()) >= 0
        return httpx.Response(
            200, json=arena_page([arena_row(model="lab/model", date=first.isoformat())])
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = collect_due_release_metrics(client=client, dossier_ids=[event.pk])
    assert result["history_applied"] == 1 and len(seen) == 1
    row = MetricValue.objects.get(source_metric__metric_key="rating")
    assert row.observation.published_date == first and row.float_value == 1400


@pytest.mark.django_db(transaction=True)
def test_contended_dossier_releases_budget_without_holding_the_worker(settings):
    import time

    from django.db import connection

    from core.release_chart_collection import collect_due_release_metrics

    job = scheduled(settings)
    event, _ = release_for(job.contract.mappings.get().subject.product)
    other = connection.copy()
    try:
        other.set_autocommit(False)
        with other.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM event_dossiers WHERE id = %s FOR UPDATE", [event.pk]
            )
            started = time.monotonic()
            with httpx.Client(
                transport=httpx.MockTransport(
                    lambda _: pytest.fail("Unexpected request")
                )
            ) as client:
                result = collect_due_release_metrics(
                    client=client, dossier_ids=[event.pk], max_seconds=2
                )
            assert time.monotonic() - started < 2
            assert result["status"] == "deferred" and result["requests"] == 0
            assert not EventDossierClaimCollectionJob.objects.exists()
    finally:
        other.rollback()
        other.close()


def test_closed_openrouter_absence_checks_next_window_without_storing_unrelated_products(
    settings, monkeypatch
):
    from core.benchmark_metric_identity import configure_collection
    from core.models import CollectionObservation, DataSource
    from core.release_chart_collection import collect_due_release_metrics
    from tests.test_benchmark_download_db_identity import setup_spec

    product, spec = setup_spec()
    spec["mappings"][0].update(
        source="openrouter",
        source_subject_kind="model",
        identifier_scope="",
        external_identifier="lab/model",
    )
    spec["source_configuration"] = {
        "openrouter": {"metrics": ["total_tokens"], "scheduling_enabled": True}
    }
    configure_collection(spec)
    DataSource.objects.filter(pk="openrouter").update(enabled=True)
    settings.BENCHMARK_COLLECTION_ENABLED = True
    monkeypatch.setenv("BENCHMARK_OPENROUTER_API_KEY", "fixture")
    event, _ = release_for(product, key="closed-ranking", days_ago=60)
    windows = []

    def respond(request):
        first, last = request.url.params["start_date"], request.url.params["end_date"]
        windows.append((first, last))
        return httpx.Response(
            200,
            json={
                "meta": {
                    "version": "v1",
                    "as_of": timezone.now().isoformat(),
                    "start_date": first,
                    "end_date": last,
                },
                "data": [
                    {
                        "date": first,
                        "model_permaslug": "different/model",
                        "total_tokens": "123",
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        for _ in range(2):
            result = collect_due_release_metrics(client=client, dossier_ids=[event.pk])
            assert result["requests"] == 1
    assert len(windows) == 2 and windows[0][1] < windows[1][0]
    assert (
        CollectionJob.objects.filter(mode="historical", state="completed").count() == 2
    )
    assert not MetricValue.objects.exists()
    assert not CollectionObservation.objects.filter(
        source_identifier="different/model"
    ).exists()


def test_unknown_publisher_recovery_runs_before_dated_chart_gate(settings, monkeypatch):
    from core import release_chart_collection as collection
    from core.models import EventDossier
    from core.release_publisher_recovery import recover_release_publisher

    job = scheduled(settings)
    event, _ = release_for(job.contract.mappings.get().subject.product)
    seen = []

    def recover(dossier, *, client, now, budget):
        assert isinstance(dossier, EventDossier)
        seen.append(("publisher", dossier.pk))
        return False

    def undated(identifier, **kwargs):
        seen.append(("date", identifier))
        raise ValueError("no dated public milestone")

    monkeypatch.setattr(recover_release_publisher.__module__ + ".recover_release_publisher", recover)
    monkeypatch.setattr(collection, "resolve_release", undated)
    collection.collect_due_release_metrics(client=None, dossier_ids=[event.pk])
    assert seen == [("publisher", event.pk), ("date", event.pk)]


def test_publisher_page_rotates_overflow_after_first_half_hour():
    from core.event_dossiers import add_claim, attach_source
    from core.release_chart_collection import _recent_publisher_findings
    from tests.test_event_dossiers import post

    pending = set()
    for i in range(15):
        key = f"burst-{i}"
        event = dossier(key)
        source = attach_source(event.pk, post_id=post(key).pk)
        add_claim(source.pk, claim_kind="release_context", scope_key="pulse-novelty-v1:" + key,
                  assertion_text="new_release", source_excerpt=key, extraction_version="test")
        if i:
            pending.add(event.pk)
        else:
            add_claim(source.pk, claim_kind="release_context", scope_key="official-hf-model:lab/test",
                      assertion_text=key, source_excerpt=key, extraction_version="pulse-publisher-source-v1")
    now = timezone.now() + timedelta(hours=1)
    seen = set()
    for slot in range(4):
        page = _recent_publisher_findings(now + timedelta(minutes=15 * slot))
        assert len(page) <= 4
        seen.update(page)
    assert seen == pending
