"""Backfill spending uses a distinct key without changing scheduled factories."""

from pathlib import Path

import pytest

from x_monitor.config import load_config
from x_monitor.reattribute import (
    build_classifier_client_from_env,
    build_relevancy_client_from_env,
    build_translator_client_from_env,
)

ROLE_FACTORIES = [
    build_classifier_client_from_env,
    build_relevancy_client_from_env,
    build_translator_client_from_env,
]


@pytest.mark.parametrize("factory", ROLE_FACTORIES)
def test_backfill_role_uses_only_on_demand_key(factory, monkeypatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "scheduled-fixture")
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "on-demand-fixture")
    cfg = load_config(Path("config.yaml"))
    client = factory(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND")
    assert client.api_key == "on-demand-fixture"
    assert factory(cfg).api_key == "scheduled-fixture"
    assert client.request_identity == factory(cfg).request_identity


@pytest.mark.parametrize("factory", ROLE_FACTORIES)
def test_backfill_role_works_without_scheduled_key(factory, monkeypatch):
    monkeypatch.delenv("DEEPINFRA_API_KEY", raising=False)
    monkeypatch.setenv("DEEPINFRA_ON_DEMAND", "on-demand-fixture")
    cfg = load_config(Path("config.yaml"))
    assert factory(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND").api_key == "on-demand-fixture"
    assert factory(cfg) is None


@pytest.mark.parametrize("factory", ROLE_FACTORIES)
@pytest.mark.parametrize("on_demand", [None, "", "   "])
def test_backfill_role_never_borrows_scheduled_key(factory, on_demand, monkeypatch):
    monkeypatch.setenv("DEEPINFRA_API_KEY", "scheduled-fixture")
    monkeypatch.delenv("DEEPINFRA_ON_DEMAND", raising=False)
    if on_demand is not None:
        monkeypatch.setenv("DEEPINFRA_ON_DEMAND", on_demand)
    cfg = load_config(Path("config.yaml"))
    assert factory(cfg, deepinfra_key_env="DEEPINFRA_ON_DEMAND") is None
    assert factory(cfg).api_key == "scheduled-fixture"
