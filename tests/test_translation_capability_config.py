from pathlib import Path

from x_monitor.config import load_config


def test_shared_translator_capability_wins_over_process_environment(monkeypatch):
    monkeypatch.setenv('X_MONITOR_LITERAL_TRANSLATION_V2_ENABLED', 'false')
    web = load_config(Path('config.yaml')).llm.literal_translation_v2_enabled
    monkeypatch.setenv('X_MONITOR_LITERAL_TRANSLATION_V2_ENABLED', 'true')
    worker = load_config(Path('config.yaml')).llm.literal_translation_v2_enabled
    assert web is worker is True
