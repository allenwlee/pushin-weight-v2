"""Main-based caller chains: onboarding, classifier catalog, and headline subjects."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import close_old_connections, transaction
from django.utils import timezone

from core.hf_catalog import execute_catalog, resolve_scope
from core.models import HFOrg, Product, TrendNarrative
from core.product_metadata import apply_metadata
from monitor.cycle import _classification_tracked_brand_catalog
from monitor.trend_narrative_lifecycle import _write_subjects
from tests.test_hf_catalog_runner import api, scope
from tests.test_onboard_brand import _config_and_policy, _row, _run, _write_input

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_onboarding_catalog_and_onboarding_rerun_preserve_identity_and_metadata(
    tmp_path,
):
    csv_path = tmp_path / "brands.csv"
    _write_input(
        csv_path,
        [
            _row(
                brand_nickname="lab",
                company_nickname="lab",
                hf_orgs="lab",
                hf_product_repo_ids="lab/model",
            )
        ],
    )
    config, policy = _config_and_policy(tmp_path, nickname="lab")
    _run(csv_path, config, policy)
    original = Product.objects.get(repo_id="lab/model")
    original.display_name = "Curated model"
    original.save(update_fields=["display_name"])
    # The fixture operator has verified this publisher; no live ownership claim.
    HFOrg.objects.filter(pk="lab").update(confirmed=True)
    manifest = resolve_scope(brands=["lab"], companies=[], rules=[])
    assert execute_catalog(scope=manifest, hf=api())["complete"]
    _run(csv_path, config, policy)
    original.refresh_from_db()
    assert original.pk == Product.objects.get(repo_id="lab/model").pk
    assert original.display_name == "Curated model"
    assert original.brand_id == original.hf_org_id == "lab"
    assert original.siblings == [{"rfilename": "w", "size": 32}]
    assert original.downloads_all_time == 4_000_000_000


def test_catalog_products_reach_existing_classifier_catalog():
    assert execute_catalog(scope=scope(), hf=api())["complete"]
    catalog = _classification_tracked_brand_catalog()
    lab = next(row for row in catalog if row["brand_id"] == "lab")
    assert set(lab["products"]) == {
        "model",
        "model-GGUF",
        "lab/model",
        "lab/model-GGUF",
    }


def test_refresh_preserves_existing_headline_product_reference():
    manifest = scope()
    assert execute_catalog(scope=manifest, hf=api())["complete"]
    product = Product.objects.get(repo_id="lab/model")
    narrative = TrendNarrative.objects.create(
        source_cycle_id="hf-catalog-reference",
        window_days=1,
        status=TrendNarrative.Status.CHECKED,
        facts_as_of=timezone.now(),
    )
    _write_subjects(
        narrative,
        [
            {
                "position": 0,
                "support_type": "measured_candidate",
                "entity_type": "model",
                "identity_type": "product",
                "canonical_key_snapshot": product.repo_id,
                "observed_name": "",
                "name_zh_cn_snapshot": "A curated model",
                "candidate_id": "lab:full_window",
                "name_en_snapshot": "A curated model",
            }
        ],
    )
    subject = narrative.subjects.get()
    assert subject.product_id == product.pk
    assert execute_catalog(scope=manifest, hf=api())["imported"] == 0
    subject.refresh_from_db()
    assert subject.product_id == product.pk
    assert subject.canonical_key_snapshot == "lab/model"
    assert subject.name_en_snapshot == "A curated model"


def test_stale_catalog_writer_waits_for_curated_edit_and_preserves_it():
    execute_catalog(scope=scope(), hf=api())
    stale = Product.objects.get(repo_id="lab/model")
    started = threading.Event()

    def write_source():
        close_old_connections()
        try:
            started.set()
            apply_metadata(
                stale, {"id": stale.repo_id, "downloads": 7}, group="expanded"
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            current = Product.objects.select_for_update().get(pk=stale.pk)
            current.display_name = "Owner's edit"
            current.save(update_fields=["display_name"])
            future = pool.submit(write_source)
            assert started.wait(5)
        future.result(timeout=10)
    stale.refresh_from_db()
    assert stale.display_name == "Owner's edit" and stale.downloads == 7
