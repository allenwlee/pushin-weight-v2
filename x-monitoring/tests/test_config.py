# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.config."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from x_monitor.config import KNOWN_MODELS, Config, load_config


def _write(tmp: Path, body: str) -> Path:
    p = tmp / "config.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_all_known_models():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
enabled_models:
  - minimax
  - qwen
  - deepseek
  - glm
  - xiaomi_mimo
  - moonshot_kimi
  - inclusionai
  - mistral
  - stepfun
  - ernie
  - hunyuan
  - llama
  - nvidia_nemo
  - doubao
  - yi
  - sensechat
  - exaone
  - sakana
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
enabled_models:
  - minimax
  - bogus_model
daily_ceiling: 100
""",
        )
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        assert "bogus_model" in str(exc_info.value)


def test_rejects_daily_ceiling_zero():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
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
enabled_models: [minimax, minimax]
daily_ceiling: 100
""",
        )
        with pytest.raises(ValidationError) as exc_info:
            load_config(path)
        assert "duplicate" in str(exc_info.value).lower()


def test_default_skip_order_is_r17():
    """R17: skip order is Q6, Q5, Q3, Q2, Q4, Q1 (Q1 last because release has the
    highest signal-per-tweet ratio)."""
    c = Config(enabled_models=["minimax"], daily_ceiling=100)
    assert c.degraded_skip_order == ["Q6", "Q5", "Q3", "Q2", "Q4", "Q1"]


def test_skip_order_must_contain_all_query_ids():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
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
enabled_models: [minimax]
daily_ceiling: 100
query_rot_streak_threshold_per_model:
  bogus_model: 5
""",
        )
        with pytest.raises(ValidationError):
            load_config(path)


def test_rejects_unknown_review_reason():
    with tempfile.TemporaryDirectory() as d:
        path = _write(
            Path(d),
            """
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
