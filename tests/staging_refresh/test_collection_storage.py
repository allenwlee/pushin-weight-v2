"""Capture the refresh caller's SQL without creating or opening a database."""

from pathlib import Path

import pytest

from scripts.staging_refresh import collection_storage, database
from scripts.staging_refresh.policy import load_policy

CHILDREN = {
    "collection_scope_rare_hits",
    "collection_scope_cursor_receipts",
    "collection_scope_request_uses",
    "collection_observation_metric_selections",
}


class RecordingCursor:
    def __init__(self, children):
        self.children = children
        self.statements = []
        self.rows = []
        self.rowcount = 0

    def execute(self, query, params=None):
        query = query if isinstance(query, str) else query.as_string()
        query = " ".join(query.split())
        self.statements.append((query, params))
        self.rows = []
        self.rowcount = 0
        if query.startswith("SELECT to_regclass"):
            self.rows = [("collection_runtime_table",)]
        elif query.startswith("SELECT name FROM unnest"):
            self.rows = [(name,) for name in params[0] if name in self.children]
        elif "FROM pg_constraint" in query:
            # A business membership really owns its saved observation, whereas
            # a capture's selection row alone must not make its run permanent.
            references = [
                ("account_query_memberships", "observation_id", "collection_observations"),
                ("collection_observation_metric_selections", "observation_id", "collection_observations"),
            ]
            self.rows = [row for row in references if row[0] not in params[0]]

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


def captured_refresh(monkeypatch, children):
    cursor = RecordingCursor(children)
    monkeypatch.setattr(database, "_catalog_counts", lambda _: {"fixture_catalog": 2})
    monkeypatch.setattr(database, "_run_purpose_expression", lambda _: "r.purpose")
    assert database.purge_collection_runtime(cursor) == {"fixture_catalog": 2}
    return [query for query, _ in cursor.statements]


@pytest.mark.parametrize("children", [
    set(), {"collection_scope_rare_hits"},
    {"collection_scope_rare_hits", "collection_scope_request_uses"}, CHILDREN,
])
def test_refresh_discovers_optional_child_tables_before_using_them(monkeypatch, children):
    statements = captured_refresh(monkeypatch, children)
    for child in CHILDREN:
        delete = [query for query in statements if query.startswith(f'DELETE FROM "{child}"')]
        assert bool(delete) == (child in children)
        if delete:
            assert "run_id NOT IN(SELECT id FROM pw_refresh_kept_runs)" in delete[0]
        if child not in children:
            assert not any(child in query for query in statements)
    closure = next(query for query in statements if "SELECT referenced FROM" in query)
    assert ("collection_scope_request_uses" in closure) == ("collection_scope_request_uses" in children)


def test_refresh_keeps_business_provenance_without_pinning_disposable_selection(monkeypatch):
    statements = captured_refresh(monkeypatch, CHILDREN)
    reference_inserts = [query for query in statements if 'o JOIN "' in query]
    assert len(reference_inserts) == 1
    assert 'JOIN "account_query_memberships" t ON t."observation_id"=o.id' in reference_inserts[0]
    assert CHILDREN <= set(collection_storage.OWNED_TABLES)
    assert {"account_query_memberships", "post_unsanctioned_flag_assignments", "source_datasets"}.isdisjoint(
        collection_storage.OWNED_TABLES,
    )


def test_refresh_closes_retained_scope_replay_over_original_request_owner(monkeypatch):
    statements = captured_refresh(monkeypatch, CHILDREN)
    closure = next(query for query in statements if "SELECT referenced FROM" in query)
    assert "JOIN pw_refresh_kept_runs k ON k.id=s.run_id" in closure
    assert "SELECT a.run_id FROM collection_scope_request_uses u" in closure
    assert "JOIN collection_requests request ON request.id=u.request_id" in closure
    assert "JOIN collection_attempts a ON a.id=request.attempt_id" in closure


def test_refresh_deletes_children_then_appearances_before_their_requests(monkeypatch):
    statements = captured_refresh(monkeypatch, CHILDREN)
    deleted = [query.split()[2].strip('"') for query in statements if query.startswith("DELETE FROM")]
    for child in CHILDREN:
        assert deleted.index(child) < deleted.index("collection_observations")
        assert deleted.index(child) < deleted.index("collection_requests")
        assert deleted.index(child) < deleted.index("collection_scope_runs")
    assert deleted.index("collection_observations") < deleted.index("collection_requests")
    assert deleted.index("collection_requests") < deleted.index("collection_attempts")
    assert deleted.index("collection_scope_runs") < deleted.index("collection_runs")


def test_rg6_children_are_copied_optional_on_old_sources_and_have_no_sequences():
    root = Path(__file__).resolve().parents[2]
    policy = load_policy(root / "config/staging_refresh.yaml")
    copied = CHILDREN - {"collection_scope_rare_hits"}
    assert copied <= policy.relations.copied_tables
    assert CHILDREN <= policy.relations.optional_source_tables
    assert copied.isdisjoint(policy.scrub.truncate_tables)
    assert not {f"{table}_id_seq" for table in CHILDREN} & policy.relations.sequences
    runbook = (root / "docs/operations/staging-data-refresh.md").read_text()
    assert all(f"'{table}'" in runbook for table in copied)


def test_copied_rg6_child_links_never_require_excluded_parent_rows():
    from django.apps import apps

    root = Path(__file__).resolve().parents[2]
    policy = load_policy(root / "config/staging_refresh.yaml")
    excluded = {"collection_scope_rare_hits", "rare_type_search_hits"}
    assert excluded <= policy.relations.excluded_tables
    assert excluded <= policy.scrub.truncate_tables
    assert excluded.isdisjoint(policy.relations.copied_tables)
    for model in apps.get_models():
        if model._meta.db_table not in CHILDREN & policy.relations.copied_tables:
            continue
        parents = {field.related_model._meta.db_table for field in model._meta.fields
                   if field.is_relation and field.concrete}
        assert parents <= policy.relations.copied_tables, model._meta.db_table


def test_model_collection_children_have_an_explicit_runtime_owner_classification():
    from django.apps import apps

    owners = {"collection_runs", "collection_scope_runs", "collection_observations",
              "collection_attempts", "collection_requests"}
    children = {
        model._meta.db_table
        for model in apps.get_models()
        if model._meta.db_table.startswith("collection_")
        and any(field.is_relation and field.concrete and field.related_model._meta.db_table in owners
                for field in model._meta.fields)
    }
    assert children <= set(collection_storage.OWNED_TABLES)
