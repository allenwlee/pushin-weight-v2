import pytest

from core.models import Product

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_exact_hf_repo_creation_converges_and_preserves_existing_identity():
    from core.product_identity import register_hf_product

    first, created = register_hf_product(
        "Acme/Model-8B", defaults={"display_name": "Model-8B"}
    )
    second, created_again = register_hf_product(
        "acme/model-8b", defaults={"display_name": "wrong"}
    )
    assert created and not created_again
    assert first.pk == second.pk
    assert first.product_key == second.product_key
    assert second.display_name == "Model-8B"
    assert Product.objects.count() == 1


def test_empty_native_identity_never_creates_a_product():
    from core.product_identity import register_hf_product

    with pytest.raises(ValueError):
        register_hf_product("", defaults={})
    assert not Product.objects.exists()


def test_saved_finding_with_unknown_identity_stays_pending_without_product():
    from core.models import Post
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    post = Post.objects.create(tweet_id="pending-identity", text="Released Model A")
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="classifier-v1",
        findings=[finding()],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "unresolved"
    assert outcome["product_key"] is None
    assert not Product.objects.exists()


def test_only_confirmed_review_can_resolve_accepted_finding():
    from django.utils import timezone

    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from core.models import EventDossierClaim, Post
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    post = Post.objects.create(tweet_id="reviewed-identity", text="Released Model A")
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[finding()],
    )
    row = result["findings"][0]
    claim = EventDossierClaim.objects.get(pk=row["anchor_claim_id"])
    product = Product.objects.create(display_name="Model A")
    first = complete_review(
        row["dossier_id"],
        expected_current_review_id=None,
        display_title="Model A",
        review_state="provisional",
        evidence_cutoff_at=timezone.now(),
        method_version="test",
        actor="test",
        reason="Test",
        claims=[ClaimDecision(claim.pk, "accepted", "Source")],
        product_release=ProductReleaseInput(
            observed_name="Model A", product_key=product.product_key
        ),
    )
    assert resolve_saved_release_finding(claim_id=claim.pk)["status"] == "unresolved"
    complete_review(
        row["dossier_id"],
        expected_current_review_id=first.pk,
        display_title="Model A",
        review_state="confirmed",
        evidence_cutoff_at=timezone.now(),
        method_version="test",
        actor="test",
        reason="Confirmed",
        claims=[ClaimDecision(claim.pk, "accepted", "Source")],
        product_release=ProductReleaseInput(
            observed_name="Model A", product_key=product.product_key
        ),
    )
    assert resolve_saved_release_finding(claim_id=claim.pk)["product_key"] == str(
        product.product_key
    )


@pytest.mark.parametrize("field", ["version", "variant"])
def test_confirmed_review_conflicting_version_or_variant_remains_unresolved(field):
    from django.utils import timezone

    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from core.models import EventDossierClaim, Post
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    post = Post.objects.create(tweet_id=f"review-version-{field}", text="Released Model A")
    item = finding()
    item[field] = "A"
    saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                               content_fingerprint="c" * 64, extraction_version="test", findings=[item])
    anchor = EventDossierClaim.objects.get(pk=saved["findings"][0]["anchor_claim_id"])
    product = Product.objects.create(display_name="Model A")
    values = {"version_label" if field == "version" else "variant": "different"}
    complete_review(saved["findings"][0]["dossier_id"], expected_current_review_id=None, display_title="Model A",
                    review_state="confirmed", evidence_cutoff_at=timezone.now(), method_version="test", actor="test",
                    reason="Confirmed", claims=[ClaimDecision(anchor.pk, "accepted", "Source")],
                    product_release=ProductReleaseInput(observed_name="Model A", product_key=product.product_key, **values))
    assert resolve_saved_release_finding(claim_id=anchor.pk)["status"] == "unresolved"
    assert not EventDossierClaim.objects.filter(scope_key__startswith="pulse-event-member-v1:").exists()


@pytest.mark.parametrize("review_version,new_version,should_merge", [(None, None, True), (None, "A", True), ("A", None, True), ("A", "B", False)])
def test_existing_confirmed_legacy_release_is_reused_for_new_finding(review_version, new_version, should_merge):
    from django.utils import timezone

    from core.event_dossiers import (
        ClaimDecision,
        ProductReleaseInput,
        add_claim,
        attach_source,
        complete_review,
        create_dossier,
        identity_key,
    )
    from core.models import Brand, EventDossier, Post, PostBrandProduct
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    brand = Brand.objects.create(nickname="legacy-event-brand")
    product = Product.objects.create(display_name="Model A", brand=brand)
    old_post = Post.objects.create(tweet_id="legacy-event-old", text="Model A launched")
    old = create_dossier(event_kind="product_release", identity_key=identity_key("test", "legacy-event"))
    source = attach_source(old.pk, post_id=old_post.pk)
    old_claim = add_claim(source.pk, claim_kind="announcement", scope_key="legacy",
                          assertion_text=old_post.text, source_excerpt=old_post.text, extraction_version="legacy-test")
    complete_review(old.pk, expected_current_review_id=None, display_title="Model A", review_state="confirmed",
                    evidence_cutoff_at=timezone.now(), method_version="test", actor="test", reason="Reviewed",
                    claims=[ClaimDecision(old_claim.pk, "accepted", "Source")],
                    product_release=ProductReleaseInput(observed_name="Model A", product_key=product.product_key, version_label=review_version))
    new_post = Post.objects.create(tweet_id="legacy-event-new", text="Model A is available")
    PostBrandProduct.objects.create(post=new_post, brand=brand, product=product, observed_name="Model A",
                                    source_evidence={}, verification_policy_version="test")
    item = finding()
    item["novelty"] = "availability_update"
    item["version"] = new_version
    saved = persist_classified_release_findings(source={"kind": "post", "id": new_post.pk}, revision_id="b" * 64,
                                               content_fingerprint="c" * 64, extraction_version="test", findings=[item])
    anchor_id = saved["findings"][0]["anchor_claim_id"]
    resolved = resolve_saved_release_finding(claim_id=anchor_id)
    if not should_merge:
        assert resolved["status"] == "unresolved"
        assert EventDossier.objects.filter(merged_into__isnull=True).count() == 2
        return
    assert resolved["status"] == "matched"
    result = reconcile_product_release_events(claim_id=anchor_id, candidate_limit=10, claim_limit=50, max_merges=1, max_seconds=5)
    if should_merge:
        assert result["status"] == "merged" and result["dossier_id"] == str(old.pk)
        assert EventDossier.objects.get(pk=old.pk).sources.count() == 2
    else:
        assert result["merged_ids"] == []
        assert EventDossier.objects.filter(merged_into__isnull=True).count() == 2
    assert EventDossier.objects.get(pk=old.pk).current_review_id is not None


def test_exact_post_product_evidence_resolves_without_creating_duplicate():
    from core.models import Brand, Post, PostBrandProduct
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    post = Post.objects.create(
        tweet_id="existing-product-evidence", text="Released Model A"
    )
    brand = Brand.objects.create(nickname="identity-brand")
    product = Product.objects.create(display_name="Model A", brand=brand)
    PostBrandProduct.objects.create(
        post=post,
        brand=brand,
        product=product,
        observed_name="Model A",
        source_evidence={"source": "reviewed"},
        verification_policy_version="test",
    )
    item = finding()
    item["brand_id"] = brand.pk
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "matched"
    assert outcome["product_key"] == str(product.product_key)
    assert Product.objects.count() == 1


def test_verified_post_edge_can_resolve_when_classifier_has_no_brand():
    from core.models import Brand, Post, PostBrandProduct
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    post = Post.objects.create(
        tweet_id="existing-unattributed-product", text="Released Model A"
    )
    brand = Brand.objects.create(nickname="verified-source-brand")
    product = Product.objects.create(display_name="Model A", brand=brand)
    PostBrandProduct.objects.create(
        post=post,
        brand=brand,
        product=product,
        observed_name="Model A",
        source_evidence={"source": "reviewed"},
        verification_policy_version="test",
    )
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[finding()],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "matched" and outcome["product_id"] == product.pk


def test_competing_post_product_edges_remain_unresolved():
    from core import models
    from core.models import Brand, Post, PostBrandProduct
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    post = Post.objects.create(
        tweet_id="ambiguous-post-product", text="Released Model A"
    )
    for number in range(2):
        brand = Brand.objects.create(nickname=f"ambiguous-{number}")
        product = Product.objects.create(display_name="Model A", brand=brand)
        PostBrandProduct.objects.create(
            post=post,
            brand=brand,
            product=product,
            observed_name="Model A",
            source_evidence={"source": "reviewed"},
            verification_policy_version="test",
        )
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[finding()],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "unresolved" and outcome["product_key"] is None
    assert not models.EventDossierClaim.objects.filter(
        extraction_version="pulse-product-identity-v1"
    ).exists()


def test_official_source_with_explicit_release_can_create_once_without_provider():
    from core.models import Account, Brand, BrandAccount, EventDossierClaim, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="creator-brand")
    account = Account.objects.create(author_id="123456789", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(
        tweet_id="new-official-model", author=account, text="We released Model A"
    )
    item = finding()
    item["assertions"][0]["source_excerpt"] = "We released Model A"
    item["issuer_evidence"] = {
        "relation": "source_author",
        "source_locator": None,
        "source_excerpt": "We released Model A",
        "observed_name": None,
    }
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )
    claim_id = result["findings"][0]["anchor_claim_id"]
    created = resolve_saved_release_finding(claim_id=claim_id)
    claim_count = EventDossierClaim.objects.count()
    replay = resolve_saved_release_finding(claim_id=claim_id)
    assert created["status"] == "created"
    assert (
        replay["status"] == "matched"
        and replay["product_key"] == created["product_key"]
    )
    assert Product.objects.count() == 1
    assert EventDossierClaim.objects.count() == claim_count
    from core.models import ProductGroup, ProductGroupMembership
    group = ProductGroup.objects.get(group_key="pulse-family:" + created["product_key"])
    assert group.name == "Model A"
    assert ProductGroupMembership.objects.filter(
        group=group, product__product_key=created["product_key"],
        taxonomy_version=group.rule_taxonomy_version, membership_status="included",
    ).count() == 1


def test_same_official_product_from_second_post_reuses_first_identity():
    from core.models import (
        Account,
        Brand,
        BrandAccount,
        EventDossier,
        EventDossierClaim,
        Post,
        Role,
    )
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import (
        persist_classified_release_findings,
        read_saved_release_findings,
    )
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="second-post-brand")
    account = Account.objects.create(author_id="123456787", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    outcomes = []
    for number in (1, 2):
        post = Post.objects.create(
            tweet_id=f"official-post-{number}",
            author=account,
            text="We released Model A",
        )
        item = finding(key=str(number) * 64)
        item["issuer_evidence"] = {
            "relation": "source_author",
            "source_locator": None,
            "source_excerpt": "We released Model A",
            "observed_name": None,
        }
        result = persist_classified_release_findings(
            source={"kind": "post", "id": post.pk},
            revision_id="b" * 64,
            content_fingerprint="c" * 64,
            extraction_version="test",
            findings=[item],
        )
        outcomes.append(
            resolve_saved_release_finding(
                claim_id=result["findings"][0]["anchor_claim_id"]
            )
        )
    assert [x["status"] for x in outcomes] == ["created", "matched"]
    assert outcomes[0]["product_key"] == outcomes[1]["product_key"]
    assert Product.objects.count() == 1
    result = reconcile_product_release_events(
        claim_id=outcomes[1]["anchor_claim_id"], candidate_limit=10, claim_limit=50, max_merges=1, max_seconds=5,
    )
    assert result["status"] == "merged" and len(result["merged_ids"]) == 1
    canonical = EventDossier.objects.get(pk=result["dossier_id"])
    assert set(canonical.sources.values_list("post_id", flat=True)) == {"official-post-1", "official-post-2"}
    assert EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=canonical,
        scope_key__startswith="pulse-self-identity-v1:", reported_product_id=outcomes[0]["product_id"],
    ).count() == 2
    for number in (1, 2):
        found = read_saved_release_findings(source={"kind": "post", "id": f"official-post-{number}"}, revision_id="b" * 64)
        assert len(found) == 1 and found[0]["dossier_id"] == str(canonical.pk)
    claim_count = EventDossierClaim.objects.count()
    for outcome in outcomes:
        resolve_saved_release_finding(claim_id=outcome["anchor_claim_id"])
    assert EventDossierClaim.objects.count() == claim_count
    assert reconcile_product_release_events(
        claim_id=outcomes[1]["anchor_claim_id"], candidate_limit=10, claim_limit=50, max_merges=1, max_seconds=5,
    )["status"] == "matched"


def test_same_product_availability_is_one_event_with_source_channel_and_date():
    from datetime import date

    from core.models import (
        Account,
        Brand,
        BrandAccount,
        EventDossier,
        EventDossierClaim,
        Post,
        PostBrandProduct,
        Role,
    )
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="availability-brand")
    account = Account.objects.create(author_id="123456770", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    first = Post.objects.create(tweet_id="availability-launch", author=account, text="We released Model A")
    item = finding(key="1" * 64)
    item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                               "source_excerpt": first.text, "observed_name": None}
    result = persist_classified_release_findings(source={"kind": "post", "id": first.pk}, revision_id="b" * 64,
                                                content_fingerprint="c" * 64, extraction_version="test", findings=[item])
    launch = resolve_saved_release_finding(claim_id=result["findings"][0]["anchor_claim_id"])
    second = Post.objects.create(tweet_id="availability-api", author=account, text="Model A is available via API")
    PostBrandProduct.objects.create(post=second, brand=brand, product_id=launch["product_id"],
                                    observed_name="Model A", source_evidence={}, verification_policy_version="test")
    update = finding(key="2" * 64)
    update["novelty"] = "availability_update"
    update["assertions"][0].update(claim_kind="availability", source_excerpt=second.text,
                                   assertion_text=second.text, access_channel="api", effective_precision="day",
                                   effective_date="2026-11-17")
    result = persist_classified_release_findings(source={"kind": "post", "id": second.pk}, revision_id="d" * 64,
                                                content_fingerprint="e" * 64, extraction_version="test", findings=[update])
    anchor_id = result["findings"][0]["anchor_claim_id"]
    assert resolve_saved_release_finding(claim_id=anchor_id)["status"] == "matched"
    merged = reconcile_product_release_events(claim_id=anchor_id, candidate_limit=10, claim_limit=50, max_merges=1, max_seconds=5)
    assert merged["status"] == "merged"
    dossier = EventDossier.objects.get(pk=merged["dossier_id"])
    claim = EventDossierClaim.objects.get(event_dossier_source__event_dossier=dossier,
                                          event_dossier_source__post=second, claim_kind_reference__code="availability")
    assert claim.release_access_channel_reference.code == "api"
    assert claim.effective_date == date(2026, 11, 17)
    assert dossier.sources.count() == 2 and Product.objects.count() == 1


@pytest.mark.parametrize("anchor_index", [0, 1])
def test_missing_version_evidence_merges_same_product_event(anchor_index):
    from core.models import Account, Brand, BrandAccount, EventDossier, Post, Role
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="version-conflict")
    account = Account.objects.create(author_id="123456769", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    outcomes = []
    for number, version in ((1, None), (2, "A")):
        post = Post.objects.create(tweet_id=f"different-version-{number}", author=account, text="We released Model A")
        item = finding(key=str(number) * 64)
        item["version"] = version
        item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                                   "source_excerpt": post.text, "observed_name": None}
        saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                                   content_fingerprint="c" * 64, extraction_version="test", findings=[item])
        outcomes.append(resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"]))
    assert outcomes[0]["product_key"] == outcomes[1]["product_key"]
    result = reconcile_product_release_events(claim_id=outcomes[anchor_index]["anchor_claim_id"], candidate_limit=10, claim_limit=50,
                                              max_merges=1, max_seconds=5.0)
    assert len(result["merged_ids"]) == 1
    assert EventDossier.objects.filter(merged_into__isnull=True).count() == 1


@pytest.mark.parametrize("rejected_index", [0, 1])
def test_rejected_dossier_is_never_merged_or_used_as_target(rejected_index):
    from core.models import Account, Brand, BrandAccount, EventDossier, Post, Role
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_pipeline import record_intake_decision
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="rejected-event-brand")
    account = Account.objects.create(author_id="123456768", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    outcomes = []
    for number in (1, 2):
        post = Post.objects.create(tweet_id=f"rejected-event-{number}", author=account, text="We released Model A")
        item = finding(key=str(number) * 64)
        item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                                   "source_excerpt": post.text, "observed_name": None}
        saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                                   content_fingerprint="c" * 64, extraction_version="test", findings=[item])
        outcomes.append(resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"]))
    rejected = outcomes[rejected_index]
    record_intake_decision(rejected["dossier_id"], claim_id=rejected["anchor_claim_id"], outcome="non_release",
                           actor="test", reason="Explicit rejection")
    result = reconcile_product_release_events(claim_id=outcomes[1]["anchor_claim_id"], candidate_limit=10, claim_limit=50,
                                              max_merges=1, max_seconds=5)
    assert result["merged_ids"] == []
    assert EventDossier.objects.filter(merged_into__isnull=True).count() == 2


@pytest.mark.parametrize("conflict_kind", ["unresolved", "stale_marker"])
def test_mixed_unresolved_offering_prevents_automatic_dossier_merge(conflict_kind):
    from core.event_dossiers import add_claim
    from core.models import Account, Brand, BrandAccount, EventDossier, Post, Role
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_pipeline import merge_dossiers
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="mixed-event-brand")
    account = Account.objects.create(author_id="123456767", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    outcomes = []
    for number in (1, 2):
        post = Post.objects.create(tweet_id=f"mixed-event-{number}", author=account, text="We released Model A and Mystery")
        item = finding(key=str(number) * 64)
        item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                                   "source_excerpt": "We released Model A", "observed_name": None}
        saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                                   content_fingerprint="c" * 64, extraction_version="test", findings=[item])
        outcomes.append(resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"]))
    if conflict_kind == "unresolved":
        mystery = finding(name="Mystery", key="3" * 64)
        mystery["novelty"] = "unresolved"
        saved = persist_classified_release_findings(source={"kind": "post", "id": "mixed-event-1"}, revision_id="d" * 64,
                                                   content_fingerprint="e" * 64, extraction_version="test", findings=[mystery])
        merge_dossiers(saved["findings"][0]["dossier_id"], outcomes[0]["dossier_id"], actor="test", reason="Fixture setup")
    else:
        from core.models import EventDossierClaim

        anchor = EventDossierClaim.objects.get(pk=outcomes[0]["anchor_claim_id"])
        add_claim(anchor.event_dossier_source_id, claim_kind="release_context",
                  scope_key="pulse-event-member-v1:" + "1" * 64 + ":" + "f" * 64,
                  assertion_text="Conflicting identity", source_excerpt=anchor.source_excerpt,
                  extraction_version="pulse-event-identity-v1", source_archive_id=anchor.source_archive_id,
                  reported_product_id=outcomes[0]["product_id"])
    result = reconcile_product_release_events(claim_id=outcomes[1]["anchor_claim_id"], candidate_limit=10, claim_limit=50,
                                              max_merges=1, max_seconds=5)
    assert result["merged_ids"] == []
    assert EventDossier.objects.filter(merged_into__isnull=True).count() == 2


def test_popular_release_accepts_new_source_without_loading_every_prior_finding():
    import hashlib
    import json
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    from core.collection_capture import archive_document
    from core.event_dossiers import add_claim, attach_source
    from core.models import (
        Account,
        Brand,
        BrandAccount,
        EventDossier,
        Post,
        PostBrandProduct,
        ReleaseMaturity,
        Role,
    )
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="popular-event-brand")
    account = Account.objects.create(author_id="123456766", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    first = Post.objects.create(tweet_id="popular-first", author=account, text="We released Model A")
    item = finding()
    item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                               "source_excerpt": first.text, "observed_name": None}
    saved = persist_classified_release_findings(source={"kind": "post", "id": first.pk}, revision_id="b" * 64,
                                               content_fingerprint="c" * 64, extraction_version="test", findings=[item])
    first_result = resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"])
    dossier = EventDossier.objects.get(pk=first_result["dossier_id"])
    maturity = ReleaseMaturity.objects.get(code="unknown")
    for number in range(51):
        post = Post.objects.create(tweet_id=f"popular-prior-{number}", author=account, text="We released Model A")
        key = hashlib.sha256(f"prior-{number}".encode()).hexdigest()
        item = finding(key=key)
        packet = {"schema": "pulse-release-intake-v1", "source": {"kind": "post", "id": post.pk},
                  "revision_id": "b" * 64, "content_fingerprint": "c" * 64,
                  "extraction_version": "test", "finding": item}
        archive = archive_document(json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(),
                                   encoding="selected-json-canonical-v1", capture_kind="product_release_intake")
        source = attach_source(dossier.pk, post_id=post.pk)
        anchor = add_claim(source.pk, claim_kind="release_report", scope_key=f"pulse-finding-v1:{key}",
                           assertion_text="Model A", source_excerpt=post.text,
                           extraction_version="pulse-classified-findings-v1:" + "b" * 64,
                           source_archive_id=archive.pk, release_maturity_id=maturity.pk)
        PostBrandProduct.objects.create(post=post, brand=brand, product_id=first_result["product_id"],
                                        observed_name="Model A", source_evidence={}, verification_policy_version="test")
        assert resolve_saved_release_finding(claim_id=anchor.pk)["status"] == "matched"
    latest = Post.objects.create(tweet_id="popular-latest", author=account, text="We released Model A")
    item = finding(key="e" * 64)
    item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                               "source_excerpt": latest.text, "observed_name": None}
    saved = persist_classified_release_findings(source={"kind": "post", "id": latest.pk}, revision_id="d" * 64,
                                               content_fingerprint="f" * 64, extraction_version="test", findings=[item])
    anchor_id = saved["findings"][0]["anchor_claim_id"]
    assert resolve_saved_release_finding(claim_id=anchor_id)["status"] == "matched"
    def reconcile():
        close_old_connections()
        try:
            return reconcile_product_release_events(claim_id=anchor_id, candidate_limit=10, claim_limit=50, max_merges=1, max_seconds=5)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reconcile(), range(2)))
    assert sum(result["status"] == "merged" for result in results) == 1
    assert all(result["status"] in {"merged", "matched", "busy"} for result in results)
    assert dossier.sources.count() == 53


@pytest.mark.parametrize("older_backfill,oversized", [(False, False), (True, False), (False, True)])
def test_release_association_progresses_with_small_pages_and_older_backfill(older_backfill, oversized):
    from datetime import timedelta

    from django.utils import timezone

    from core.models import Account, Brand, BrandAccount, EventDossier, Post, Role
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="backfill-event-brand")
    account = Account.objects.create(author_id="123456765", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    outcomes = []
    for number in (1, 2, 3):
        post = Post.objects.create(tweet_id=f"backfill-event-{number}", author=account, text="We released Model A",
                                   fetched_at=timezone.now() - timedelta(days=1) if older_backfill and number == 3 else timezone.now())
        item = finding(key=str(number) * 64)
        item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                                   "source_excerpt": post.text, "observed_name": None}
        saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                                   content_fingerprint="c" * 64, extraction_version="test", findings=[item])
        outcomes.append(resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"]))
        if oversized and number == 1:
            from core.event_dossiers import add_claim
            from core.models import EventDossierClaim

            anchor = EventDossierClaim.objects.get(pk=outcomes[0]["anchor_claim_id"])
            for extra in range(10):
                add_claim(anchor.event_dossier_source_id, claim_kind="release_context", scope_key=f"extra-{extra}",
                          assertion_text="Additional evidence", source_excerpt=post.text, extraction_version="test")
        if older_backfill and number == 2:
            first_merge = reconcile_product_release_events(claim_id=outcomes[1]["anchor_claim_id"], candidate_limit=2, claim_limit=50,
                                                           max_merges=1, max_seconds=5)
            assert first_merge["status"] == "merged"
    for _ in range(3):
        result = reconcile_product_release_events(claim_id=outcomes[2]["anchor_claim_id"], candidate_limit=2, claim_limit=10,
                                                  max_merges=1, max_seconds=5)
        if not result["more_remaining"]:
            break
    assert EventDossier.objects.filter(merged_into__isnull=True).count() == (2 if oversized else 1)
    if oversized:
        assert result["status"] == "candidate_limit" and result["more_remaining"]
        blocked = reconcile_product_release_events(claim_id=outcomes[0]["anchor_claim_id"], candidate_limit=2,
                                                   claim_limit=10, max_merges=1, max_seconds=5)
        assert blocked["status"] == "candidate_limit"
    else:
        assert EventDossier.objects.get(merged_into__isnull=True).sources.count() == 3


@pytest.mark.parametrize(
    "variant", ["unknown_issuer", "wrong_owner", "quoted", "existing_name_only"]
)
def test_uncertain_issuer_or_existing_name_never_creates_product(variant):
    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="not-necessarily-owner")
    account = Account.objects.create(author_id="123456788", handle="creator")
    if variant != "wrong_owner":
        BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(
        tweet_id=f"unqualified-{variant}",
        author=account,
        text="We released Model A",
        is_quote=(variant == "quoted"),
    )
    if variant == "existing_name_only":
        Product.objects.create(display_name="Model A", brand=brand)
    item = finding()
    item["issuer_evidence"] = (
        None
        if variant == "unknown_issuer"
        else {
            "relation": "source_author",
            "source_locator": None,
            "source_excerpt": "We released Model A",
            "observed_name": None,
        }
    )
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "unresolved" and outcome["product_key"] is None
    assert Product.objects.count() == (1 if variant == "existing_name_only" else 0)


@pytest.mark.parametrize(
    "statement", [
        "We will release Model A",
        "We never released Model A",
        "Our team tried the newly released Model A",
        "We celebrated when Acme released Model A",
    ]
)
def test_statement_without_direct_owned_release_cannot_create_product(statement):
    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="future-brand")
    account = Account.objects.create(author_id="123456785", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(tweet_id="future-test", author=account, text=statement)
    item = finding()
    item["issuer_evidence"] = {
        "relation": "source_author",
        "source_locator": None,
        "source_excerpt": statement,
        "observed_name": None,
    }
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "unresolved" and not Product.objects.exists()


def test_concurrent_official_mentions_converge_without_duplicate_product():
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="concurrent-brand")
    account = Account.objects.create(author_id="123456784", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    anchors = []
    for number in (1, 2):
        post = Post.objects.create(
            tweet_id=f"concurrent-post-{number}",
            author=account,
            text="We released Model A",
        )
        item = finding(key=str(number) * 64)
        item["issuer_evidence"] = {
            "relation": "source_author",
            "source_locator": None,
            "source_excerpt": "We released Model A",
            "observed_name": None,
        }
        result = persist_classified_release_findings(
            source={"kind": "post", "id": post.pk},
            revision_id="b" * 64,
            content_fingerprint="c" * 64,
            extraction_version="test",
            findings=[item],
        )
        anchors.append(result["findings"][0]["anchor_claim_id"])

    def resolve(anchor):
        close_old_connections()
        try:
            return resolve_saved_release_finding(claim_id=anchor)
        except ValueError as error:
            if "busy" not in str(error):
                raise
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(resolve, anchors))
    results = [
        result or resolve_saved_release_finding(claim_id=anchor)
        for result, anchor in zip(results, anchors, strict=True)
    ]
    assert {result["status"] for result in results} <= {"created", "matched"}
    assert len({result["product_key"] for result in results}) == 1
    assert Product.objects.count() == 1


def test_known_attributed_alias_blocks_duplicate_creation():
    from core.measurement_attribution import record_attribution
    from core.measurement_taxonomy import configure_taxonomy, resolve_subject_id
    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="alias-brand")
    account = Account.objects.create(author_id="123456783", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    from core.models import ProductType

    product = Product.objects.create(
        display_name="Existing Product",
        brand=brand,
        product_type=ProductType.objects.get(code="model-llm"),
    )
    taxonomy = configure_taxonomy(
        {
            "reviewed_by": "test",
            "subjects": [{"kind": "product", "key": str(product.product_key)}],
            "qualifications": {str(product.product_key): {"reason": "test"}},
        }
    )
    old_post = Post.objects.create(tweet_id="old-alias-post", text="Model A")
    record_attribution(
        taxonomy,
        old_post,
        resolve_subject_id("product", str(product.product_key)),
        observed_name="Model A",
        policy_version="test",
        evidence={"reviewed_by": "test", "span_start": 0, "span_end": 7},
    )
    post = Post.objects.create(
        tweet_id="new-alias-post", author=account, text="We released Model A"
    )
    item = finding()
    item["issuer_evidence"] = {
        "relation": "source_author",
        "source_locator": None,
        "source_excerpt": "We released Model A",
        "observed_name": None,
    }
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "unresolved" and Product.objects.count() == 1


def test_variant_not_in_observed_name_remains_unresolved():
    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="variant-owner")
    account = Account.objects.create(author_id="123456782", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(
        tweet_id="variant-post", author=account, text="We released Model A 8B"
    )
    item = finding()
    item["variant"] = "8B"
    item["issuer_evidence"] = {
        "relation": "source_author",
        "source_locator": None,
        "source_excerpt": "We released Model A 8B",
        "observed_name": None,
    }
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "unresolved" and not Product.objects.exists()


@pytest.mark.parametrize("whole_excerpt", [False, True])
def test_attributed_quote_is_not_source_author_creation(whole_excerpt):
    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="quoted-publisher")
    account = Account.objects.create(author_id="123456781", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(
        tweet_id="quoted-source", author=account, text='They said "We released Model A"'
    )
    item = finding()
    item["issuer_evidence"] = {
        "relation": "source_author",
        "source_locator": None,
        "source_excerpt": post.text if whole_excerpt else "We released Model A",
        "observed_name": None,
    }
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk},
        revision_id="b" * 64,
        content_fingerprint="c" * 64,
        extraction_version="test",
        findings=[item],
    )
    outcome = resolve_saved_release_finding(
        claim_id=result["findings"][0]["anchor_claim_id"]
    )
    assert outcome["status"] == "unresolved" and not Product.objects.exists()


def test_conflicting_attributed_brand_remains_unresolved():
    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    owner = Brand.objects.create(nickname="actual-owner")
    other = Brand.objects.create(nickname="other-brand")
    account = Account.objects.create(author_id="123456780", handle="creator")
    BrandAccount.objects.create(brand=owner, account=account, role=role)
    post = Post.objects.create(tweet_id="conflicting-brand", author=account, text="We released Model A")
    item = finding()
    item["brand_id"] = other.pk
    item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                               "source_excerpt": post.text, "observed_name": None}
    result = persist_classified_release_findings(
        source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
        content_fingerprint="c" * 64, extraction_version="test", findings=[item],
    )
    assert resolve_saved_release_finding(claim_id=result["findings"][0]["anchor_claim_id"])["status"] == "unresolved"
    assert not Product.objects.exists()


def test_saved_anchor_rejects_packet_from_a_different_source():
    import json

    from core.collection_capture import archive_document
    from core.event_dossiers import (
        add_claim,
        attach_source,
        create_dossier,
        identity_key,
    )
    from core.models import Post
    from core.product_identity import resolve_saved_release_finding
    from tests.test_pulse_finding_persistence import finding

    post = Post.objects.create(tweet_id="anchor-source", text="Released Model A")
    event = create_dossier(
        event_kind="product_release", identity_key=identity_key("test", "wrong-source")
    )
    source = attach_source(event.pk, post_id=post.pk)
    packet = {
        "schema": "pulse-release-intake-v1",
        "source": {"kind": "post", "id": "another"},
        "revision_id": "b" * 64,
        "content_fingerprint": "c" * 64,
        "extraction_version": "test",
        "finding": finding(),
    }
    archive = archive_document(
        json.dumps(packet).encode(),
        encoding="selected-json-canonical-v1",
        capture_kind="product_release_intake",
    )
    claim = add_claim(
        source.pk,
        claim_kind="release_signal",
        scope_key="pulse-finding-v1:" + "a" * 64,
        assertion_text="Released Model A",
        source_excerpt=post.text,
        extraction_version="pulse-classified-findings-v1:" + "b" * 64,
        source_archive_id=archive.pk,
    )
    with pytest.raises(ValueError, match="source|archive"):
        resolve_saved_release_finding(claim_id=claim.pk)


def test_shared_finder_creates_by_existing_stable_key_only_once():
    from uuid import uuid4

    from core.product_identity import find_or_create_product

    key = uuid4()
    first, created = find_or_create_product(
        product_key=key, defaults={"display_name": "Source project"}
    )
    again, repeated = find_or_create_product(
        product_key=key, defaults={"display_name": "Other name"}
    )
    assert created and not repeated and first.pk == again.pk
    assert again.display_name == "Source project"
    with pytest.raises(ValueError):
        find_or_create_product(defaults={"display_name": "No authority"})


def test_missing_version_does_not_bridge_conflicting_explicit_versions():
    from core.models import Account, Brand, BrandAccount, EventDossier, Post, Role
    from core.product_identity import (
        reconcile_product_release_events,
        resolve_saved_release_finding,
    )
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key='official')
    brand = Brand.objects.create(nickname='explicit-conflicts')
    account = Account.objects.create(author_id='123456768', handle='creator')
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    outcomes = []
    for number, version in ((1, None), (2, 'A'), (3, 'B')):
        post = Post.objects.create(tweet_id=f'explicit-conflict-{number}', author=account,
                                   text='We released Model A B')
        item = finding(key=str(number) * 64)
        item['observed_name'] = 'Model A B'
        item['version'] = version
        item['assertions'][0]['source_excerpt'] = post.text
        item['assertions'][0]['assertion_text'] = post.text
        item['issuer_evidence'] = {'relation': 'source_author', 'source_locator': None,
                                   'source_excerpt': post.text, 'observed_name': None}
        saved = persist_classified_release_findings(source={'kind': 'post', 'id': post.pk}, revision_id='b' * 64,
                                                   content_fingerprint='c' * 64, extraction_version='test', findings=[item])
        outcomes.append(resolve_saved_release_finding(claim_id=saved['findings'][0]['anchor_claim_id']))
    assert len({outcome['product_key'] for outcome in outcomes}) == 1
    for outcome in outcomes:
        result = reconcile_product_release_events(claim_id=outcome['anchor_claim_id'], candidate_limit=10,
                                                  claim_limit=50, max_merges=2, max_seconds=5)
        assert not result['merged_ids']
    assert EventDossier.objects.filter(merged_into__isnull=True).count() == 3


def test_explicit_successor_joins_families_and_preserves_history():
    from types import SimpleNamespace
    from uuid import uuid4

    from django.db import transaction
    from django.db.models import F

    from core.models import Brand, ProductGroupMembership, ProductType
    from core.product_identity import (
        _ensure_model_family,
        _join_reported_successor_family,
    )

    brand = Brand.objects.create(nickname='family-successors')
    model_type = ProductType.objects.get(code='model-llm')
    first = Product.objects.create(display_name='Model One', brand=brand, product_type=model_type)
    second = Product.objects.create(display_name='Model Two', brand=brand, product_type=model_type)
    claim = SimpleNamespace(pk=uuid4())
    relation = {'relationship_kind': 'new_version', 'parent_observed_name': 'Model One',
                'source_excerpt': 'Model Two is a new version of Model One.', 'source_locator': None}
    with transaction.atomic():
        first_group = _ensure_model_family(first, {'observed_name': 'Model One'}, claim)
        second_group = _ensure_model_family(second, {'observed_name': 'Model Two'}, claim)
        historical_count = ProductGroupMembership.objects.count()
        chosen = _join_reported_successor_family(second, {'lineage_evidence': [relation]}, claim)
        assert chosen == first_group
        assert _join_reported_successor_family(second, {'lineage_evidence': [relation]}, claim) == first_group
    current = ProductGroupMembership.objects.filter(
        product__in=[first, second], membership_status='included',
        taxonomy_version_id=F('group__rule_taxonomy_version_id'),
    )
    assert current.count() == 2
    assert set(current.values_list('group_id', flat=True)) == {first_group}
    assert current.first().group.name == 'Model'
    assert ProductGroupMembership.objects.count() > historical_count
    assert ProductGroupMembership.objects.filter(group_id=second_group, product=second).exists()


def test_finetune_alone_does_not_join_same_brand_families():
    from types import SimpleNamespace
    from uuid import uuid4

    from django.db import transaction

    from core.models import Brand, ProductType
    from core.product_identity import (
        _ensure_model_family,
        _join_reported_successor_family,
    )

    brand = Brand.objects.create(nickname='family-finetunes')
    model_type = ProductType.objects.get(code='model-llm')
    first = Product.objects.create(display_name='Model Base', brand=brand, product_type=model_type)
    second = Product.objects.create(display_name='Different Line', brand=brand, product_type=model_type)
    claim = SimpleNamespace(pk=uuid4())
    relation = {'relationship_kind': 'finetune', 'parent_observed_name': 'Model Base',
                'source_excerpt': 'Different Line is fine-tuned from Model Base.', 'source_locator': None}
    with transaction.atomic():
        first_group = _ensure_model_family(first, {'observed_name': 'Model Base'}, claim)
        second_group = _ensure_model_family(second, {'observed_name': 'Different Line'}, claim)
        assert _join_reported_successor_family(second, {'lineage_evidence': [relation]}, claim) is None
    assert first_group != second_group


def test_explicit_family_name_updates_same_family_and_preserves_old_snapshot():
    from types import SimpleNamespace
    from uuid import uuid4

    from django.db import transaction

    from core.models import Brand, ProductGroup, ProductType
    from core.product_identity import _apply_reported_family_name, _ensure_model_family

    brand = Brand.objects.create(nickname='named-family-brand')
    model_type = ProductType.objects.get(code='model-llm')
    product = Product.objects.create(display_name='Atlas-7B', brand=brand, product_type=model_type)
    claim = SimpleNamespace(pk=uuid4())
    evidence = {'name': 'Atlas', 'source_excerpt': 'Atlas-7B is part of the Atlas family.', 'source_locator': None}
    with transaction.atomic():
        group_id = _ensure_model_family(product, {'observed_name': 'Atlas-7B'}, claim)
        group = ProductGroup.objects.get(pk=group_id)
        old_version = group.rule_taxonomy_version
        assert _apply_reported_family_name(product, evidence, claim) == group_id
        assert _apply_reported_family_name(product, evidence, claim) == group_id
    group.refresh_from_db()
    assert group.name == 'Atlas'
    assert old_version.snapshot['groups'][group.group_key]['name'] == 'Atlas'
    assert group.rule_taxonomy_version.snapshot['groups'][group.group_key]['evidence']['method'] == 'publisher_named'


def test_publisher_named_family_reuses_named_line_but_not_a_provisional_name():
    from types import SimpleNamespace
    from uuid import uuid4

    from django.db import transaction
    from django.db.models import F

    from core.models import Brand, ProductGroupMembership, ProductType
    from core.product_identity import _apply_reported_family_name, _ensure_model_family

    brand = Brand.objects.create(nickname='named-family-collisions')
    model_type = ProductType.objects.get(code='model-llm')
    unrelated = Product.objects.create(display_name='Atlas', brand=brand, product_type=model_type)
    first = Product.objects.create(display_name='Atlas One', brand=brand, product_type=model_type)
    second = Product.objects.create(display_name='Atlas Two', brand=brand, product_type=model_type)
    claim = SimpleNamespace(pk=uuid4())
    with transaction.atomic():
        unrelated_family = _ensure_model_family(unrelated, {'observed_name': 'Atlas'}, claim)
        first_family = _ensure_model_family(first, {'observed_name': 'Atlas One'}, claim)
        second_family = _ensure_model_family(second, {'observed_name': 'Atlas Two'}, claim)
        named_first = {'name': 'Atlas', 'source_excerpt': 'Atlas One is in the Atlas family.', 'source_locator': None}
        named_second = {'name': 'Atlas', 'source_excerpt': 'Atlas Two is in the Atlas family.', 'source_locator': None}
        assert _apply_reported_family_name(first, named_first, claim) == first_family
        assert _apply_reported_family_name(second, named_second, claim) == first_family
    memberships = ProductGroupMembership.objects.filter(
        product__in=[unrelated, first, second], membership_status='included',
        taxonomy_version_id=F('group__rule_taxonomy_version_id'),
    )
    assert memberships.get(product=unrelated).group_id == unrelated_family
    assert memberships.get(product=first).group_id == memberships.get(product=second).group_id == first_family
    assert first_family != unrelated_family and second_family != first_family


@pytest.mark.parametrize(('name', 'expected'), [
    ('Model One', 'Model'),
    ('Qwen2.5-Math-7B', 'Qwen2.5-Math'),
    ('Qwen3.5-0.8B', 'Qwen3.5'),
    ('BotPsy-0.8B', 'BotPsy'),
    ('DeepSeek Coder 33B Instruct', 'DeepSeek Coder'),
    ('Llama', 'Llama'),
])
def test_single_model_gets_a_provisional_family_name(name, expected):
    from types import SimpleNamespace
    from uuid import uuid4

    from django.db import transaction

    from core.models import Brand, ProductGroup, ProductType
    from core.product_identity import _ensure_model_family

    brand = Brand.objects.create(nickname='provisional-family')
    product = Product.objects.create(display_name=name, brand=brand, product_type=ProductType.objects.get(code='model-llm'))
    with transaction.atomic():
        group_id = _ensure_model_family(product, {'observed_name': name}, SimpleNamespace(pk=uuid4()))
    assert ProductGroup.objects.get(pk=group_id).name == expected
