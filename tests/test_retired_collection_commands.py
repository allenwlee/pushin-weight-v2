"""One-time legacy copiers are retained at 70fb5f6e, not runnable after RG6."""

import pytest
from django.core.management import get_commands


@pytest.mark.parametrize("command", [
    "archive_collection_metric_payloads", "migrate_collection_storage",
    "project_archive_import_links", "project_arena_publications",
    "project_collection_continuations", "project_collection_invocations",
    "project_collection_metric_requests", "project_collection_provenance",
    "project_collection_scope_bounds", "project_opencode_endpoints",
    "project_product_match_targets", "project_scope_rare_hits",
    "project_scope_request_uses", "project_x_query_targets",
])
def test_legacy_copy_commands_are_not_discoverable(command):
    assert command not in get_commands()


def test_page_module_exposes_only_typed_or_supplied_evidence_paths():
    from core import collection_pages

    for name in ("adopt_unprojected_page_receipts", "project_page_receipts_batch",
                 "page_receipt_parity_batch"):
        assert not hasattr(collection_pages, name)
    assert callable(collection_pages.project_page_receipts)
    assert callable(collection_pages.page_receipts)
