# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.config."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from x_monitor.config import KNOWN_MODELS, Config, load_config


def _write(tmp: Path, body: str) -> Path:
    p = tmp / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_live_headline_cadences_pin_hourly_one_day_and_slow_long_windows():
    config = load_config(Path(__file__).resolve().parents[1] / "config.yaml")

    assert config.headline_narrative.cadence_minutes == {
        1: 60,
        7: 1_440,
        30: 10_080,
        365: 43_200,
    }
    assert config.headline_narrative.stale_minutes == {
        1: 120,
        7: 2_880,
        30: 20_160,
        365: 86_400,
    }


def test_loads_all_known_models():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models:
  - minimax
  - qwen
  - deepseek
  - glm
  - mimo
  - moonshot_kimi
  - inclusionai
  - mistral
  - stepfun
  - ernie
  - hunyuan
  - llama
  - nemo_megatron
  - doubao
  - yi
  - sensechat
  - exaone
  - sakana_ai
  - kuaishou
  - upstage
daily_ceiling: 333
""",
        )
        c = load_config(path)
        assert len(c.enabled_models) == len(KNOWN_MODELS)
        for m in KNOWN_MODELS:
            assert m in c.enabled_models


def test_rejects_unknown_brand_id():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models:
  - minimax
  - bogus model
daily_ceiling: 100
""",
        )
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        assert "bogus model" in str(exc_info.value)


def test_rejects_daily_ceiling_zero():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
daily_ceiling: 0
""",
        )
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        assert "daily_ceiling" in str(exc_info.value)


def test_rejects_negative_daily_ceiling():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
daily_ceiling: -1
""",
        )
        with pytest.raises(ValidationError):
            load_config(path)


def test_rejects_empty_enabled_models():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: []
daily_ceiling: 100
""",
        )
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        # Pydantic emits "list should have at least 1 item" for min_length=1.
        assert "at least 1" in str(exc_info.value)


def test_rejects_duplicate_models():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax, minimax]
daily_ceiling: 100
""",
        )
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        assert "duplicate" in str(exc_info.value).lower()


def test_default_skip_order_is_r17():
    """The seven logical calls have one deterministic degraded skip order."""
    c = Config(enabled_models=["minimax"], daily_ceiling=100)
    assert c.degraded_skip_order == ["B3", "B2", "B1", "C3", "C2", "C1", "A"]


def test_skip_order_must_contain_all_query_ids():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
daily_ceiling: 100
degraded_skip_order: [Q1, Q2, Q3]
""",
        )
        with pytest.raises(ValidationError):
            load_config(path)


def test_per_model_rot_threshold_validated():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
daily_ceiling: 100
query_rot_streak_threshold_per_model:
  bogus_model: 5
""",
        )
        with pytest.raises(ValidationError):
            load_config(path)


def test_accepts_enabled_nickname_outside_legacy_registry():
    """The v2 config gate is data-driven, not tied to KNOWN_MODELS."""
    c = Config(enabled_models=["dots"], daily_ceiling=100)
    assert c.enabled_models == ["dots"]


@pytest.mark.parametrize("nickname", ["Dots", "dots model", "-dots", "dots-"])
def test_rejects_non_nickname_shaped_enabled_model(nickname):
    with pytest.raises(ValidationError):
        Config(enabled_models=[nickname], daily_ceiling=100)


def test_per_model_rot_threshold_must_use_enabled_nickname():
    with pytest.raises(ValidationError, match="not enabled"):
        Config(
            enabled_models=["dots"],
            daily_ceiling=100,
            query_rot_streak_threshold_per_model={"minimax": 5},
        )


def test_rejects_unknown_review_reason():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
daily_ceiling: 100
review_reasons: [bogus_reason]
""",
        )
        with pytest.raises(ValidationError):
            load_config(path)


def test_clustering_defaults():
    c = Config(enabled_models=["minimax"], daily_ceiling=100)
    assert c.clustering.min_commenters == 3
    assert c.clustering.min_posts == 2


# --- U1: SearchConfig ----------------------------------------------------


def test_search_defaults():
    # No `search:` block in YAML -> defaults match today's hardcoded values.
    c = Config(enabled_models=["minimax"], daily_ceiling=100)
    assert c.search.max_results == 50
    assert c.search.max_per_page == 20
    assert c.search.max_pages == 5


def test_search_defaults_via_yaml_no_block(tmp_path):
    # YAML loads cleanly with no search: block; defaults apply.
    p = _write(
        tmp_path,
        "enabled_models: [minimax]\ndaily_ceiling: 100\n",
    )
    c = load_config(p)
    assert c.search.max_results == 50
    assert c.search.max_per_page == 20
    assert c.search.max_pages == 5


def test_search_explicit_override(tmp_path):
    # All three caps overridable via YAML.
    p = _write(
        tmp_path,
        (
            "enabled_models: [minimax]\n"
            "daily_ceiling: 100\n"
            "search:\n"
            "  max_results: 25\n"
            "  max_per_page: 10\n"
            "  max_pages: 3\n"
        ),
    )
    c = load_config(p)
    assert c.search.max_results == 25
    assert c.search.max_per_page == 10
    assert c.search.max_pages == 3


def test_search_partial_override(tmp_path):
    # Only max_pages overridden; others fall back to defaults.
    p = _write(
        tmp_path,
        (
            "enabled_models: [minimax]\n"
            "daily_ceiling: 100\n"
            "search:\n"
            "  max_pages: 3\n"
        ),
    )
    c = load_config(p)
    assert c.search.max_results == 50
    assert c.search.max_per_page == 20
    assert c.search.max_pages == 3


@pytest.mark.parametrize("field", ["max_results", "max_per_page", "max_pages"])
def test_search_rejects_non_positive(tmp_path, field):
    # Any non-positive integer triggers Pydantic validation.
    p = _write(
        tmp_path,
        (
            f"enabled_models: [minimax]\n"
            f"daily_ceiling: 100\n"
            f"search:\n"
            f"  {field}: 0\n"
        ),
    )
    with pytest.raises(ValidationError) as excinfo:
        load_config(p)
    assert field in str(excinfo.value)


# --- U4 (Plan 2026-07-13-002) call_b_groups dedup pins -----------
#
# U4 restores the 3915675 dedup: 6 polysemous brands were re-added
# to B after the U3 wire-in (commit ab12419). They are covered by
# C1 (llama, mimo, moonshot_kimi, yi) and C2 (ernie, upstage) via
# the co-occurrence AND-filter, so listing them in B is duplicate
# TwitterAPI credit spend with no recall gain.


def test_call_b_groups_dedup_shape_pinned():
    """The live config.yaml's call_b_groups is the 6/4/4 dedup'd
    shape — the 6 polysemous brands are absent."""
    with tempfile.TemporaryDirectory() as d:
        # Mirror the live config.yaml structure: 4 polysemous brands
        # in C1, 2 in C2, and a dedup'd call_b_groups.
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models:
  - minimax
  - qwen
  - llama
  - mimo
review_reasons:
  - low_engagement
x_query_specs:
  - brands:
      llama:         [Llama]
      mimo:          [MiMo]
      moonshot_kimi: [Kimi]
      yi:            [Yi]
    co_occurrence: [api, llm, model]
    min_faves: 0
    call_id: C1
  - brands:
      ernie:   [ERNIE]
      upstage: [Upstage]
    co_occurrence: [api, llm, model]
    min_faves: 0
    call_id: C2
call_b_groups:
  - [minimax, qwen, deepseek, mistral, stepfun, hunyuan]
  - [doubao, glm, sensechat, inclusionai]
  - [nemo_megatron, exaone, sakana_ai, kuaishou]
""",
        )
        c = load_config(path)
    expected = [
        ["minimax", "qwen", "deepseek", "mistral", "stepfun", "hunyuan"],
        ["doubao", "glm", "sensechat", "inclusionai"],
        ["nemo_megatron", "exaone", "sakana_ai", "kuaishou"],
    ]
    assert c.call_b_groups == expected, (
        f"call_b_groups shape drifted from the U4 6/4/4 dedup: "
        f"got {c.call_b_groups}, expected {expected}"
    )


def test_call_b_groups_dedup_emits_no_warning_for_clean_config(caplog):
    """Loading the dedup'd live config does NOT emit a B/C dupe
    warning. Pins the validator's clean-config path."""
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
review_reasons: [low_engagement]
x_query_specs:
  - brands:
      llama: [Llama]
    co_occurrence: [api, llm, model]
    min_faves: 0
    call_id: C1
call_b_groups:
  - [minimax, qwen, deepseek]
""",
        )
        with caplog.at_level(logging.WARNING, logger="x_monitor.config"):
            load_config(path)
        dupe_warnings = [
            r for r in caplog.records
            if "call_b_groups shares" in r.getMessage()
        ]
        assert not dupe_warnings, (
            f"Dedup'd config should NOT emit a dupe warning; got: "
            f"{[r.getMessage() for r in dupe_warnings]}"
        )


def test_call_b_groups_dedup_warns_when_dupe_reintroduced(caplog):
    """If a future config reintroduces a brand in BOTH B and C, the
    validator emits a logging.warning naming the offending brands.
    Pin the warning so a refactor that suppresses it fails this test."""
    import logging
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
review_reasons: [low_engagement]
x_query_specs:
  - brands:
      llama: [Llama]
    co_occurrence: [api, llm, model]
    min_faves: 0
    call_id: C1
call_b_groups:
  - [minimax, llama]
""",
        )
        with caplog.at_level(logging.WARNING, logger="x_monitor.config"):
            load_config(path)
        dupe_msgs = [
            r.getMessage() for r in caplog.records
            if "call_b_groups shares" in r.getMessage()
        ]
        assert dupe_msgs, (
            "Config with a brand in both B and C must emit a "
            "dupe warning via logging.warning"
        )
        assert "llama" in dupe_msgs[0], (
            f"Dupe warning must name the offending brand; got: "
            f"{dupe_msgs[0]}"
        )


def test_call_b_groups_dropped_brands_covered_by_call_c_specs():
    """The 6 brands dropped from B (llama, mimo, moonshot_kimi, yi,
    ernie, upstage) are all covered by some x_query_specs[*].brands
    entry. Pins the recall-preservation invariant."""
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
daily_ceiling: 333
enabled_models: [minimax]
review_reasons: [low_engagement]
x_query_specs:
  - brands:
      llama: [Llama]
      mimo: [MiMo]
      moonshot_kimi: [Kimi]
      yi: [Yi]
    co_occurrence: [api, llm, model]
    min_faves: 0
    call_id: C1
  - brands:
      ernie: [ERNIE]
      upstage: [Upstage]
    co_occurrence: [api, llm, model]
    min_faves: 0
    call_id: C2
call_b_groups:
  - [minimax, qwen]
""",
        )
        c = load_config(path)
    covered: set[str] = set()
    for spec in c.x_query_specs:
        covered.update((spec.brands or {}).keys())
    for spec in c.call_c_specs:
        covered.update((spec.brands or {}).keys())
    for brand in ("llama", "mimo", "moonshot_kimi", "yi", "ernie", "upstage"):
        assert brand in covered, (
            f"Brand {brand!r} was dropped from call_b_groups but is "
            f"not covered by any x_query_specs entry — recall "
            f"regression."
        )
