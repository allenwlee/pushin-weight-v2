from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import httpx
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import (
    Account,
    Brand,
    BrandAccount,
    BrandCompany,
    BrandDiscoveryCandidate,
    Company,
    HFOrg,
    ModelRelease,
    Post,
    PostBrandProduct,
    Product,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
    Role,
)
from core.product_verification import (
    POLICY_VERSION,
    attach_verified_product,
    decide_product_proposal,
    drain_pending_verifications,
    evaluate_known_publisher,
    exact_model_metadata,
    hf_org_socials,
    import_known_org_catalog,
    source_repo_evidence,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def _publisher():
    brand = Brand.objects.create(nickname="minimax", display_name="MiniMax")
    company = Company.objects.create(nickname="minimax-company", display_name="MiniMax")
    BrandCompany.objects.create(brand=brand, company=company)
    org = HFOrg.objects.create(namespace="MiniMaxAI", company=company, confirmed=True)
    role = Role.objects.create(key="official")
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


def test_known_publisher_hf_match_attaches_to_owner_approved_x_only_product():
    brand, _org, account, post = _publisher()
    now = timezone.now()
    release = ModelRelease.objects.create(
        brand=brand,
        observed_model_name="M2",
        release_identity="known-m2-release",
        first_seen_at=now,
        last_seen_at=now,
        extraction_version="test",
    )
    first = ProductVerificationProposal.objects.create(
        proposal_key="7" * 64,
        source_post=post,
        source_release=release,
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
        source_release=release,
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


def test_catalog_import_is_bounded_reports_truncation_and_never_downloads_files():
    brand, org, _account, _post = _publisher()
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=[{"id": "MiniMaxAI/M1", "author": "MiniMaxAI"}],
            headers={
                "link": '<https://huggingface.co/api/models?cursor=next>; rel="next"'
            },
        )

    result = import_known_org_catalog(
        brand=brand,
        hf_org=org,
        client=_client(respond),
        max_requests=1,
        max_models=10,
    )
    assert (result.imported, result.complete, result.stop_reason) == (
        1,
        False,
        "request_cap",
    )
    assert len(calls) == 1
    assert calls[0].url.path == "/api/models"


def test_catalog_keeps_quantized_variant_as_separate_product_and_replay_updates():
    brand, org, _account, _post = _publisher()
    payload = [
        {"id": "MiniMaxAI/M2", "author": "MiniMaxAI", "sha": "a"},
        {"id": "MiniMaxAI/M2-GGUF", "author": "MiniMaxAI", "sha": "b"},
    ]
    client = _client(lambda _request: httpx.Response(200, json=payload))
    first = import_known_org_catalog(
        brand=brand,
        hf_org=org,
        client=client,
        max_requests=1,
        max_models=10,
    )
    second = import_known_org_catalog(
        brand=brand,
        hf_org=org,
        client=client,
        max_requests=1,
        max_models=10,
    )
    assert (first.imported, second.updated, Product.objects.count()) == (2, 2, 2)
    assert set(Product.objects.values_list("type", flat=True)) == {None}


def test_catalog_refresh_preserves_metadata_omitted_from_listing():
    brand, org, _account, _post = _publisher()
    Product.objects.create(
        repo_id="MiniMaxAI/M2",
        brand=brand,
        hf_org=org,
        siblings=[{"rfilename": "config.json"}],
        raw={"detail_only": "kept", "sha": "old"},
    )
    result = import_known_org_catalog(
        brand=brand,
        hf_org=org,
        client=_client(
            lambda _request: httpx.Response(
                200,
                json=[
                    {
                        "id": "MiniMaxAI/M2",
                        "author": "MiniMaxAI",
                        "sha": "new",
                    }
                ],
            )
        ),
        max_requests=1,
        max_models=10,
    )
    product = Product.objects.get()
    assert (result.updated, product.sha) == (1, "new")
    assert product.siblings == [{"rfilename": "config.json"}]
    assert product.raw == {
        "detail_only": "kept",
        "sha": "new",
        "id": "MiniMaxAI/M2",
        "author": "MiniMaxAI",
    }


def test_catalog_resume_returns_exact_next_cursor():
    brand, org, _account, _post = _publisher()
    seen = []

    def respond(request):
        seen.append(request.url.params.get("cursor"))
        return httpx.Response(
            200,
            json=[{"id": "MiniMaxAI/M3", "author": "MiniMaxAI"}],
            headers={
                "link": '<https://huggingface.co/api/models?cursor=NEXT>; rel="next"'
            },
        )

    result = import_known_org_catalog(
        brand=brand,
        hf_org=org,
        client=_client(respond),
        max_requests=1,
        max_models=10,
        cursor="START",
    )
    assert seen == ["START"]
    assert (result.complete, result.stop_reason, result.next_cursor) == (
        False,
        "request_cap",
        "NEXT",
    )


def test_catalog_rejects_wrong_brand_owner_before_network():
    _brand, org, _account, _post = _publisher()
    wrong_brand = Brand.objects.create(nickname="wrong")
    calls = []
    with pytest.raises(ValueError, match="does not own"):
        import_known_org_catalog(
            brand=wrong_brand,
            hf_org=org,
            client=_client(lambda request: calls.append(request)),
            max_requests=1,
            max_models=1,
        )
    assert calls == []


def test_catalog_command_preview_is_provider_free(monkeypatch):
    brand, org, _account, _post = _publisher()
    monkeypatch.setattr(
        "monitor.management.commands.import_hf_product_catalog.httpx.Client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preview must not construct an HTTP client")
        ),
    )
    stdout = StringIO()
    call_command(
        "import_hf_product_catalog",
        "--brand",
        brand.pk,
        "--confirmed-namespace",
        org.pk,
        "--max-requests",
        "1",
        "--max-models",
        "5",
        stdout=stdout,
    )
    payload = json.loads(stdout.getvalue())
    assert payload == {
        "brand": "minimax",
        "confirmed_namespace": "MiniMaxAI",
        "cursor": None,
        "max_models": 5,
        "max_requests": 1,
        "mode": "preview",
    }


def test_catalog_command_rejects_wrong_brand_before_network(monkeypatch):
    _brand, org, _account, _post = _publisher()
    wrong_brand = Brand.objects.create(nickname="wrong")
    monkeypatch.setattr(
        "monitor.management.commands.import_hf_product_catalog.httpx.Client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("invalid ownership must fail before HTTP")
        ),
    )
    with pytest.raises(CommandError, match="does not own"):
        call_command(
            "import_hf_product_catalog",
            "--brand",
            wrong_brand.pk,
            "--confirmed-namespace",
            org.pk,
            "--max-requests",
            "1",
            "--max-models",
            "1",
            "--commit",
        )


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


def test_catalog_owner_conflict_stops_without_reassignment():
    brand, org, _account, _post = _publisher()
    other = Brand.objects.create(nickname="other")
    product = Product.objects.create(repo_id="MiniMaxAI/M2", brand=other)
    result = import_known_org_catalog(
        brand=brand,
        hf_org=org,
        client=_client(
            lambda _request: httpx.Response(
                200, json=[{"id": "MiniMaxAI/M2", "author": "MiniMaxAI"}]
            )
        ),
        max_requests=1,
        max_models=10,
    )
    assert result.stop_reason == "owner_conflict"
    product.refresh_from_db()
    assert product.brand_id == "other"


def _new_publisher_proposal(*, verified_type: str = "Business"):
    account = Account.objects.create(
        author_id="1888791214864072705",
        handle="NewPublisher_AI",
        verified_type=verified_type,
        is_blue_verified=False,
    )
    post = Post.objects.create(
        tweet_id="new-publisher-release",
        author=account,
        author_handle="NewPublisher_AI",
        author_verified_type=verified_type,
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
        "stable_account_id": account.pk,
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
    release = ModelRelease.objects.create(
        brand_discovery_candidate=candidate,
        observed_model_name="Model One",
        release_identity="new-publisher-release",
        first_seen_at=now,
        last_seen_at=now,
        extraction_version="test",
    )
    proposal.source_release = release
    proposal.save(update_fields=["source_release", "updated_at"])
    return proposal


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
    assert product.hf_org_id is None
    assert BrandCompany.objects.count() == 0
    candidate = BrandDiscoveryCandidate.objects.get(
        candidate_identity="new-publisher-ai"
    )
    assert candidate.reviewed_brand_id == "newpublisher_ai"
    assert not Brand.objects.get(pk="newpublisher_ai").keywords.exists()
    release = ModelRelease.objects.get()
    assert release.brand_id is None
    assert release.brand_discovery_candidate_id == candidate.pk
    assert proposal.source_release_id == release.pk
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
