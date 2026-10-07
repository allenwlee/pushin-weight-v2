import json
from decimal import Decimal

import httpx
import pytest

from core.official_company_hf import PublicHF, development_quote, verify


@pytest.fixture(autouse=True)
def private_hf_signing_key(monkeypatch):
    monkeypatch.setenv("PUSHINWEIGHT_OFFICIAL_COMPANY_HF_SIGNING_KEY", "isolated-hf-test-key")


def evidence(handle="examplelab"):
    return {"identity": "evidence-hash", "handle": handle, "domains": ["example.ai"],
            "sources": [{"id": "account:bio", "text": "We develop our own speech models."}]}


def transport(*, card="Our model was trained by Example Lab.", verified=True, profile_handle="examplelab", status=200, tags=None):
    calls = []

    def respond(request):
        calls.append(request)
        assert "authorization" not in request.headers and "cookie" not in request.headers
        path = request.url.path
        if path == "/api/quicksearch":
            return httpx.Response(200, json={"orgs": []})
        if path.endswith("/overview"):
            return httpx.Response(200, json={"name": "examplelab", "fullname": "Example Lab", "isVerified": verified})
        if path == "/examplelab":
            return httpx.Response(200, text=f'<a class="leading-snug" href="https://x.com/{profile_handle}">X</a><a class="leading-snug" href="https://example.ai">Website</a>')
        if path == "/api/models":
            return httpx.Response(200, json=[{"id": "examplelab/speech", "sha": "a" * 40, "private": False, "siblings": [{"rfilename": "model.safetensors"}], "tags": tags or []}])
        if path.endswith("README.md"):
            return httpx.Response(status, text=card)
        raise AssertionError(path)

    return httpx.MockTransport(respond), calls


@pytest.mark.parametrize("card,verified,profile_handle,status,tags", [
    ("Model developer: Meta", True, "examplelab", 200, []),
    ("Our model was trained by Example Lab.", False, "examplelab", 200, []),
    ("Our model was trained by Example Lab.", True, "impostor", 200, []),
    ("Our model was trained by Example Lab.", True, "examplelab", 401, []),
    ("Our model was trained by Example Lab.", True, "examplelab", 200, ["base_model:quantized:Meta/Llama"]),
])
def test_ineligible_or_unavailable_hf_proof_stays_reviewable(card, verified, profile_handle, status, tags):
    route, calls = transport(card=card, verified=verified, profile_handle=profile_handle, status=status, tags=tags)
    with httpx.Client(transport=route, headers={"Authorization": "unrelated", "Cookie": "unrelated"}) as client:
        result = verify(evidence(), {"organization_name": "Example Lab"}, client=client)
    assert result["outcome"] == "review_needed"
    assert len(calls) <= 12
    assert len(calls) == len(result["requests"])


def test_real_profile_and_pinned_own_model_proof():
    route, calls = transport()
    with httpx.Client(transport=route) as client:
        result = verify(evidence(), {"organization_name": "Example Lab"}, client=client)
    assert result["outcome"] == "passed"
    assert result["development_quote"] == "Our model was trained by Example Lab."
    assert result["sha"] == "a" * 40
    assert calls[-1].url.path == "/examplelab/speech/raw/" + "a" * 40 + "/README.md"
    assert result["identity_namespace"] == "examplelab"


@pytest.mark.parametrize("credit", ["Cohere", "Cohere and Cohere Labs"])
def test_verified_parent_company_binds_research_publisher_to_exact_x_account(credit):
    def respond(request):
        path = request.url.path
        if path == "/api/quicksearch":
            return httpx.Response(200, json={"orgs": [{"name": "CohereLabs"}]})
        if path.endswith("/overview"):
            ns = path.split("/")[-2]
            return httpx.Response(200, json={"name": ns, "fullname": "Cohere Labs" if ns == "coherelabs" else "Cohere", "isVerified": True})
        if path in {"/cohere", "/coherelabs"}:
            handle = "cohere" if path == "/cohere" else "Cohere_Labs"
            return httpx.Response(200, text=f'<a class="leading-snug" href="https://twitter.com/{handle}">X</a><a class="leading-snug" href="https://cohere.com/research">Website</a>')
        if path == "/api/models":
            return httpx.Response(200, json=[] if request.url.params["author"] == "cohere" else [{"id": "CohereLabs/command", "sha": "a" * 40, "private": False, "siblings": [{"rfilename": "model.safetensors"}]}])
        return httpx.Response(200, text=f"- **Developed by:** {credit}")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = verify(evidence("cohere"), {"organization_name": "Cohere"}, client=client)
    assert result["outcome"] == "passed"
    assert result["identity_namespace"] == "cohere" and result["namespace"] == "coherelabs"


def test_developer_credit_cannot_match_host_name_elsewhere_or_name_prefix():
    assert development_quote("Developed by Meta, hosted by Example Lab", "Example Lab", "examplelab") == ""
    assert development_quote("Developed by Example Laboratory impostor", "Example Lab", "examplelab") == ""
    assert development_quote("finetuned by Abacus.AI. Training data is private.", "Abacus.AI, Inc.", "abacusai")
    assert development_quote("Model developer: Cohere and Cohere Labs", "Cohere Labs", "CohereLabs")


def test_request_and_response_caps_are_physical_and_fail_closed():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="x" * (1024 * 1024 + 1)))) as client:
        api = PublicHF(client, max_requests=1)
        assert api.get("/examplelab", text=True) is None
        assert api.get("/other", text=True) is None
        assert len(api.observations) == 1 and api.observations[0]["outcome"] == "response_cap"


@pytest.mark.parametrize("valid_model_decision", [True, False])
@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_hf_exception_registers_but_forged_stale_or_ordinary_model_proofs_cannot(monkeypatch, valid_model_decision):
    from core import official_company_hf
    from core.models import Account, OfficialCompanyListIntent
    from core.official_company_accounts import (
        enqueue_account,
        evaluate_account,
        register_account,
    )
    from tests.test_official_company_cycle import accept
    from x_monitor.config import OfficialCompanyConfig

    cfg = OfficialCompanyConfig(enabled=True, registration_enabled=True, hf_verification_enabled=True,
                                max_usd_per_cycle=Decimal(1), max_usd_per_day=Decimal(1))
    a = Account.objects.create(author_id="918321", handle="examplelab", bio="We develop our own speech models.")
    state = enqueue_account(a)
    call = accept if valid_model_decision else lambda *args: {"invalid": True, "usage": {"input_tokens": 10, "output_tokens": 10}}
    assert evaluate_account(state.pk, cfg=cfg, call=call, budget_scope="hf-proof")
    state.refresh_from_db()
    attempt_decision = state.attempt_records.get().decision
    assert state.status == "review_needed" and register_account(state.pk, cfg=cfg) is None
    state.decision["hf_verification"] = {"outcome": "passed", "signature": "forged"}
    state.save()
    state.status = "accepted"
    state.save()
    assert register_account(state.pk, cfg=cfg) is None
    state.refresh_from_db()
    # Use the real verifier transport; only network transport is replaced.
    original = official_company_hf.verify
    route, _ = transport()

    def local_verify(ev, decision, **kwargs):
        with httpx.Client(transport=route) as client:
            return original(ev, decision, client=client, **kwargs)

    monkeypatch.setattr(official_company_hf, "verify", local_verify)
    result = official_company_hf.verify_review_candidates(limit=1)
    assert result == {"checked": 1, "approved": 1}
    state.refresh_from_db()
    assert official_company_hf.approved(state)
    saved_hash = state.evidence_hash
    state.evidence_hash = "changed"
    state.save()
    assert register_account(state.pk, cfg=cfg) is None
    state.refresh_from_db()
    state.evidence_hash = saved_hash
    state.status = "accepted"
    state.save()
    assert register_account(state.pk, cfg=cfg) is not None
    state.refresh_from_db()
    assert state.status == "registered"
    assert state.decision["organization_name"] == "Example Lab"
    intent = OfficialCompanyListIntent.objects.get(account=a)
    assert intent.state == state
    assert state.attempt_records.get().decision == attempt_decision
    assert official_company_hf.verify_review_candidates(limit=1) == {"checked": 0, "approved": 0}


def test_canonical_hf_namespace_avoids_redirect_without_following_arbitrary_location():
    paths = []
    def respond(request):
        paths.append(request.url.path)
        if request.url.path == "/api/quicksearch":
            return httpx.Response(200, json={"orgs": []})
        if request.url.path.endswith("/overview"):
            return httpx.Response(200, json={"name": "ExampleLab", "fullname": "Example Lab", "isVerified": True})
        assert request.url.path == "/ExampleLab"
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/secrets"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = verify(evidence(), {"organization_name": "Example Lab"}, client=client)
    assert result["outcome"] == "review_needed" and paths[-1] == "/ExampleLab"
    assert len(paths) == 3


def test_readme_only_repository_does_not_prove_a_released_model():
    route, calls = transport()
    def respond(request):
        response = route.handle_request(request)
        if request.url.path == "/api/models":
            row = json.loads(response.content)[0]
            row["siblings"] = [{"rfilename": "README.md"}]
            return httpx.Response(200, json=[row])
        return response
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = verify(evidence(), {"organization_name": "Example Lab"}, client=client)
    assert result["outcome"] == "review_needed"
    assert not any(call.url.path.endswith("README.md") for call in calls)


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_missing_private_key_stops_before_hf_network_or_approval(monkeypatch):
    from unittest.mock import Mock

    from core import official_company_hf
    monkeypatch.delenv(official_company_hf.KEY_ENV)
    network = Mock(side_effect=AssertionError("must not dispatch"))
    monkeypatch.setattr(official_company_hf, "verify", network)
    assert official_company_hf.verify_review_candidates() == {"checked": 0, "approved": 0, "status": "signing_key_unavailable"}
    network.assert_not_called()


def test_null_handle_and_invalid_review_name_do_not_crash_discovery():
    route, calls = transport()
    with httpx.Client(transport=route) as client:
        result = verify({**evidence(), "handle": None}, {}, client=client)
        assert result["outcome"] == "review_needed" and calls == []
        result = verify(evidence(), {"organization_name": 42}, client=client)
    assert result["outcome"] == "passed"


@pytest.mark.parametrize("quote", ["Developed by [Cohere](https://cohere.com/).", "- **Model developer:** [Cohere](https://cohere.com/)."])
def test_parent_credit_link_must_match_verified_publisher_website_and_name(quote):
    assert development_quote(quote, 'Cohere Labs', 'CohereLabs', publisher_urls=['https://cohere.com/research']) == quote
    assert not development_quote(quote, 'Cohere Labs', 'CohereLabs', publisher_urls=['https://impostor.ai'])
    assert not development_quote(quote, 'Unrelated Labs', 'unrelatedlabs', publisher_urls=['https://cohere.com'])
    assert not development_quote('Developed by [Meta](https://meta.com/).', 'Meta Labs', 'metalabs', publisher_urls=['https://metalabs.ai'])
