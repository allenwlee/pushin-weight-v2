# {{AGENT_ATTRIBUTION}}
"""v1.7 tests for x_monitor.query_plan: 2-call wide-net shape.

These tests verify the v1.7 redesign described in
docs/plans/2026-06-17-001-refactor-two-call-wide-net-translation-plan.md
(amended 2026-06-17 for length-cap, not operator-cap). They should FAIL
against the v1.6 implementation and PASS against the v1.7 rewrite.

v1.7 shape:
  Call A (account):   (list:<x_monitor_list_id>) min_faves:1   (29 chars)
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
    "xiaomi_mimo", "moonshot_kimi", "inclusionai",
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
    """v1.7.x: plan_calls with a non-empty call_c_specs list emits one extra
    PlannedCall per spec, in order, with stable call_id C1, C2, ..."""
    from x_monitor.query_plan import plan_calls, CallCBrandSpec

    specs = [
        CallCBrandSpec(
            brand_id="xiaomi_mimo",
            tokens=["MiMo", "Xiaomi MiMo", "小米 MiMo"],
            co_occurrence=["api", "llm", "model", "xiaomi", "小米"],
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
    assert call_c.brand_id == "xiaomi_mimo"
    assert call_c.expected_signal == "other"
    # Shape: (<tokens>) (<co_occurrence>) min_faves:0
    assert call_c.query_string == (
        "(MiMo OR Xiaomi MiMo OR 小米 MiMo) "
        "(api OR llm OR model OR xiaomi OR 小米) min_faves:0"
    )
    assert call_c.query_length < 512


def test_plan_calls_v17_call_c_length_cap_raises(v17_data_dir):
    """An over-cap Call C query (e.g., 600 chars) must raise ValueError from
    assert_under_length_cap. Verifies the cap is enforced per Call C spec,
    not just on Call A / Call B."""
    import pytest
    from x_monitor.query_plan import plan_calls, CallCBrandSpec

    # Construct a Call C that's guaranteed over the 512-char cap.
    huge = ["x" * 200] * 10  # 10x200 = 2000 chars in tokens alone
    specs = [CallCBrandSpec(
        brand_id="oversized",
        tokens=huge,
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
    # from 224 -> 212). Pin a range, not a magic number.
    assert 180 <= len(call_b.query_string) <= 256, (
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
        "xiaomi_mimo":   ["MiMo", "Xiaomi MiMo", "小米 MiMo"],
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
    for yaml in ["minimax.yaml", "qwen.yaml", "deepseek.yaml", "glm.yaml", "xiaomi_mimo.yaml"]:
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
        f"Inner: {inner!r}"
    )


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
        expected_signal="other",
        query_length=12,
    )
    assert p.call_kind == "brand_wide"
