"""Regression cases from the November 5 production coverage audit."""

from pathlib import Path

import pytest

from x_monitor.attribution import (
    attribute_to_brands,
    compile_keyword_index,
    detect_brand_mentions,
)
from x_monitor.harvest_policy import load_policy
from x_monitor.query_plan import plan_calls
from x_monitor.specs_from_policy import (
    active_policy_tokens,
    primary_keywords_from_policy,
    specs_from_policy,
)

POLICY = Path(__file__).resolve().parents[1] / "config/harvest_policy.yaml"


def keyword_index():
    policy = load_policy(POLICY)
    rows = [
        (b, t, False)
        for b, terms in active_policy_tokens(policy).items()
        for t in terms
    ]
    return compile_keyword_index(rows, policy=policy)


@pytest.mark.parametrize(
    "brand,text",
    [
        ("doubao", "seedance 2.5 looks noticeably clearer"),
        ("doubao", "Seedream edit model"),
        ("kuaishou", "Kling 4.0 Flash is now live on fal"),
        ("mistral", "Llama 4 和 Codestral"),
        ("mistral", "Ministral released"),
        ("mistral", "Mistralのモデル"),
        ("stepfun", "the full @StepFun_ai Step 5"),
        ("stepfun", "StepAudio 3"),
        ("hunyuan", "Hy4真的比deepseek-v4.1-flash 强么？"),
        ("hunyuan", "HunyuanVideo released"),
        ("hunyuan", "看完Hunyuan4的blog"),
        ("hunyuan", "混元3之后"),
        ("exaone", "EXAONE입니다"),
        ("moonshot_kimi", "K3.1 Pro from Modal"),
        ("moonshot_kimi", "Kimi今天更新了"),
        ("moonshot_kimi", "可以跟 kimi3.1pro 不相上下"),
        ("ernie", "文心才是世界上最好的 AI！"),
        ("sakana_ai", "SakanaAI released Namazu"),
        ("sakana_ai", "ShinkaEvolve released"),
        ("inclusionai", "Ring-2.6-1T released"),
        ("exaone", "EXAONEを試した"),
        ("mimo", "MiMo新版本"),
        ("mimo", "Xiaomi AI research"),
        ("mimo", "小米大模型更新"),
        ("sensechat", "SenseNova U1"),
        ("upstage", "Solar Open released"),
        ("yi", "万智 Wanzhi"),
        ("dots", "DotsOCR released"),
    ],
)
def test_archived_misses_and_portfolio_controls(brand, text):
    assert brand in detect_brand_mentions(text, keyword_index())


def test_nine_calls_including_list_with_complete_time_bounds():
    policy = load_policy(POLICY)
    calls = plan_calls(
        "1956117777936941342",
        specs_from_policy(policy),
        primary_keywords=primary_keywords_from_policy(policy),
        excluded_author_handles=("xxyweb3",),
    )
    assert len(calls) == 9
    assert {c.call_id for c in calls} == {"A", "B1", "B2", "B3", "C1", "C2", "C3", "C4", "B4"}
    for call in calls:
        assert (
            len((call.query_string + " since_time:1792807200 until_time:1792808100").encode("utf-8"))
            <= 512
        )


def test_policy_handle_mention_and_observed_link_have_durable_evidence():
    post = {
        "tweet_id": "101",
        "created_at": "2026-11-04T10:00:00Z",
        "text": "@StepFun_ai thanks for this",
        "entities": {
            "user_mentions": [{"screen_name": "StepFun_ai"}],
            "urls": [{"expanded_url": "https://github.com/SakanaAI/ShinkaEvolve"}],
        },
    }
    mentions = attribute_to_brands(post, {}, {}, keyword_index(), [], {})
    assert ("stepfun", "user_mention") in {(m.brand_id, m.source) for m in mentions}
    assert ("sakana_ai", "url_keyword") in {(m.brand_id, m.source) for m in mentions}


def _clauses(query):
    """Independent Boolean implication check; not a simulation of X tokenization."""
    import re

    tokens = re.findall(r'"[^"]*"|\(|\)|[^\s()]+', query)
    tokens = [t.casefold() if t != "OR" else t for t in tokens if t != "min_faves:0"]
    pos = 0

    def either():
        nonlocal pos
        result = both()
        while pos < len(tokens) and tokens[pos] == "OR":
            pos += 1
            result += both()
        return result

    def both():
        nonlocal pos
        result = [frozenset()]
        while pos < len(tokens) and tokens[pos] not in ("OR", ")"):
            if tokens[pos] == "(":
                pos += 1
                factor = either()
                assert tokens[pos] == ")"
                pos += 1
            else:
                token = re.sub(r"(?<=\w)-(?=\w)", " ", tokens[pos])
                # The live Hy4 probe establishes word separation, not joining.
                # Quoted phrases stay phrases; unquoted hyphens imply AND.
                factor = [
                    frozenset([token] if token.startswith('"') else token.split())
                ]
                pos += 1
            result = [a | b for a in result for b in factor]
        return result

    clauses = either()
    assert pos == len(tokens)
    return clauses


def _phrase_words(clause):
    import re

    return clause | {
        word
        for atom in clause
        for word in re.sub(r"(?<=\w)-(?=\w)", " ", atom.strip('"')).split()
    }


def test_every_old_query_branch_is_preserved_or_broadened():
    import json

    from x_monitor.query_plan import _build_query

    old = json.loads(
        (
            POLICY.parents[1] / "tests/golden/harvest_before_portfolio_queries.json"
        ).read_text()
    )
    new = [
        c
        for spec in specs_from_policy(load_policy(POLICY))
        for c in _clauses(_build_query(spec))
    ]
    for call, query in old.items():
        if call == "A":
            continue
        for clause in _clauses(query):
            facts = _phrase_words(clause)
            assert any(candidate <= facts for candidate in new), (call, clause)


def test_all_78_nvidia_aliases_still_satisfy_a_search_branch():
    from x_monitor.query_plan import _build_query

    policy = load_policy(POLICY)
    clauses = [c for s in specs_from_policy(policy) for c in _clauses(_build_query(s))]
    for alias in policy.brands["nemo_megatron"].all_c_bare_aliases:
        facts = _phrase_words(frozenset([f'"{alias.casefold()}"', alias.casefold()]))
        assert any(c <= facts for c in clauses), alias


@pytest.mark.parametrize(
    "brand,term,context",
    [
        ("glm", "GLM-5", "model"),
        ("llama", "Muse", "AI"),
        ("minimax", "海螺", "AI"),
    ],
)
def test_preserved_contexts_still_reject_bare_terms(brand, term, context):
    from x_monitor.query_plan import _build_query

    specs = specs_from_policy(load_policy(POLICY), brand_nicknames=[brand])
    clauses = [c for spec in specs for c in _clauses(_build_query(spec))]
    bare = _phrase_words(frozenset([term.casefold()]))
    assert not any(c <= bare for c in clauses)
    assert any(c <= bare | {context.casefold()} for c in clauses)


def test_packing_is_deterministic_and_whole_brand_groups_stay_together():
    from dataclasses import replace

    from x_monitor.query_plan import _build_query

    p = load_policy(POLICY)
    baseline = specs_from_policy(p)
    reordered = replace(p, brands=dict(reversed(list(p.brands.items()))))
    assert [(s.call_id, _build_query(s), s.component_names) for s in baseline] == [
        (s.call_id, _build_query(s), s.component_names)
        for s in specs_from_policy(reordered)
    ]
    names = [n for s in baseline for n in s.component_names]
    assert len(names) == len(set(names))
    assert {n for n in names if "/" not in n} == set(p.brands) - {"nemo_megatron"}
    for brand in p.brands:
        subset = specs_from_policy(p, brand_nicknames=[brand])
        assert {s.call_id for s in subset} == {
            s.call_id
            for s in baseline
            if any(n.split("/")[0] == brand for n in s.component_names)
        }


def test_brand_replacement_changes_only_its_explicit_group():
    from dataclasses import replace

    from x_monitor.harvest_policy import BrandPolicy
    from x_monitor.query_plan import _build_query

    p = load_policy(POLICY)
    brands = {k: v for k, v in p.brands.items() if k != "mimo"}
    brands["new_lab"] = BrandPolicy("new_lab", frozenset({"bare"}), tokens=("NewLab",))
    pool = p.query_pools[0]
    groups = tuple(
        replace(
            group, blocks=tuple("new_lab" if b == "mimo" else b for b in group.blocks)
        )
        for group in pool.groups
    )
    specs = specs_from_policy(
        replace(p, brands=brands, query_pools=(replace(pool, groups=groups),))
    )
    names = {n for s in specs for n in s.component_names}
    assert "mimo" not in names and "new_lab" in names
    assert len(specs) == 8
    before = {s.call_id: _build_query(s) for s in specs_from_policy(p)}
    after = {s.call_id: _build_query(s) for s in specs}
    assert all(after[call] == query for call, query in before.items() if call != "B4")


def test_budget_overflow_fails_before_planning_or_provider_calls():
    from dataclasses import replace

    p = load_policy(POLICY)
    pool = p.query_pools[0]
    group = replace(
        pool.groups[0], blocks=tuple(b for g in pool.groups for b in g.blocks)
    )
    p = replace(p, query_pools=(replace(pool, groups=(group,)),))
    with pytest.raises(ValueError, match="exceeds 512"):
        specs_from_policy(p)


def test_oversized_brand_requires_named_split_instead_of_silent_slicing():
    from dataclasses import replace

    from x_monitor.harvest_policy import BrandPolicy

    p = load_policy(POLICY)
    brands = dict(p.brands)
    brands["new_lab"] = BrandPolicy(
        "new_lab",
        frozenset({"bare"}),
        tokens=tuple(f"LongNewModel{i}" for i in range(60)),
    )
    with pytest.raises(ValueError, match="split into named groups"):
        specs_from_policy(replace(p, brands=brands))


def test_empty_active_brand_cannot_silently_disappear():
    from dataclasses import replace

    from x_monitor.harvest_policy import BrandPolicy

    p = load_policy(POLICY)
    brands = dict(
        p.brands, new_lab=BrandPolicy("new_lab", frozenset({"co"}), co=("AI",))
    )
    with pytest.raises(ValueError, match="no searchable aliases or handles"):
        specs_from_policy(replace(p, brands=brands))


@pytest.mark.parametrize("duplicate", [False, True])
def test_explicit_groups_reject_missing_or_duplicate_ownership(duplicate):
    from dataclasses import replace

    p = load_policy(POLICY)
    pool = p.query_pools[0]
    first = pool.groups[0]
    blocks = (*first.blocks, first.blocks[0]) if duplicate else first.blocks[1:]
    changed = replace(pool, groups=(replace(first, blocks=blocks), *pool.groups[1:]))
    with pytest.raises(
        ValueError, match="more than once" if duplicate else "ownership mismatch"
    ):
        specs_from_policy(replace(p, query_pools=(changed,)))


def test_every_official_handle_is_an_independent_ungated_search_branch():
    from x_monitor.query_plan import _build_query

    p = load_policy(POLICY)
    for brand in p.brands.values():
        if "handle" not in brand.paths:
            continue
        clauses = [
            c
            for spec in specs_from_policy(p, brand_nicknames=[brand.nickname])
            for c in _clauses(_build_query(spec))
        ]
        for handle in brand.handles:
            assert frozenset(["@" + handle.casefold()]) in clauses, (
                brand.nickname,
                handle,
            )


def test_xiaomi_company_context_does_not_gate_mimo_or_handles():
    from x_monitor.query_plan import _build_query

    p = load_policy(POLICY)
    clauses = [
        c
        for spec in specs_from_policy(p, brand_nicknames=["mimo"])
        for c in _clauses(_build_query(spec))
    ]
    assert frozenset(["mimo"]) in clauses
    assert frozenset(["@xiaomimimo"]) in clauses
    assert frozenset(["xiaomi", "ai"]) in clauses
    assert frozenset(["小米", "大模型"]) in clauses
    assert not any(c <= {"xiaomi"} or c <= {"小米"} for c in clauses)
    assert "mimo" not in detect_brand_mentions(
        "Xiaomi quarterly earnings", keyword_index()
    )


def test_redundant_hyphen_branches_are_removed_but_aliases_remain():
    from x_monitor.query_plan import _build_query

    p = load_policy(POLICY)
    queries = " ".join(_build_query(s) for s in specs_from_policy(p))
    for redundant in [
        "Hy4-preview",
        "Hy5-preview",
        "GLM-4",
        "GLM-5",
        "GLM-6",
        "Yi-VL",
        "Yi-Coder",
        "PaddleOCR-VL",
        "K-EXAONE",
        '"dots-3-note"',
    ]:
        assert redundant not in queries
    for brand, text in [
        ("hunyuan", "Hy5-preview"),
        ("glm", "GLM-5 model"),
        ("yi", "Yi-Coder"),
        ("ernie", "PaddleOCR-VL"),
        ("exaone", "K-EXAONE"),
    ]:
        assert brand in detect_brand_mentions(text, keyword_index())
    # Hyphenated names without a covering base remain; concatenation is distinct.
    assert "Step-Audio" in queries and "StepAudio" in queries
    assert "OxAlpha" in queries and "ox-alpha" in queries


def test_future_giants_use_independent_budget_and_do_not_repack_tracked_brands():
    from dataclasses import replace

    from x_monitor.harvest_policy import BrandPolicy, QueryGroup, QueryPool
    from x_monitor.query_plan import _build_query
    from x_monitor.specs_from_policy import validate_derived_call_ids

    p = load_policy(POLICY)
    before = {s.call_id: _build_query(s) for s in specs_from_policy(p)}
    brands = dict(p.brands)
    for name, term in [("openai", "OpenAI"), ("anthropic", "Anthropic")]:
        brands[name] = BrandPolicy(
            name, frozenset({"bare"}), tokens=(term,), query_pool="giants"
        )
    candidate = replace(
        p,
        brands=brands,
        query_pools=(
            *p.query_pools,
            QueryPool(
                "giants", (QueryGroup("GIANTS_1", "Giants", ("openai", "anthropic")),)
            ),
        ),
    )
    after = {
        s.call_id: _build_query(s)
        for s in validate_derived_call_ids(
            specs_from_policy(candidate), policy=candidate
        )
    }
    assert {k: after[k] for k in before} == before
    assert set(after) - set(before) == {"GIANTS_1"}
    assert "OpenAI" in after["GIANTS_1"] and "Anthropic" in after["GIANTS_1"]


@pytest.mark.parametrize(
    "text",
    [
        "Kimimania",
        "myMiMoApp",
        "EXAONEish",
        "notStepFun",
        "MiMoé",
        "αMiMo",
        "abc@StepFun_ai.example",
    ],
)
def test_no_embedded_name_or_email_handle_matches(text):
    post = {"tweet_id": "101", "created_at": "now", "text": text}
    assert not any(
        m.brand_id for m in attribute_to_brands(post, {}, {}, keyword_index(), [], {})
    )


@pytest.mark.parametrize(
    "text,brands,expected",
    [
        ("Meta model F1", ["llama"], True),
        ("Meta model F1 with Hunyuan", ["llama", "hunyuan"], False),
        ("Meta model F1 with DotsOCR", ["llama", "dots"], False),
        ("Hunyuan F1 comparison", ["hunyuan"], False),
        ("@AIatMeta F1", ["llama"], False),
        ("Meta model release", ["llama"], False),
    ],
)
def test_packed_post_filters_do_not_leak_between_brands(text, brands, expected):
    from monitor.cycle import _excluded_by_call

    p = load_policy(POLICY)
    call = next(c for c in plan_calls("1", specs_from_policy(p)) if c.brand_not_include)
    assert _excluded_by_call({"text": text, "brand_ids": brands}, call) is expected


@pytest.mark.parametrize('brand,text',[
    ('qwen','苹果国行AI牵手千问落地'),
    ('deepseek','V4.1F-1017 is a superior model'),
    ('doubao','字节扣子企业版分阶段停售'),
    ('doubao','Coze workflow updates'),
    ('moonshot_kimi','Model card weights: the precision Moonshot serves'),
    ('moonshot_kimi','Moonshot 自报，API 每百万 token 定价'),
])
def test_locked_window_additions_have_attribution_and_search_coverage(brand,text):
    from scripts.harvest_db_replay import Matcher
    from x_monitor.query_plan import _build_query
    p=load_policy(POLICY)
    specs=specs_from_policy(p,brand_nicknames=[brand])
    assert Matcher([{'call_id':s.call_id,'query':_build_query(s)} for s in specs]).calls(text,'writer')
    assert brand in detect_brand_mentions(text,keyword_index())


def test_bare_moonshot_still_requires_ai_context_and_does_not_gate_handle():
    from scripts.harvest_db_replay import Matcher
    from x_monitor.query_plan import _build_query
    specs=specs_from_policy(load_policy(POLICY),brand_nicknames=['moonshot_kimi'])
    m=Matcher([{'call_id':s.call_id,'query':_build_query(s)} for s in specs])
    assert not m.calls('a moonshot space mission','writer')
    assert m.calls('@Kimi_Moonshot thanks','writer')


def test_llama_pretraining_research_has_query_and_attribution_evidence():
    from scripts.harvest_db_replay import Matcher
    from x_monitor.query_plan import _build_query
    text='Cohere synthetic pretraining results. In a 400M LLaMA setup, changing token embedding initialization improves perplexity.'
    specs=specs_from_policy(load_policy(POLICY),brand_nicknames=['llama'])
    assert Matcher([{'call_id':s.call_id,'query':_build_query(s)} for s in specs]).calls(text,'writer')
    assert 'llama' in detect_brand_mentions(text,keyword_index())
