import pytest
from django.db import connection, transaction

from core.models import EventDossierClaim, ProductRelationship

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def test_recovery_finds_saved_child_and_skips_completed_relationship():
    from django.test.utils import CaptureQueriesContext

    from core.product_release_lineage import resolve_reported_lineage
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings

    parent, child = _two_saved_findings()
    with pytest.raises(ValueError, match="caller's transaction"):
        find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=5, max_bytes=10000, max_seconds=5)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        with CaptureQueriesContext(connection) as captured:
            page = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=5, max_bytes=10000, max_seconds=5)
        lookup = next(row["sql"] for row in captured if "MD5(UPPER(" in row["sql"] and "event_dossier_claims" in row["sql"])
        cursor.execute("EXPLAIN " + lookup)
        plan = "\n".join(row[0] for row in cursor.fetchall())
        assert "event_dossier_claims" in plan
    assert page["posts"] == ["lineage-post-5"] and not page["more_remaining"]
    assert not ProductRelationship.objects.exists()
    assert resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0, basis_version_id=None,
                                    max_candidates=5, max_subjects=2, max_seconds=5)["status"] == "created"
    with transaction.atomic():
        replay = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=5, max_bytes=10000, max_seconds=5)
    assert replay["posts"] == [] and not replay["more_remaining"]


def test_recovery_wakes_child_when_current_review_changes_its_product():
    from django.utils import timezone

    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from core.models import Product
    from core.product_release_lineage import resolve_reported_lineage
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings

    parent, child = _two_saved_findings()
    assert resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0, basis_version_id=None,
                                    max_candidates=5, max_subjects=2, max_seconds=5)["status"] == "created"
    old = Product.objects.get(pk=child["product_id"])
    replacement = Product.objects.create(display_name="Model 5", brand=old.brand, product_type=old.product_type)
    complete_review(child["dossier_id"], expected_current_review_id=None, display_title="Model 5", review_state="confirmed",
                    evidence_cutoff_at=timezone.now(), method_version="test", actor="test", reason="Corrected identity",
                    claims=[ClaimDecision(child["anchor_claim_id"], "accepted", "Source")],
                    product_release=ProductReleaseInput(observed_name="Model 5", product_key=replacement.product_key))
    with transaction.atomic():
        page = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=5, max_bytes=10000, max_seconds=5)
    assert page["posts"] == ["lineage-post-5"]


def test_lookup_failure_restores_outer_transaction_timeouts(monkeypatch):
    import core.product_release_dossiers as dossiers
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout = '9s'")
        monkeypatch.setattr(dossiers, "_read_pulse_packet", lambda _claim: (_ for _ in ()).throw(ValueError("bad source")))
        with pytest.raises(ValueError, match="bad source"):
            find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=5, max_bytes=10000, max_seconds=1)
        cursor.execute("SHOW statement_timeout")
        assert cursor.fetchone()[0] == "9s"


def test_recovery_keyset_and_byte_budget_preserve_pending_rows():
    from core.models import Post
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings
    from tests.test_pulse_finding_persistence import finding

    parent, _ = _two_saved_findings()
    post = Post.objects.create(tweet_id="lineage-pending-another", text="Model 6 succeeds Model 4")
    item = finding(name="Model 6", key="6" * 64)
    item["assertions"][0].update(assertion_text=post.text, source_excerpt=post.text)
    item["lineage_evidence"] = [{"relationship_kind": "new_version", "parent_observed_name": "Model 4",
                                 "source_excerpt": post.text, "source_locator": None}]
    persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="a" * 64,
                                        content_fingerprint="b" * 64, extraction_version="test", findings=[item])
    with transaction.atomic():
        blocked = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=1, max_bytes=1, max_seconds=5)
    assert blocked["status"] == "budget" and blocked["next_cursor"] is None and blocked["more_remaining"]
    with transaction.atomic():
        first = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=1, max_bytes=10000, max_seconds=5)
        second = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], after=first["next_cursor"],
                                         limit=1, max_bytes=10000, max_seconds=5)
    assert first["more_remaining"] and set(first["posts"] + second["posts"]) == {"lineage-post-5", post.pk}
    assert not second["more_remaining"]


def test_recovery_preserves_non_x_source_without_fabricating_a_post():
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_benchmark_download_db_models import measurement
    from tests.test_product_release_lineage import _two_saved_findings
    from tests.test_pulse_finding_persistence import finding

    parent, _ = _two_saved_findings()
    _, _, observation = measurement()
    item = finding(name="Model 6", key="6" * 64)
    item["lineage_evidence"] = [{"relationship_kind": "new_version", "parent_observed_name": "Model 4",
                                 "source_excerpt": "Model 6 succeeds Model 4", "source_locator": None}]
    persist_classified_release_findings(source={"kind": "observation", "id": observation.pk}, revision_id="a" * 64,
                                        content_fingerprint="b" * 64, extraction_version="test", findings=[item])
    with transaction.atomic():
        page = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=5, max_bytes=20000, max_seconds=5)
    assert observation.pk in page["observations"]
    assert page["posts"] == ["lineage-post-5"]


def test_online_index_covers_preexisting_lineage_claims(monkeypatch):
    from django.db.migrations.executor import MigrationExecutor

    from tests.test_product_release_lineage import _two_saved_findings

    old = [("core", "0227_pulse_product_category_guard")]
    new = [("core", "0231_lineage_fanin_index")]
    MigrationExecutor(connection).migrate(old)
    try:
        # Simulate the prior writer, which predates the new job operation.
        monkeypatch.setattr("core.product_release_lineage_recovery.register_lineage_wakeup", lambda **kwargs: None)
        _two_saved_findings()
        assert EventDossierClaim.objects.filter(scope_key__startswith="pulse-lineage-v1:").exists()
    finally:
        MigrationExecutor(connection).migrate(new)
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT indisvalid FROM pg_index WHERE indexrelid = 'idx_ed_lineage_hash_id'::regclass")
        assert cursor.fetchone()[0] is True
        cursor.execute("SET LOCAL enable_seqscan = off")
        cursor.execute("EXPLAIN SELECT id FROM event_dossier_claims WHERE source_archive_id IS NOT NULL AND scope_key LIKE 'pulse-lineage-v1:%%' AND md5(upper(assertion_text)) = md5(upper(%s))",
                       ["Classifier-reported new_version: Model 4"])
        assert "idx_ed_lineage_hash_id" in "\n".join(row[0] for row in cursor.fetchall())


def test_synthetic_lookup_plan_with_unrelated_claim_history():
    import hashlib

    from django.test.utils import CaptureQueriesContext

    from core.models import EventClaimKind
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    source_id = EventDossierClaim.objects.get(pk=parent["anchor_claim_id"]).event_dossier_source_id
    kind = EventClaimKind.objects.get(code="release_context")
    EventDossierClaim.objects.bulk_create([
        EventDossierClaim(event_dossier_source_id=source_id, claim_kind_reference=kind,
                          scope_key=f"synthetic-unrelated-{number}", extraction_version="fixture",
                          claim_hash=hashlib.sha256(str(number).encode()).hexdigest(), assertion_text="Unrelated evidence",
                          source_excerpt="Unrelated evidence", source_hash=hashlib.sha256(b"Unrelated evidence").hexdigest())
        for number in range(3000)
    ], batch_size=500)
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE event_dossier_claims")
    with transaction.atomic(), connection.cursor() as cursor:
        with CaptureQueriesContext(connection) as captured:
            page = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=5, max_bytes=10000, max_seconds=5)
        lookup = next(row["sql"] for row in captured if "MD5(UPPER(" in row["sql"] and "event_dossier_claims" in row["sql"])
        cursor.execute("EXPLAIN " + lookup)
        plan = "\n".join(row[0] for row in cursor.fetchall())
        print("Synthetic 3,000 unrelated claims: lineage hash index used:", "idx_ed_lineage_hash_id" in plan)
    assert page["posts"] == ["lineage-post-5"]


def test_wakeup_job_commits_enqueue_and_cursor_and_replays_without_growth():
    from core.models import CollectionJob, ProductReleaseDetectionState
    from core.product_release_lineage_recovery import (
        drain_lineage_wakeup,
        register_lineage_wakeup,
    )
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    budgets = {"requests": 1, "bytes": 10000, "seconds": 5, "items": 1}
    with transaction.atomic():
        registered = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None, budgets=budgets)
        repeated = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None, budgets=budgets)
    assert registered["status"] == "registered" and repeated["job_id"] == registered["job_id"]
    result = drain_lineage_wakeup(registered["job_id"])
    assert result["status"] == "complete" and result["posts"] == 1
    assert ProductReleaseDetectionState.objects.filter(post_id="lineage-post-5").exists()
    job = CollectionJob.objects.get(pk=registered["job_id"])
    assert job.last_success.scopes.get(scope_kind="lineage_wakeup").cursor
    assert drain_lineage_wakeup(job.pk) == {"status": "complete", "reused": True}


def test_wakeup_registration_rolls_back_with_qualification():
    from core.models import CollectionJob
    from core.product_release_lineage_recovery import register_lineage_wakeup
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    before = CollectionJob.objects.filter(operation="lineage_wakeup").count()
    with pytest.raises(RuntimeError, match="rollback"), transaction.atomic():
        register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                               budgets={"requests": 1, "bytes": 10000, "seconds": 5, "items": 2})
        raise RuntimeError("rollback")
    assert CollectionJob.objects.filter(operation="lineage_wakeup").count() == before


def test_wakeup_preserves_non_x_pending_observation():
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_lineage_recovery import (
        drain_lineage_wakeup,
        register_lineage_wakeup,
    )
    from tests.test_benchmark_download_db_models import measurement
    from tests.test_product_release_lineage import _two_saved_findings
    from tests.test_pulse_finding_persistence import finding

    parent, _ = _two_saved_findings()
    _, _, observation = measurement()
    item = finding(name="Model 6", key="6" * 64)
    item["lineage_evidence"] = [{"relationship_kind": "new_version", "parent_observed_name": "Model 4",
                                 "source_excerpt": "Model 6 succeeds Model 4", "source_locator": None}]
    persist_classified_release_findings(source={"kind": "observation", "id": observation.pk}, revision_id="a" * 64,
                                        content_fingerprint="b" * 64, extraction_version="test", findings=[item])
    with transaction.atomic():
        job = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                                      budgets={"requests": 1, "bytes": 20000, "seconds": 5, "items": 10})
    first = drain_lineage_wakeup(job["job_id"])
    assert first["status"] == "non_x_pending" and first["non_x_pending"] == 1
    assert drain_lineage_wakeup(job["job_id"]) == {"status": "non_x_pending", "non_x_pending": 1, "reused": True}


def test_wakeup_commits_a_byte_limited_prefix_before_resuming():
    from core.models import CollectionJob, Post, ProductReleaseDetectionState
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_lineage_recovery import (
        drain_lineage_wakeup,
        register_lineage_wakeup,
    )
    from tests.test_product_release_lineage import _two_saved_findings
    from tests.test_pulse_finding_persistence import finding

    parent, _ = _two_saved_findings()
    post = Post.objects.create(tweet_id="lineage-later-child", text="Model 6 succeeds Model 4")
    item = finding(name="Model 6", key="6" * 64)
    item["assertions"][0].update(assertion_text=post.text, source_excerpt=post.text)
    item["lineage_evidence"] = [{"relationship_kind": "new_version", "parent_observed_name": "Model 4",
                                 "source_excerpt": post.text, "source_locator": None}]
    persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="a" * 64,
                                        content_fingerprint="b" * 64, extraction_version="test", findings=[item])
    parent_size = EventDossierClaim.objects.get(pk=parent["anchor_claim_id"]).source_archive.byte_count
    sizes = list(EventDossierClaim.objects.filter(scope_key__startswith="pulse-lineage-v1:").values_list("source_archive__byte_count", flat=True))
    assert len(sizes) == 2 and max(sizes) < sum(sizes)
    with transaction.atomic():
        job = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                                      budgets={"requests": 1, "bytes": parent_size + max(sizes), "seconds": 5, "items": 10})
    first = drain_lineage_wakeup(job["job_id"])
    assert first["status"] == "pending" and first["posts"] == 1
    run = CollectionJob.objects.get(pk=job["job_id"]).last_attempt
    assert run.scopes.get(scope_kind="lineage_wakeup").cursor
    second = drain_lineage_wakeup(job["job_id"])
    assert second["status"] == "complete" and second["posts"] == 1
    assert ProductReleaseDetectionState.objects.filter(post_id__in=[post.pk, "lineage-post-5"]).count() == 2


def test_identity_and_confirmed_review_register_distinct_transactional_wakeups(monkeypatch):
    from django.utils import timezone

    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from core.models import CollectionJob, EventDossier
    from core.product_identity import resolve_saved_release_finding
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    anchor_id = parent["anchor_claim_id"]
    linked = CollectionJob.objects.filter(operation="lineage_wakeup", dossier_claim_links__claim_id=anchor_id)
    assert linked.count() == 0
    resolve_saved_release_finding(claim_id=anchor_id)
    assert linked.count() == 1
    resolve_saved_release_finding(claim_id=anchor_id)
    assert linked.count() == 1
    args = {"expected_current_review_id": None, "display_title": "Model 4", "review_state": "confirmed",
                "evidence_cutoff_at": timezone.now(), "method_version": "test", "actor": "test", "reason": "Confirmed",
                "claims": [ClaimDecision(anchor_id, "accepted", "Source")],
                "product_release": ProductReleaseInput(observed_name="Model 4", product_key=parent["product_key"])}
    import core.product_release_lineage_recovery as recovery

    original = recovery.register_lineage_wakeup
    monkeypatch.setattr(recovery, "register_lineage_wakeup", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("outbox failure")))
    with pytest.raises(RuntimeError, match="outbox failure"):
        complete_review(parent["dossier_id"], **args)
    assert EventDossier.objects.get(pk=parent["dossier_id"]).current_review_id is None
    assert linked.count() == 1
    monkeypatch.setattr(recovery, "register_lineage_wakeup", original)
    review = complete_review(parent["dossier_id"], **args)
    assert linked.count() == 2
    assert linked.filter(targets__target_key=f"parent:{review.pk}").exists()


def test_wakeup_identity_write_growth_and_replay(monkeypatch):
    from django.test.utils import CaptureQueriesContext

    import core.product_identity as identity
    from core.models import (
        CollectionJob,
        CollectionJobTarget,
        EventDossierClaimCollectionJob,
    )
    from tests.test_product_release_lineage import _two_saved_findings

    original = identity.resolve_saved_release_finding
    measurements = []
    def measured(**kwargs):
        before = (CollectionJob.objects.count(), CollectionJobTarget.objects.count(), EventDossierClaimCollectionJob.objects.count())
        with CaptureQueriesContext(connection) as queries:
            result = original(**kwargs)
        after = (CollectionJob.objects.count(), CollectionJobTarget.objects.count(), EventDossierClaimCollectionJob.objects.count())
        measurements.append((len(queries), tuple(b - a for a, b in zip(before, after, strict=True))))
        return result
    monkeypatch.setattr(identity, "resolve_saved_release_finding", measured)
    parent, _ = _two_saved_findings()
    identity.resolve_saved_release_finding(claim_id=parent["anchor_claim_id"])
    identity.resolve_saved_release_finding(claim_id=parent["anchor_claim_id"])
    import core.product_release_lineage_recovery as recovery

    with monkeypatch.context() as without_wakeup:
        without_wakeup.setattr(recovery, "register_lineage_wakeup", lambda **kwargs: None)
        identity.resolve_saved_release_finding(claim_id=parent["anchor_claim_id"])
    print("WAKEUP_RESOLUTION_GROWTH", measurements)
    assert measurements[0][1] == (0, 0, 0)
    assert measurements[-3][1] == (1, 1, 1)
    assert measurements[-1][1] == (0, 0, 0)


def test_wakeup_oversize_is_explicit_and_new_budget_can_resume():
    from core.models import CollectionJob
    from core.product_release_lineage_recovery import (
        drain_lineage_wakeup,
        register_lineage_wakeup,
    )
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    budgets = {"requests": 1, "bytes": 1, "seconds": 5, "items": 2}
    with transaction.atomic():
        blocked = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None, budgets=budgets)
    assert drain_lineage_wakeup(blocked["job_id"])["status"] == "budget_blocked"
    assert CollectionJob.objects.get(pk=blocked["job_id"]).state == "paused"
    with transaction.atomic():
        retry = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                                       budgets={**budgets, "bytes": 10000})
    assert retry["job_id"] != blocked["job_id"]
    assert drain_lineage_wakeup(retry["job_id"])["status"] == "complete"


def test_ready_wakeup_selector_can_use_partial_ordered_index():
    from core.models import CollectionJob
    from core.product_release_lineage_recovery import register_lineage_wakeup
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    with transaction.atomic():
        register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                                budgets={"requests": 1, "bytes": 10000, "seconds": 5, "items": 2})
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
            query = CollectionJob.objects.filter(operation="lineage_wakeup", state="ready", last_success__isnull=True).order_by("updated_at", "id")[:1]
            assert "idx_lineage_wakeup_ready" in query.explain()


def test_invalid_lineage_claim_id_survives_completed_page(monkeypatch):
    import core.product_release_lineage_recovery as recovery
    from core.models import CollectionJob
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    lead = EventDossierClaim.objects.get(scope_key__startswith="pulse-lineage-v1:")
    original = recovery.find_lineage_dependents
    def invalid_page(**kwargs):
        page = original(**kwargs)
        page.update(posts=[], invalid=[str(lead.pk)])
        return page
    with transaction.atomic():
        job = recovery.register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None,
                                               budgets={"requests": 1, "bytes": 10000, "seconds": 5, "items": 5})
    monkeypatch.setattr(recovery, "find_lineage_dependents", invalid_page)
    result = recovery.drain_lineage_wakeup(job["job_id"])
    assert result["invalid"] == 1
    run = CollectionJob.objects.get(pk=job["job_id"]).last_success
    assert run.scopes.filter(scope_kind="lineage_invalid", scope_key=str(lead.pk)).exists()


def test_reviewed_parent_name_wakes_and_resolves_existing_child():
    from django.utils import timezone

    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from core.models import CollectionJob
    from core.product_release_lineage import resolve_reported_lineage
    from core.product_release_lineage_recovery import drain_lineage_wakeup
    from tests.test_product_release_lineage import _two_saved_findings

    parent, child = _two_saved_findings(lineage_excerpt="Model 5 succeeds Reviewed 4", parent_name="Reviewed 4")
    args = {"child_claim_id": child["anchor_claim_id"], "relation_index": 0, "basis_version_id": None,
            "max_candidates": 5, "max_subjects": 2, "max_seconds": 5}
    assert resolve_reported_lineage(**args)["status"] == "unresolved"
    review = complete_review(parent["dossier_id"], expected_current_review_id=None,
                             display_title="Reviewed 4", review_state="confirmed", evidence_cutoff_at=timezone.now(),
                             method_version="test", actor="test", reason="Corrected name",
                             claims=[ClaimDecision(parent["anchor_claim_id"], "accepted", "Source")],
                             product_release=ProductReleaseInput(observed_name="Reviewed 4", product_key=parent["product_key"]))
    job = CollectionJob.objects.get(operation="lineage_wakeup", targets__target_key=f"parent:{review.pk}")
    assert job.targets.get().native_identifier == "Reviewed 4"
    assert drain_lineage_wakeup(job.pk)["posts"] == 1
    assert resolve_reported_lineage(**args)["status"] == "created"
    assert resolve_reported_lineage(**args)["status"] == "matched_replay"


def test_busy_wakeup_moves_behind_other_ready_jobs(monkeypatch):
    from datetime import timedelta

    from django.utils import timezone

    import core.collection_state as state
    from core.models import CollectionJob
    from core.product_release_lineage_recovery import (
        drain_lineage_wakeup,
        register_lineage_wakeup,
    )
    from tests.test_product_release_lineage import _two_saved_findings

    parent, child = _two_saved_findings()
    budgets = {"requests": 1, "bytes": 10000, "seconds": 5, "items": 2}
    with transaction.atomic():
        first = register_lineage_wakeup(parent_claim_id=parent["anchor_claim_id"], cause_review_id=None, budgets=budgets)
        second = register_lineage_wakeup(parent_claim_id=child["anchor_claim_id"], cause_review_id=None, budgets=budgets)
    CollectionJob.objects.filter(pk=first["job_id"]).update(updated_at=timezone.now() - timedelta(minutes=1))
    def busy(*args, **kwargs):
        raise state.BusyJob("lease active")
    monkeypatch.setattr(state, "claim_job", busy)
    assert drain_lineage_wakeup(first["job_id"])["status"] == "busy"
    ready = CollectionJob.objects.filter(pk__in=[first["job_id"], second["job_id"]]).order_by("updated_at", "id")
    assert str(ready.first().pk) == second["job_id"]


def test_same_parent_fan_in_plan_measurement():
    import hashlib

    from django.test.utils import CaptureQueriesContext

    from core.models import EventClaimKind
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    seed = EventDossierClaim.objects.get(scope_key__startswith="pulse-lineage-v1:")
    kind = EventClaimKind.objects.get(code="release_context")
    EventDossierClaim.objects.bulk_create([
        EventDossierClaim(event_dossier_source_id=seed.event_dossier_source_id, claim_kind_reference=kind,
                          scope_key=f"pulse-lineage-v1:synthetic:{number}", extraction_version="fixture",
                          claim_hash=hashlib.sha256(str(number).encode()).hexdigest(),
                          assertion_text="Classifier-reported new_version: Model 4",
                          source_excerpt="Synthetic evidence", source_hash=hashlib.sha256(b"Synthetic evidence").hexdigest(),
                          source_archive_id=seed.source_archive_id)
        for number in range(3000)
    ], batch_size=500)
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE event_dossier_claims")
    with transaction.atomic(), CaptureQueriesContext(connection) as captured:
        find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=50, max_bytes=1048576, max_seconds=20)
    lookup = next(row["sql"] for row in captured if "MD5(UPPER(" in row["sql"] and "event_dossier_claims" in row["sql"])
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) " + lookup)
        plan = "\n".join(row[0] for row in cursor.fetchall())
    print("SAME_PARENT_3000_PLAN\n" + plan)
    assert "idx_ed_lineage_hash_id" in plan and "rows=51" in plan
    assert "Sort  " not in plan


def test_oversized_merged_history_does_not_block_canonical_child():
    import hashlib
    from uuid import UUID

    from core.collection_capture import archive_document
    from core.event_dossiers import attach_source, create_dossier
    from core.models import EventClaimKind, EventDossier, Post
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings

    parent, _ = _two_saved_findings()
    source_post = Post.objects.create(tweet_id="merged-lineage-old", text="old source")
    old = create_dossier(event_kind="product_release", identity_key=hashlib.sha256(b"old-dossier").hexdigest())
    source = attach_source(old.pk, post_id=source_post.pk)
    archive = archive_document(b"x" * 20000)
    EventDossierClaim.objects.create(
        pk=UUID(int=1), event_dossier_source=source, claim_kind_reference=EventClaimKind.objects.get(code="release_context"),
        scope_key="pulse-lineage-v1:old:synthetic", extraction_version="fixture", claim_hash=hashlib.sha256(b"old").hexdigest(),
        assertion_text="Classifier-reported new_version: Model 4", source_excerpt="old",
        source_hash=hashlib.sha256(b"old").hexdigest(), source_archive=archive,
    )
    EventDossier.objects.filter(pk=old.pk).update(merged_into_id=parent["dossier_id"])
    with transaction.atomic():
        first = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], limit=1, max_bytes=10000, max_seconds=5)
        second = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], after=first["next_cursor"],
                                         limit=1, max_bytes=10000, max_seconds=5)
    assert first["status"] == "ok" and first["next_cursor"] == str(UUID(int=1)) and first["more_remaining"]
    assert second["posts"] == ["lineage-post-5"]


def test_keyset_pages_include_all_five_relation_kinds():
    from core.models import Post
    from core.product_release_dossiers import persist_classified_release_findings
    from core.product_release_lineage_recovery import find_lineage_dependents
    from tests.test_product_release_lineage import _two_saved_findings
    from tests.test_pulse_finding_persistence import finding

    parent, _ = _two_saved_findings()
    expected = {"lineage-post-5"}
    for number, kind in enumerate(("new_version", "finetune", "adapter", "quantized", "merge"), start=6):
        name = f"Model {number}"
        post = Post.objects.create(tweet_id=f"kind-post-{number}", text=f"{name} derives from Model 4")
        item = finding(name=name, key=f"{number:x}" * 64)
        item["assertions"][0].update(assertion_text=post.text, source_excerpt=post.text)
        item["lineage_evidence"] = [{"relationship_kind": kind, "parent_observed_name": "Model 4",
                                     "source_excerpt": post.text, "source_locator": None}]
        persist_classified_release_findings(source={"kind": "post", "id": post.pk}, revision_id="a" * 64,
                                            content_fingerprint="b" * 64, extraction_version="test", findings=[item])
        expected.add(post.pk)
    after, seen = None, set()
    for _ in range(10):
        with transaction.atomic():
            page = find_lineage_dependents(parent_claim_id=parent["anchor_claim_id"], after=after,
                                           limit=2, max_bytes=20000, max_seconds=5)
        assert page["status"] == "ok"
        seen.update(page["posts"])
        after = page["next_cursor"]
        if not page["more_remaining"]:
            break
    assert seen == expected and not page["more_remaining"]


def test_unicode_parent_names_follow_database_lookup_rules():
    from django.utils import timezone

    from core.event_dossiers import ClaimDecision, ProductReleaseInput, complete_review
    from core.models import CollectionJob
    from core.product_release_lineage import (
        _same_product_name,
        resolve_reported_lineage,
    )
    from tests.test_product_release_lineage import _two_saved_findings

    with connection.cursor() as cursor:
        cursor.execute("SELECT UPPER(%s) = UPPER(%s)", ["Straße", "Strasse"])
        database_matches = cursor.fetchone()[0]
    assert _same_product_name("Straße", "Strasse") == database_matches
    parent, child = _two_saved_findings(lineage_excerpt="Model 5 succeeds Strasse", parent_name="Strasse")
    review = complete_review(parent["dossier_id"], expected_current_review_id=None, display_title="Straße",
                             review_state="confirmed", evidence_cutoff_at=timezone.now(), method_version="test",
                             actor="test", reason="Reviewed spelling", claims=[ClaimDecision(parent["anchor_claim_id"], "accepted", "Source")],
                             product_release=ProductReleaseInput(observed_name="Straße", product_key=parent["product_key"]))
    job_exists = CollectionJob.objects.filter(operation="lineage_wakeup", targets__target_key=f"parent:{review.pk}").exists()
    assert job_exists == database_matches
    result = resolve_reported_lineage(child_claim_id=child["anchor_claim_id"], relation_index=0, basis_version_id=None,
                                      max_candidates=5, max_subjects=2, max_seconds=5)
    if not database_matches:
        assert result["status"] == "unresolved"
