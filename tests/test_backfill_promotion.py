"""Actual staged collection/export and isolated destination-like import fixtures."""
import copy
import json
from io import StringIO
from uuid import uuid4

import pytest
from django.core.management import call_command

from core.collection_capture import run_report_document
from core.models import (
    Account,
    CollectionJob,
    CollectionObservation,
    Post,
    PostBrandMention,
    PostEnrichmentState,
)
from monitor import backfill_promotion as promotion
from monitor.backfill_collection import execute_job
from tests.test_backfill_collection import live_writer  # noqa: F401
from tests.test_backfill_prefetch import http_pages, pipeline  # noqa: F401
from tests.test_backfill_staging import result_for, staged_job

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def seal(package):
    package["sha256"] = promotion.signature({k: v for k, v in package.items() if k != "sha256"})
    return package


@pytest.fixture
def exported(http_pages, monkeypatch):  # noqa: F811
    job = staged_job(monkeypatch, 2)
    with http_pages(result_for):
        execute_job(job.pk, collection_options={"concurrency": 2})
    package = promotion.export_posts(job.pk)
    assert len(package["ids"]) == 2
    # One isolated test DB: source collection remains intact. A detached package
    # represents another source DB; tests never connect to production.
    package["source"]["database"]["name"] = "separate_staging_fixture"
    return seal(package)


def destination_package(package, *, new_authors=True):
    p = copy.deepcopy(package)
    ids = {i: "promoted-" + i for i in p["ids"]}
    accounts = {r["account_key"]: str(uuid4()) for r in p["rows"]["Account"]}
    for name, records in p["rows"].items():
        for row in records:
            for key in ("tweet_id", "post_id", "first_source_post_id", "quoted_status_id_id"):
                if key in row and row[key] in ids:
                    row[key] = ids[row[key]]
            if name == "Post":
                row["author_id"] = accounts[row["author_id"]]
            elif name == "Account":
                row["account_key"] = accounts[row["account_key"]]
                if new_authors:
                    for key in ("external_identifier", "normalized_identifier", "author_id", "handle", "normalized_handle"):
                        if row.get(key):
                            row[key] = "promoted-" + row[key]
            elif "account_id" in row:
                row["account_id"] = accounts[row["account_id"]]
            if new_authors:
                for key in ("native_author_id", "native_account_id"):
                    if row.get(key):
                        row[key] = "promoted-" + row[key]
    p["ids"] = sorted(ids.values())
    p["next_after"] = p["ids"][-1]
    return seal(p)


def test_export_command_keyset_and_frozen_file(exported, tmp_path):
    output, stdout = tmp_path / "page.json", StringIO()
    call_command("transfer_backfill", "export", job=exported["source"]["job_id"], output=output,
                 limit=1, stdout=stdout)
    first = json.loads(output.read_text())
    assert len(first["ids"]) == 1
    second = promotion.export_posts(exported["source"]["job_id"], after=first["next_after"], limit=1)
    assert first["ids"] + second["ids"] == exported["ids"]
    assert promotion.export_posts(exported["source"]["job_id"], after=second["next_after"]) is None
    assert output.stat().st_mode & 0o077 == 0
    assert json.loads(stdout.getvalue())["sha256"] == first["sha256"]


@pytest.mark.parametrize("new_authors", [False, True])
def test_transfer_remaps_accounts_preserves_typed_records_and_retries(exported, new_authors):
    package = destination_package(exported, new_authors=new_authors)
    before = Account.objects.count()
    target = promotion.database_identity()
    inspection = promotion.promote_posts(package, target=target)
    assert inspection["existing_posts"] == 0
    assert not Post.objects.filter(pk__in=package["ids"]).exists()
    result = promotion.promote_posts(package, target=target, execute=True)
    assert result["new_post_ids"] == package["ids"]
    assert result["twitterapi_requests"] == result["model_requests"] == 0
    assert Account.objects.count() == before + (2 if new_authors else 0)
    for row in package["rows"]["Post"]:
        post = Post.objects.get(pk=row["tweet_id"])
        assert post.text == row["text"]
        assert post.fetched_at == Post._meta.get_field("fetched_at").to_python(row["fetched_at"])
        assert str(post.author_id) != row["author_id"]
        assert post.author.profile_snapshots.exists()
        state = post.enrichment_state
        assert state.translation_status == state.classification_status == "pending"
        assert str(state.source_collection_job_id) == result["job_id"]
        expected = {f.attname: f.to_python(row[f.attname]) for f in promotion.fields(Post)}
        expected["author_id"] = post.author_id
        assert {f.attname: f.value_from_object(post) for f in promotion.fields(Post)} == expected
    assert set(CollectionObservation.objects.filter(run_id=result["run_id"]).values_list("post_id", flat=True)) == set(package["ids"])
    assert PostBrandMention.objects.filter(post_id__in=package["ids"]).count() == len(package["rows"]["PostBrandMention"])
    assert promotion.promote_posts(package, target=target, execute=True)["replayed"]


def test_existing_live_post_account_and_enrichment_are_unchanged(exported):
    post = Post.objects.get(pk=exported["ids"][0])
    Post.objects.filter(pk=post.pk).update(text="newer live text", like_count=999)
    Account.objects.filter(pk=post.author_id).update(display_name="newer live name")
    PostEnrichmentState.objects.filter(post=post).update(translation_status="succeeded", classification_status="succeeded")
    posts_before = list(Post.objects.order_by("pk").values())
    states_before = list(PostEnrichmentState.objects.order_by("pk").values())
    accounts_before = list(Account.objects.order_by("pk").values())
    result = promotion.promote_posts(exported, target=promotion.database_identity(), execute=True)
    assert result["existing_posts"] == 2 and result["new_post_ids"] == []
    assert list(Post.objects.order_by("pk").values()) == posts_before
    assert list(PostEnrichmentState.objects.order_by("pk").values()) == states_before
    assert list(Account.objects.order_by("pk").values()) == accounts_before


def test_failure_after_post_insert_rolls_back_entire_cohort(exported, monkeypatch):
    package = destination_package(exported)
    before = (Post.objects.count(), Account.objects.count(), CollectionJob.objects.count())
    original = promotion.insert_rows
    def failing(model, records):
        if model is PostBrandMention:
            raise ValueError("fixture relation failure")
        return original(model, records)
    monkeypatch.setattr(promotion, "insert_rows", failing)
    with pytest.raises(ValueError, match="relation failure"):
        promotion.promote_posts(package, target=promotion.database_identity(), execute=True)
    assert (Post.objects.count(), Account.objects.count(), CollectionJob.objects.count()) == before
    monkeypatch.setattr(promotion, "insert_rows", original)
    assert len(promotion.promote_posts(package, target=promotion.database_identity(), execute=True)["new_post_ids"]) == 2


@pytest.mark.parametrize("fault", ["hash", "schema", "identity", "source_target", "target", "field", "timestamp"])
def test_corrupt_or_wrong_destination_package_refused_before_writes(exported, fault):
    package = destination_package(exported)
    target = promotion.database_identity()
    if fault == "hash":
        package["sha256"] = "0" * 64
    elif fault == "schema":
        package["schema"] = "old-schema"; seal(package)
    elif fault == "identity":
        package["rows"]["Account"][0]["normalized_identifier"] = "wrong"; seal(package)
    elif fault == "source_target":
        package["source"]["database"] = {**target, "user": "different-role"}; seal(package)
    elif fault == "target":
        target["name"] = "wrong"
    elif fault == "field":
        package["rows"]["Post"][0]["unexpected"] = True; seal(package)
    else:
        package["rows"]["Post"][0]["created_at_epoch"] = 1; seal(package)
    before = (Post.objects.count(), CollectionJob.objects.count())
    with pytest.raises(ValueError):
        promotion.promote_posts(package, target=target, execute=True)
    assert (Post.objects.count(), CollectionJob.objects.count()) == before


def test_quote_parents_arriving_later_reconcile_only_unchanged_new_posts(exported):
    package = destination_package(exported)
    for row in package["rows"]["Post"]:
        row["quoted_status_id_id"] = "late-parent"
    seal(package)
    target = promotion.database_identity()
    promotion.promote_posts(package, target=target, execute=True)
    assert promotion.reconcile_quotes(package, target=target)["pending"] == package["ids"]
    Post.objects.create(tweet_id="late-parent", text="parent")
    Post.objects.filter(pk=package["ids"][1]).update(text="newer edited text")
    result = promotion.reconcile_quotes(package, target=target, execute=True)
    assert result["attached"] == package["ids"][:1]
    assert result["changed"] == package["ids"][1:]
    assert Post.objects.get(pk=package["ids"][1]).quoted_status_id_id is None
    assert promotion.reconcile_quotes(package, target=target, execute=True)["already_attached"] == package["ids"][:1]


def test_promotion_respects_real_live_writer(exported, live_writer):  # noqa: F811
    package = destination_package(exported)
    with live_writer(), pytest.raises(ValueError, match="waiting for live writer"):
        promotion.promote_posts(package, target=promotion.database_identity(), execute=True)
    assert not Post.objects.filter(pk__in=package["ids"]).exists()


def test_promote_command_defaults_to_read_only(exported, tmp_path):
    package = destination_package(exported)
    source = tmp_path / "package.json"
    source.write_bytes(promotion.encoded(package))
    target = promotion.database_identity()
    stdout = StringIO()
    call_command("transfer_backfill", "promote", package=source, target_host=target["host"],
                 target_name=target["name"], target_user=target["user"], stdout=stdout)
    assert json.loads(stdout.getvalue())["posts"] == 2
    assert not Post.objects.filter(pk__in=package["ids"]).exists()


def test_live_arriving_during_promotion_rolls_back_and_gets_writer(exported, monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections

    from monitor.run_lock import backfill_yield_requested, harvest_writer_lock

    package = destination_package(exported)
    original = promotion.insert_rows
    pending = []
    def live():
        try:
            with harvest_writer_lock(execution_mode="live", entrypoint="test.promotion.queued",
                                     wait_for_backfill_seconds=10) as lease:
                return lease.acquired
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        def insert(model, records):
            value = original(model, records)
            if model is Post:
                pending.append(pool.submit(live))
                until = time.monotonic() + 5
                while not backfill_yield_requested() and time.monotonic() < until:
                    time.sleep(.01)
                assert backfill_yield_requested()
            return value
        monkeypatch.setattr(promotion, "insert_rows", insert)
        with pytest.raises(ValueError, match="yielding to live writer"):
            promotion.promote_posts(package, target=promotion.database_identity(), execute=True)
        assert pending[0].result(timeout=10)
    assert not Post.objects.filter(pk__in=package["ids"]).exists()


def test_promoted_cohort_is_visible_to_existing_enrichment_command(exported):
    package = destination_package(exported)
    result = promotion.promote_posts(package, target=promotion.database_identity(), execute=True)
    stdout = StringIO()
    call_command("backfill", collection_job=result["job_id"], enrich_direct=True, status=True,
                 stdout=stdout)
    status = json.loads(stdout.getvalue())
    assert status["source_collection_job"] == result["job_id"]
    assert status["cohort_count"] == status["pending_count"] == 2
    assert status["model_requests_sent"] == status["twitterapi_requests"] == 0
    assert status["status"] == "partial"


def test_live_arriving_during_quote_repair_rolls_back_links(exported, monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections
    from django.db.models import QuerySet

    from monitor.run_lock import backfill_yield_requested, harvest_writer_lock

    package = destination_package(exported)
    for row in package["rows"]["Post"]:
        row["quoted_status_id_id"] = "late-parent"
    seal(package)
    target = promotion.database_identity()
    result = promotion.promote_posts(package, target=target, execute=True)
    Post.objects.create(tweet_id="late-parent", text="parent")
    original = QuerySet.update
    pending = []

    def live():
        try:
            with harvest_writer_lock(execution_mode="live", entrypoint="test.promotion.quotes.queued",
                                     wait_for_backfill_seconds=10) as lease:
                return lease.acquired
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        def update(queryset, **values):
            count = original(queryset, **values)
            if queryset.model is Post and "quoted_status_id_id" in values:
                pending.append(pool.submit(live))
                until = time.monotonic() + 5
                while not backfill_yield_requested() and time.monotonic() < until:
                    time.sleep(.01)
                assert backfill_yield_requested()
            return count
        monkeypatch.setattr(QuerySet, "update", update)
        with pytest.raises(ValueError, match="yielding to live writer"):
            promotion.reconcile_quotes(package, target=target, execute=True)
        assert pending[0].result(timeout=10)
    assert not Post.objects.filter(pk__in=package["ids"], quoted_status_id__isnull=False).exists()
    assert "quote_reconciliation" not in run_report_document(CollectionJob.objects.get(pk=result["job_id"]).last_success)
