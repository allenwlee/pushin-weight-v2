"""Shared pytest markers and PostgreSQL verification reporting.

The v2 schema uses PostgreSQL-only features (notably ICU collations), so a
SQLite run cannot exercise database-backed regression nets. Required tests
are skipped centrally when PostgreSQL is absent, reported as incomplete, and
made non-green rather than silently accepted.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def ensure_shared_locale_rows_for_database_tests(request):
    """Restore the small shared locale catalogue after transactional flushes."""
    from django.test import SimpleTestCase

    django_test_class = (
        request.cls is not None
        and issubclass(request.cls, SimpleTestCase)
        and bool(request.cls.databases)
    )
    database_fixture = any(
        name in request.fixturenames for name in ("db", "transactional_db")
    )
    if (
        request.node.get_closest_marker("django_db") is None
        and not django_test_class
        and not database_fixture
    ):
        return
    request.getfixturevalue("db")
    from core.models import Language, Locale

    locale_codes = ("und", "en", "en-Latn", "zh-Hans", "ja")
    if Locale.objects.filter(pk__in=locale_codes).count() == len(locale_codes):
        return
    for code in locale_codes:
        language = code.split("-", 1)[0]
        Language.objects.get_or_create(code=language)
        Locale.objects.get_or_create(code=code, defaults={"language_id": language})


@pytest.fixture(autouse=True)
def ensure_shared_business_catalogues_for_database_tests(request):
    from django.test import SimpleTestCase

    django_test_class = (
        request.cls is not None and issubclass(request.cls, SimpleTestCase)
        and bool(request.cls.databases)
    )
    if (request.node.get_closest_marker("django_db") is None and not django_test_class
            and not any(name in request.fixturenames for name in ("db", "transactional_db"))):
        return
    request.getfixturevalue("db")
    from core.job_vocabulary import NORMALIZER_ID, register_job_normalizer
    from core.models import (
        AffiliationType,
        Currency,
        DefinitionVersion,
        EmploymentType,
        ProductType,
    )
    from core.shared_vocabulary import seed_shared_vocabulary
    if not ProductType.objects.filter(code="llm-model").exists():
        seed_shared_vocabulary(catalogues=(
            "product_types", "product_relationship_types", "model_gating_states",
        ))

    if not Currency.objects.filter(pk="USD").exists() or not EmploymentType.objects.filter(code="full_time").exists():
        seed_shared_vocabulary(catalogues=(
            "currencies", "salary_periods", "job_functions", "seniority_levels",
            "employment_types", "workplace_types", "organization_ai_relationship_types",
            "role_ai_relationship_types",
        ))
    if not DefinitionVersion.objects.filter(pk=NORMALIZER_ID).exists():
        register_job_normalizer()
    if not AffiliationType.objects.filter(code="employment").exists():
        seed_shared_vocabulary(catalogues=(
            "affiliation_types", "opportunity_types", "event_kinds",
            "event_claim_kinds", "release_maturities", "release_access_channels",
            "release_availability_states", "personnel_change_types",
        ))


@pytest.fixture
def company_country_catalogue(db):
    """Seed the pinned selected places; return local IDs for external-input fixtures."""
    from django.conf import settings

    from core.geolocations import import_geonames_documents, load_pinned_geonames
    documents, metadata, roots = load_pinned_geonames(settings.BASE_DIR / "data/geonames")
    identities = import_geonames_documents(documents, country_metadata=metadata, selected_ids=roots)
    return {code: identities[external] for external, code in metadata.items() if external in identities}


@pytest.fixture
def migration_rehearsal_schema(transactional_db, request):
    baseline = getattr(request, "param", ("core", "0128_require_correction_actor"))
    yield from _migration_rehearsal_schema(baseline)


@pytest.fixture
def collection_history_schema(transactional_db):
    """Historical collection tests share the approved database, not a new one."""
    yield from _migration_rehearsal_schema(("core", "0065_measurement_taxonomy"))


def _migration_rehearsal_schema(baseline):
    """Rehearse in a temporary schema in the same exclusively owned test database.

    Never include public in search_path: an absent recorder/table must not fall
    through to shared tables. Each migration retains its normal transaction
    policy, including concurrent indexes. Restore extension locations and drop
    only these temporary schemas on completion or failure.
    """
    import uuid

    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    assert connection.vendor == "postgresql"
    assert connection.settings_dict["NAME"].startswith("test_")
    namespace = "migration_rehearsal_" + uuid.uuid4().hex
    extensions = namespace + "_extensions"
    quote = connection.ops.quote_name
    moved_extensions = []
    with connection.cursor() as cursor:
        cursor.execute("SHOW search_path")
        original_path = cursor.fetchone()[0]
        cursor.execute("SELECT app,name FROM public.django_migrations ORDER BY app,name")
        original_history = cursor.fetchall()
        cursor.execute(f"CREATE SCHEMA {quote(namespace)}")
        cursor.execute(f"CREATE SCHEMA {quote(extensions)}")
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT extname FROM pg_extension WHERE extrelocatable "
                "AND extnamespace='public'::regnamespace"
            )
            for (extension,) in cursor.fetchall():
                cursor.execute(
                    f"ALTER EXTENSION {quote(extension)} SET SCHEMA {quote(extensions)}"
                )
                moved_extensions.append(extension)
            cursor.execute(
                f"SET search_path TO {quote(namespace)}, {quote(extensions)}"
            )
            cursor.execute("SELECT to_regclass('django_migrations')")
            assert cursor.fetchone()[0] is None
        executor = MigrationExecutor(connection)
        assert not executor.loader.applied_migrations
        executor.migrate([baseline])
        yield namespace
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('search_path', %s, false)", [original_path])
            for extension in moved_extensions:
                cursor.execute(f"ALTER EXTENSION {quote(extension)} SET SCHEMA public")
            cursor.execute(f"DROP SCHEMA {quote(namespace)} CASCADE")
            cursor.execute(f"DROP SCHEMA {quote(extensions)} CASCADE")
            cursor.execute("SELECT app,name FROM public.django_migrations ORDER BY app,name")
            assert cursor.fetchall() == original_history


PYTEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@pytest.fixture(autouse=True)
def _use_finder_backed_staticfiles_storage(settings):
    """Keep ordinary tests independent of collected production manifests."""
    settings.STORAGES = PYTEST_STORAGES


@pytest.fixture
def seeded_policy_keywords(db):
    """Seed the active policy's DB attribution rows for cycle tests.

    Live ``CycleRunner`` preflight intentionally requires every normalized
    literal emitted by the checked-in policy to have a ``BrandKeyword`` row.
    Tests that exercise that path opt into this fixture explicitly; keeping it
    non-autouse preserves focused unit tests that do not need Django data.
    """
    from core.models import Brand, BrandKeyword
    from x_monitor.config import load_config
    from x_monitor.harvest_policy import load_policy
    from x_monitor.specs_from_policy import active_policy_tokens

    repo_root = Path(__file__).resolve().parents[1]
    cfg = load_config(repo_root / "config.yaml")
    policy = load_policy(repo_root / "config" / "harvest_policy.yaml")
    expected = active_policy_tokens(policy, brand_nicknames=cfg.enabled_models)

    for nickname in cfg.enabled_models:
        Brand.objects.get_or_create(
            nickname=nickname,
            defaults={"display_name": nickname, "is_sentinel": False},
        )
    for nickname, tokens in expected.items():
        for token in tokens:
            BrandKeyword.objects.get_or_create(
                brand_id=nickname,
                pattern=token,
                defaults={"is_primary": False},
            )
    return expected


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def postgres_available() -> bool:
    """Return whether Django has been configured with a PostgreSQL URL."""
    return _database_url().startswith(("postgres://", "postgresql://"))


requires_postgres = pytest.mark.requires_postgres

_SKIP_REASON = (
    "requires real PostgreSQL: this test is incomplete on SQLite because core "
    "models use PostgreSQL ICU collations. Re-run with DATABASE_URL=postgres://..."
)
_REQUIRED_POSTGRES_ITEMS: set[str] = set()
_SKIPPED_REQUIRED_POSTGRES_ITEMS: set[str] = set()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_postgres: required verification that executes only against a "
        "real PostgreSQL Django test database.",
    )


def pytest_collection_modifyitems(config, items):
    """Classify PostgreSQL-required tests before Django attempts SQLite setup."""
    _REQUIRED_POSTGRES_ITEMS.clear()
    _SKIPPED_REQUIRED_POSTGRES_ITEMS.clear()
    _REQUIRED_POSTGRES_ITEMS.update(
        item.nodeid for item in items if "requires_postgres" in item.keywords
    )
    if postgres_available():
        return

    skip = pytest.mark.skip(reason=_SKIP_REASON)
    for item in items:
        if item.nodeid in _REQUIRED_POSTGRES_ITEMS:
            item.add_marker(skip)
            _SKIPPED_REQUIRED_POSTGRES_ITEMS.add(item.nodeid)


def _required_postgres_report_counts(terminalreporter) -> tuple[int, int, int]:
    """Return executed, skipped, and setup/call/teardown-error required counts."""
    stats = terminalreporter.stats
    skipped = {
        report.nodeid
        for report in stats.get("skipped", [])
        if report.nodeid in _REQUIRED_POSTGRES_ITEMS
    }
    skipped.update(_SKIPPED_REQUIRED_POSTGRES_ITEMS)
    errors = {
        report.nodeid
        for report in stats.get("error", [])
        if report.nodeid in _REQUIRED_POSTGRES_ITEMS
    }
    return len(_REQUIRED_POSTGRES_ITEMS) - len(skipped), len(skipped), len(errors)


def pytest_sessionfinish(session, exitstatus):
    """A skipped required PostgreSQL net is incomplete verification, not green."""
    terminalreporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminalreporter is None:
        return
    _executed, skipped, errors = _required_postgres_report_counts(terminalreporter)
    if skipped or errors:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Always expose whether required PostgreSQL verification actually ran."""
    executed, skipped, errors = _required_postgres_report_counts(terminalreporter)
    terminalreporter.write_sep(
        "=", "PostgreSQL required-verification status", yellow=True
    )
    terminalreporter.write_line(
        f"required tests: executed={executed} skipped={skipped} errors={errors}"
    )
    if skipped or errors:
        terminalreporter.write_line(
            "INCOMPLETE: required PostgreSQL verification did not fully pass; "
            "this pytest run is intentionally non-green."
        )
        if skipped:
            terminalreporter.write_line(
                f"DATABASE_URL is {_database_url() or '<unset>'}; {_SKIP_REASON}"
            )


@pytest.fixture
def isolated_migration_database(transactional_db):
    """Old migration proofs cannot reverse mixed-source account identities.

    Use a disposable test database at the preceding schema; preserve the main
    test database and always drop this database, even on a failed assertion.
    """
    import uuid

    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    assert connection.vendor == "postgresql"
    original_name = connection.settings_dict["NAME"]
    assert original_name.startswith("test_")
    name = "test_pw_migration_" + uuid.uuid4().hex
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE DATABASE "{name}"')
    connection.close()
    connection.settings_dict["NAME"] = name
    try:
        executor = MigrationExecutor(connection)
        executor.migrate([("core", "0065_measurement_taxonomy")])
        yield
    finally:
        connection.close()
        connection.settings_dict["NAME"] = original_name
        with connection.cursor() as cursor:
            cursor.execute(f'DROP DATABASE "{name}"')


@pytest.fixture
def collection_instruction_bridge(collection_history_schema, monkeypatch):
    """Preceding-reader compatibility belongs to the explicit 0089 bridge."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    target = [("core", "0089_job_owned_run_instructions")]
    executor.migrate(target)
    historical = executor.loader.project_state(target).apps
    from tests.collection_bridge_fixture import bridge_runtime

    with bridge_runtime(historical):
        yield historical


@pytest.fixture
def provider_tweet_entities():
    """Provider-shaped evidence; the HF destination exists only in entities."""
    return {
        "urls": [{"url": "https://t.co/example",
                  "expanded_url": "https://huggingface.co/Qwen/Qwen3-4B",
                  "display_url": "huggingface.co/Qwen/Qwen3-4B", "indices": [20, 40]}],
        "hashtags": [{"text": "Qwen", "indices": [14, 19]}],
        "user_mentions": [{"id_str": "1001", "screen_name": "Alibaba_Qwen",
                           "name": "Qwen", "indices": [0, 13]}],
    }
