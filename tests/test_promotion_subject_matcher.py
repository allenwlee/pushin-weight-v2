"""The promotion filter reads subject evidence, independently of post attribution."""

from copy import deepcopy

import pytest

from monitor.promotion_subject_matcher import (
    PromotionSubjectMatcher,
    load_matching_config,
    parse_matching_config,
)

CATALOG = [
    {"brand_id": "minimax", "aliases": ["MiniMax", "海螺"], "keywords": ["智能", "H3"],
     "products": ["MiniMax-H3"], "domains": ["minimax.io"],
     "handles": ["MiniMaxAgent", "ResearchPerson"],
     "accounts": [{"handle": "MiniMaxAgent", "role": "official"},
                  {"handle": "ResearchPerson", "role": "staff"}]},
    {"brand_id": "doubao", "aliases": ["Doubao", "Seedance"], "keywords": ["Seedance"],
     "products": ["ArbitraryProduct"], "domains": []},
    {"brand_id": "llama", "aliases": ["Meta"], "keywords": ["Meta"]},
    {"brand_id": "kimi", "aliases": ["Kimi"], "keywords": ["K2"]},
    {"brand_id": "qwen", "aliases": ["Qwen"]},
    {"brand_id": "deepseek", "aliases": ["DeepSeek"]},
    {"brand_id": "glm", "aliases": ["GLM"]},
    {"brand_id": "hunyuan", "aliases": ["Hunyuan"]},
    {"brand_id": "kuaishou", "keywords": ["Kling"]},
    {"brand_id": "nemo_megatron", "keywords": ["RAPIDS"]},
]


def _document():
    return {
        "version": 1,
        "global_excluded_terms": [],
        "brands": {
            "llama": {"excluded_terms": ["Meta"], "extra_terms": []},
            "minimax": {"excluded_terms": ["智能"], "extra_terms": []},
            "doubao": {"excluded_terms": [], "extra_terms": ["Dreamina", "CapCut"]},
        },
    }


def _matcher(catalog=CATALOG):
    return PromotionSubjectMatcher(catalog, config=parse_matching_config(_document()))


@pytest.mark.parametrize("name,owner", [
    ("MiniMax H3-Image", "minimax"), ("Kimi K3.1 Pro", "kimi"),
    ("Qwen Code", "qwen"), ("DeepSeek V4.1 Flash", "deepseek"),
    ("Seedance2.0", "doubao"), ("Qwen3-Coder", "qwen"),
    ("DeepSeekV3", "deepseek"), ("GLM4.5", "glm"),
    ("Hunyuan3D", "hunyuan"), ("Kling Video", "kuaishou"),
    ("RAPIDS CUDA", "nemo_megatron"), ("海螺AI", "minimax"),
    ("Dreamina Studio", "doubao"), ("CapCut app", "doubao"),
])
def test_containment_terms_are_owned_and_boundary_aware(name, owner):
    match = _matcher().match({"name": name})
    assert match is not None
    assert match.tier == "containment"
    assert match.owners == (owner,)
    assert match.matched_term
    assert len(match.matcher_revision) == 64


@pytest.mark.parametrize("name", [
    "Kimiko Labs", "Metaverse Hub", "Token Machine", "B.AI", "Meta Ads",
    "Meta AI Glasses", "人工智能应用", "K2 Think", "ArbitraryProduct Pro",
])
def test_noisy_or_product_terms_do_not_contain_match(name):
    assert _matcher().match({"name": name}) is None


@pytest.mark.parametrize("name,owner", [
    ("Meta", "llama"), ("K2", "kimi"), ("智能", "minimax"),
    ("ArbitraryProduct", "doubao"), ("  ＭｉｎｉＭａｘ  ", "minimax"),
])
def test_exact_tier_keeps_excluded_terms_and_products(name, owner):
    match = _matcher().match({"name": name})
    assert match.tier == "exact"
    assert match.owners == (owner,)


@pytest.mark.parametrize("subject,owner", [
    ({"handle": "@MiniMaxAgent"}, "minimax"),
    ({"handle": "@deepseek_airdrop"}, "deepseek"),
    ({"handle": "@ResearchPerson"}, "minimax"),
    ({"domain": "https://platform.minimax.io/"}, "minimax"),
    ({"domain": "seedance-pro.app"}, "doubao"),
])
def test_handle_and_domain_evidence(subject, owner):
    assert _matcher().match(subject).owners == (owner,)


@pytest.mark.parametrize("subject", [
    {"handle": "@kimikodev"}, {"handle": "@ResearchPerson_news"},
    {"account_handle": "deepseek_airdrop"}, {"domain": "github.com/deepseek-ai"},
    {"domain": "deepseek.example.com"}, {"domain": "seedancely.app"},
])
def test_handles_and_domains_do_not_expand_other_evidence(subject):
    assert _matcher().match(subject) is None


def test_company_terms_and_multiple_owners_are_reported_without_mutating_catalog():
    original = deepcopy(CATALOG)
    matcher = PromotionSubjectMatcher(
        CATALOG, config=parse_matching_config(_document()),
        company_terms={"doubao": ["ByteDance"], "qwen": ["ByteDance"]},
    )
    match = matcher.match({"name": "ByteDance tools"})
    assert match.owners == ("doubao", "qwen")
    assert match.as_dict()["matched_term"] == "ByteDance"
    assert CATALOG == original


def test_revision_covers_terms_and_config_and_is_order_independent():
    a = _matcher()
    assert a.revision == _matcher(list(reversed(CATALOG))).revision
    changed = deepcopy(CATALOG)
    changed[0]["aliases"].append("NewIdentity")
    assert a.revision != _matcher(changed).revision
    document = _document()
    document["brands"]["doubao"]["extra_terms"].append("NewTool")
    assert a.revision != PromotionSubjectMatcher(
        CATALOG, config=parse_matching_config(document)
    ).revision


@pytest.mark.parametrize("change", [
    lambda d: d.update(unknown=True),
    lambda d: d.update(version=2),
    lambda d: d.update(version=True),
    lambda d: d["brands"].update(nonexistent={"extra_terms": ["Thing"]}),
    lambda d: d["brands"]["minimax"].update(extra_terms=[""]),
    lambda d: d["brands"]["minimax"].update(extra_terms=["Name", "name"]),
    lambda d: d["brands"]["minimax"].update(unknown=[]),
])
def test_config_rejects_invalid_shape_or_registry(change):
    document = _document()
    change(document)
    with pytest.raises(ValueError):
        parse_matching_config(document, known_brand_ids={r["brand_id"] for r in CATALOG})


def test_loader_rejects_duplicate_yaml_keys_and_hashes_source_bytes(tmp_path):
    path = tmp_path / "matching.yaml"
    path.write_text("version: 1\nversion: 1\nglobal_excluded_terms: []\nbrands: {}\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_matching_config(path)
    path.write_text("version: 1\nglobal_excluded_terms: []\nbrands: {}\n")
    config = load_matching_config(path)
    assert len(config.digest) == 64
    assert config == load_matching_config(path)


def test_discard_and_strict_publication_share_the_matcher_and_return_discard_evidence():
    from monitor.classification_persistence import (
        _subject_is_tracked,
        discard_tracked_promotion_subjects,
    )

    subjects = [
        {"name": name, "handle": None, "domain": None, "account_handle": None, "evidence": name}
        for name in ("MiniMax H3-Image", "Unrelated Rewards")
    ]
    result = {"promoted_subjects": subjects, "untracked_brand_promotions": ["general"]}
    matcher = _matcher()
    assert _subject_is_tracked(subjects[0], CATALOG, matcher=matcher)
    records = []
    trimmed = discard_tracked_promotion_subjects(result, CATALOG, matcher=matcher, discard_records=records)
    assert trimmed["promoted_subjects"] == subjects[1:]
    assert result["promoted_subjects"] == subjects
    assert records[0]["subject"] == subjects[0]
    assert records[0]["owners"] == ["minimax"]
    assert records[0]["tier"] == "containment"


def test_shared_company_term_discards_a_subject_with_multiple_owners():
    from monitor.classification_persistence import discard_tracked_promotion_subjects

    matcher = PromotionSubjectMatcher(
        CATALOG, config=parse_matching_config(_document()),
        company_terms={"doubao": ["ByteDance"], "qwen": ["ByteDance"]},
    )
    subject = {"name": "ByteDance tools", "handle": None, "domain": None,
               "account_handle": None, "evidence": "ByteDance tools"}
    records = []
    result = discard_tracked_promotion_subjects(
        {"promoted_subjects": [subject], "untracked_brand_promotions": ["general"]},
        CATALOG, matcher=matcher, discard_records=records,
    )
    assert result["promoted_subjects"] == result["untracked_brand_promotions"] == []
    assert records[0]["owners"] == ["doubao", "qwen"]


def test_system_check_reports_invalid_config_without_weakening_validation(tmp_path):
    from monitor.checks import check_promotion_subject_matching_config

    path = tmp_path / "invalid.yaml"
    path.write_text("version: 1\nglobal_excluded_terms: []\nbrands:\n  absent: {}\n")
    errors = check_promotion_subject_matching_config(config_path=path, known_brand_ids={"minimax"})
    assert len(errors) == 1
    assert errors[0].id == "monitor.E051"
    assert "unknown brand" in errors[0].msg


def test_legacy_publication_drops_a_subject_owned_by_two_tracked_brands():
    """Legacy (two_role) normalization drops a shared-name subject instead of
    raising classification_promotion_identity_ambiguous (2026-11-24)."""
    from monitor.classification_persistence import discard_tracked_promotion_subjects

    subject = {"name": "Muse", "handle": None, "domain": None, "account_handle": None, "evidence": "Try Muse."}
    result = {"valid": True, "promoted_subjects": [subject], "untracked_brand_promotions": ["general"]}
    catalog = [{"brand_id": b, "aliases": ["Muse"], "products": [], "keywords": []} for b in ("deepseek", "another-brand")]
    records = []
    normalized = discard_tracked_promotion_subjects(result, catalog, discard_records=records)
    assert normalized["promoted_subjects"] == []
    assert normalized["untracked_brand_promotions"] == []
    assert sorted(records[0]["owners"]) == ["another-brand", "deepseek"]
