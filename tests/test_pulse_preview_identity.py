"""Replay the saved publisher disclosure. The finding is a local input, not a new model response."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from core import models
from core.measurement_taxonomy import digest
from core.product_identity import resolve_saved_release_finding
from core.product_release_dossiers import persist_classified_release_findings
from tests.product_factory import product_type_fields
from tests.test_pulse_finding_persistence import finding

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/pulse-glm-flash-preview.json").read_text()
)
ALIAS = "Ox Alpha"
PUBLIC = "GLM-5.3-Flash"
REVEAL = "2092616204787626030"


def save_finding(post, name):
    item = finding(name, key=digest([post.pk, name]))
    lead = post.text.splitlines()[0]
    item.update(
        brand_id="glm",
        issuer_evidence={
            "relation": "source_author",
            "observed_name": None,
            "source_excerpt": lead,
            "source_locator": None,
        },
    )
    item["assertions"][0].update(
        assertion_text=lead,
        source_excerpt=lead,
        effective_precision="day",
        effective_date=post.created_at.date().isoformat(),
    )
    if post.author_handle != "Zai_org":
        item.pop("issuer_evidence")
        item["assertions"][0]["claim_kind"] = "release_report"
    from core.classified_product_releases import (
        TARGETED_RELEASE_REVISION,
        _output_manifest,
        _release_source_hash,
    )

    fingerprint = digest(post.text)
    revision = digest(
        {
            "post_id": post.pk,
            "fingerprint": fingerprint,
            "producer": "targeted-release-v1",
            "selection": "offline-replay",
        }
    )
    models.PostBrandClassificationJudgment.objects.create(
        post=post,
        brand_id="glm",
        revision_id=revision,
        stage="content",
        canonical_judgment={},
        contract_version="pulse-release-only-v1",
        taxonomy_version="pulse-release-only-v1",
        prompt_version=TARGETED_RELEASE_REVISION,
        model="offline-replay",
        provider_role="targeted-release",
        input_context_fingerprint=fingerprint,
        selector_version="pulse-release-only-v1",
        validation_state="release_only",
        changes_json={
            "selection": "offline-replay",
            "brand_ids": ["glm"],
            "source_evidence_hash": _release_source_hash(post),
            "release_output": _output_manifest([item]),
        },
    )
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id=revision,
        content_fingerprint=fingerprint,
        extraction_version=TARGETED_RELEASE_REVISION,
        findings=[item],
    )
    return result["findings"][0]


def replay_inputs():
    brand = models.Brand.objects.create(nickname="glm", display_name="Z.ai")
    account = models.Account.objects.create(
        author_id="1726486879456096256", handle="Zai_org"
    )
    models.Role.objects.get_or_create(key="official")
    models.BrandAccount.objects.create(brand=brand, account=account, role_id="official")
    products = {}
    for record in FIXTURE["products"]:
        product = models.Product.objects.create(
            brand=brand,
            product_key=record["product_key"],
            display_name=record["display_name"],
            repo_id=record["repo_id"],
            **product_type_fields(models.Product, "model-llm"),
        )
        product.refresh_from_db()
        products[product.display_name] = product
    posts = {}
    for record in FIXTURE["posts"]:
        post = models.Post.objects.create(
            tweet_id=record["tweet_id"],
            text=record["text"],
            created_at=datetime.fromisoformat(record["created_at"]),
            author_handle=record["author_handle"],
            author=account if record["author_handle"] == "Zai_org" else None,
        )
        models.PostBrand.objects.create(brand=brand, post=post)
        posts[post.pk] = post
    for pid, name in [("2123659545637785838", ALIAS), ("2123696185680826434", PUBLIC)]:
        models.PostBrandProduct.objects.create(
            post=posts[pid],
            brand=brand,
            product=products[name],
            observed_name=name,
            source_evidence={"source": "retained post"},
            verification_policy_version="stored-replay",
        )
    return products, posts


def test_publisher_preview_replay_and_cutoffs():
    products, posts = replay_inputs()
    flash = products[PUBLIC]
    src = posts[REVEAL]
    saved = save_finding(src, PUBLIC)
    before_processing = timezone.now()
    for _ in range(2):
        result = resolve_saved_release_finding(claim_id=saved["anchor_claim_id"])
        assert result["product_id"] == flash.pk
    claims = models.EventDossierClaim.objects.filter(
        event_dossier_source__post=src,
        extraction_version="pulse-publisher-preview-v1",
        reported_product=flash,
    )
    assert claims.count() == 1
    assert claims.get().effective_at == src.created_at
    spans = models.PostSubjectAttribution.objects.filter(post=src, observed_name=ALIAS)
    assert list(spans.values_list("subject__product_id", flat=True)) == [
        flash.product_key
    ]
    from core.product_preview_names import preview_targets

    assert (
        preview_targets("glm", ALIAS, as_of=src.created_at - timedelta(seconds=1))
        == set()
    )
    assert preview_targets("glm", ALIAS, as_of=src.created_at) == {flash.pk}
    assert preview_targets("glm", ALIAS, as_of=before_processing, strict=True) == set()
    assert preview_targets("glm", ALIAS, as_of=timezone.now(), strict=True) == {
        flash.pk
    }
    assert preview_targets("other", ALIAS) == set()
    assert preview_targets("glm", "GLM-5.3") == set()
    assert models.Product.objects.filter(brand_id="glm").count() == 3


def load_recorded_tokens(product, *, spec=None):
    from core.benchmark_metric_identity import configure_collection
    from core.benchmark_metric_store import persist_source
    from core.measurement_taxonomy import configure_taxonomy, resolve_subject_id
    from tests.test_benchmark_download_db_identity import setup_spec

    if spec is None:
        _, spec = setup_spec()
    flash = product.display_name == PUBLIC
    row = FIXTURE["openrouter" if flash else "openrouter_original"]
    version = configure_taxonomy(
        {
            "reviewed_by": "offline replay",
            "subjects": [{"kind": "product", "key": str(product.product_key)}],
        }
    )
    mapping = {
        "source": "openrouter",
        "source_subject_kind": "model",
        "identifier_scope": "",
        "external_identifier": row["model_permaslug"],
        "subject_id": str(resolve_subject_id("product", product.product_key)),
        "evidence_url": "https://openrouter.ai/"
        + row["model_permaslug"].rsplit("-", 1)[0],
    }
    contract = configure_collection(
        {
            **spec,
            "taxonomy_version": str(version.pk),
            "mappings": [mapping],
            "source_configuration": {"openrouter": {"metrics": ["total_tokens"]}},
        }
    )
    run = persist_source(
        contract,
        "openrouter",
        digest(row),
        {
            "status": "ok",
            "coverage": "top_50_public_models",
            "as_of": "2026-11-25T08:07:19.356Z"
            if flash
            else FIXTURE["openrouter_original_as_of"],
            "meta": {"version": "v1"},
            "rows": [row],
        },
    )
    return run.observations.get().values.get()


def test_flash_chart_from_queue_and_retained_usage(client, settings, monkeypatch):
    from django.core.cache.backends.locmem import LocMemCache

    from core.chart_engine import (
        ChartRequest,
        ReleaseAnchor,
        _single_brand_discussion,
        validate_request,
    )
    from core.product_release_detection_queue import drain_posts, enqueue_posts
    from core.release_chart_handoff import resolve_release

    settings.SECURE_SSL_REDIRECT = False
    products, posts = replay_inputs()
    flash = products[PUBLIC]
    src = posts[REVEAL]
    saved = save_finding(src, PUBLIC)
    models.PostEnrichmentState.objects.create(
        post=src, classification_status="succeeded"
    )
    for _ in range(2):
        enqueue_posts([src.pk])
        result = drain_posts(classified_only=True, post_ids=[src.pk])
        assert result["processed"] == 1 and not result["failed"]
    rel = resolve_release(saved["dossier_id"])
    assert rel.date == src.created_at.date() and rel.product_key == flash.product_key
    from tests.test_benchmark_download_db_identity import setup_spec

    _, spec = setup_spec()
    original_value = load_recorded_tokens(products["GLM-5.3"], spec=spec)
    value = load_recorded_tokens(flash, spec=spec)
    assert original_value.integer_value == 195375201868
    assert value.integer_value == 360760043126
    from monitor import single_brand_chart

    monkeypatch.setattr(single_brand_chart, "cache", LocMemCache("preview-chart", {}))
    monkeypatch.setattr(single_brand_chart, "_LAST_BUILD_FINISHED", float("-inf"))
    params = {"release": str(rel.dossier_id), "locale": "en"}
    page = client.get("/pulse", params)
    assert page.status_code == 200 and PUBLIC.encode() in page.content
    response = client.get("/general/chart/", params)
    assert response.status_code == 200, response.content
    chart = response.json()
    points = {line["key"]: line["points"] for line in chart["lines"]}
    tokens = [p for p in points["openrouter:total_tokens"] if p["date"] == "2026-08-26"]
    assert len(tokens) == 1 and int(tokens[0]["raw"]) == value.integer_value
    # The publisher used both names, and has both an edge and a literal attribution.
    assert sum(int(p["raw"] or 0) for p in points["discussion:product_posts"]) == 1
    brand_only = models.Post.objects.create(
        tweet_id="brand-only-control",
        text="GLM",
        created_at=posts["2123696185680826434"].created_at,
    )
    models.PostBrand.objects.create(post=brand_only, brand_id="glm")
    for product, n in [(flash, 2), (products["GLM-5.3"], 0)]:
        anchor = ReleaseAnchor.from_qualified(rel)
        if product != flash:
            # Use the original model's own dossier/anchor for its chart.
            original = posts["2088132965922476159"]
            s = save_finding(original, product.display_name)
            resolve_saved_release_finding(claim_id=s["anchor_claim_id"])
            anchor = ReleaseAnchor.from_qualified(resolve_release(s["dossier_id"]))
            monkeypatch.setattr(
                single_brand_chart, "_LAST_BUILD_FINISHED", float("-inf")
            )
            original_response = client.get(
                "/general/chart/", {"release": str(s["dossier_id"]), "locale": "en"}
            )
            assert original_response.status_code == 200, original_response.content
            original_tokens = next(
                line
                for line in original_response.json()["lines"]
                if line["key"] == "openrouter:total_tokens"
            )
            assert [
                int(p["raw"])
                for p in original_tokens["points"]
                if p["date"] == "2026-08-26"
            ] == [original_value.integer_value]
        request = ChartRequest(
            target=anchor,
            start=datetime(2026, 11, 20, tzinfo=UTC),
            end=datetime(2026, 11, 21, tzinfo=UTC),
            cutoff=timezone.now(),
            history_mode="hindsight",
        )
        counts = _single_brand_discussion(validate_request(request))
        assert sum(counts["daily"].values()) == 3
        assert sum(counts["product_daily"].values()) == n


@pytest.mark.parametrize("preview_first", [True, False])
def test_preview_milestone_keeps_its_date_and_redirects_only_after_disclosure(
    preview_first,
):
    from core.pulse_readers import release_page
    from core.release_chart_handoff import resolve_release

    products, posts = replay_inputs()
    flash = products[PUBLIC]
    historical = FIXTURE["preview_report"]
    report = models.Post.objects.create(
        tweet_id=historical["tweet_id"],
        text=historical["text"],
        author_handle=historical["author_handle"],
        created_at=datetime.fromisoformat(historical["created_at"]),
    )
    models.PostBrand.objects.create(post=report, brand_id="glm")
    models.PostBrandProduct.objects.create(
        post=report,
        product=products[ALIAS],
        brand_id="glm",
        observed_name=ALIAS,
        source_evidence={"source": "provisional preview association in replay"},
        verification_policy_version="offline",
    )
    first = save_finding(report, ALIAS)
    if preview_first:
        assert (
            resolve_saved_release_finding(claim_id=first["anchor_claim_id"])[
                "product_id"
            ]
            == products[ALIAS].pk
        )
        assert (
            resolve_release(first["dossier_id"]).product_key
            == products[ALIAS].product_key
        )
    public = save_finding(posts[REVEAL], PUBLIC)
    resolve_saved_release_finding(claim_id=public["anchor_claim_id"])
    for _ in range(2):
        result = resolve_saved_release_finding(claim_id=first["anchor_claim_id"])
        assert result["product_id"] == flash.pk
        historic = resolve_release(first["dossier_id"])
        assert historic.product_key == flash.product_key
        assert (
            historic.date == report.created_at.date()
            and historic.milestone_kind == "release_report"
        )
        assert (
            resolve_release(public["dossier_id"]).date
            == posts[REVEAL].created_at.date()
        )
        by_id = {v["id"]: v for v in release_page()["entries"]}
        assert by_id[first["dossier_id"]]["product_key"] == str(flash.product_key)
    assert not models.ProductRelationship.objects.filter(child_product=flash).exists()


@pytest.mark.parametrize(
    "wrong", ["other_publisher", "quotation", "negated", "uncertain"]
)
def test_unqualified_preview_disclosure_creates_no_alias(wrong):
    _products, posts = replay_inputs()
    post = posts[REVEAL]
    if wrong == "other_publisher":
        models.BrandAccount.objects.filter(brand_id="glm").delete()
    elif wrong == "quotation":
        post.is_quote = True
    elif wrong == "negated":
        post.text = post.text.replace(
            "Previously previewed as", "Never previously previewed as"
        )
    else:
        post.text = post.text.replace("Ox Alpha,", "Ox Alpha or Acme,")
    post.save()
    row = save_finding(post, PUBLIC)
    resolve_saved_release_finding(claim_id=row["anchor_claim_id"])
    assert not models.EventDossierClaim.objects.filter(
        extraction_version="pulse-publisher-preview-v1"
    ).exists()


def test_conflicting_official_disclosures_do_not_assign_preview_posts():
    from core.product_preview_names import chart_preview_names, preview_targets

    products, posts = replay_inputs()
    src = posts[REVEAL]
    first = save_finding(src, PUBLIC)
    resolve_saved_release_finding(claim_id=first["anchor_claim_id"])
    other = products["GLM-5.3"]
    competing = models.Post.objects.create(
        tweet_id="competing-official-claim",
        author=src.author,
        author_handle=src.author_handle,
        created_at=src.created_at + timedelta(days=1),
        text=f"Introducing {other.display_name}\n\n- Previously previewed as {ALIAS}",
    )
    models.PostBrand.objects.create(post=competing, brand_id="glm")
    report = save_finding(competing, other.display_name)
    resolve_saved_release_finding(claim_id=report["anchor_claim_id"])
    assert preview_targets("glm", ALIAS) == {other.pk, products[PUBLIC].pk}
    assert chart_preview_names(products[PUBLIC], timezone.now(), True) == []
    assert chart_preview_names(other, timezone.now(), True) == []
    old = posts["2123659545637785838"]
    record = save_finding(old, ALIAS)
    assert (
        resolve_saved_release_finding(claim_id=record["anchor_claim_id"])["status"]
        == "unresolved"
    )
