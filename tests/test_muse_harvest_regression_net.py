"""Caller-chain pins for Muse collection on the seven-call harvest path."""

from importlib import import_module
from io import StringIO
from pathlib import Path

import pytest
from django.apps import apps
from django.core.management import call_command
from django.test import override_settings

from monitor.cycle import plan_calls_for_cycle
from x_monitor.config import load_config
from x_monitor.harvest_policy import load_policy

REPO = Path(__file__).resolve().parent.parent
MUSE_PHRASES = ('"Meta Muse"', '"Muse Spark"', '"Muse Glimmer"', '"Muse Realtime"')


def test_live_policy_plans_muse_phrases_in_existing_c1_call(monkeypatch):
    monkeypatch.chdir(REPO)
    cfg = load_config(REPO / "config.yaml")
    policy = load_policy(REPO / "config" / "harvest_policy.yaml")

    assert "muse" in cfg.enabled_models
    assert "muse" in policy.co_packs[0].brand_nicknames
    calls = plan_calls_for_cycle(cfg)
    assert {call.call_id for call in calls} == {"A", "B1", "B2", "B3", "C1", "C2", "C3"}
    c1 = next(call.query_string for call in calls if call.call_id == "C1")
    assert all(phrase in c1 for phrase in MUSE_PHRASES)
    assert "(llm OR model OR api OR agentic OR huggingface)" in c1
    assert len(c1) + len(" since_time:9999999999 until_time:9999999999") <= 512
    b3 = next(call.query_string for call in calls if call.call_id == "B3")
    assert "alexandr_wang" not in b3


def test_muse_phrase_collection_does_not_add_bare_muse_or_a_new_call(monkeypatch):
    monkeypatch.chdir(REPO)
    policy = load_policy(REPO / "config" / "harvest_policy.yaml")
    muse = policy.brand("muse")

    assert muse.paths == frozenset({"co"})
    assert "muse" not in muse.tokens
    assert "muse" not in [token.casefold() for token in muse.tokens]


def test_scheduled_muse_c1_keeps_quality_author_exclusion_and_time_headroom(
    monkeypatch,
):
    monkeypatch.chdir(REPO)
    cfg = load_config(REPO / "config.yaml")

    calls = plan_calls_for_cycle(cfg, scheduled_exclusions=True)
    assert {call.call_id for call in calls} == {"A", "B1", "B2", "B3", "C1", "C2", "C3"}
    c1 = next(call.query_string for call in calls if call.call_id == "C1")
    assert all(phrase in c1 for phrase in MUSE_PHRASES)
    assert "-from:xxyweb3" in c1
    assert len(c1) + len(" since_time:9999999999 until_time:9999999999") <= 512


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_muse_migration_catalog_is_idempotent_and_keeps_nvidia_product():
    from core.models import Brand, BrandKeyword, BrandSearchTerm, Product
    from monitor.cycle import _classification_tracked_brand_catalog

    muse = Brand.objects.get(nickname="muse")
    assert muse.display_name == "Meta Muse"
    assert muse.companies.filter(company_id="meta").exists()
    expected = {"Meta Muse", "Muse Spark", "Muse Glimmer", "Muse Realtime"}
    assert set(
        BrandKeyword.objects.filter(brand=muse, is_regex=False).values_list(
            "pattern", flat=True
        )
    ) >= expected
    assert set(
        BrandSearchTerm.objects.filter(brand=muse).values_list("term", flat=True)
    ) >= expected
    assert set(
        Product.objects.filter(brand=muse).values_list("display_name", flat=True)
    ) >= {"Muse Spark", "Muse Glimmer"}

    nvidia, _ = Brand.objects.get_or_create(nickname="nemo_megatron")
    nvidia_product = Product.objects.create(
        brand=nvidia, display_name="Muse Glimmer NVIDIA variant"
    )
    migration = import_module("core.migrations.0059_account_user_about_and_muse")
    BrandKeyword.objects.get_or_create(
        brand_id="llama", pattern="Muse Spark", defaults={"is_regex": False}
    )
    before_products = Product.objects.filter(brand=muse).count()
    migration.install_muse_catalog(apps, None)
    migration.install_muse_catalog(apps, None)

    assert Product.objects.get(pk=nvidia_product.pk).brand_id == "nemo_megatron"
    assert Product.objects.filter(brand=muse).count() == before_products
    assert not BrandKeyword.objects.filter(
        brand_id="llama", pattern="Muse Spark"
    ).exists()
    catalog = {
        row["brand_id"]: row
        for row in _classification_tracked_brand_catalog()
    }
    assert {"Muse Spark", "Muse Glimmer"} <= set(catalog["muse"]["products"])


@pytest.mark.requires_postgres
@pytest.mark.django_db
@override_settings(KNOWN_MODELS=frozenset({"llama", "muse"}))
def test_meta_seed_keeps_wang_llama_staff_only():
    from core.models import BrandAccount

    call_command("load_seed", brands="llama,muse", stdout=StringIO())

    assert BrandAccount.objects.filter(
        brand_id="llama", account_id="alexandr_wang", role_id="staff"
    ).exists()
    assert not BrandAccount.objects.filter(
        brand_id="muse", account_id="alexandr_wang"
    ).exists()
