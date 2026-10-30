from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    BrandDiscoveryCandidate,
    EventDossier,
    EventDossierClaim,
    Post,
    PostBrandProduct,
    Product,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
    Role,
)
from core.product_release_dossiers import record_release_report
from core.product_verification import (
    POLICY_VERSION,
    attach_verified_product,
    decide_product_proposal,
    drain_pending_verifications,
    evaluate_known_publisher,
    exact_model_metadata,
    hf_org_socials,
    source_repo_evidence,
)
from tests.account_factory import x_verification_id
from tests.company_factory import company_with_label
from tests.publisher_fixtures import hf_publisher

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _publisher():
    brand = Brand.objects.create(nickname="minimax", display_name="MiniMax")
    company = company_with_label("minimax-company", "MiniMax")
    BrandCompany.objects.create(brand=brand, company=company)
    org = hf_publisher(namespace="MiniMaxAI", company=company, confirmed=True)
    role, _ = Role.objects.get_or_create(key="official")
    account = Account.objects.create(
        author_id="12345",
        handle="MiniMax__AI",
        is_blue_verified=True,
    )
    BrandAccount.objects.create(brand=brand, account=account, role=role)
    post = Post.objects.create(tweet_id="p1", author=account, text="MiniMaxAI/M2")
    return brand, org, account, post


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_blue_alone_and_same_looking_handle_do_not_authenticate_publisher():
    brand, _org, account, _post = _publisher()
    BrandAccount.objects.all().delete()
    decision = evaluate_known_publisher(
        account=account, brand=brand, namespace="MiniMaxAI"
    )
    assert not decision.qualifies
    assert decision.reason == "account_not_tracked_official"


def test_confirmed_known_publisher_attaches_exact_repo_idempotently():
    brand, _org, account, post = _publisher()
    metadata = {"id": "MiniMaxAI/M2", "author": "MiniMaxAI", "sha": "abc"}
    first = attach_verified_product(
        post=post,
        brand=brand,
        repo_id="MiniMaxAI/M2",
        observed_name="M2",
        account=account,
        metadata=metadata,
        evidence={"source": "x_post"},
        product_type="llm-model",
    )
    second = attach_verified_product(
        post=post,
        brand=brand,
        repo_id="MiniMaxAI/M2",
        observed_name="M2",
        account=account,
        metadata={**metadata, "sha": "def"},
        evidence={"source": "x_post"},
        product_type="llm-model",
    )
    assert first.pk == second.pk
    assert Product.objects.get(pk=first.pk).sha == "def"
    assert PostBrandProduct.objects.count() == 1


@pytest.mark.parametrize("mode,expected", [
    ("official", True), ("comparison", False), ("question", False),
    ("unofficial", False), ("ambiguous", False), ("rejected", False),
])
def test_no_link_official_release_uses_verified_search_and_exact_capture(mode, expected):
    from core.models import DataSource
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )

    brand, _org, account, post = _publisher()
    if mode == "unofficial":
        BrandAccount.objects.filter(account=account, brand=brand).delete()
    post.text = ("We release Other, trained on M2" if mode == "comparison" else
                 "Did we announce M2?" if mode == "question" else "We announce M2!")
    post.author_handle = account.handle
    post.save(update_fields=["text", "author_handle"])
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": "M2"}, release_identity="no-link-verified",
        observed_name="M2", source_url=None, brand=brand, maturity_code="unknown",
        release_value=None, release_precision="unknown", extraction_version="test",
    )
    report = EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    RareTypeCategoryAssignment.objects.create(
        post=post, brand=brand, category="llm-model", source_evidence={}, classification_version="test"
    )
    proposal = ProductVerificationProposal.objects.create(
        proposal_key="f" * 64, source_post=post, source_dossier=dossier, proposed_brand=brand,
        account=account, account_handle_snapshot=account.handle, observed_name="M2",
        candidate_repo_id="", policy_version=POLICY_VERSION, hf_outcome="deferred",
        review_status="rejected" if mode == "rejected" else "pending",
    )
    job = queue_hf_name_search(report.pk)
    calls = []
    def respond(request):
        calls.append(request)
        if request.url.path == "/api/models":
            rows = [{"id": "MiniMaxAI/M2"}]
            if mode == "ambiguous":
                rows.append({"id": "MiniMaxAI/M-2"})
            return httpx.Response(200, json=rows)
        return httpx.Response(200, json={"id": "MiniMaxAI/M2", "author": "MiniMaxAI"})
    client = _client(respond)
    search = execute_hf_name_search(job.pk, client=client)
    child = models_for_test_exact_job("MiniMaxAI/M2")
    exact = execute_hf_name_search(child.pk, client=client)
    proposal.refresh_from_db()
    assert exact["integration"]["products_resolved"] == int(expected)
    assert (proposal.review_status == "approved") is expected
    assert Product.objects.count() == int(expected)
    assert PostBrandProduct.objects.count() == int(expected)
    if expected:
        edge = PostBrandProduct.objects.get()
        assert edge.source_evidence["search_observation_id"] in list(
            EventDossierClaim.objects.filter(event_dossier_source__event_dossier=dossier,
                event_dossier_source__collection_observation__run_id=search["run_id"])
            .values_list("event_dossier_source__collection_observation_id", flat=True)
        )
        assert edge.source_evidence["exact_observation_id"] is not None
    assert dossier.current_review_id is None
    assert execute_hf_name_search(child.pk, client=client)["physical_requests"] == 0
    assert len(calls) == 2 and Product.objects.count() == int(expected)


def models_for_test_exact_job(identifier):
    from core.models import CollectionJob

    return CollectionJob.objects.get(targets__target_role="exact_model", targets__native_identifier=identifier)


@pytest.mark.parametrize("observed_name,official,excluded,expected", [
    ("M2", True, False, True),
    ("Other Student", True, False, False),
    ("M2", False, False, False),
    ("M2", True, True, False),
])
def test_captured_exact_release_metadata_reuses_known_publisher_verifier(
    observed_name, official, excluded, expected
):
    from core.models import DataSource
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )

    brand, _org, account, post = _publisher()
    if not official:
        BrandAccount.objects.filter(account=account, brand=brand).delete()
    url = "https://huggingface.co/MiniMaxAI/M2"
    post.text = f"We announce {observed_name} {url}"
    post.author_handle = account.handle
    post.save(update_fields=["text", "author_handle"])
    DataSource.objects.get_or_create(
        pk="hf", defaults={"name": "Hugging Face", "source_type": "model_adoption"}
    )
    dossier, _, _ = record_release_report(
        post=post, record={"model_name": observed_name, "source_url": url},
        release_identity="captured-exact-verification", observed_name=observed_name,
        source_url=url, brand=brand, maturity_code="unknown", release_value=None,
        release_precision="unknown", extraction_version="test",
    )
    claim = EventDossierClaim.objects.get(
        event_dossier_source__event_dossier=dossier, claim_kind_reference__code="release_report"
    )
    RareTypeCategoryAssignment.objects.create(
        post=post, brand=brand, category="llm-model", source_evidence={}, classification_version="test"
    )
    proposal = ProductVerificationProposal.objects.create(
        proposal_key="e" * 64, source_post=post, source_dossier=dossier,
        proposed_brand=brand, account=account, account_handle_snapshot=account.handle,
        observed_name=observed_name, candidate_repo_id="MiniMaxAI/M2", policy_version=POLICY_VERSION,
        account_evidence={"stable_account_id": account.author_id, **source_repo_evidence(post, "MiniMaxAI/M2")},
    )
    job = queue_hf_name_search(claim.pk)
    if excluded:
        from core.product_release_pipeline import record_intake_decision

        other, _, _ = record_release_report(
            post=post, record={"model_name": "M2", "source_url": url},
            release_identity="other-shared-job", observed_name="M2", source_url=url,
            brand=brand, maturity_code="unknown", release_value=None,
            release_precision="unknown", extraction_version="test",
        )
        other_claim = EventDossierClaim.objects.get(
            event_dossier_source__event_dossier=other, claim_kind_reference__code="release_report"
        )
        assert queue_hf_name_search(other_claim.pk).pk == job.pk
        record_intake_decision(dossier.pk, claim_id=claim.pk, outcome="scam",
                               actor="test", reason="Documented impersonation")
    calls = []
    client = _client(lambda request: (calls.append(request) or httpx.Response(
        200, json={"id": "MiniMaxAI/M2", "author": "MiniMaxAI", "likes": 7}
    )))
    result = execute_hf_name_search(job.pk, client=client)
    proposal.refresh_from_db()
    assert result["integration"]["products_resolved"] == int(expected)
    assert (proposal.review_status == "approved") is expected
    assert Product.objects.count() == int(expected)
    assert PostBrandProduct.objects.count() == int(expected)
    assert dossier.sources.filter(collection_observation__isnull=False).count() == 1
    assert EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=dossier, scope_key__startswith="hf_capture:"
    ).count() == 1
    again = execute_hf_name_search(job.pk, client=client)
    assert again["physical_requests"] == 0 and len(calls) == 1
    assert Product.objects.count() == int(expected)
    assert EventDossierClaim.objects.filter(
        event_dossier_source__event_dossier=dossier, scope_key__startswith="hf_capture:"
    ).count() == 1
    assert dossier.current_review_id is None


def test_known_publisher_hf_match_attaches_to_owner_approved_x_only_product():
    brand, _org, account, post = _publisher()
    release, _, _ = record_release_report(
        post=post, record={"model_name": "M2"},
        release_identity="known-m2-release", observed_name="M2",
        source_url=None, brand=brand, maturity_code="unknown",
        release_value=None, release_precision="unknown", extraction_version="test",
    )
    first = ProductVerificationProposal.objects.create(
        proposal_key="7" * 64,
        source_post=post,
        source_dossier=release,
        proposed_brand=brand,
        account=account,
        observed_name="M2",
        policy_version="product-x-hf-v1",
        hf_outcome="deferred",
    )
    decide_product_proposal(
        proposal_id=first.pk,
        action="approve",
        reviewer="owner@example.com",
        reason="Official closed model",
        brand_id=brand.pk,
        product_type="llm-model",
        catalog_mode="x_only",
    )
    x_only_product = Product.objects.get()
    assert x_only_product.repo_id is None

    RareTypeCategoryAssignment.objects.create(
        post=post,
        brand=brand,
        category="llm-model",
        source_evidence={},
        classification_version="test",
    )
    ProductVerificationProposal.objects.create(
        proposal_key="8" * 64,
        source_post=post,
        source_dossier=release,
        proposed_brand=brand,
        account=account,
        observed_name="M2",
        candidate_repo_id="MiniMaxAI/M2",
        policy_version="product-x-hf-v1",
    )
    result = drain_pending_verifications(
        max_requests=1,
        deadline=None,
        client=_client(
            lambda _request: httpx.Response(
                200,
                json={"id": "MiniMaxAI/M2", "author": "MiniMaxAI"},
            )
        ),
    )
    assert result.resolved == 1
    assert Product.objects.count() == 1
    x_only_product.refresh_from_db()
    assert x_only_product.repo_id == "MiniMaxAI/M2"
    assert set(
        ProductVerificationProposal.objects.values_list(
            "resolved_product_id", flat=True
        )
    ) == {x_only_product.pk}


@pytest.mark.parametrize(
    "status,outcome",
    [(404, "missing"), (403, "private"), (429, "throttled"), (500, "error")],
)
def test_exact_metadata_preserves_failure_outcomes(status, outcome):
    result = exact_model_metadata(
        "MiniMaxAI/M2", client=_client(lambda _request: httpx.Response(status))
    )
    assert result.outcome == outcome


def test_exact_metadata_timeout_and_deadline_make_no_retry():
    calls = []

    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    assert (
        exact_model_metadata("MiniMaxAI/M2", client=_client(timeout)).outcome
        == "timeout"
    )
    assert len(calls) == 1
    calls.clear()
    result = exact_model_metadata(
        "MiniMaxAI/M2",
        client=_client(timeout),
        deadline=timezone.now() - timedelta(seconds=1),
    )
    assert result.outcome == "deferred"
    assert calls == []


def test_exact_metadata_is_public_only_and_rejects_invalid_path_without_http(
    monkeypatch,
):
    monkeypatch.setenv("HF_TOKEN", "must-not-leak")
    calls = []

    def respond(request):
        calls.append(request)
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"id": "MiniMaxAI/M2"})

    client = _client(respond)
    assert exact_model_metadata("MiniMaxAI/M2", client=client).outcome == "matched"
    assert (
        exact_model_metadata("MiniMaxAI/../api/whoami", client=client).outcome
        == "malformed"
    )
    assert len(calls) == 1


def test_source_repo_evidence_requires_exact_safe_hf_link():
    post = Post.objects.create(
        tweet_id="source-links",
        text=(
            "MiniMaxAI/M2 guessed; "
            "https://huggingface.co/MiniMaxAI/M2/tree/main is not exact"
        ),
        entities={
            "urls": [
                {"expanded_url": "https://huggingface.co/MiniMaxAI/M2"},
                {"expanded_url": "https://evil.example/MiniMaxAI/M2"},
                {"expanded_url": "https://huggingface.co:bad/MiniMaxAI/M2"},
            ]
        },
    )
    evidence = source_repo_evidence(post, "MiniMaxAI/M2")
    assert evidence["exact_hf_repo_link"] is True
    assert evidence["matched_hf_urls"] == ["https://huggingface.co/MiniMaxAI/M2"]
    assert source_repo_evidence(post, "MiniMaxAI/Other")["exact_hf_repo_link"] is False


def test_hf_socials_requires_exact_org_shape_and_never_follows_payload_urls():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "org": "MiniMaxAI",
                "socialHandles": {
                    "twitter": "MiniMax_AI",
                    "website": "http://127.0.0.1/private",
                },
            },
        )

    result = hf_org_socials("MiniMaxAI", client=_client(respond))
    assert result.outcome == "matched"
    assert len(calls) == 1
    assert calls[0].url.path == "/api/organizations/MiniMaxAI/socials"


def test_existing_product_owner_conflict_fails_without_reassignment():
    brand, _org, account, post = _publisher()
    other = Brand.objects.create(nickname="other")
    product = Product.objects.create(repo_id="MiniMaxAI/M2", brand=other)
    with pytest.raises(ValueError, match="product_owner_conflict"):
        attach_verified_product(
            post=post,
            brand=brand,
            repo_id="MiniMaxAI/M2",
            observed_name="M2",
            account=account,
            metadata={"id": "MiniMaxAI/M2"},
            evidence={},
            product_type="llm-model",
        )
    product.refresh_from_db()
    assert product.brand_id == "other"


def _new_publisher_proposal(*, verified_type: str = "Business"):
    account = Account.objects.create(
        author_id="1888791214864072705",
        handle="NewPublisher_AI",
        verified_type_id=x_verification_id(verified_type),
        is_blue_verified=False,
    )
    post = Post.objects.create(
        tweet_id="new-publisher-release",
        author=account,
        author_handle="NewPublisher_AI",
        author_verified_type_id=x_verification_id(verified_type),
        text="New model: https://huggingface.co/NewPublisher-AI/Model-One",
        entities={
            "urls": [
                {"expanded_url": ("https://huggingface.co/NewPublisher-AI/Model-One")}
            ]
        },
    )
    now = timezone.now()
    candidate = BrandDiscoveryCandidate.objects.create(
        observed_name="New Publisher AI",
        candidate_identity="new-publisher-ai",
        source_post=post,
        first_observed_at=now,
        last_observed_at=now,
    )
    RareTypeCategoryAssignment.objects.create(
        post=post,
        brand_discovery_candidate=candidate,
        category="llm-model",
        source_evidence={},
        classification_version="test",
    )
    evidence = {
        "stable_account_id": account.author_id,
        **source_repo_evidence(post, "NewPublisher-AI/Model-One"),
    }
    proposal = ProductVerificationProposal.objects.create(
        proposal_key="9" * 64,
        source_post=post,
        proposed_candidate=candidate,
        account=account,
        account_handle_snapshot="NewPublisher_AI",
        observed_name="Model One",
        candidate_repo_id="NewPublisher-AI/Model-One",
        account_evidence=evidence,
        policy_version=POLICY_VERSION,
    )
    release, _, _ = record_release_report(
        post=post, record={"model_name": "Model One"},
        release_identity="new-publisher-release", observed_name="Model One",
        source_url=None, candidate=candidate, maturity_code="unknown",
        release_value=None, release_precision="unknown", extraction_version="test",
    )
    proposal.source_dossier = release
    proposal.save(update_fields=["source_dossier", "updated_at"])
    return proposal


@pytest.mark.parametrize("verified_type,handle,observed_name,category,candidate_status,approved", [
    ("Business", "NewPublisher_AI", "Model One", True, "pending", True),
    ("Blue", "NewPublisher_AI", "Model One", True, "pending", False),
    ("Business", "SomeoneElse", "Model One", True, "pending", False),
    ("Business", "NewPublisher_AI", "Different Product", True, "pending", False),
    ("Business", "NewPublisher_AI", "Model One", False, "pending", False),
    ("Business", "NewPublisher_AI", "Model One", True, "rejected", False),
    ("Business", "NewPublisher_AI", "Model One", True, "needs_review", False),
    ("Business", "NewPublisher_AI", "Model One", True, "collision", False),
    ("Blue", "NewPublisher_AI", "Model One", True, "self_declared", True),
    ("Blue", "NewPublisher_AI", "Model One", True, "third_party", False),
    ("Blue", "NewPublisher_AI", "Model One", True, "quoted", False),
    ("Blue", "NewPublisher_AI", "Model One", True, "future", False),
    ("Blue", "SomeoneElse", "Model One", True, "self_declared", False),
    ("Blue", "NewPublisher_AI", "Model One", True, "individual", True),
    ("Blue", "SomeoneElse", "Model One", True, "individual", False),
])
def test_captured_sources_use_existing_new_publisher_policy(
    verified_type, handle, observed_name, category, candidate_status, approved
):
    from core.event_dossiers import add_claim
    from core.measurement_taxonomy import digest
    from core.models import CollectionJob, DataSource
    from core.product_release_acquisition import (
        execute_hf_name_search,
        queue_hf_name_search,
    )

    proposal = _new_publisher_proposal(verified_type=verified_type)
    candidate = proposal.proposed_candidate
    declared_text = {
        "self_declared": "I released Model One at https://huggingface.co/NewPublisher-AI/Model-One",
        "third_party": "They released Model One at https://huggingface.co/NewPublisher-AI/Model-One",
        "quoted": 'They said "I released Model One" at https://huggingface.co/NewPublisher-AI/Model-One',
        "future": "I will release Model One at https://huggingface.co/NewPublisher-AI/Model-One",
        "individual": "I released Model One at https://huggingface.co/NewPublisher-AI/Model-One",
    }
    if candidate_status in declared_text:
        proposal.source_post.text = declared_text[candidate_status]
        proposal.source_post.save(update_fields=["text"])
    if candidate_status == "collision":
        Brand.objects.create(nickname="newpublisher_ai", display_name="Unrelated publisher")
    candidate.verification_status = ("pending" if candidate_status in {"collision", *declared_text}
                                     else candidate_status)
    candidate.save(update_fields=["verification_status"])
    if not category:
        RareTypeCategoryAssignment.objects.filter(post=proposal.source_post).delete()
    proposal.observed_name = observed_name
    proposal.save(update_fields=["observed_name", "updated_at"])
    DataSource.objects.get_or_create(pk="hf", defaults={"name": "HF", "source_type": "model_adoption"})
    source = proposal.source_dossier.sources.get(post=proposal.source_post)
    repo = proposal.candidate_repo_id
    lead = add_claim(
        source.pk, claim_kind="release_context", scope_key="hf_repo_lead:" + digest(repo.casefold()),
        assertion_text=f"Source references {repo}", source_excerpt=proposal.source_post.text,
        source_locator=f"https://huggingface.co/{repo}", extraction_version="test",
    )
    job = queue_hf_name_search(lead.pk)
    def respond(request):
        if request.url.path.startswith("/api/models/"):
            return httpx.Response(200, json={"id": repo, "author": "NewPublisher-AI"})
        if candidate_status == "individual":
            if request.url.path.startswith("/api/organizations/"):
                return httpx.Response(404)
            assert request.url.path == "/api/users/NewPublisher-AI/socials"
            return httpx.Response(200, json={"user": "NewPublisher-AI", "socialHandles": {"twitter": handle}})
        return httpx.Response(200, json={"org": "NewPublisher-AI", "socialHandles": {"twitter": handle}})
    client = _client(respond)
    assert execute_hf_name_search(job.pk, client=client)["outcome"] == "found"
    social_job = CollectionJob.objects.get(targets__target_role="publisher_socials")
    result = execute_hf_name_search(social_job.pk, client=client)
    assert result["physical_requests"] == (2 if candidate_status == "individual" else 1)
    proposal.refresh_from_db()
    assert result["integration"]["products_resolved"] == int(approved)
    assert (proposal.review_status == "approved") == approved
    assert Product.objects.count() == int(approved)
    candidate.refresh_from_db()
    assert candidate.verification_status == ("confirmed" if approved else
                                             "pending" if candidate_status in {"collision", *declared_text}
                                             else candidate_status)
    assert proposal.source_dossier.sources.filter(
        collection_observation__projection_kind="hf-release-socials-v1"
    ).exists()
    assert proposal.source_dossier.current_review_id is None
    assert execute_hf_name_search(social_job.pk, client=client)["physical_requests"] == 0


def test_new_publisher_exact_model_is_cached_then_socials_resume_without_refetch():
    proposal = _new_publisher_proposal()
    calls = []

    def respond(request):
        calls.append(request.url.path)
        if request.url.path.startswith("/api/models/"):
            return httpx.Response(
                200,
                json={
                    "id": "NewPublisher-AI/Model-One",
                    "author": "NewPublisher-AI",
                    "sha": "abc",
                },
            )
        return httpx.Response(
            200,
            json={
                "_id": "hf-org-id",
                "org": "NewPublisher-AI",
                "socialHandles": {"twitter": "NewPublisher_AI"},
            },
        )

    first = drain_pending_verifications(
        max_requests=1,
        deadline=None,
        client=_client(respond),
    )
    proposal.refresh_from_db()
    assert (first.attempted, first.resolved, first.deferred) == (1, 0, 1)
    assert proposal.hf_outcome == "deferred"
    assert proposal.hf_evidence["_exact_model"]["sha"] == "abc"

    second = drain_pending_verifications(
        max_requests=1,
        deadline=None,
        client=_client(respond),
    )
    proposal.refresh_from_db()
    assert (second.attempted, second.resolved) == (1, 1)
    assert calls == [
        "/api/models/NewPublisher-AI/Model-One",
        "/api/organizations/NewPublisher-AI/socials",
    ]
    assert proposal.review_status == "approved"
    assert proposal.proposed_candidate_id is None
    assert proposal.proposed_brand_id == "newpublisher_ai"
    product = Product.objects.get()
    assert product.brand_id == "newpublisher_ai"
    assert product.hf_namespace is None
    assert BrandCompany.objects.count() == 0
    candidate = BrandDiscoveryCandidate.objects.get(
        candidate_identity="new-publisher-ai"
    )
    assert candidate.reviewed_brand_id == "newpublisher_ai"
    assert not Brand.objects.get(pk="newpublisher_ai").keywords.exists()
    release = EventDossier.objects.get()
    claim = EventDossierClaim.objects.get(event_dossier_source__event_dossier=release)
    assert claim.reported_brand_id is None
    assert claim.reported_brand_discovery_candidate_id == candidate.pk
    assert proposal.source_dossier_id == release.pk
    assert proposal.resolved_product_id == product.pk


def test_new_publisher_blue_or_non_business_stops_before_http():
    proposal = _new_publisher_proposal(verified_type="Blue")
    calls = []
    result = drain_pending_verifications(
        max_requests=3,
        deadline=None,
        client=_client(lambda request: calls.append(request)),
    )
    proposal.refresh_from_db()
    assert (result.attempted, result.resolved, calls) == (0, 0, [])
    assert proposal.review_status == "pending"
    assert "automatic_verification_stopped:x_business_gold_missing" in (
        proposal.rule_trace
    )


def test_new_publisher_handle_change_stops_before_http():
    proposal = _new_publisher_proposal()
    proposal.account.handle = "HijackedHandle"
    proposal.account.save(update_fields=["handle"])
    calls = []
    drain_pending_verifications(
        max_requests=1,
        deadline=None,
        client=_client(lambda request: calls.append(request)),
    )
    proposal.refresh_from_db()
    assert calls == []
    assert "automatic_verification_stopped:source_handle_changed" in (
        proposal.rule_trace
    )


def test_new_publisher_extractor_guess_without_source_link_stops_before_http():
    proposal = _new_publisher_proposal()
    proposal.account_evidence = {
        **proposal.account_evidence,
        "exact_hf_repo_link": False,
        "matched_hf_urls": [],
    }
    proposal.save(update_fields=["account_evidence", "updated_at"])
    calls = []
    drain_pending_verifications(
        max_requests=1,
        deadline=None,
        client=_client(lambda request: calls.append(request)),
    )
    proposal.refresh_from_db()
    assert calls == []
    assert "automatic_verification_stopped:source_exact_repo_link_missing" in (
        proposal.rule_trace
    )


def test_new_publisher_conflicting_hf_social_handle_creates_nothing():
    proposal = _new_publisher_proposal()

    def respond(request):
        if request.url.path.startswith("/api/models/"):
            return httpx.Response(
                200,
                json={
                    "id": "NewPublisher-AI/Model-One",
                    "author": "NewPublisher-AI",
                },
            )
        return httpx.Response(
            200,
            json={
                "org": "NewPublisher-AI",
                "socialHandles": {"twitter": "SomeoneElse"},
            },
        )

    result = drain_pending_verifications(
        max_requests=2,
        deadline=None,
        client=_client(respond),
    )
    proposal.refresh_from_db()
    assert (result.attempted, result.resolved) == (2, 0)
    assert proposal.review_status == "pending"
    assert "automatic_verification_stopped:hf_social_handle_conflict" in (
        proposal.rule_trace
    )
    assert not Brand.objects.exists()
    assert not Product.objects.exists()


def test_pending_drainer_runs_after_deadline_gate_and_resolves_known_publisher():
    brand, _org, account, post = _publisher()
    RareTypeCategoryAssignment.objects.create(
        post=post,
        brand=brand,
        category="llm-model",
        source_evidence={},
        classification_version="test",
    )
    ProductVerificationProposal.objects.create(
        proposal_key="a" * 64,
        source_post=post,
        proposed_brand=brand,
        account=account,
        observed_name="M2",
        candidate_repo_id="MiniMaxAI/M2",
        policy_version="product-x-hf-v1",
    )

    class Deadline:
        def __init__(self, allowed):
            self.allowed = allowed

        def can_start(self, _seconds):
            return self.allowed

    calls = []
    client = _client(
        lambda request: (
            calls.append(request)
            or httpx.Response(200, json={"id": "MiniMaxAI/M2", "sha": "one"})
        )
    )
    blocked = drain_pending_verifications(
        max_requests=3, deadline=Deadline(False), client=client
    )
    assert (blocked.attempted, blocked.deferred, calls) == (0, 1, [])
    drained = drain_pending_verifications(
        max_requests=3, deadline=Deadline(True), client=client
    )
    assert (drained.attempted, drained.resolved, len(calls)) == (1, 1, 1)
    proposal = ProductVerificationProposal.objects.get()
    assert proposal.resolved_product_id == Product.objects.get().pk
    assert PostBrandProduct.objects.count() == 1


def test_drainer_skips_rejected_and_active_claims_without_http():
    brand, _org, account, post = _publisher()
    base = {
        "source_post": post,
        "proposed_brand": brand,
        "account": account,
        "observed_name": "M2",
        "candidate_repo_id": "MiniMaxAI/M2",
        "policy_version": "product-x-hf-v1",
    }
    ProductVerificationProposal.objects.create(
        proposal_key="b" * 64, review_status="rejected", **base
    )
    ProductVerificationProposal.objects.create(
        proposal_key="c" * 64,
        verification_claim_token="11111111-1111-1111-1111-111111111111",
        verification_claim_expires_at=timezone.now() + timedelta(minutes=1),
        **base,
    )
    calls = []
    result = drain_pending_verifications(
        max_requests=3,
        deadline=None,
        client=_client(lambda request: calls.append(request)),
    )
    assert (result.attempted, calls) == (0, [])


def test_resolution_conflict_is_retained_and_does_not_abort_next_proposal():
    brand, _org, account, post = _publisher()
    RareTypeCategoryAssignment.objects.create(
        post=post,
        brand=brand,
        category="llm-model",
        source_evidence={},
        classification_version="test",
    )
    other = Brand.objects.create(nickname="other")
    Product.objects.create(repo_id="MiniMaxAI/conflict", brand=other)
    for key, repo in (("d" * 64, "MiniMaxAI/conflict"), ("e" * 64, "MiniMaxAI/good")):
        ProductVerificationProposal.objects.create(
            proposal_key=key,
            source_post=post,
            proposed_brand=brand,
            account=account,
            observed_name=repo.rsplit("/", 1)[-1],
            candidate_repo_id=repo,
            policy_version="product-x-hf-v1",
        )
    result = drain_pending_verifications(
        max_requests=2,
        deadline=None,
        client=_client(
            lambda request: httpx.Response(
                200, json={"id": request.url.path.removeprefix("/api/models/")}
            )
        ),
    )
    assert (result.attempted, result.resolved) == (2, 1)
    conflict = ProductVerificationProposal.objects.get(
        candidate_repo_id="MiniMaxAI/conflict"
    )
    assert conflict.review_status == "pending"
    assert "resolution_error:ValueError" in conflict.rule_trace
    assert (
        ProductVerificationProposal.objects.get(
            candidate_repo_id="MiniMaxAI/good"
        ).review_status
        == "approved"
    )


def test_owner_decision_during_http_wins_over_stale_worker_finalization():
    brand, _org, account, post = _publisher()
    proposal = ProductVerificationProposal.objects.create(
        proposal_key="f" * 64,
        source_post=post,
        proposed_brand=brand,
        account=account,
        observed_name="M2",
        candidate_repo_id="MiniMaxAI/M2",
        policy_version="product-x-hf-v1",
    )

    def decide_while_in_flight(_request):
        ProductVerificationProposal.objects.filter(pk=proposal.pk).update(
            review_status="rejected", review_reason="owner rejected"
        )
        return httpx.Response(200, json={"id": "MiniMaxAI/M2"})

    result = drain_pending_verifications(
        max_requests=1, deadline=None, client=_client(decide_while_in_flight)
    )
    proposal.refresh_from_db()
    assert result.resolved == 0
    assert proposal.review_status == "rejected"
    assert proposal.review_reason == "owner rejected"
    assert proposal.resolved_product_id is None
