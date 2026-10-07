from types import SimpleNamespace

import pytest

from core.official_company_accounts import (
    build_evidence,
    validate_decision,
    x_account_identifier,
)


def account(**values):
    return SimpleNamespace(
        author_id="123",
        handle="examplelab",
        display_name="Example Lab",
        bio="",
        description="",
        profile_bio_text="",
        **values,
    )


def test_nested_profile_and_old_post_are_retained():
    evidence = build_evidence(
        account(),
        [
            {
                "id": "old-post",
                "text": "We release our image generation model.",
                "profile_bio": {
                    "description": "We develop AI models",
                    "entities": {
                        "url": {"urls": [{"expanded_url": "https://example.ai"}]}
                    },
                },
            }
        ],
    )
    assert any(s["text"] == "We develop AI models" for s in evidence["sources"])
    assert "example.ai" in evidence["domains"]
    assert any("image generation" in s["text"] for s in evidence["sources"])
    assert evidence["provider"] == "x"


def test_identity_boundary_rejects_non_x_even_with_same_id():
    assert x_account_identifier(account()) == "123"
    with pytest.raises(ValueError, match="provider"):
        x_account_identifier(account(), provider="hf")


def test_acceptance_requires_grounded_evidence_for_all_identity_claims():
    evidence = build_evidence(
        account(),
        [
            {
                "id": "1",
                "text": "We are Example Lab, releasing our own speech model today.",
            }
        ],
    )
    source = next(s for s in evidence["sources"] if s["id"] == "post:1")
    citation = {"source_id": source["id"], "quote": source["text"]}
    decision = {
        "outcome": "accepted",
        "organization_name": "Example Lab",
        "model_types": ["speech"],
        "rationale": "First-party organization and model release.",
        "contradictions": [],
        "claims": {
            "organization": [citation],
            "official_account": [citation],
            "model_developer": [citation],
        },
    }
    assert validate_decision(decision, evidence)["outcome"] == "accepted"
    decision["claims"]["model_developer"] = [
        {"source_id": "not-supplied", "quote": "invented"}
    ]
    with pytest.raises(ValueError, match="citation"):
        validate_decision(decision, evidence)


def test_evidence_hash_ignores_post_order_and_follower_counts():
    rows = [
        {"id": "1", "text": "Research update"},
        {"id": "2", "text": "New audio model"},
    ]
    a = account()
    a.followers_count = 1
    first = build_evidence(a, rows)
    a.followers_count = 9000
    assert first["identity"] == build_evidence(a, list(reversed(rows)))["identity"]


@pytest.mark.parametrize("kind", ["model", "agent", "harness"])
def test_own_product_development_can_use_third_party_models_without_hf(kind):
    evidence = build_evidence(account(), [{"id": "1", "text": f"We are Example Lab. We develop our own {kind}, using an open-weight base."}])
    citation = {"source_id": "post:1", "quote": evidence["sources"][0]["text"]}
    decision = {
        "outcome": "accepted", "organization_name": "Example Lab",
        "development_type": kind, "model_types": ["speech"] if kind == "model" else [],
        "rationale": "Our own developed product, without an HF requirement.", "contradictions": [],
        "claims": {key: [citation] for key in ["organization", "official_account", "product_developer"]},
    }
    assert validate_decision(decision, evidence)["development_type"] == kind
    decision["claims"]["product_developer"] = [{"source_id": "unknown", "quote": "unsupported developer"}]
    with pytest.raises(ValueError, match="citation"):
        validate_decision(decision, evidence)


def test_prompt_policy_change_preserves_existing_evidence_identity(monkeypatch):
    from core import official_company_accounts

    rows = [{"id": "1", "text": "We develop our own speech models."}]
    before = build_evidence(account(), rows)
    monkeypatch.setattr(official_company_accounts, "POLICY_VERSION", "future-evaluator")
    after = build_evidence(account(), rows)
    assert after == before
    assert after["policy_version"] == "official-model-developer-v2"


def test_known_positive_evidence_is_read_without_attestation_shortcut():
    import json
    from pathlib import Path

    source = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/research/2026-10-06-100039-official-company-account-evidence.json"
        ).read_text()
    )
    for row in source["accounts"]:
        a = account()
        a.author_id, a.handle = row["author_id"], row["handle"]
        posts = [
            {
                "id": p["tweet_id"],
                "text": p["text"],
                "profile_bio": p.get("author_profile_bio"),
            }
            for p in source["posts"]
            if p["author_id"] == a.author_id
        ]
        evidence = build_evidence(a, posts)
        assert evidence["sources"]
        assert evidence["domains"]
        assert "owner_verified_official" not in evidence


@pytest.mark.parametrize(
    "bad_profile",
    [
        None,
        [],
        "",
        {"entities": []},
        {"entities": {"url": None}},
        {
            "entities": {
                "url": {"urls": [None, "bad", {"expanded_url": "javascript:alert(1)"}]}
            }
        },
    ],
)
def test_malformed_profile_does_not_invent_domain(bad_profile):
    evidence = build_evidence(
        account(), [{"id": "1", "text": "Known text", "profile_bio": bad_profile}]
    )
    assert evidence["domains"] == []
    assert evidence["sources"] == [{"id": "post:1", "text": "Known text"}]


def test_owner_amended_candidate_prompt_is_versioned_and_pinned():
    import hashlib

    from core.official_company_accounts import POLICY_VERSION, SYSTEM_PROMPT

    assert POLICY_VERSION == "official-ai-product-developer-v3"
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest() == "79c370c67f9717bd408b60210b4f8262d3b93817c03504c89f4dc135dc972c7d"


@pytest.mark.parametrize("signal", ["blockchain", "Web3", "web-3", "区块链", "ブロックチェーン"])
def test_blockchain_risk_changes_prompt_without_changing_eligibility_or_base_prompt(signal):
    from core.official_company_accounts import (
        BLOCKCHAIN_POLICY_VERSION,
        POLICY_VERSION,
        SYSTEM_PROMPT,
        evaluator_prompt,
    )

    ordinary = build_evidence(account(), [{"id": "1", "text": "We trained and released our own speech model."}])
    assert evaluator_prompt(ordinary) == (SYSTEM_PROMPT, POLICY_VERSION)
    risky = build_evidence(account(), [{"id": "1", "text": "We trained and released our own speech model. " + signal}])
    prompt, policy = evaluator_prompt(risky)
    assert prompt.startswith(SYSTEM_PROMPT)
    assert policy == BLOCKCHAIN_POLICY_VERSION
    assert "higher technical-evidence hurdle" in prompt and "Blockchain association alone" in prompt
