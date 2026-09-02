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
    terminalreporter.write_sep("=", "PostgreSQL required-verification status", yellow=True)
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
