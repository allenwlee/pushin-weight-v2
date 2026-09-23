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
    Company,
    HFOrg,
    Post,
    PostBrandProduct,
    Product,
    ProductVerificationProposal,
    RareTypeCategoryAssignment,
    Role,
)
from core.product_verification import (
    attach_verified_product,
    drain_pending_verifications,
    evaluate_known_publisher,
    exact_model_metadata,
    import_known_org_catalog,
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
