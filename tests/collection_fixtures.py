"""Explicit instruction registration for saved collection evidence fixtures."""

import sys
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from functools import wraps

import pytest
from django.db import models

from core.collection_state import register_direct_job

_historical_fixture_active = ContextVar("historical_collection_fixture", default=False)


def evidence_job(*, source_id, purpose="catalog", contract_id=None, scope=None):
    return register_direct_job(
        source_id=source_id,
        purpose=purpose,
        contract_id=contract_id,
        scope={} if scope is None else scope,
        driver="persist_source" if purpose == "metric" else "execute_catalog",
        limits={"fixture": True},
    )


@contextmanager
def historical_fixture_models(historical):
    """Seed an old schema with its own field set, never today's extra columns.

    Domain fixture builders are shared across migration tests. Only their model
    bindings change here; the tested migration and frozen old writers do not.
    """
    if _historical_fixture_active.get():
        yield
        return
    from django.apps import apps as current_apps

    from core import models as current
    from core.account_identity import normalize_account

    properties = {
        name: getattr(current.Product, name)
        for name in ("hf_namespace", "publisher_ownership")
    }
    job_properties = {
        name: getattr(current.CollectionJob, name)
        for name in (
            "scope",
            "budgets",
            "schedule",
            "campaign_settings",
            "instructions",
        )
    }
    replacements = {
        m._meta.model_name: m for m in historical.get_app_config("core").get_models()
    }
    canonical = {
        m._meta.model_name: m for m in current_apps.get_app_config("core").get_models()
    }
    existing_attributes = {
        (name, key)
        for name, module in list(sys.modules.items())
        if name.startswith(("core.", "tests.")) and module is not None
        for key in vars(module)
    }
    with pytest.MonkeyPatch.context() as patch:
        account = replacements.get("account")
        if account and any(f.name == "data_source" for f in account._meta.fields):
            original_save = account.save

            def save_account(instance, *args, **kwargs):
                normalize_account(instance)
                return original_save(instance, *args, **kwargs)

            patch.setattr(account, "save", save_account)
        product = replacements.get("product")
        if product:
            for name, value in properties.items():
                patch.setattr(product, name, value, raising=False)
        job = replacements.get("collectionjob")
        if job:
            for name, value in job_properties.items():
                patch.setattr(job, name, value, raising=False)
        for module_name, module in list(sys.modules.items()):
            if not module_name.startswith(("core.", "tests.")) or module is None:
                continue
            for name, value in list(vars(module).items()):
                if (
                    isinstance(value, type)
                    and issubclass(value, models.Model)
                    and value._meta.app_label == "core"
                ):
                    replacement = replacements.get(value._meta.model_name)
                    if replacement:
                        patch.setattr(module, name, replacement)
        token = _historical_fixture_active.set(True)
        try:
            from tests.historical_catalog_fixture import catalog_runtime

            pre_rg5 = product and any(f.name == "type" for f in product._meta.fields)
            with catalog_runtime(historical) if pre_rg5 else nullcontext():
                yield
        finally:
            _historical_fixture_active.reset(token)
            # A module first imported inside this context copied the historical
            # aliases without entering MonkeyPatch's original binding list.
            for name, module in list(sys.modules.items()):
                if not name.startswith(("core.", "tests.")) or module is None:
                    continue
                for key, value in list(vars(module).items()):
                    if (
                        (name, key) not in existing_attributes
                        and isinstance(value, type)
                        and issubclass(value, models.Model)
                        and value._meta.app_label == "core"
                        and value is replacements.get(value._meta.model_name)
                    ):
                        setattr(module, key, canonical[value._meta.model_name])


def with_database_models(function):
    """Shared fixture builders follow an explicitly selected historical schema."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        if _historical_fixture_active.get():
            return function(*args, **kwargs)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM django_migrations WHERE app='core' AND name='0105_collection_schedule_ownership')"
            )
            current = cursor.fetchone()[0]
        if current:
            return function(*args, **kwargs)
        executor = MigrationExecutor(connection)
        historical = executor.loader.project_state(
            list(executor.loader.applied_migrations)
        ).apps
        with historical_fixture_models(historical):

            def argument(value):
                if isinstance(value, models.Model) and value._meta.app_label == "core":
                    model = historical.get_model("core", value._meta.model_name)
                    if type(value) is not model:
                        return model.objects.get(pk=value.pk)
                return value

            return function(
                *(argument(value) for value in args),
                **{key: argument(value) for key, value in kwargs.items()},
            )

    return wrapped


def upgrade_legacy_collection_for_current_reader():
    """Upgrade fixture evidence using the same archive and retirement guards."""
    import hashlib

    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from core.migrations._rg6_retirement_v1 import FIELDS
    from tests.test_rg6_retirement import authorization

    call_command("prepare_refresh_references", verbosity=0)
    target = [("core", "0200_merge_rg6_enrichment_budget_contract")]
    MigrationExecutor(connection).migrate(target)
    historical = MigrationExecutor(connection).loader.project_state(target).apps
    archive_model = historical.get_model("core", "CollectionEvidenceArchive")
    with connection.cursor() as cursor:
        for table, fields in FIELDS.items():
            pairs = ",".join(f"'{field}',{field}" for field in fields)
            cursor.execute(f"SELECT id,convert_to(jsonb_build_object({pairs})::text,'UTF8') FROM {table}")
            for key, raw in cursor.fetchall():
                body = bytes(raw)
                archive, _ = archive_model.objects.get_or_create(
                    content_sha256=hashlib.sha256(body).hexdigest(),
                    encoding="legacy-jsonb-text-v1",
                    defaults={"media_type": "application/json", "byte_count": len(body),
                              "body": body, "capture_kind": "legacy_collection"},
                )
                cursor.execute(f"UPDATE {table} SET legacy_archive_id=%s WHERE id=%s", [archive.pk, key])
    with authorization():
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes("core"))
