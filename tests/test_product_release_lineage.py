import pytest

from core.models import ProductRelationship, TaxonomyVersion

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _two_saved_findings(*, lineage_excerpt="Model 5 succeeds Model 4", post_lineage=None, parent_name="Model 4"):
    from core.models import Account, Brand, BrandAccount, Post, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="lineage-product-brand")
    account = Account.objects.create(author_id="123456764", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    outcomes = []
    for number in (4, 5):
        name = f"Model {number}"
        text = f"We released {name}" + (". " + (post_lineage or lineage_excerpt) if number == 5 else "")
        post = Post.objects.create(tweet_id=f"lineage-post-{number}", author=account, text=text)
        item = finding(name=name, key=str(number) * 64)
        item["assertions"][0].update(assertion_text=text, source_excerpt=text)
        item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                                   "source_excerpt": f"We released {name}", "observed_name": None}
        if number == 5:
            item["lineage_evidence"] = [{"relationship_kind": "new_version", "parent_observed_name": parent_name,
                                         "source_excerpt": lineage_excerpt, "source_locator": None}]
        saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                                   content_fingerprint="c" * 64, extraction_version="test", findings=[item])
        outcomes.append(resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"]))
    return outcomes


def test_explicit_lineage_reuses_qualified_products_and_compact_taxonomy():
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings()
    baseline_versions = TaxonomyVersion.objects.count()
    assert parent["product_key"] != child["product_key"]
    result = register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                        relation_index=0, basis_version_id=None, max_subjects=2, max_seconds=5)
    assert result["status"] == "created"
    edge = ProductRelationship.objects.get(pk=result["relationship_id"])
    assert str(edge.parent_product.product_key) == parent["product_key"]
    assert str(edge.child_product.product_key) == child["product_key"]
    assert edge.product_relationship_type.code == "new_version"
    assert edge.evidence["source_excerpt"] == "Model 5 succeeds Model 4"
    assert len(edge.taxonomy_version.snapshot["products"]) == 2
    assert register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                      relation_index=0, basis_version_id=None, max_subjects=2, max_seconds=5)["status"] == "matched_replay"
    assert ProductRelationship.objects.count() == 1
    assert TaxonomyVersion.objects.count() == baseline_versions + 1


def test_lineage_does_not_match_wrong_parent_or_unverified_excerpt():
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings(lineage_excerpt="Model 5 succeeds Model 4 (invented)",
                                        post_lineage="Model 5 succeeds Model 4")
    assert register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                      relation_index=0, basis_version_id=None, max_subjects=2, max_seconds=5)["status"] == "unresolved"
    assert not ProductRelationship.objects.exists()


@pytest.mark.parametrize("excerpt", ["Model 5 does not succeed Model 4", "We compared Model 5 with Model 4",
                                     "Model 5 succeeds Model 4.1", "Model 5 succeeds Model 4-32B",
                                     "It is not true that Model 5 succeeds Model 4",
                                     "Reportedly Model 5 succeeds Model 4",
                                     "If Model 5 succeeds Model 4, we will publish benchmarks",
                                     "Model 5 succeeds Model 4?",
                                     "I don't believe Model 5 succeeds Model 4"])
def test_names_alone_or_negation_never_create_a_relationship(excerpt):
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings(lineage_excerpt=excerpt)
    result = register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                        relation_index=0, basis_version_id=None, max_subjects=2, max_seconds=5)
    assert result["status"] == "unresolved"
    assert not ProductRelationship.objects.exists()


def test_explicit_basis_keeps_conflicting_historical_taxonomy_versions_separate():
    from core.measurement_taxonomy import configure_taxonomy
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings()
    baseline_versions = TaxonomyVersion.objects.count()
    args = {"child_claim_id": child["anchor_claim_id"], "parent_claim_id": parent["anchor_claim_id"],
            "relation_index": 0, "basis_version_id": None, "max_subjects": 2, "max_seconds": 5}
    first = register_qualified_lineage(**args)
    alternative = configure_taxonomy({
        "reviewed_by": "fixture", "subjects": [{"kind": "product", "key": outcome["product_key"]} for outcome in (parent, child)],
        "relationships": [{"parent": parent["product_key"], "child": child["product_key"],
                           "type": "quantized", "evidence": {"source": "different historical snapshot"}}],
    })
    assert register_qualified_lineage(**{**args, "basis_version_id": first["taxonomy_version_id"]})["status"] == "matched"
    assert register_qualified_lineage(**{**args, "basis_version_id": alternative.pk})["status"] == "conflict"
    assert TaxonomyVersion.objects.count() == baseline_versions + 2


def test_changed_product_does_not_rewrite_frozen_basis_data():
    from core.measurement_taxonomy import configure_taxonomy
    from core.models import Product
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings()
    baseline_versions = TaxonomyVersion.objects.count()
    basis = configure_taxonomy({"reviewed_by": "fixture", "subjects": [{"kind": "product", "key": parent["product_key"]}]})
    Product.objects.filter(pk=parent["product_id"]).update(display_name="Renamed after snapshot")
    result = register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                        relation_index=0, basis_version_id=basis.pk, max_subjects=2, max_seconds=5)
    assert result["status"] == "basis_drift"
    assert TaxonomyVersion.objects.count() == baseline_versions + 1 and not ProductRelationship.objects.exists()


def test_basis_drift_between_validation_and_write_rolls_back(monkeypatch):
    import core.measurement_taxonomy as taxonomy
    from core.models import Product
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings()
    baseline_versions = TaxonomyVersion.objects.count()
    basis = taxonomy.configure_taxonomy({"reviewed_by": "fixture", "subjects": [{"kind": "product", "key": parent["product_key"]}]})
    original = taxonomy.configure_taxonomy

    def changed_between_checks(spec):
        Product.objects.filter(pk=parent["product_id"]).update(display_name="Concurrent change")
        return original(spec)

    monkeypatch.setattr(taxonomy, "configure_taxonomy", changed_between_checks)
    result = register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                        relation_index=0, basis_version_id=basis.pk, max_subjects=2, max_seconds=5)
    assert result["status"] == "basis_drift"
    assert Product.objects.get(pk=parent["product_id"]).display_name == "Model 4"
    assert TaxonomyVersion.objects.count() == baseline_versions + 1 and not ProductRelationship.objects.exists()


def test_group_basis_is_not_mutated_by_lineage_writer():
    from core.measurement_taxonomy import configure_taxonomy
    from core.models import ProductGroup
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings()
    basis = configure_taxonomy({
        "reviewed_by": "fixture", "subjects": [{"kind": "product", "key": outcome["product_key"]} for outcome in (parent, child)],
        "groups": [{"key": "lineage-guard-family", "name": "Guard family", "include": [parent["product_key"]]}],
        "relationships": [{"parent": parent["product_key"], "child": child["product_key"],
                           "type": "new_version", "evidence": {"source": "existing"}}],
    })
    group = ProductGroup.objects.get(group_key="lineage-guard-family")
    result = register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                        relation_index=0, basis_version_id=basis.pk, max_subjects=2, max_seconds=5)
    assert result["status"] == "unsupported_basis"
    group.refresh_from_db()
    assert group.rule_taxonomy_version_id == basis.pk and ProductRelationship.objects.count() == 1


def test_explicit_subject_budget_leaves_lineage_unwritten_when_too_small():
    from core.product_release_lineage import register_qualified_lineage

    parent, child = _two_saved_findings()
    baseline_versions = TaxonomyVersion.objects.count()
    result = register_qualified_lineage(child_claim_id=child["anchor_claim_id"], parent_claim_id=parent["anchor_claim_id"],
                                        relation_index=0, basis_version_id=None, max_subjects=1, max_seconds=5)
    assert result["status"] == "subject_limit"
    assert TaxonomyVersion.objects.count() == baseline_versions and not ProductRelationship.objects.exists()


def test_bounded_parent_discovery_uses_evidence_and_replays_without_growth():
    from core.models import Product
    from core.product_release_lineage import resolve_reported_lineage

    parent, child = _two_saved_findings()
    baseline_versions = TaxonomyVersion.objects.count()
    original = Product.objects.get(pk=parent["product_id"])
    Product.objects.create(display_name="Model 4", brand=original.brand)
    args = {"child_claim_id": child["anchor_claim_id"], "relation_index": 0,
            "basis_version_id": None, "max_candidates": 5, "max_subjects": 2, "max_seconds": 5}
    first = resolve_reported_lineage(**args)
    assert first["status"] == "created" and first["retryable"] is False
    assert resolve_reported_lineage(**args)["status"] == "matched_replay"
    assert ProductRelationship.objects.count() == 1
    assert TaxonomyVersion.objects.count() == baseline_versions + 1


def test_parent_discovery_keeps_conflicting_source_backed_products_unresolved():
    from core.models import Post, PostBrandProduct, Product
    from core.product_release_lineage import resolve_reported_lineage

    parent, child = _two_saved_findings()
    original = Product.objects.get(pk=parent["product_id"])
    other = Product.objects.create(display_name="Model 4", brand=original.brand)
    post = Post.objects.create(tweet_id="lineage-ambiguous-parent", text="Model 4")
    PostBrandProduct.objects.create(post=post, brand=original.brand, product=other, observed_name="Model 4",
                                    source_evidence={}, verification_policy_version="test")
    result = resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0,
                                      basis_version_id=None, max_candidates=5, max_subjects=2, max_seconds=5)
    assert result == {"status": "ambiguous", "retryable": False}
    assert not ProductRelationship.objects.exists()


def test_parent_discovery_skips_rejected_evidence_and_uses_later_valid_source():
    from core.models import Post, PostBrandProduct, Product
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_lineage import resolve_reported_lineage
    from core.product_release_pipeline import record_intake_decision
    from tests.test_pulse_finding_persistence import finding

    parent, child = _two_saved_findings()
    record_intake_decision(parent["dossier_id"], claim_id=parent["anchor_claim_id"], outcome="non_release",
                           actor="test", reason="Rejected older evidence")
    product = Product.objects.get(pk=parent["product_id"])
    post = Post.objects.create(tweet_id="lineage-valid-parent", text="Model 4")
    PostBrandProduct.objects.create(post=post, brand=product.brand, product=product, observed_name="Model 4",
                                    source_evidence={}, verification_policy_version="test")
    item = finding(name="Model 4")
    item["assertions"][0].update(assertion_text=post.text, source_excerpt=post.text)
    saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="d" * 64,
                                               content_fingerprint="e" * 64, extraction_version="test", findings=[item])
    assert resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"])["status"] == "matched"
    result = resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0,
                                      basis_version_id=None, max_candidates=5, max_subjects=2, max_seconds=5)
    assert result["status"] == "created"


def test_parent_discovery_accepts_current_confirmed_legacy_review():
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
    from core.models import Account, Brand, BrandAccount, Post, Product, Role
    from core.product_identity import resolve_saved_release_finding
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_lineage import resolve_reported_lineage
    from tests.product_factory import product_type_fields
    from tests.test_pulse_finding_persistence import finding

    brand = Brand.objects.create(nickname="legacy-lineage-brand")
    parent = Product.objects.create(display_name="Model 4", brand=brand, **product_type_fields(Product, "model-llm"))
    old_post = Post.objects.create(tweet_id="legacy-lineage-parent", text="Model 4 released")
    dossier = create_dossier(event_kind="product_release", identity_key=identity_key("test", "legacy-lineage"))
    source = attach_source(dossier.pk, post_id=old_post.pk)
    claim = add_claim(source.pk, claim_kind="announcement", scope_key="legacy", assertion_text=old_post.text,
                      source_excerpt=old_post.text, extraction_version="test")
    complete_review(dossier.pk, expected_current_review_id=None, display_title="Model 4", review_state="confirmed",
                    evidence_cutoff_at=timezone.now(), method_version="test", actor="test", reason="Verified",
                    claims=[ClaimDecision(claim.pk, "accepted", "Source")],
                    product_release=ProductReleaseInput(observed_name="Model 4", product_key=parent.product_key))
    role, _ = Role.objects.get_or_create(key="official")
    account = Account.objects.create(author_id="123456763", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(tweet_id="legacy-lineage-child", author=account, text="We released Model 5. Model 5 succeeds Model 4")
    item = finding(name="Model 5")
    item["assertions"][0].update(assertion_text=post.text, source_excerpt=post.text)
    item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                               "source_excerpt": "We released Model 5", "observed_name": None}
    item["lineage_evidence"] = [{"relationship_kind": "new_version", "parent_observed_name": "Model 4",
                                 "source_excerpt": "Model 5 succeeds Model 4", "source_locator": None}]
    saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                               content_fingerprint="c" * 64, extraction_version="test", findings=[item])
    child = resolve_saved_release_finding(claim_id=saved["findings"][0]["anchor_claim_id"])
    result = resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0,
                                      basis_version_id=None, max_candidates=5, max_subjects=2, max_seconds=5)
    assert result["status"] == "created"
    assert ProductRelationship.objects.get().parent_product_id == parent.product_key


def test_parent_discovery_skips_reviewed_anchor_with_conflicting_version():
    from django.utils import timezone

    from core.event_dossiers import (
        ClaimDecision,
        ProductReleaseInput,
        add_claim,
        attach_source,
        complete_review,
    )
    from core.models import EventDossierClaim, Post, Product
    from core.product_release_lineage import resolve_reported_lineage

    parent, child = _two_saved_findings()
    anchor = EventDossierClaim.objects.get(pk=parent["anchor_claim_id"])
    post = Post.objects.create(tweet_id="lineage-later-reviewed-parent", text="Model 4 released")
    source = attach_source(parent["dossier_id"], post_id=post.pk)
    legacy = add_claim(source.pk, claim_kind="announcement", scope_key="legacy", assertion_text=post.text,
                       source_excerpt=post.text, extraction_version="test")
    product = Product.objects.get(pk=parent["product_id"])
    complete_review(parent["dossier_id"], expected_current_review_id=None, display_title="Model 4",
                    review_state="confirmed", evidence_cutoff_at=timezone.now(), method_version="test", actor="test",
                    reason="Verified", claims=[ClaimDecision(anchor.pk, "accepted", "Source"), ClaimDecision(legacy.pk, "accepted", "Source")],
                    product_release=ProductReleaseInput(observed_name="Model 4", product_key=product.product_key,
                                                        version_label="1"))
    result = resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0,
                                      basis_version_id=None, max_candidates=5, max_subjects=2, max_seconds=5)
    assert result["status"] == "created"
    assert ProductRelationship.objects.get().parent_product_id == product.product_key


def test_merged_obsolete_review_does_not_create_false_parent_ambiguity():
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
    from core.models import Post, Product
    from core.product_release_lineage import resolve_reported_lineage
    from core.product_release_pipeline import merge_dossiers

    parent, child = _two_saved_findings()
    post = Post.objects.create(tweet_id="obsolete-lineage-review", text="Model 4")
    old = create_dossier(event_kind="product_release", identity_key=identity_key("test", "obsolete-parent"))
    source = attach_source(old.pk, post_id=post.pk)
    claim = add_claim(source.pk, claim_kind="announcement", scope_key="legacy", assertion_text=post.text,
                      source_excerpt=post.text, extraction_version="test")
    other = Product.objects.create(display_name="Other Model 4")
    complete_review(old.pk, expected_current_review_id=None, display_title="Model 4", review_state="confirmed",
                    evidence_cutoff_at=timezone.now(), method_version="test", actor="test", reason="Historical",
                    claims=[ClaimDecision(claim.pk, "accepted", "Source")],
                    product_release=ProductReleaseInput(observed_name="Model 4", product_key=other.product_key))
    target = create_dossier(event_kind="product_release", identity_key=identity_key("test", "obsolete-target"))
    merge_dossiers(old.pk, target.pk, actor="test", reason="Historical reconciliation")
    result = resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0,
                                      basis_version_id=None, max_candidates=5, max_subjects=2, max_seconds=5)
    assert result["status"] == "created"
    assert str(ProductRelationship.objects.get().parent_product.product_key) == parent["product_key"]


def test_parent_changed_after_selection_is_retryable(monkeypatch):
    import core.product_release_lineage as lineage
    from core.product_release_pipeline import record_intake_decision

    parent, child = _two_saved_findings()
    original = lineage.register_qualified_lineage

    def parent_changes(**kwargs):
        record_intake_decision(parent["dossier_id"], claim_id=parent["anchor_claim_id"], outcome="non_release",
                               actor="test", reason="Changed after selection")
        return original(**kwargs)

    monkeypatch.setattr(lineage, "register_qualified_lineage", parent_changes)
    result = lineage.resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0,
                                              basis_version_id=None, max_candidates=5, max_subjects=2, max_seconds=5)
    assert result == {"status": "stale_parent", "retryable": True}
    assert not ProductRelationship.objects.exists()


def test_child_brand_changed_after_selection_is_retryable(monkeypatch):
    import core.product_release_lineage as lineage
    from core.models import Brand, Product

    _, child = _two_saved_findings()
    other_brand = Brand.objects.create(nickname="changed-child-brand")
    original = lineage.register_qualified_lineage

    def child_changes(**kwargs):
        Product.objects.filter(pk=child["product_id"]).update(brand=other_brand)
        return original(**kwargs)

    monkeypatch.setattr(lineage, "register_qualified_lineage", child_changes)
    result = lineage.resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0,
                                              basis_version_id=None, max_candidates=5, max_subjects=2, max_seconds=5)
    assert result == {"status": "stale_child", "retryable": True}
    assert not ProductRelationship.objects.exists()


def test_parent_name_evidence_lock_fails_fast_and_retries():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, transaction

    from core.product_identity_locks import lock_product_evidence_names
    from core.product_release_lineage import resolve_reported_lineage

    _, child = _two_saved_findings()
    held, release = Event(), Event()

    def hold_name():
        close_old_connections()
        try:
            with transaction.atomic():
                lock_product_evidence_names(["mOdEl 4"])
                held.set()
                release.wait(5)
        finally:
            close_old_connections()

    args = {"child_claim_id": child["anchor_claim_id"], "relation_index": 0,
            "basis_version_id": None, "max_candidates": 5, "max_subjects": 2, "max_seconds": 5}
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold_name)
        try:
            assert held.wait(3)
            assert resolve_reported_lineage(**args) == {"status": "busy", "retryable": True}
            assert not ProductRelationship.objects.exists()
        finally:
            release.set()
            future.result(timeout=5)
    assert resolve_reported_lineage(**args)["status"] == "created"


def test_review_cannot_publish_competing_name_while_selection_holds_lock():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, transaction
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
    from core.models import EventDossierReview, Post, Product
    from core.product_identity_locks import ProductNameBusy, lock_product_evidence_names

    post = Post.objects.create(tweet_id="name-lock-review", text="Model 4 released")
    event = create_dossier(event_kind="product_release", identity_key=identity_key("test", "name-lock"))
    source = attach_source(event.pk, post_id=post.pk)
    claim = add_claim(source.pk, claim_kind="announcement", scope_key="test", assertion_text=post.text,
                      source_excerpt=post.text, extraction_version="test")
    product = Product.objects.create(display_name="Model 4")
    held, release = Event(), Event()

    def hold_name():
        close_old_connections()
        try:
            with transaction.atomic():
                lock_product_evidence_names(["MODEL 4"])
                held.set()
                release.wait(5)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold_name)
        try:
            assert held.wait(3)
            with pytest.raises(ProductNameBusy):
                complete_review(event.pk, expected_current_review_id=None, display_title="Model 4", review_state="confirmed",
                                evidence_cutoff_at=timezone.now(), method_version="test", actor="test", reason="Verified",
                                claims=[ClaimDecision(claim.pk, "accepted", "Source")],
                                product_release=ProductReleaseInput(observed_name="model 4", product_key=product.product_key))
            assert not EventDossierReview.objects.exists()
        finally:
            release.set()
            future.result(timeout=5)


def test_official_product_edge_cannot_race_name_selection():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, transaction

    from core.models import (
        Account,
        Brand,
        BrandAccount,
        Post,
        PostBrandProduct,
        Product,
        Role,
    )
    from core.product_identity import resolve_saved_release_finding
    from core.product_identity_locks import ProductNameBusy, lock_product_evidence_names
    from core.product_release_dossiers import persist_classified_release_findings
    from tests.test_pulse_finding_persistence import finding

    role, _ = Role.objects.get_or_create(key="official")
    brand = Brand.objects.create(nickname="locked-source-brand")
    account = Account.objects.create(author_id="123456762", handle="creator")
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(tweet_id="locked-source-post", author=account, text="We released Model 4")
    item = finding(name="Model 4")
    item["assertions"][0].update(assertion_text=post.text, source_excerpt=post.text)
    item["issuer_evidence"] = {"relation": "source_author", "source_locator": None,
                               "source_excerpt": post.text, "observed_name": None}
    saved = persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="b" * 64,
                                               content_fingerprint="c" * 64, extraction_version="test", findings=[item])
    anchor_id = saved["findings"][0]["anchor_claim_id"]
    held, release = Event(), Event()

    def hold_name():
        close_old_connections()
        try:
            with transaction.atomic():
                lock_product_evidence_names(["MODEL 4"])
                held.set()
                release.wait(5)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(hold_name)
        try:
            assert held.wait(3)
            with pytest.raises(ProductNameBusy):
                resolve_saved_release_finding(claim_id=anchor_id)
            assert not Product.objects.exists() and not PostBrandProduct.objects.exists()
        finally:
            release.set()
            future.result(timeout=5)
    assert resolve_saved_release_finding(claim_id=anchor_id)["status"] == "created"

def test_saved_finding_worker_records_lineage_once_and_replays(monkeypatch, tmp_path, settings):
    from core import classified_product_releases
    from core.models import EventDossierClaim, PostEnrichmentState
    from core.product_release_detection_queue import enqueue_posts
    from core.product_release_dossiers import _read_pulse_packet
    from monitor import pulse_control, pulse_processing

    parent, child = _two_saved_findings()
    baseline_versions = TaxonomyVersion.objects.count()
    anchor = EventDossierClaim.objects.get(pk=child["anchor_claim_id"])
    post = anchor.event_dossier_source.post
    PostEnrichmentState.objects.create(post=post)
    packet = _read_pulse_packet(anchor)
    monkeypatch.setattr(classified_product_releases, "read_publication_findings", lambda post_id: (
        {"anchor_claim_id": anchor.pk, "finding": packet["finding"]},
    ))
    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    enqueue_posts([post.pk])
    result = pulse_processing.process_saved_findings()
    assert result["processed"] == 1 and result["failed"] == 0
    edge = ProductRelationship.objects.get()
    assert str(edge.parent_product.product_key) == parent["product_key"]
    assert str(edge.child_product.product_key) == child["product_key"]
    enqueue_posts([post.pk])
    assert pulse_processing.process_saved_findings()["failed"] == 0
    assert ProductRelationship.objects.count() == 1
    assert TaxonomyVersion.objects.count() == baseline_versions + 1


def test_lineage_busy_preserves_queue_generation_and_retries_without_reclassification(monkeypatch, tmp_path, settings):
    from core import classified_product_releases, product_release_lineage
    from core.models import (
        EventDossierClaim,
        PostEnrichmentState,
        ProductReleaseDetectionState,
    )
    from core.product_release_detection_queue import enqueue_posts
    from core.product_release_dossiers import _read_pulse_packet
    from monitor import pulse_control, pulse_processing

    _parent, child = _two_saved_findings()
    anchor = EventDossierClaim.objects.get(pk=child["anchor_claim_id"])
    post = anchor.event_dossier_source.post
    PostEnrichmentState.objects.create(post=post)
    packet = _read_pulse_packet(anchor)
    monkeypatch.setattr(classified_product_releases, "read_publication_findings", lambda post_id: (
        {"anchor_claim_id": anchor.pk, "finding": packet["finding"]},
    ))
    settings.PULSE_CONTROL_DIRECTORY = str(tmp_path)
    pulse_control.initialize(directory=tmp_path, state="running", actor="fixture", reason="test")
    enqueue_posts([post.pk])
    ProductReleaseDetectionState.objects.filter(post=post).update(attempts=2)
    original = product_release_lineage.resolve_reported_lineage
    calls = []

    def busy_once(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {"status": "busy", "retryable": True}
        return original(**kwargs)

    monkeypatch.setattr(product_release_lineage, "resolve_reported_lineage", busy_once)
    first = pulse_processing.process_saved_findings()
    state = ProductReleaseDetectionState.objects.get(post=post)
    assert first["failed"] == 0 and first["association_pending"] == 1
    assert state.attempts == 2 and state.completed_at is None
    assert not ProductRelationship.objects.exists()
    second = pulse_processing.process_saved_findings()
    state.refresh_from_db()
    assert second["failed"] == 0 and state.attempts == 0 and state.completed_at is not None
    assert len(calls) == 2 and ProductRelationship.objects.count() == 1
