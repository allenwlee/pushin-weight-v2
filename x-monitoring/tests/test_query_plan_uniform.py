# {{AGENT_ATTRIBUTION}}
"""Tests for the uniform renderer + planner (plan 2026-07-11-001 U2).

Replaces the Call-B-specific tests in test_query_plan_v17.py (which
the plan retires alongside the v1.7 Call B path).
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from x_monitor.config import load_config
from x_monitor.query_plan import (
    CallCBrandSpec,  # backwards-compat alias for XQuerySpec
    PlannedCall,
    XQuerySpec,
    _build_query,
    plan_calls,
)


GOLDEN_PATH = (
    Path(__file__).parent / "golden" / "query_plan_v17_strings.txt"
)


# ----------------------------------------------------------------------
# 1. Backwards-compat alias — CallCBrandSpec is XQuerySpec.
# ----------------------------------------------------------------------


def test_call_c_brand_spec_alias_is_x_query_spec() -> None:
    """The v1.7-era name is preserved as a backwards-compat alias so
    external imports (and the existing test_call_c_specs.py probes)
    keep working through the rename."""
    assert CallCBrandSpec is XQuerySpec


# ----------------------------------------------------------------------
# 2. _build_query — Call A degenerate case (KTD1).
# ----------------------------------------------------------------------


def test_build_query_call_a_renders_list_form() -> None:
    """A spec with empty `brands` and empty `co_occurrence` renders as
    `(list:<id>) min_faves:1` — the Call A degenerate case."""
    spec = XQuerySpec(
        brands={}, co_occurrence=[], min_faves=99, call_id="A"
    )
    out = _build_query(spec, x_monitor_list_id=2067062923525275922)
    assert out == "(list:2067062923525275922) min_faves:1"


def test_build_query_call_a_requires_list_id() -> None:
    """An empty-brands spec WITHOUT x_monitor_list_id raises — the
    Call A branch needs the list ID to render."""
    spec = XQuerySpec(brands={}, co_occurrence=[], min_faves=1)
    with pytest.raises(ValueError, match="x_monitor_list_id"):
        _build_query(spec)


# ----------------------------------------------------------------------
# 3. _build_query — Call C body shape (the legacy v1.7.x form).
# ----------------------------------------------------------------------


def test_build_query_call_c_body_matches_golden() -> None:
    """The Call C body shape produced by `_build_query` is byte-equal
    to the v1.7.x `_build_call_c_query` output captured in the golden
    file at U1 time. The two C1 + C2 specs in the live config each
    pin to one line of the golden file."""
    text = GOLDEN_PATH.read_text(encoding="utf-8")
    # Parse the golden file lines starting with "CALLC".
    c_lines = {
        line.split("call_id=")[1].split(" ")[0]: line
        for line in text.splitlines()
        if line.startswith("CALLC call_id=")
    }
    assert "C1" in c_lines and "C2" in c_lines, (
        f"golden file missing C1/C2 lines: {list(c_lines)}"
    )

    cfg = load_config(Path("config.yaml"))
    by_id = {s.call_id: s for s in cfg.x_query_specs}
    for spec_id, golden_line in c_lines.items():
        spec = by_id[spec_id]
        # The golden line embeds the rendered query as a Python repr
        # string (because the U1 generator used `!r`). The repr starts
        # and ends with `'` — strip both.
        rendered = _build_query(spec)
        # Format: `CALLC call_id=... min_faves=N: '<repr-of-query>'`
        # Find the `: '` separator and the trailing `'`.
        idx = golden_line.rfind(": '")
        assert idx > 0
        repr_str = golden_line[idx + 3 :]  # skip `: '`
        # Strip trailing newline / whitespace, then the closing `'`.
        expected = repr_str.rstrip()
        if expected.endswith("'"):
            expected = expected[:-1]
        assert rendered == expected, (
            f"Call {spec_id} query differs from golden: "
            f"expected {expected!r}, got {rendered!r}"
        )


# ----------------------------------------------------------------------
# 4. _build_query — degenerate case (empty brands dict, but spec
#    has tokens OR has call_id != "A") doesn't accidentally render
#    the list form.
# ----------------------------------------------------------------------


def test_build_query_spec_with_brands_renders_body_shape() -> None:
    """A spec with at least one brand renders the body shape (NOT the
    list form), even if co_occurrence is empty."""
    spec = XQuerySpec(
        brands={"minimax": ["MiniMax"]},
        co_occurrence=[],
        min_faves=0,
        call_id="X1",
    )
    out = _build_query(spec, x_monitor_list_id=2067062923525275922)
    assert "(list:" not in out
    assert "(MiniMax)" in out
    assert "min_faves:0" in out


# ----------------------------------------------------------------------
# 5. _build_query — min_faves=0 still emits the trailing directive.
# ----------------------------------------------------------------------


def test_build_query_min_faves_zero_emitted() -> None:
    """KTD1: the trailing `min_faves:N` is always present, even at N=0."""
    spec = XQuerySpec(
        brands={"minimax": ["MiniMax"]}, co_occurrence=[], min_faves=0
    )
    out = _build_query(spec)
    assert out.endswith(" min_faves:0")


# ----------------------------------------------------------------------
# 6. plan_calls — emits exactly len(x_query_specs) + 1 (Call A first).
# ----------------------------------------------------------------------


def test_plan_calls_emits_call_a_plus_each_spec() -> None:
    """The planner emits Call A first, then one PlannedCall per
    XQuerySpec. With 2 live specs, total = 3 calls."""
    cfg = load_config(Path("config.yaml"))
    calls = plan_calls(cfg.x_monitor_list_id, cfg.x_query_specs)
    assert len(calls) == len(cfg.x_query_specs) + 1
    assert calls[0].call_id == "A"
    assert calls[0].call_kind == "account"
    assert [c.call_id for c in calls[1:]] == [
        s.call_id for s in cfg.x_query_specs
    ]


def test_plan_calls_empty_x_query_specs_only_call_a() -> None:
    """With empty x_query_specs, only Call A fires — no defensively-
    emitted Call B or other artifact."""
    calls = plan_calls(2067062923525275922, [])
    assert len(calls) == 1
    assert calls[0].call_id == "A"


def test_plan_calls_requires_list_id() -> None:
    """plan_calls() raises TypeError when x_monitor_list_id is None —
    Call A is the only list-based call; no fallback."""
    with pytest.raises(TypeError, match="x_monitor_list_id"):
        plan_calls(None, [])


# ----------------------------------------------------------------------
# 7. plan_calls — Call A's query is the live curated-list form.
# ----------------------------------------------------------------------


def test_plan_calls_call_a_query_is_list_form() -> None:
    """Call A's emitted query is `(list:<x_monitor_list_id>) min_faves:1`."""
    cfg = load_config(Path("config.yaml"))
    calls = plan_calls(cfg.x_monitor_list_id, cfg.x_query_specs)
    assert calls[0].query_string == (
        f"(list:{cfg.x_monitor_list_id}) min_faves:1"
    )
    assert calls[0].query_length == len(calls[0].query_string)


# ----------------------------------------------------------------------
# 8. Retired v1.7 helpers are absent (KTD6 / R7).
# ----------------------------------------------------------------------


def test_retired_v17_helpers_absent() -> None:
    """`parse_brand_tokens`, `_parse_first_paren_group`, and
    `_build_brand_wide_query` are removed in U2. The plan requires
    `hasattr() == False` for these symbols."""
    import x_monitor.query_plan as qp
    for name in (
        "parse_brand_tokens",
        "_parse_first_paren_group",
        "_build_brand_wide_query",
        "_build_call_c_query",  # renamed to _build_query
    ):
        assert not hasattr(qp, name), (
            f"{name!r} should be removed in U2; still present on "
            f"x_monitor.query_plan"
        )


# ----------------------------------------------------------------------
# 9. Config — load_config normalizes legacy `call_c_specs:` key.
# ----------------------------------------------------------------------


def test_config_normalizes_legacy_call_c_specs(tmp_path: Path) -> None:
    """Older config files that still use `call_c_specs:` are loaded
    transparently into `x_query_specs`. The field is a parallel alias
    so existing tests pass without edits."""
    cfg = tmp_path / "legacy.yaml"
    cfg.write_text(
        "enabled_models:\n  - minimax\n"
        "daily_ceiling: 333\n"
        "x_monitor_list_id: 2067062923525275922\n"
        "call_c_specs:\n"
        "  - brands:\n"
        "      minimax: [MiniMax]\n"
        "    co_occurrence: [llm]\n"
        "    min_faves: 0\n"
        "    call_id: legacy_c\n",
        encoding="utf-8",
    )
    from x_monitor.config import load_config
    loaded = load_config(cfg)
    assert len(loaded.x_query_specs) == 1
    assert loaded.x_query_specs[0].call_id == "legacy_c"


# ----------------------------------------------------------------------
# 10. Wide-net B-call revival (plan 2026-07-11-002 U2).
# ----------------------------------------------------------------------


def test_build_query_wide_net_renders_from_primary_keywords() -> None:
    """A spec with `is_wide_net=True` and `wide_net_brands=['minimax','qwen']`
    reads per-brand tokens from `primary_keywords` and renders the
    same `<tokens> (<co_occurrence>) min_faves:N` shape."""
    spec = XQuerySpec(
        brands={},
        co_occurrence=["llm", "api"],
        min_faves=0,
        call_id="B1",
        is_wide_net=True,
        wide_net_brands=["minimax", "qwen"],
    )
    out = _build_query(
        spec,
        primary_keywords={
            "minimax": ["MiniMax", "Hailuo"],
            "qwen": ["Qwen", "Qwen3"],
        },
    )
    # Per-brand paren groups joined with OR, then OR'd into primary.
    assert "(MiniMax OR Hailuo)" in out
    assert "(Qwen OR Qwen3)" in out
    assert "(llm OR api)" in out
    assert out.endswith(" min_faves:0")
    # Rendered form is one big OR-of-paren-groups.
    assert out == (
        "((MiniMax OR Hailuo) OR (Qwen OR Qwen3)) (llm OR api) min_faves:0"
    )


def test_build_query_wide_net_requires_primary_keywords() -> None:
    """A wide-net spec without `primary_keywords` raises (operator
    misconfiguration — the DB load was forgotten)."""
    spec = XQuerySpec(
        brands={},
        co_occurrence=["llm"],
        min_faves=0,
        call_id="B1",
        is_wide_net=True,
        wide_net_brands=["minimax"],
    )
    with pytest.raises(ValueError, match="primary_keywords"):
        _build_query(spec)


def test_build_query_wide_net_skips_brands_with_no_primary_tokens() -> None:
    """A brand in `wide_net_brands` that's absent from `primary_keywords`
    is skipped (defensive — matches the existing all-empty branch).
    The remaining brands render normally."""
    spec = XQuerySpec(
        brands={},
        co_occurrence=["llm"],
        min_faves=0,
        call_id="B1",
        is_wide_net=True,
        wide_net_brands=["minimax", "qwen"],
    )
    out = _build_query(
        spec,
        primary_keywords={"minimax": ["MiniMax"]},  # qwen missing
    )
    assert "(MiniMax)" in out
    assert "qwen" not in out.lower()


def test_build_query_call_a_path_unchanged_when_is_wide_net_false() -> None:
    """A spec with empty brands but `is_wide_net=False` (the Call A
    degenerate) still renders the list form — the new flag does not
    accidentally catch this path."""
    spec = XQuerySpec(
        brands={},
        co_occurrence=[],
        min_faves=1,
        call_id="A",
    )
    out = _build_query(spec, x_monitor_list_id=2067062923525275922)
    assert out == "(list:2067062923525275922) min_faves:1"


def test_build_query_c_spec_ignores_primary_keywords() -> None:
    """A non-wide-net C-spec (`is_wide_net=False`, `brands={...}`) reads
    from `spec.brands`, NOT from `primary_keywords`. The kwarg is
    silently ignored."""
    spec = XQuerySpec(
        brands={"minimax": ["MiniMax"]},
        co_occurrence=["llm"],
        min_faves=0,
        call_id="C1",
    )
    out_with = _build_query(
        spec, primary_keywords={"minimax": ["OTHER_TOKEN_THAT_SHOULD_NOT_APPEAR"]}
    )
    out_without = _build_query(spec)
    assert out_with == out_without
    assert "OTHER_TOKEN" not in out_with


def test_plan_calls_emits_six_calls_with_three_wide_net_specs() -> None:
    """plan_calls synthesizes Call A from `x_monitor_list_id` and emits
    one call per spec in `x_query_specs`. With 5 specs (C1, C2, B1,
    B2, B3) and a populated `primary_keywords` dict the planner emits
    exactly 6 PlannedCall rows in the order [A, C1, C2, B1, B2, B3]."""
    primary = {
        "minimax": ["MiniMax"], "qwen": ["Qwen"], "deepseek": ["DeepSeek"],
        "mistral": ["Mistral"], "stepfun": ["StepFun"], "ernie": ["ERNIE"],
        "hunyuan": ["Hunyuan"], "doubao": ["Doubao"], "glm": ["GLM"],
        "moonshot_kimi": ["Kimi"], "mimo": ["MiMo"], "sensechat": ["SenseChat"],
        "yi": ["Yi"], "inclusionai": ["InclusionAI"],
        "nemo_megatron": ["NVIDIA NeMo"], "exaone": ["EXAONE"],
        "sakana_ai": ["Sakana"], "kuaishou": ["Kuaishou"], "upstage": ["Upstage"],
        "llama": ["Llama"],
    }
    # Call A is synthesized by plan_calls from x_monitor_list_id; the
    # spec list carries only the per-cycle co-occurrence + wide-net
    # specs. Passing an explicit Call A degenerate in x_query_specs
    # would cause plan_calls to emit TWO Call A entries.
    specs = [
        XQuerySpec(  # C1 — 5 brands, co-occurrence
            brands={
                "mimo": ["MiMo"], "moonshot_kimi": ["Kimi"], "yi": ["Yi"],
                "upstage": ["Upstage"], "llama": ["Llama"],
            },
            co_occurrence=["api", "llm"], min_faves=0, call_id="C1",
        ),
        XQuerySpec(  # C2 — ERNIE
            brands={"ernie": ["ERNIE"]},
            co_occurrence=["baidu"], min_faves=0, call_id="C2",
        ),
        XQuerySpec(  # B1 — top-presence / global
            brands={}, co_occurrence=["api", "llm"], min_faves=0,
            call_id="B1", is_wide_net=True,
            wide_net_brands=["llama", "minimax", "qwen", "deepseek",
                             "mistral", "stepfun", "ernie", "hunyuan"],
        ),
        XQuerySpec(  # B2 — Chinese-language
            brands={}, co_occurrence=["api", "llm"], min_faves=0,
            call_id="B2", is_wide_net=True,
            wide_net_brands=["doubao", "glm", "moonshot_kimi", "mimo",
                             "sensechat", "yi", "inclusionai"],
        ),
        XQuerySpec(  # B3 — specialized / smaller
            brands={}, co_occurrence=["api", "llm"], min_faves=0,
            call_id="B3", is_wide_net=True,
            wide_net_brands=["nemo_megatron", "exaone", "sakana_ai",
                             "kuaishou", "upstage"],
        ),
    ]
    calls = plan_calls(2067062923525275922, specs, primary_keywords=primary)
    assert len(calls) == 6
    assert [c.call_id for c in calls] == ["A", "C1", "C2", "B1", "B2", "B3"]


def test_plan_calls_wide_net_query_under_cap_with_live_primary_subset() -> None:
    """The live `brand_keywords.is_primary=1` subset produces B-call
    query strings under 512 chars (the X advanced-search cap)."""
    from x_monitor.store import Store
    from x_monitor.config import load_config

    cfg = load_config(Path("config.yaml"))
    # Live DB after migration 036.
    with tempfile_db() as db_path:
        s = Store(db_path, auto_migrate=True)
        try:
            primary = s.read_primary_brand_keywords()
            # Build the same 3 wide-net specs U3 will write into config.yaml.
            b_specs = [
                XQuerySpec(
                    brands={}, co_occurrence=cfg.x_query_specs[0].co_occurrence,
                    min_faves=0, call_id="B1", is_wide_net=True,
                    wide_net_brands=[
                        "llama", "minimax", "qwen", "deepseek",
                        "mistral", "stepfun", "ernie", "hunyuan",
                    ],
                ),
                XQuerySpec(
                    brands={}, co_occurrence=cfg.x_query_specs[0].co_occurrence,
                    min_faves=0, call_id="B2", is_wide_net=True,
                    wide_net_brands=[
                        "doubao", "glm", "moonshot_kimi", "mimo",
                        "sensechat", "yi", "inclusionai",
                    ],
                ),
                XQuerySpec(
                    brands={}, co_occurrence=cfg.x_query_specs[0].co_occurrence,
                    min_faves=0, call_id="B3", is_wide_net=True,
                    wide_net_brands=[
                        "nemo_megatron", "exaone", "sakana_ai",
                        "kuaishou", "upstage",
                    ],
                ),
            ]
            calls = plan_calls(cfg.x_monitor_list_id, b_specs,
                                primary_keywords=primary)
            for c in calls:
                assert c.query_length < 512, (
                    f"{c.call_id} query is {c.query_length} chars — "
                    f"over the 512-char cap: {c.query_string!r}"
                )
        finally:
            s.close()


# ----------------------------------------------------------------------
# Helper — fresh in-memory-ish DB per test (avoids polluting live DB).
# ----------------------------------------------------------------------


import tempfile


@contextmanager
def tempfile_db():
    """Yield a tmp Path for a fresh DB; auto-cleanup."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    try:
        yield path
    finally:
        try:
            path.unlink()
        except OSError:
            pass
