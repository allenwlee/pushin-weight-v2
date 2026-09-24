from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandCompany,
    BrandDiscoveryCandidate,
    Company,
    ModelRelease,
    Post,
    PostBrandProduct,
    Product,
    ProductVerificationProposal,
)
from core.product_verification import decide_product_proposal

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def _disable_ssl_redirect(settings):
    settings.SECURE_SSL_REDIRECT = False


def _proposal(
    key: str,
    *,
    brand: Brand | None = None,
    candidate: BrandDiscoveryCandidate | None = None,
    repo_id: str = "",
    hf_outcome: str = "deferred",
    release: ModelRelease | None = None,
    text: str = "Release <script>alert(1)</script>",
) -> ProductVerificationProposal:
    account = Account.objects.create(author_id=f"account-{key}", handle=f"handle-{key}")
    post = Post.objects.create(tweet_id=f"post-{key}", author=account, text=text)
    return ProductVerificationProposal.objects.create(
        proposal_key=key * 64,
        source_post=post,
        source_release=release,
        proposed_brand=brand,
        proposed_candidate=candidate,
        account=account,
        account_handle_snapshot=account.handle,
        observed_name="Model X",
        candidate_repo_id=repo_id,
        hf_outcome=hf_outcome,
        hf_evidence={"id": repo_id, "card": "<img src=x onerror=alert(1)>"},
        policy_version="product-x-hf-v1",
        rule_trace=["needs owner review"],
    )


def _staff_client(*, csrf: bool = False) -> Client:
    user = get_user_model().objects.create_user(
        username=f"staff-{get_user_model().objects.count()}",
        email="staff@example.com",
        password="test-password",
        is_staff=True,
    )
    client = Client(enforce_csrf_checks=csrf)
    client.force_login(user)
    return client


def _release(brand: Brand) -> ModelRelease:
    now = timezone.now()
    return ModelRelease.objects.create(
        brand=brand,
        observed_model_name="Model X",
        release_identity="r" * 64,
        first_seen_at=now,
        last_seen_at=now,
        extraction_version="test",
    )


def test_anonymous_redirected_and_ordinary_user_forbidden():
    assert Client().get(reverse("product_review")).status_code == 302
    user = get_user_model().objects.create_user(
        username="ordinary", email="ordinary@example.com", password="test-password"
    )
    client = Client()
    client.force_login(user)
    assert client.get(reverse("product_review")).status_code == 403


@override_settings(PRODUCT_REVIEW_OWNER_EMAILS=frozenset({"owner@example.com"}))
def test_owner_allowlist_can_view_but_other_signed_in_user_cannot():
    owner = get_user_model().objects.create_user(
        username="owner", email="OWNER@example.com", password="test-password"
    )
    client = Client()
    client.force_login(owner)
    assert client.get(reverse("product_review")).status_code == 200


def test_detail_escapes_hostile_source_and_renders_locale_copy():
    brand = Brand.objects.create(nickname="known")
    proposal = _proposal("a", brand=brand)
    client = _staff_client()
    response = client.get(reverse("product_review_detail", args=[proposal.pk]))
    body = response.content.decode()
    assert response.status_code == 200
    assert "box-sizing: border-box" in body
    assert "Release &lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "<script>alert(1)</script>" not in body
    client.cookies["pw_locale"] = "zh_hans"
    assert "产品审核" in client.get(reverse("product_review")).content.decode()


def test_csrf_and_forged_brand_fail_closed():
    brand = Brand.objects.create(nickname="known")
    proposal = _proposal("b", brand=brand)
    client = _staff_client(csrf=True)
    url = reverse("product_review_detail", args=[proposal.pk])
    payload = {
        "action": "approve",
        "reason": "Reviewed",
        "brand_id": "forged",
        "product_type": "llm-model",
        "catalog_mode": "x_only",
    }
    assert client.post(url, payload).status_code == 403
    token = client.get(url).cookies["csrftoken"].value
    assert client.post(url, payload, HTTP_X_CSRFTOKEN=token).status_code == 400
    assert not Product.objects.exists()


def test_x_only_approval_is_idempotent_links_source_and_makes_no_network(monkeypatch):
    monkeypatch.setattr(
        "core.product_verification.httpx.Client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("approval must not create an HTTP client")
        ),
    )
    brand = Brand.objects.create(nickname="known")
    proposal = _proposal("c", brand=brand)
    client = _staff_client()
    url = reverse("product_review_detail", args=[proposal.pk])
    payload = {
        "action": "approve",
        "reason": "Official closed model",
        "brand_id": brand.pk,
        "product_type": "llm-model",
        "catalog_mode": "x_only",
    }
    assert client.post(url, payload).status_code == 302
    assert client.post(url, payload).status_code == 302
    product = Product.objects.get()
    assert product.repo_id is None
    assert product.brand_id == brand.pk
    assert PostBrandProduct.objects.filter(
        post_id=proposal.source_post_id, brand=brand, product=product
    ).exists()


def test_two_posts_for_same_release_reuse_x_only_product_then_attach_hf_repo():
    brand = Brand.objects.create(nickname="known")
    release = _release(brand)
    first = _proposal("d", brand=brand, release=release)
    decide_product_proposal(
        proposal_id=first.pk,
        action="approve",
        reviewer="owner@example.com",
        reason="Reviewed X announcement",
        brand_id=brand.pk,
        product_type="llm-model",
        catalog_mode="x_only",
    )
    second = _proposal(
        "e",
        brand=brand,
        release=release,
        repo_id="KnownOrg/Model-X",
        hf_outcome="matched",
    )
    decided = decide_product_proposal(
        proposal_id=second.pk,
        action="approve",
        reviewer="owner@example.com",
        reason="Exact repository reviewed",
        brand_id=brand.pk,
        product_type="llm-model",
        catalog_mode="hf",
    )
    assert Product.objects.count() == 1
    first.refresh_from_db()
    assert decided.resolved_product_id == first.resolved_product_id
    assert Product.objects.get().repo_id == "KnownOrg/Model-X"
    assert PostBrandProduct.objects.count() == 2


def test_candidate_can_create_untracked_brand_and_company_without_harvest_membership():
    company = Company.objects.create(nickname="new_company", display_name="New Company")
    now = timezone.now()
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="New Publisher",
        candidate_identity="candidate-new-publisher",
        first_observed_at=now,
        last_observed_at=now,
    )
    proposal = _proposal("f", candidate=candidate)
    decided = decide_product_proposal(
        proposal_id=proposal.pk,
        action="approve",
        reviewer="owner@example.com",
        reason="Canonical publisher reviewed",
        new_brand_id="new_publisher",
        company_id=company.pk,
        product_type="other-ai-model",
        catalog_mode="x_only",
    )
    assert decided.proposed_brand_id == "new_publisher"
    assert BrandCompany.objects.filter(
        brand_id="new_publisher", company=company
    ).exists()
    candidate.refresh_from_db()
    assert candidate.reviewed_brand_id == "new_publisher"
    assert not Brand.objects.get(pk="new_publisher").keywords.exists()


def test_candidate_new_brand_path_rejects_existing_nickname_collision():
    Brand.objects.create(nickname="existing", display_name="Existing")
    now = timezone.now()
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="Different Publisher",
        candidate_identity="candidate-collision",
        first_observed_at=now,
        last_observed_at=now,
    )
    proposal = _proposal("j", candidate=candidate)
    with pytest.raises(ValueError, match="already exists"):
        decide_product_proposal(
            proposal_id=proposal.pk,
            action="approve",
            reviewer="owner@example.com",
            reason="Typo should fail",
            new_brand_id="existing",
            product_type="llm-model",
            catalog_mode="x_only",
        )
    candidate.refresh_from_db()
    assert candidate.reviewed_brand_id is None


def test_rejection_keeps_evidence_and_creates_no_product():
    brand = Brand.objects.create(nickname="known")
    proposal = _proposal("g", brand=brand)
    decide_product_proposal(
        proposal_id=proposal.pk,
        action="reject",
        reviewer="owner@example.com",
        reason="Ambiguous identity",
    )
    proposal.refresh_from_db()
    assert proposal.review_status == "rejected"
    assert proposal.source_post.text.startswith("Release")
    assert not Product.objects.exists()


def test_distinct_proposals_for_same_hf_repo_converge_without_duplicate():
    brand = Brand.objects.create(nickname="known")
    proposals = [
        _proposal(key, brand=brand, repo_id="KnownOrg/Same", hf_outcome="matched")
        for key in ("h", "i")
    ]

    def approve(proposal_id):
        close_old_connections()
        try:
            return decide_product_proposal(
                proposal_id=proposal_id,
                action="approve",
                reviewer="owner@example.com",
                reason="Exact repo reviewed",
                brand_id=brand.pk,
                product_type="llm-model",
                catalog_mode="hf",
            ).resolved_product_id
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        product_ids = list(pool.map(approve, [proposal.pk for proposal in proposals]))
    assert product_ids[0] == product_ids[1]
    assert Product.objects.count() == 1
