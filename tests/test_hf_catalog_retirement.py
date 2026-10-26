"""Exercise HF catalog writes with the retirement ORM shape and denied columns."""

from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from django.apps import apps
from django.db import ProgrammingError, connection, transaction
from psycopg import sql

from core.collection_capture import observation_object_documents, run_report_document
from core.hf_catalog import catalog_report, execute_catalog
from core.models import CollectionObservation, CollectionRun, CollectionScopeRun
from tests.test_hf_catalog_runner import api, scope

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]

RETIRED = {
    CollectionRun: {"invocations", "report", "request_params", "source_metadata", "raw_payload"},
    CollectionObservation: {"listing", "dimensions", "source_metadata", "groups", "envelopes"},
    CollectionScopeRun: {"ownership", "cursor_history", "envelopes"},
}


def _defaults():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname,a.attname,pg_get_expr(d.adbin,d.adrelid) "
            "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
            "WHERE n.nspname='public' AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped "
            "ORDER BY c.relname,a.attnum",
            [[model._meta.db_table for model in RETIRED]],
        )
        return cursor.fetchall()


@contextmanager
def denied_retirement_columns():
    """No DROP or migration; role, grants and test defaults all roll back."""
    role = "pw_hf_retire_" + uuid4().hex[:16]
    before = _defaults()
    fields = {model: model._meta.local_fields for model in RETIRED}
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOINHERIT").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(role)))
                cursor.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(role)))
                for model, retired in RETIRED.items():
                    table = sql.Identifier(model._meta.db_table)
                    cursor.execute(sql.SQL("REVOKE SELECT,INSERT,UPDATE ON {} FROM {}").format(table, sql.Identifier(role)))
                    allowed = [field.column for field in model._meta.local_concrete_fields if field.name not in retired]
                    for privilege in ("SELECT", "INSERT", "UPDATE"):
                        cursor.execute(sql.SQL("GRANT {} ({}) ON {} TO {}").format(
                            sql.SQL(privilege), sql.SQL(",").join(map(sql.Identifier, allowed)), table, sql.Identifier(role),
                        ))
                    # The pre-retirement physical schema still has NOT NULL
                    # columns. Empty defaults let this fixture issue exactly the
                    # post-retirement INSERT column list; no source data moves.
                    for name in retired:
                        empty = "[]" if name in {"invocations", "envelopes", "cursor_history"} else "{}"
                        cursor.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT {}::jsonb").format(
                            table, sql.Identifier(name), sql.Literal(empty),
                        ))
                cursor.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                cursor.execute("SELECT current_user")
                assert cursor.fetchone()[0] == role
            for model, retired in RETIRED.items():
                model._meta.local_fields = [field for field in fields[model] if field.name not in retired]
                model._meta.__dict__.pop("db_returning_fields", None)
            apps.clear_cache()
            # Prove that the database actually rejects access, not just that
            # this test's ORM omits the old attributes.
            for model, retired in RETIRED.items():
                for name in retired:
                    with (
                        pytest.raises(ProgrammingError, match="permission denied"),
                        transaction.atomic(), connection.cursor() as cursor,
                    ):
                        cursor.execute(sql.SQL("SELECT {} FROM {} LIMIT 0").format(
                            sql.Identifier(name), sql.Identifier(model._meta.db_table),
                        ))
            try:
                yield
            finally:
                transaction.set_rollback(True)
    finally:
        for model, original in fields.items():
            model._meta.local_fields = original
            model._meta.__dict__.pop("db_returning_fields", None)
        apps.clear_cache()
        assert _defaults() == before
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_roles WHERE rolname=%s", [role])
            assert cursor.fetchone()[0] == 0


def test_fresh_capture_resume_and_operator_report_need_no_retiring_columns():
    from core.collection_reports import job_status

    manifest = scope()
    with denied_retirement_columns():
        first = execute_catalog(scope=manifest, hf=api(budget=2))
        assert first["requests"] == 2 and not first["complete"]
        run = CollectionRun.objects.get(pk=first["run_id"])
        observations = list(run.observations.order_by("pk"))
        assert [observation_object_documents(row)[0]["id"] for row in observations] == ["lab/model", "lab/model-GGUF"]
        assert all(row.numeric_fields_explicit is False for row in observations)
        resumed = execute_catalog(run_id=run.pk, hf=api())
        assert resumed["complete"] and resumed["requests"] == 4
        assert resumed["cumulative_requests"] == 6
        run.refresh_from_db()
        assert catalog_report(run) == run_report_document(run) == resumed
        run.job.last_attempt = run.job.last_success = run
        run.job.save(update_fields=["last_attempt", "last_success"])
        status = job_status(run.job_id)
        assert status["last_attempt"]["selected_count"] == status["last_success"]["success_count"] == 2
        replay = execute_catalog(run_id=run.pk, hf=api(lambda _: pytest.fail("completed replay fetched HTTP")))
        assert replay["complete"] and replay["requests"] == 0
        assert replay["cumulative_requests"] == 6


@pytest.mark.parametrize("across_pages", [False, True])
def test_repeated_repository_keeps_exact_selected_object_and_original_page_evidence(across_pages):
    def pages(request):
        if request.url.path != "/api/models":
            return None
        first, last = {"id": "lab/model", "downloads": 1}, {"id": "Lab/Model", "downloads": 2}
        if not across_pages:
            return httpx.Response(200, json=[first, last])
        if request.url.params.get("cursor"):
            return httpx.Response(200, json=[last])
        return httpx.Response(200, json=[first], headers={
            "link": '<https://huggingface.co/api/models?cursor=next>; rel="next"',
        })

    manifest = scope()
    with denied_retirement_columns():
        result = execute_catalog(scope=manifest, hf=api(pages))
        assert result["complete"] and result["unique_models"] == 1
        assert result["namespaces"][0]["raw_count"] == 2
        observation = CollectionObservation.objects.get(observation_kind="hf_catalog_listing")
        assert observation.source_identifier == "lab/model"
        assert observation_object_documents(observation) == ({"id": "Lab/Model", "downloads": 2}, {}, {})
        links = observation.inputs.filter(input_role="listing")
        assert links.count() == (2 if across_pages else 1)
        if not across_pages:
            assert links.get().row_locator == "1"


@pytest.mark.parametrize("tamper", ["locator", "checksum"])
def test_listing_replay_rejects_changed_selected_input(tamper):
    manifest = scope()
    with denied_retirement_columns():
        result = execute_catalog(scope=manifest, hf=api(budget=2))
        observation = CollectionObservation.objects.filter(run_id=result["run_id"]).first()
        edge = observation.inputs.get(input_role="listing")
        if tamper == "locator":
            edge.row_locator = "01"
            edge.save(update_fields=["row_locator"])
        else:
            edge.input_sha256 = "f" * 64
            edge.save(update_fields=["input_sha256"])
        with pytest.raises(ValueError, match="HF listing"):
            observation_object_documents(observation)


def test_failed_identity_validation_stays_queryable_after_successful_resume():
    from core.models import CollectionRequest

    manifest = scope()
    with denied_retirement_columns():
        failed = execute_catalog(scope=manifest, hf=api(lambda _: httpx.Response(200, json={"name": "wrong"})))
        assert not failed["complete"] and failed["requests"] == 1
        prior = CollectionRequest.objects.get()
        assert (prior.request_group, prior.transport_outcome, prior.http_status, prior.error_code) == (
            "identity", "received", 200, "hf_validation:identity_mismatch",
        )
        resumed = execute_catalog(run_id=failed["run_id"], hf=api())
        assert resumed["complete"] and resumed["cumulative_requests"] == 7
        prior.refresh_from_db()
        assert prior.error_code == "hf_validation:identity_mismatch"
        assert CollectionRequest.objects.filter(request_group="identity", error_code__isnull=True).count() == 1


def test_archived_catalog_resume_adopts_namespace_identity_without_refetch():
    from core.collection_capture import archive_legacy
    from core.measurement_taxonomy import digest
    from core.models import CollectionJob

    manifest = scope()
    first = execute_catalog(scope=manifest, hf=api(budget=2))
    run = CollectionRun.objects.get(pk=first["run_id"])
    definition = {
        "version": 1, "scope": manifest, "schedule": None, "budgets": None,
        "historical_instructions": "unknown_beyond_stored_fields",
        "execution": {"driver": "none", "executable": False}, "archived_run_id": str(run.pk),
    }
    archived = CollectionJob.objects.create(
        job_key=f"archive:run:{run.pk}", source_id="hf", purpose="catalog",
        operation="archived_run", mode="historical", state="completed", definition=definition,
        definition_sha256=digest({"source": "hf", "purpose": "catalog", "contract": None,
                                  "operation": "archived_run", "mode": "historical", "definition": definition}),
    )
    run.job = archived
    run.save(update_fields=["job"])
    for observation in run.observations.all():
        raw, dimensions, metadata = observation_object_documents(observation)
        observation.legacy_archive = archive_legacy({
            "listing": raw, "dimensions": dimensions, "source_metadata": metadata,
        })
        observation.observation_kind = None
        observation.save(update_fields=["legacy_archive", "observation_kind"])
    namespace = run.scopes.get(scope_kind="namespace")
    namespace.phase = None
    namespace.legacy_archive = archive_legacy({
        "ownership": manifest["namespaces"][0], "cursor_history": [],
        "envelopes": [{"group": "identity", "validation_outcome": "ok"}],
    })
    namespace.save(update_fields=["phase", "legacy_archive"])
    with denied_retirement_columns():
        result = execute_catalog(run_id=run.pk, hf=api())
        assert result["complete"] and result["requests"] == 4
        namespace.refresh_from_db()
        assert namespace.phase == "hf_identity_verified"
        run.refresh_from_db()
        assert run_report_document(run) == result
        assert all(observation_object_documents(row)[0]["id"] == row.source_identifier
                   for row in run.observations.all())
