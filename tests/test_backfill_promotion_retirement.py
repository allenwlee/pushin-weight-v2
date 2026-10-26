"""Manual Post transfer and quote repair with retired collection columns denied."""
# ruff: noqa: F811 -- imported pytest fixtures are named by each test signature.

import copy
import json
from io import StringIO

import httpx
import pytest
from django.core.management import call_command
from django.db import transaction

from core.collection_capture import archive_legacy, run_report_document
from core.models import CollectionJob, Post
from monitor import backfill_promotion as promotion
from tests.test_backfill_promotion import (  # noqa: F401
    destination_package,
    exported,
    http_pages,
    pipeline,
    seal,
)
from tests.test_hf_catalog_retirement import denied_retirement_columns

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def quote_package(exported):
    package = destination_package(exported)
    for row in package["rows"]["Post"]:
        row["quoted_status_id_id"] = "late-parent"
    return seal(package)


def legacy_receipt(package, *, reconciled=False):
    target = promotion.database_identity()
    result = promotion.promote_posts(package, target=target, execute=True)
    job = CollectionJob.objects.get(pk=result["job_id"])
    if reconciled:
        promotion.reconcile_saved_quotes(job.pk, target=target, execute=True)
    run = job.last_success
    report = run_report_document(run)
    run.legacy_archive = archive_legacy({"report": report})
    run.save(update_fields=["legacy_archive"])
    run.scopes.filter(scope_kind="quote_repair").delete()
    run.scopes.filter(scope_kind="staged_post_copy").update(phase=None)
    run.observations.update(
        projection_kind=None, observation_kind=None, processing_outcome=None,
        coordinate_key=None, payload_sha256=promotion.signature({}),
    )
    return job, run, report, target


def test_real_command_replay_and_saved_quote_repair_use_typed_membership(
    exported, tmp_path, monkeypatch,
):
    package = quote_package(exported)
    path = tmp_path / "package.json"
    path.write_bytes(promotion.encoded(package))
    target = promotion.database_identity()
    monkeypatch.setattr(httpx.Client, "send", lambda *a, **kw: pytest.fail("promotion fetched HTTP"))
    with denied_retirement_columns():
        output = StringIO()
        call_command("transfer_backfill", "promote", package=path, execute=True,
                     target_host=target["host"], target_name=target["name"],
                     target_user=target["user"], stdout=output)
        result = json.loads(output.getvalue())
        job = CollectionJob.objects.get(pk=result["job_id"])
        run = job.last_success
        assert run_report_document(run)["promotion"] == result
        members = list(run.observations.order_by("post_id"))
        assert [item.post_id for item in members] == package["ids"]
        assert all(item.processing_outcome == "inserted" and item.coordinate_key == "late-parent"
                   and item.projection_kind == promotion.MEMBERSHIP_KIND for item in members)
        assert run.request_count == 0 and run.attempts.get().actual_requests == 0
        assert run.attempts.get().accounting_complete
        assert promotion.promote_posts(package, target=target, execute=True) == {**result, "replayed": True}
        path.unlink()
        Post.objects.create(tweet_id="late-parent", text="parent")
        Post.objects.filter(pk=package["ids"][1]).update(text="newer live text")
        repaired = promotion.reconcile_saved_quotes(job.pk, target=target, execute=True)
        assert repaired["attached"] == package["ids"][:1]
        assert repaired["changed"] == package["ids"][1:]
        assert run_report_document(run)["quote_reconciliation"] == repaired
        repeated = promotion.reconcile_saved_quotes(job.pk, target=target, execute=True)
        assert repeated["already_attached"] == package["ids"][:1]
        assert run_report_document(run)["promotion"]["pending_quotes"] == result["pending_quotes"]
        assert Post.objects.get(pk=package["ids"][1]).quoted_status_id_id is None


def test_existing_live_members_and_empty_quote_reconciliation_remain_explicit(exported):
    target = promotion.database_identity()
    before = list(Post.objects.order_by("pk").values())
    with denied_retirement_columns():
        result = promotion.promote_posts(exported, target=target, execute=True)
        job = CollectionJob.objects.get(pk=result["job_id"])
        assert result["new_post_ids"] == [] and result["existing_posts"] == 2
        assert set(job.last_success.observations.values_list("processing_outcome", flat=True)) == {"existing"}
        assert "quote_reconciliation" not in run_report_document(job.last_success)
        summary = promotion.reconcile_saved_quotes(job.pk, target=target, execute=True)
        assert summary == {"job_id": str(job.pk), "attached": [], "already_attached": [], "pending": [], "changed": []}
        assert run_report_document(job.last_success)["quote_reconciliation"] == summary
        assert not job.last_success.scopes.filter(scope_kind="quote_repair").exists()
        assert list(Post.objects.order_by("pk").values()) == before


def test_historical_promotion_replays_archive_until_explicit_repair_adoption(exported):
    package = quote_package(exported)
    job, run, report, target = legacy_receipt(package)
    with denied_retirement_columns():
        assert run_report_document(run) == report
        assert promotion.promote_posts(package, target=target, execute=True)["replayed"]
        assert promotion.reconcile_saved_quotes(job.pk, target=target)["pending"] == package["ids"]
        assert run.scopes.get(scope_kind="staged_post_copy").phase is None
        assert not run.observations.exclude(projection_kind=None).exists()
        Post.objects.create(tweet_id="late-parent", text="parent")
        result = promotion.reconcile_saved_quotes(job.pk, target=target, execute=True)
        assert result["attached"] == package["ids"]
        assert run_report_document(run)["promotion"] == report["promotion"]
        assert run_report_document(run)["quote_reconciliation"] == result
        assert run.scopes.get(scope_kind="staged_post_copy").phase == promotion.QUOTE_PHASE
        assert run.observations.filter(projection_kind=promotion.MEMBERSHIP_KIND).count() == 2


def test_exact_adoption_preserves_archived_quote_outcomes(exported):
    _, run, report, _ = legacy_receipt(quote_package(exported), reconciled=True)
    with denied_retirement_columns(), transaction.atomic():
        promotion.adopt_promotion_run(run)
        assert run_report_document(run) == report
        assert run.scopes.filter(scope_kind="quote_repair", phase=promotion.QUOTE_PHASE).count() == 2


@pytest.mark.parametrize("fault", ["new_member", "export_hash", "quote_hash", "typed_conflict", "missing_archive"])
def test_legacy_quote_adoption_refuses_unqualified_receipt_before_post_changes(exported, fault):
    package = quote_package(exported)
    job, run, report, target = legacy_receipt(package)
    changed = copy.deepcopy(report)
    if fault == "new_member":
        changed["promotion"]["new_post_ids"].append("unowned")
    elif fault == "export_hash":
        changed["promotion"]["export_sha256"] = "a" * 64
    elif fault == "quote_hash":
        changed["promotion"]["pending_quotes"][package["ids"][0]]["text_sha256"] = "bad"
    elif fault == "typed_conflict":
        run.observations.filter(post_id=package["ids"][0]).update(processing_outcome="existing")
    run.legacy_archive = None if fault == "missing_archive" else archive_legacy({"report": changed})
    run.save(update_fields=["legacy_archive"])
    Post.objects.create(tweet_id="late-parent", text="parent")
    with denied_retirement_columns():
        with pytest.raises(ValueError):
            promotion.reconcile_saved_quotes(job.pk, target=target, execute=True)
        assert not Post.objects.filter(pk__in=package["ids"], quoted_status_id__isnull=False).exists()
        assert run.scopes.get(scope_kind="staged_post_copy").phase is None
        assert not run.scopes.filter(scope_kind="quote_repair").exists()


@pytest.mark.parametrize("fault", ["member_outcome", "quote_owner", "quote_parent"])
def test_typed_promotion_report_rejects_changed_membership_owners(exported, fault):
    package = quote_package(exported)
    target = promotion.database_identity()
    with denied_retirement_columns():
        result = promotion.promote_posts(package, target=target, execute=True)
        job = CollectionJob.objects.get(pk=result["job_id"])
        promotion.reconcile_saved_quotes(job.pk, target=target, execute=True)
        run = job.last_success
        members = list(run.observations.order_by("post_id"))
        if fault == "member_outcome":
            run.observations.filter(pk=members[0].pk).update(processing_outcome="existing")
        else:
            scope = run.scopes.get(scope_kind="quote_repair", scope_key=members[0].post_id)
            if fault == "quote_owner":
                scope.resource_observation = members[1]
                scope.save(update_fields=["resource_observation"])
            else:
                scope.parent_scope = None
                scope.save(update_fields=["parent_scope"])
        with pytest.raises(ValueError):
            run_report_document(run)
