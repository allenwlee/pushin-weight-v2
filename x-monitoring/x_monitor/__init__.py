# {{AGENT_ATTRIBUTION}}
"""x-monitor: daily X conversation monitoring for the 9 v1 Chinese AI models.

v1.8 architecture (call-path attribution):

  - ``x_monitor.attribution``     multi-brand extraction pipeline
                                   (replaces single-brand v1.7 logic in
                                   ``x_monitor.intent_classifier``).
  - ``x_monitor.store``           SQLite store; per-post rows in
                                   ``post_brands`` / ``post_mentions`` /
                                   ``post_brand_signals`` (one row per
                                   detected brand, not one per post).
  - ``x_monitor.reattribute``     CLI subcommand to backfill the new
                                   tables from historical ``posts`` rows.

The public API exposed via ``__all__`` is the stable surface for
external callers (tests, scripts, downstream tools). Module-internal
helpers remain accessible at their original paths but are not part
of the contract.

The legacy ``x_monitor.intent_classifier`` module is kept as a thin
compat shim that re-exports the v1.8 names and emits
``DeprecationWarning`` on its legacy function bodies. A follow-up
commit deletes it once all callers migrate.
"""

from __future__ import annotations

__version__ = "0.1.0"

# --- Public API ---------------------------------------------------------

from x_monitor.attribution import (
    UNATTRIBUTED_BRAND_ID,
    BRAND_SOURCE_PRIORITY,
    MentionRow,
    BrandRow,
    Source,
    SourceType,
    validate_raw_token,
    compile_keyword_index,
    extract_user_mentions,
    extract_hashtag_mentions,
    extract_body_keywords,
    extract_search_term_match,
    compute_post_brands,
    attribute_to_brands,
    classify_signal,
    AnthropicClaudeClient,
)
from x_monitor.store import Store


def reattribute_all_posts(*args, **kwargs):
    """Backfill the new v1.8 tables for historical posts.

    Thin re-export of ``x_monitor.reattribute.reattribute_all_posts``.
    Import is deferred so callers that only need attribution or store
    primitives don't pay the cost of loading the CLI module.
    """
    from x_monitor.reattribute import reattribute_all_posts as _impl
    return _impl(*args, **kwargs)


__all__ = [
    # Version
    "__version__",
    # Attribution constants
    "UNATTRIBUTED_BRAND_ID",
    "BRAND_SOURCE_PRIORITY",
    # Attribution types
    "MentionRow",
    "BrandRow",
    "Source",
    "SourceType",
    # Attribution functions
    "validate_raw_token",
    "compile_keyword_index",
    "extract_user_mentions",
    "extract_hashtag_mentions",
    "extract_body_keywords",
    "extract_search_term_match",
    "compute_post_brands",
    "attribute_to_brands",
    "classify_signal",
    "AnthropicClaudeClient",
    # Store
    "Store",
    # Backfill CLI
    "reattribute_all_posts",
]
