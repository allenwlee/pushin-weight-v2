"""An upload list identifies exact model Products without dating their launch."""

import pytest

HEADER = "Currently uploading the following models to Huggingface:"
NAMES = (
    "Velqora-38M-Base",
    "Velqora-38M-Instruct",
    "Velqora-40M-Base",
    "Velqora-40M-Instruct",
)


def finding(name):
    return {
        "observed_name": name,
        "category": "model-llm",
        "novelty": "availability_update",
        "issuer_evidence": {"relation": "source_author", "source_excerpt": HEADER},
        "assertions": [{"claim_kind": "availability", "source_excerpt": HEADER}],
    }


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("item_excerpt", [False, True])
def test_publisher_upload_list_names_each_exact_model(name, item_excerpt):
    from core.product_availability_identity import names_uploaded_model

    f = finding(name)
    if item_excerpt:
        f["issuer_evidence"]["source_excerpt"] = name
        f["assertions"][0]["source_excerpt"] = name
    assert names_uploaded_model(HEADER + "\n" + "\n".join(NAMES), f)


@pytest.mark.parametrize(
    ("header", "text", "name"),
    [
        (HEADER, "Velqora-38M-Base-GGUF", "Velqora-38M-Base"),
        (
            HEADER,
            "Velqora-40M-Base\n\nTraining base:\nVelqora-38M-Base",
            "Velqora-38M-Base",
        ),
        (HEADER, "Velqora-40M-Base\nBuilt on:\nVelqora-38M-Base", "Velqora-38M-Base"),
        (
            "Not currently uploading the following models:",
            "Velqora-38M-Base",
            "Velqora-38M-Base",
        ),
        ("Tomorrow we will upload:", "Velqora-38M-Base", "Velqora-38M-Base"),
        ("Models I use:", "Velqora-38M-Base", "Velqora-38M-Base"),
    ],
)
def test_upload_evidence_cannot_leak_to_another_model_or_claim(header, text, name):
    from core.product_availability_identity import names_uploaded_model

    f = finding(name)
    f["issuer_evidence"]["source_excerpt"] = header
    f["assertions"][0]["source_excerpt"] = header
    assert not names_uploaded_model(header + "\n" + text, f)


@pytest.fixture
def velqora_evidence():
    import json
    from pathlib import Path

    from django.core.management import call_command

    from core import models
    from core.product_release_dossiers import persist_classified_release_findings
    from core.shared_vocabulary import seed_shared_vocabulary

    call_command("seed_i18n_labels", verbosity=0)
    seed_shared_vocabulary(
        catalogues=(
            "product_types",
            "affiliation_types",
            "event_kinds",
            "event_claim_kinds",
            "release_maturities",
            "release_access_channels",
            "release_availability_states",
        )
    )
    data = json.loads(
        (Path(__file__).parent / "fixtures/pulse-velqora-availability.json").read_text()
    )
    models.Brand.objects.get_or_create(nickname=data["brand"]["nickname"])
    models.Account.objects.create(**data["account"])
    models.Role.objects.get_or_create(pk="official")
    models.BrandAccount.objects.create(**data["official_link"])
    for post_data in data["posts"]:
        post = models.Post.objects.create(**post_data)
        models.PostBrand.objects.create(post=post, brand_id="mono-ai-studio")
        models.PostEnrichmentState.objects.create(
            post=post, classification_status="succeeded"
        )
    for row in data["judgments"]:
        models.PostBrandClassificationJudgment.objects.create(**row)
    models.PostBrandClassificationState.objects.create(**data["original_feed"])
    for publication in data["publications"]:
        persist_classified_release_findings(**publication)
    return [post["tweet_id"] for post in data["posts"]]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("original_first", [True, False])
def test_saved_velqora_publications_reuse_four_products(
    velqora_evidence, original_first
):
    from core import models
    from core.product_release_detection_queue import drain_posts, enqueue_posts
    from core.pulse_readers import release_page

    original, follow_up = velqora_evidence
    order = [original, follow_up] if original_first else [follow_up, original]
    product_keys = set()
    for post in order * 2:
        enqueue_posts([post])
        result = drain_posts(post_ids=[post], classified_only=True)
        assert (
            result["processed"] == 1 and result["failed"] == result["unresolved"] == 0
        )
        keys = set(
            models.Product.objects.filter(brand_id="mono-ai-studio").values_list(
                "product_key", flat=True
            )
        )
        assert len(keys) == 4
        assert not product_keys or product_keys == keys
        product_keys = keys
    for post in order:
        edges = models.PostBrandProduct.objects.filter(post_id=post)
        assert set(edges.values_list("observed_name", flat=True)) == set(NAMES)
        assert set(edges.values_list("product__product_key", flat=True)) == product_keys
    for edge in models.PostBrandProduct.objects.filter(post_id=follow_up):
        publisher_claim = models.EventDossierClaim.objects.get(
            pk=edge.source_evidence["publisher_finding_claim_id"]
        )
        assert publisher_claim.event_dossier_source.post_id == original
    cards = [c for c in release_page()["entries"] if c["name"] in NAMES]
    assert len(cards) == 4
    from core.release_chart_handoff import resolve_release

    for card in cards:
        assert card["novelty"] == "availability_update"
        assert card["product_key"] in {str(key) for key in product_keys}
        with pytest.raises(
            ValueError, match="Release has no unique qualified P2 product and milestone"
        ):
            resolve_release(card["id"])
    assert not models.SourceSubjectMapping.objects.filter(
        subject__product_id__in=product_keys
    ).exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "scenario", ["other_product_kind", "unverified_author", "changed_quote"]
)
def test_saved_upload_needs_unambiguous_compatible_evidence(velqora_evidence, scenario):
    from core import models
    from core.product_release_detection_queue import drain_posts, enqueue_posts

    _, follow_up = velqora_evidence
    if scenario == "other_product_kind":
        models.Product.objects.create(
            display_name=NAMES[0],
            brand_id="mono-ai-studio",
            product_type=models.ProductType.objects.get(code="agent"),
        )
    elif scenario == "unverified_author":
        models.BrandAccount.objects.filter(brand_id="mono-ai-studio").delete()
    else:
        models.Post.objects.filter(pk=follow_up).update(
            quoted_status_id_id=None, quoted_text="Unrelated model"
        )
    enqueue_posts([follow_up])
    result = drain_posts(post_ids=[follow_up], classified_only=True)
    assert result["processed"] == 1 and result["failed"] == 0
    assert result["unresolved"] == (1 if scenario == "other_product_kind" else 4)
    assert not models.PostBrandProduct.objects.filter(
        post_id=follow_up, observed_name=NAMES[0]
    ).exists()
