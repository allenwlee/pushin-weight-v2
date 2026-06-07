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


def test_loads_all_9_models():
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
  - inclusionai_ling
  - inclusionai_ring
  - inclusionai_ming
daily_ceiling: 333
""",
        )
        c = load_config(path)
        assert len(c.enabled_models) == 9
        for m in KNOWN_MODELS:
            assert m in c.enabled_models


def test_rejects_unknown_model_id():
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
    """R17: skip order is Q5, Q3, Q2, Q4, Q1 (Q1 last because release has the
    highest signal-per-tweet ratio)."""
    c = Config(enabled_models=["minimax"], daily_ceiling=100)
    assert c.degraded_skip_order == ["Q5", "Q3", "Q2", "Q4", "Q1"]


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
