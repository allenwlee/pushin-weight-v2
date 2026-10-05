import pytest

from monitor.editorial.config import EditorialConfig, load_editorial_config
from monitor.editorial.voices import load_voice


def test_shipped_configuration_cannot_spend_or_publish():
    cfg = load_editorial_config()
    assert not cfg.enabled and not cfg.public_enabled
    assert cfg.picture_mode("chatter", "x") == "off"
    assert cfg.daily_usd == 0


def test_atomic_platform_override_does_not_disable_headline_pictures():
    cfg = EditorialConfig(
        pictures={"atomic": "select_only", "atomic:x": "off", "chatter": "derive"},
        daily_usd=1,
        assessment_usd=1,
        daily_calls=5,
        media_daily_calls=1,
        media_cost_ceiling_usd=1,
    )
    assert cfg.picture_mode("atomic", "x") == "off"
    assert cfg.picture_mode("atomic", "youtube") == "select_only"
    assert cfg.picture_mode("chatter", "x") == "derive"


def test_enabled_generation_requires_explicit_routes_and_budgets():
    with pytest.raises(ValueError):
        EditorialConfig(enabled=True)


def test_voice_is_versioned_independent_of_provider_and_atomic_tone():
    voice = load_voice("chatter-en-v1")
    assert voice.locale == "en" and voice.track == "chatter"
    assert len(voice.digest) == 64
    assert "New York Post" in voice.instructions
    with pytest.raises(ValueError):
        load_voice("../config")
    with pytest.raises(ValueError, match="unavailable"):
        load_voice("chatter-ja-v1")


def test_unavailable_or_mismatched_bindings_rejected_before_activation():
    from tests.editorial_support import active_config

    with pytest.raises(ValueError, match="binding mismatch"):
        active_config(voices={"chatter:en": "pulse-en-v1"})
    with pytest.raises(ValueError, match="unavailable"):
        active_config(voices={"chatter:ja": "chatter-ja-v1"})
