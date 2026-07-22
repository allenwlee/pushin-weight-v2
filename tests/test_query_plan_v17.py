# {{AGENT_ATTRIBUTION}}
"""v1.7 tests for x_monitor.query_plan: 2-call wide-net shape.

These tests verify the v1.7 redesign described in
docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
(amended 2026-06-17 for length-cap, not operator-cap). They should FAIL
against the v1.6 implementation and PASS against the v1.7 rewrite.

v1.7 shape:
  Call A (account):   (list:<x_monitor_list_id>) min_faves:0   (29 chars)
  Call B (brand_wide): ((BrandTok1a OR BrandTok1b) OR ... OR
                         (BrandTokNa OR ...)) min_faves:0       (218 chars at 7 brands)

The cap is on character LENGTH (~512, per docs.x.com), not operator count.
The v1.6 `INTENT_BUCKETS` constant and `_split_brands_to_fit_cap` recursion
are removed; signal classification is post-fetch via classify_signal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# --- v1.7 plan_calls: 2-call shape --------------------------------------


V17_LIST_ID = 1234567890
V17_MODELS = [
    "minimax", "qwen", "deepseek", "glm",
    "mimo", "moonshot_kimi", "inclusionai",
]


@pytest.fixture
def v17_data_dir() -> Path:
    """Return the project data/ directory (already populated with the 7 yaml files)."""
    # The worktree's tests are run from x-monitoring/, so data/ is right here.
    return Path(__file__).resolve().parent.parent / "data"


def test_plan_calls_v17_returns_exactly_two_calls_by_default(v17_data_dir):
    """plan_calls(data, 7_models, x_monitor_list_id=...) with no call_c_specs
    must emit exactly 2 calls (Call A + Call B). The v1.7 2-call baseline is
    preserved when the operator has not configured any Call C specs."""
    from x_monitor.query_plan import plan_calls

    calls = plan_calls(
        v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID
    )
    assert len(calls) == 2, (
        f"v1.7 default must emit exactly 2 calls; got {len(calls)}: "
        f"{[c.call_kind for c in calls]}"
    )
    assert calls[0].call_id == "A"
    assert calls[1].call_id == "B"


def test_plan_calls_v17_emits_call_c_when_spec_provided(v17_data_dir):
    """v1.7.x: plan_calls with a non-empty call_c_specs list emits one
    PlannedCall per spec. Each spec is multi-brand (mirrors Call B's
    per-brand paren grouping) and the post-fetch attribute_to_brands
    routes results to the right brand by token match."""
    from x_monitor.query_plan import plan_calls, CallCBrandSpec

    # Single spec covering both MiMo and Kimi — same shape as a
    # multi-brand Call B.
    specs = [
        CallCBrandSpec(
            brands={
                "mimo":  ["MiMo", "Xiaomi MiMo", "小米 MiMo"],
                "moonshot_kimi": ["Kimi", "月之暗面", "暗面"],
            },
            co_occurrence=["api", "llm", "model"],
        ),
    ]
    calls = plan_calls(
        v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID,
        call_c_specs=specs,
    )
    assert len(calls) == 3, (
        f"expected 2 + 1 Call C; got {len(calls)}: "
        f"{[c.call_id for c in calls]}"
    )
    assert [c.call_id for c in calls] == ["A", "B", "C1"]
    call_c = calls[2]
    assert call_c.call_kind == "brand_wide"
    # brand_id is a placeholder (one raw file per call); actual routing
    # is via post-fetch attribute_to_brands matching the per-brand
    # paren group.
    assert call_c.brand_id in {"mimo", "moonshot_kimi"}
    # U9 (migration 022): PlannedCall no longer carries
    # `expected_signal` — the 6-signal taxonomy was replaced by
    # (post_type, sentiment) classification at ingestion time.
    # Shape: ((brand1) OR (brand2)) (co_occurrence) min_faves:0
    # Brand group order is dict-insertion order (py3.7+); both brands
    # are in the outer paren, joined with OR.
    expected = (
        "((MiMo OR Xiaomi MiMo OR 小米 MiMo) OR (Kimi OR 月之暗面 OR 暗面)) "
        "(api OR llm OR model) min_faves:0"
    )
    assert call_c.query_string == expected, (
        f"unexpected query string:\n  got:      {call_c.query_string!r}\n"
        f"  expected: {expected!r}"
    )
    assert call_c.query_length < 512


def test_plan_calls_v17_call_c_per_brand_paren_grouping(v17_data_dir):
    """Call C with multiple brands must put each brand's tokens in its
    own paren group (Call B's structure), NOT a flat OR of all tokens.
    This is what makes post-fetch attribute_to_brands work — the regex
    matcher needs the per-brand paren boundaries to know which brand a
    given post's token matched."""
    from x_monitor.query_plan import plan_calls, CallCBrandSpec

    specs = [CallCBrandSpec(
        brands={
            "a": ["alpha", "al"],
            "b": ["beta", "be"],
        },
        co_occurrence=["ctx"],
    )]
    calls = plan_calls(
        v17_data_dir, ["a", "b"], x_monitor_list_id=V17_LIST_ID,
        call_c_specs=specs,
    )
    q = calls[2].query_string
    # Per-brand paren groups: (alpha OR al) and (beta OR be)
    assert "(alpha OR al)" in q
    assert "(beta OR be)" in q
    # Outer primary paren wraps the per-brand groups
    assert q.startswith("((")
    # Co-occurrence group
    assert "(ctx)" in q
    assert q.endswith(" min_faves:0")


def test_plan_calls_v17_call_c_length_cap_raises(v17_data_dir):
    """An over-cap Call C query (e.g., 600 chars) must raise ValueError from
    assert_under_length_cap. Verifies the cap is enforced per Call C spec,
    not just on Call A / Call B."""
    import pytest
    from x_monitor.query_plan import plan_calls, CallCBrandSpec

    # Construct a Call C that's guaranteed over the 512-char cap.
    huge = ["x" * 200] * 10  # 10x200 = 2000 chars in tokens alone
    specs = [CallCBrandSpec(
        brands={"oversized": huge},
        co_occurrence=["api", "llm", "model", "xiaomi", "小米"],
    )]
    with pytest.raises(ValueError, match="length"):
        plan_calls(
            v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID,
            call_c_specs=specs,
        )


def test_plan_calls_v17_call_a_is_list_query(v17_data_dir):
    """Call A must be (list:<id>) min_faves:1."""
    from x_monitor.query_plan import plan_calls

    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID)
    call_a = calls[0]
    assert call_a.call_kind == "account"
    assert call_a.query_string == f"(list:{V17_LIST_ID}) min_faves:1"
    assert len(call_a.query_string) == 29  # ~12 list ID + "list:" + parens + min_faves:1


def test_plan_calls_v17_call_b_is_brand_wide_paren_grouped(v17_data_dir):
    """Call B must be a paren-grouped OR chain of all brand tokens, with min_faves:0."""
    from x_monitor.query_plan import plan_calls

    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID)
    call_b = calls[1]
    assert call_b.call_kind == "brand_wide"
    # Call B's shape: outer wrap + 1 paren group per brand.
    # 7 brands => 7 brand groups + 1 outer wrap = 8 open parens.
    n_open = call_b.query_string.count("(")
    n_close = call_b.query_string.count(")")
    assert n_open == 8, f"expected 8 open parens (7 brand + 1 outer); got {n_open}"
    assert n_close == 8, f"expected 8 close parens; got {n_close}"
    # Count brand groups: take the inner of the outer wrap and count its parens.
    inner = call_b.query_string.strip()[1:call_b.query_string.rindex(")")]
    n_brand_groups = inner.count("(")
    assert n_brand_groups == 7, f"expected 7 brand paren groups; got {n_brand_groups}"
    assert call_b.query_string.endswith(" min_faves:0")
    # Char count is sensitive to per-brand token changes (e.g. the moonshot
    # disambig that removed bare "Moonshot" and added 月之暗面 shrank Call B
    # from 224 -> 212; the 2026-06-25 widening added MiMo-V2.5-Pro/V2.5/Code/
    # 7B/VL + GLM-5.2 + Kimi K2 + Qwen3 + DeepSeek V4, growing it to 364).
    # Pin a range, not a magic number.
    assert 180 <= len(call_b.query_string) <= 400, (
        f"Call B length {len(call_b.query_string)} outside expected range. "
        f"Query: {call_b.query_string!r}"
    )


def test_plan_calls_v17_call_b_uses_yaml_brand_tokens(v17_data_dir):
    """Call B's paren groups must contain each brand's tokens from data/queries/<m>.yaml."""
    from x_monitor.query_plan import plan_calls

    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID)
    call_b = calls[1].query_string

    # Sample of expected tokens from the v1.7 plan's per-brand table
    expected_tokens = {
        "minimax":       ["MiniMax", "海螺", "Hailuo"],
        "qwen":          ["Qwen", "通义千问", "通义"],
        "deepseek":      ["DeepSeek", "深度求索"],
        "glm":           ["GLM", "智谱", "ChatGLM"],
        "mimo":   ["MiMo", "Xiaomi MiMo", "小米 MiMo"],
        "moonshot_kimi": ["Kimi", "月之暗面"],  # bare "Moonshot" removed by disambig
        "inclusionai":   ["InclusionAI", "Ling", "Ring", "Ming"],
    }
    for model, toks in expected_tokens.items():
        for tok in toks:
            assert tok in call_b, f"token {tok!r} for {model} missing from Call B: {call_b!r}"


def test_plan_calls_v17_call_b_stays_under_length_cap(v17_data_dir):
    """Call B at 7 brands must be under 512 chars (the X length cap)."""
    from x_monitor.query_plan import plan_calls

    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID)
    call_b = calls[1]
    assert len(call_b.query_string) <= 512, (
        f"Call B is {len(call_b.query_string)} chars; cap is 512. "
        f"Will silently fail. Query: {call_b.query_string!r}"
    )


def test_plan_calls_v17_requires_x_monitor_list_id(v17_data_dir):
    """Calling plan_calls without x_monitor_list_id must raise (TypeError or ValueError)."""
    from x_monitor.query_plan import plan_calls

    with pytest.raises((TypeError, ValueError)):
        # No x_monitor_list_id kwarg passed
        plan_calls(v17_data_dir, V17_MODELS)


def test_plan_calls_v17_call_b_groups_in_model_iteration_order(v17_data_dir):
    """Paren groups must follow the input enabled_models order, not alphabetical."""
    from x_monitor.query_plan import plan_calls

    # Reverse the order
    models_reversed = list(reversed(V17_MODELS))
    calls = plan_calls(v17_data_dir, models_reversed, x_monitor_list_id=V17_LIST_ID)
    call_b = calls[1].query_string

    # The first paren group should contain inclusionai's first token (InclusionAI)
    # and the last paren group should contain minimax's first token (MiniMax).
    first_group = re.search(r"\(([^()]*)\)", call_b).group(1)
    last_group = re.findall(r"\(([^()]*)\)", call_b)[-1]

    assert "InclusionAI" in first_group
    assert "MiniMax" in last_group


def test_plan_calls_v17_handles_missing_brand_query_yaml(v17_data_dir, tmp_path):
    """If a model's data/queries/<m>.yaml is missing, that brand contributes 0 paren groups."""
    from x_monitor.query_plan import plan_calls

    # Copy only 5 of 7 yaml files
    src_queries = v17_data_dir / "queries"
    dst_queries = tmp_path / "queries"
    dst_queries.mkdir()
    for yaml in ["minimax.yaml", "qwen.yaml", "deepseek.yaml", "glm.yaml", "mimo.yaml"]:
        (dst_queries / yaml).write_bytes((src_queries / yaml).read_bytes())

    # Build a parallel data dir that mirrors v17_data_dir but with a thin queries/
    thin_data = tmp_path
    for sub in ("accounts", "filters", "runs"):
        if (v17_data_dir / sub).exists():
            (thin_data / sub).mkdir(exist_ok=True)
            for f in (v17_data_dir / sub).iterdir():
                (thin_data / sub / f.name).write_bytes(f.read_bytes())

    calls = plan_calls(thin_data, V17_MODELS, x_monitor_list_id=V17_LIST_ID)
    call_b = calls[1].query_string
    # 5 brands contribute paren groups; moonshot_kimi + inclusionai contribute 0.
    # Outer wrap adds 1 more: 5 brand + 1 outer = 6 open parens total.
    assert call_b.count("(") == 6, (
        f"expected 6 open parens (5 brand + 1 outer); got {call_b.count('(')}. "
        f"Query: {call_b!r}"
    )
    # And the inner (after stripping outer wrap) has exactly 5 brand groups.
    inner = call_b.strip()[1:call_b.rindex(")")]
    assert inner.count("(") == 5, (
        f"expected 5 brand paren groups in inner; got {inner.count('(')}. "
        f"Inner: {call_b!r}"
    )


# --- v1.7.x: call_b_groups split into N Call Bs ------------------------


def test_plan_calls_v17_default_emits_single_call_b(v17_data_dir):
    """Without call_b_groups, plan_calls emits exactly one Call B (legacy v1.7 behavior)."""
    from x_monitor.query_plan import plan_calls

    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID)
    # Call A + Call B = 2 calls (no Call C in this default)
    assert len(calls) == 2
    assert calls[0].call_id == "A"
    assert calls[1].call_id == "B"


def test_plan_calls_v17_call_b_groups_emits_n_calls(v17_data_dir):
    """With call_b_groups of 3 lists, plan_calls emits 3 Call Bs labeled B1/B2/B3."""
    from x_monitor.query_plan import plan_calls

    groups = [
        ["minimax", "qwen"],
        ["deepseek", "glm"],
        ["mimo", "moonshot_kimi", "inclusionai"],
    ]
    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID, call_b_groups=groups)
    # Call A + 3 Call Bs = 4 calls
    assert len(calls) == 4
    assert calls[0].call_id == "A"
    assert [c.call_id for c in calls[1:]] == ["B1", "B2", "B3"]


def test_plan_calls_v17_call_b_groups_each_under_cap(v17_data_dir):
    """Each Call B in a multi-group split must be under the 512-char cap."""
    from x_monitor.query_plan import plan_calls

    groups = [
        ["minimax", "qwen", "deepseek", "glm"],
        ["mimo", "moonshot_kimi", "inclusionai"],
    ]
    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID, call_b_groups=groups)
    for c in calls[1:]:
        assert len(c.query_string) <= 512, (
            f"{c.call_id} is {len(c.query_string)} chars; cap is 512. Query: {c.query_string!r}"
        )


def test_plan_calls_v17_call_b_groups_contain_only_grouped_brands(v17_data_dir):
    """Call B1 must only contain brand tokens for brands in group 1, not group 2."""
    from x_monitor.query_plan import plan_calls

    groups = [
        ["minimax"],
        ["glm"],
    ]
    calls = plan_calls(v17_data_dir, V17_MODELS, x_monitor_list_id=V17_LIST_ID, call_b_groups=groups)
    b1, b2 = calls[1].query_string, calls[2].query_string
    # B1 has MiniMax/海螺/Hailuo (from minimax.yaml), not GLM/智谱/ChatGLM
    assert "MiniMax" in b1
    assert "GLM" not in b1
    # B2 has GLM/智谱/ChatGLM, not minimax tokens
    assert "GLM" in b2
    assert "MiniMax" not in b2


# --- v1.7 helpers: assert_under_length_cap ------------------------------


def test_assert_under_length_cap_silent_when_under():
    """assert_under_length_cap must not raise when query is under the cap."""
    from x_monitor.queries import assert_under_length_cap

    # Any under-cap query must not raise. We construct a clearly-under-cap
    # string (50 chars) rather than locking the exact char count.
    q = " OR ".join(f"t{i}" for i in range(10))  # 10 terms, well under cap
    assert len(q) < 512
    assert_under_length_cap(q)  # must not raise


def test_assert_under_length_cap_silent_at_exact_cap():
    """assert_under_length_cap must not raise at exactly 512 chars."""
    from x_monitor.queries import assert_under_length_cap

    q = "x" * 512
    assert_under_length_cap(q)


def test_assert_under_length_cap_raises_over_cap():
    """assert_under_length_cap must raise ValueError on strings > 512 chars."""
    from x_monitor.queries import assert_under_length_cap

    q = "x" * 513
    with pytest.raises(ValueError, match="512"):
        assert_under_length_cap(q)


def test_assert_under_length_cap_cap_constant():
    """Lock the cap at 512 chars (the official X API v2 self-serve limit)."""
    from x_monitor.queries import X_LENGTH_CAP

    assert X_LENGTH_CAP == 512


# --- v1.7 retirements ---------------------------------------------------


def test_v17_removes_intent_buckets_from_query_plan():
    """INTENT_BUCKETS must be removed from x_monitor.query_plan (post-fetch classify)."""
    import x_monitor.query_plan as qp

    assert not hasattr(qp, "INTENT_BUCKETS"), (
        "INTENT_BUCKETS should be removed in v1.7; signal classification is post-fetch."
    )


def test_v17_removes_split_brands_to_fit_cap():
    """_split_brands_to_fit_cap must be removed (Call B is 1 call, not split)."""
    import x_monitor.query_plan as qp

    assert not hasattr(qp, "_split_brands_to_fit_cap"), (
        "_split_brands_to_fit_cap should be removed in v1.7; Call B is 1 call at 7 brands."
    )


def test_v17_query_plan_does_not_count_operators():
    """v1.7's query_plan must not import count_x_operators (replaced by length check)."""
    import x_monitor.query_plan as qp

    src = Path(qp.__file__).read_text(encoding="utf-8")
    assert "count_x_operators" not in src, (
        "v1.7's query_plan should not use count_x_operators; cap is on length, not operators."
    )


def test_v17_planned_call_call_kind_is_union():
    """v1.7 PlannedCall.call_kind must accept 'brand_wide' (new in v1.7)."""
    from x_monitor.query_plan import PlannedCall

    p = PlannedCall(
        call_id="B",
        call_kind="brand_wide",  # type: ignore[arg-type]
        brand_id="*",
        bucket=None,
        query_string="(x) min_faves:0",
        query_length=12,
    )
    assert p.call_kind == "brand_wide"
