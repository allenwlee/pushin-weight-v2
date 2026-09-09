"""Deterministic, provenance-aware analysis of stored Stage 1 classifications."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from django.conf import settings
from django.db import connection

from core.classification_contract import (
    CANONICAL_TAXONOMY_VERSION,
    COMPATIBLE_TAXONOMY_VERSIONS,
    CONTRACT_VERSION,
    TAXONOMY_KEY_CROSSWALK,
    taxonomy_crosswalk_rows,
)
from core.models import Brand

ANALYSIS_SCHEMA_VERSION = "classification-analysis/v1"
HISTORY_POLICIES = ("current_definition", "historical_inclusive")
HistoryPolicy = Literal["current_definition", "historical_inclusive"]
_FULL_REVISION = re.compile(r"^[0-9a-f]{40}$")

# This is the complete unversioned dashboard vocabulary at
# af272b6fe0b43be3276429792508749b9ddc8194:monitor/views.py. Canonical targets
# are always derived from the shared taxonomy crosswalk above.
LEGACY_DASHBOARD_POST_TYPE_KEYS = (
    "buzz_releases",
    "hands_on_usage",
    "performance_comparisons",
    "feedback_questions",
    "advertising_marketing",
    "event_announcement",
)


class AnalysisInputError(ValueError):
    """A safe, structured error that callers may return to an operator."""

    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": self.message}
        if self.field is not None:
            result["field"] = self.field
        return result


@dataclass(frozen=True)
class AnalysisRequest:
    history_policy: HistoryPolicy
    start: datetime
    end: datetime
    brands: tuple[str, ...] = ()
    schema_version: str = ANALYSIS_SCHEMA_VERSION


@dataclass(frozen=True)
class _SourceIdentity:
    revision: str
    kind: str
    worktree_dirty: bool | None


def _resolve_source_identity() -> _SourceIdentity:
    """Observe the deployed revision or local Git HEAD without a shell."""

    deployed = os.environ.get("RENDER_GIT_COMMIT", "").strip().lower()
    if deployed:
        if _FULL_REVISION.fullmatch(deployed):
            return _SourceIdentity(deployed, "render_deploy", False)
        return _SourceIdentity("unavailable", "invalid_render_environment", None)
    try:
        repository_root = (
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=settings.BASE_DIR,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            .stdout.strip()
        )
        if Path(repository_root).resolve() != Path(settings.BASE_DIR).resolve():
            return _SourceIdentity(
                "unavailable", "parent_git_repository_ignored", None
            )
        revision = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=settings.BASE_DIR,
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            .stdout.strip()
            .lower()
        )
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=settings.BASE_DIR,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return _SourceIdentity("unavailable", "unavailable", None)
    if not _FULL_REVISION.fullmatch(revision):
        return _SourceIdentity("unavailable", "invalid_local_git_revision", None)
    return _SourceIdentity(revision, "local_git_head", bool(status.strip()))


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_request(request: AnalysisRequest) -> AnalysisRequest:
    if request.schema_version != ANALYSIS_SCHEMA_VERSION:
        raise AnalysisInputError(
            "unsupported_schema_version",
            f"schema_version must be {ANALYSIS_SCHEMA_VERSION!r}",
            field="schema_version",
        )
    if request.history_policy not in HISTORY_POLICIES:
        raise AnalysisInputError(
            "invalid_history_policy",
            f"history_policy must be one of {', '.join(HISTORY_POLICIES)}",
            field="history_policy",
        )
    for field, value in (("start", request.start), ("end", request.end)):
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise AnalysisInputError(
                "invalid_utc_timestamp",
                f"{field} must be a timezone-aware UTC timestamp",
                field=field,
            )
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise AnalysisInputError(
                "invalid_utc_timestamp",
                f"{field} must use UTC (Z or +00:00)",
                field=field,
            )
    if request.start >= request.end:
        raise AnalysisInputError(
            "invalid_range",
            "start must be earlier than end for the half-open UTC range",
            field="range",
        )
    cleaned = [
        brand.strip()
        for brand in request.brands
        if isinstance(brand, str) and brand.strip()
    ]
    if len(cleaned) != len(request.brands) or len(
        {brand.casefold() for brand in cleaned}
    ) != len(cleaned):
        raise AnalysisInputError(
            "invalid_brand_scope",
            "brands must be case-insensitively unique, nonblank strings",
            field="brands",
        )
    requested = tuple(sorted(cleaned, key=str.casefold))
    if requested:
        rows = list(
            Brand.objects.filter(nickname__in=requested).values(
                "nickname", "is_sentinel"
            )
        )
        by_folded = {row["nickname"].casefold(): row for row in rows}
        invalid = [
            brand
            for brand in requested
            if brand.casefold() not in by_folded
            or by_folded[brand.casefold()]["is_sentinel"]
        ]
        if invalid:
            raise AnalysisInputError(
                "unknown_or_sentinel_brand",
                "unknown or sentinel brand scope: " + ", ".join(invalid),
                field="brands",
            )
        requested = tuple(
            by_folded[brand.casefold()]["nickname"] for brand in requested
        )

    # Validate the derived public API before any aggregate. The contract module
    # performs the same check at import time; this boundary keeps injected or
    # adapter-supplied collisions a structured CLI failure too.
    try:
        for family in ("post_type", "product_label"):
            rows = taxonomy_crosswalk_rows(family)
            sources = [source for source, _canonical in rows]
            if len(sources) != len(set(sources)):
                raise ValueError(f"duplicate {family} crosswalk source")
        post_type_sources = {
            source for source, _canonical in taxonomy_crosswalk_rows("post_type")
        }
        if not set(LEGACY_DASHBOARD_POST_TYPE_KEYS).issubset(post_type_sources):
            raise ValueError("legacy dashboard key missing from post-type crosswalk")
    except ValueError as exc:
        raise AnalysisInputError(
            "invalid_taxonomy_crosswalk",
            "taxonomy crosswalk is incomplete or contains a collision",
            field="taxonomy_crosswalk",
        ) from exc
    return AnalysisRequest(
        history_policy=request.history_policy,
        start=request.start.astimezone(UTC),
        end=request.end.astimezone(UTC),
        brands=requested,
        schema_version=request.schema_version,
    )


def _values_sql(rows: tuple[tuple[str, str], ...]) -> tuple[str, list[str]]:
    return ", ".join(["(%s, %s)"] * len(rows)), [item for row in rows for item in row]


def _query_rows(request: AnalysisRequest) -> list[dict[str, Any]]:
    post_type_rows = taxonomy_crosswalk_rows("post_type")
    product_rows = taxonomy_crosswalk_rows("product_label")
    post_values, post_params = _values_sql(post_type_rows)
    product_values, product_params = _values_sql(product_rows)
    all_brands = not request.brands
    brands = list(request.brands)

    sql = f"""
        WITH post_type_crosswalk(source_key, canonical_key) AS (
            VALUES {post_values}
        ),
        product_crosswalk(source_key, canonical_key) AS (
            VALUES {product_values}
        ),
        legacy_source_keys(source_key) AS (
            SELECT * FROM unnest(%s::text[])
        ),
        observation AS (
            SELECT statement_timestamp() AS observed_at
        ),
        scoped_pairs AS (
            SELECT pb.post_id::text, pb.brand_id::text, p.created_at
            FROM posts_brands pb
            JOIN posts p ON p.tweet_id = pb.post_id
            JOIN brands b ON b.nickname = pb.brand_id
            WHERE NOT b.is_sentinel
              AND p.created_at >= %s::timestamptz
              AND p.created_at < %s::timestamptz
              AND (%s::boolean OR pb.brand_id::text = ANY(%s::text[]))
        ),
        null_timestamp_pairs AS (
            SELECT pb.post_id::text, pb.brand_id::text
            FROM posts_brands pb
            JOIN posts p ON p.tweet_id = pb.post_id
            JOIN brands b ON b.nickname = pb.brand_id
            WHERE NOT b.is_sentinel
              AND p.created_at IS NULL
              AND (%s::boolean OR pb.brand_id::text = ANY(%s::text[]))
        ),
        states AS (
            SELECT pair.post_id, pair.brand_id,
                   state.contract_version, state.taxonomy_version,
                   state.prompt_version, state.model, state.outcome,
                   state.classified_at
            FROM scoped_pairs pair
            JOIN posts_brands_classification_states state
              ON state.post_id = pair.post_id AND state.brand_id = pair.brand_id
        ),
        recognized_states AS (
            SELECT * FROM states
            WHERE contract_version = %s
              AND taxonomy_version = ANY(%s::text[])
              AND outcome IN ('classified', 'context_missing')
        ),
        invalid_states AS (
            SELECT * FROM states
            WHERE NOT (
                contract_version = %s
                AND taxonomy_version = ANY(%s::text[])
                AND outcome IN ('classified', 'context_missing')
            )
        ),
        exact_raw_edges AS (
            SELECT state.post_id, state.brand_id, state.contract_version,
                   state.taxonomy_version, state.prompt_version, state.model,
                   state.classified_at, 'post_type'::text AS family,
                   signal.post_type_key::text AS source_key,
                   crosswalk.canonical_key
            FROM recognized_states state
            JOIN posts_brands_signals signal
              ON signal.post_id = state.post_id AND signal.brand_id = state.brand_id
            LEFT JOIN post_type_crosswalk crosswalk
              ON crosswalk.source_key = signal.post_type_key::text
            WHERE state.outcome = 'classified'
            UNION ALL
            SELECT state.post_id, state.brand_id, state.contract_version,
                   state.taxonomy_version, state.prompt_version, state.model,
                   state.classified_at, 'product_label'::text,
                   product.product_label_key::text, crosswalk.canonical_key
            FROM recognized_states state
            JOIN posts_brands_product_labels product
              ON product.post_id = state.post_id AND product.brand_id = state.brand_id
            LEFT JOIN product_crosswalk crosswalk
              ON crosswalk.source_key = product.product_label_key::text
            WHERE state.outcome = 'classified'
        ),
        exact_memberships AS (
            SELECT DISTINCT post_id, brand_id, contract_version,
                   taxonomy_version, prompt_version, model, classified_at,
                   family, canonical_key
            FROM exact_raw_edges
            WHERE canonical_key IS NOT NULL
        ),
        unversioned_raw_edges AS (
            SELECT pair.post_id, pair.brand_id, 'post_type'::text AS family,
                   signal.post_type_key::text AS source_key
            FROM scoped_pairs pair
            JOIN posts_brands_signals signal
              ON signal.post_id = pair.post_id AND signal.brand_id = pair.brand_id
            WHERE NOT EXISTS (
                SELECT 1 FROM posts_brands_classification_states state
                WHERE state.post_id = pair.post_id AND state.brand_id = pair.brand_id
            )
            UNION ALL
            SELECT pair.post_id, pair.brand_id, 'product_label'::text,
                   product.product_label_key::text
            FROM scoped_pairs pair
            JOIN posts_brands_product_labels product
              ON product.post_id = pair.post_id AND product.brand_id = pair.brand_id
            WHERE NOT EXISTS (
                SELECT 1 FROM posts_brands_classification_states state
                WHERE state.post_id = pair.post_id AND state.brand_id = pair.brand_id
            )
        ),
        legacy_memberships AS (
            SELECT DISTINCT edge.post_id, edge.brand_id,
                   crosswalk.canonical_key
            FROM unversioned_raw_edges edge
            JOIN legacy_source_keys legacy ON legacy.source_key = edge.source_key
            JOIN post_type_crosswalk crosswalk
              ON crosswalk.source_key = legacy.source_key
            WHERE edge.family = 'post_type'
        )
        SELECT 'observation'::text AS row_kind,
               NULL::text AS family, NULL::text AS key,
               NULL::text AS contract_version, NULL::text AS taxonomy_version,
               NULL::text AS prompt_version, NULL::text AS model,
               NULL::text AS outcome, NULL::bigint AS count_a,
               NULL::bigint AS count_b, NULL::bigint AS count_c,
               observed_at AS min_at, NULL::timestamptz AS max_at
        FROM observation
        UNION ALL
        SELECT 'exact_summary'::text AS row_kind,
               NULL::text AS family, NULL::text AS key,
               NULL::text AS contract_version, NULL::text AS taxonomy_version,
               NULL::text AS prompt_version, NULL::text AS model,
               NULL::text AS outcome,
               count(DISTINCT post_id)::bigint AS count_a,
               count(*) FILTER (WHERE outcome = 'classified')::bigint AS count_b,
               count(*) FILTER (WHERE outcome = 'context_missing')::bigint AS count_c,
               NULL::timestamptz AS min_at, NULL::timestamptz AS max_at
        FROM recognized_states
        UNION ALL
        SELECT 'exact_membership', family, canonical_key,
               NULL, NULL, NULL, NULL, NULL,
               count(*)::bigint, NULL, NULL, NULL, NULL
        FROM exact_memberships
        GROUP BY family, canonical_key
        UNION ALL
        SELECT 'exact_provenance', NULL, NULL, contract_version,
               taxonomy_version, prompt_version, model, NULL,
               count(DISTINCT post_id)::bigint,
               count(*) FILTER (WHERE outcome = 'classified')::bigint,
               count(*) FILTER (WHERE outcome = 'context_missing')::bigint,
               min(classified_at), max(classified_at)
        FROM recognized_states
        GROUP BY contract_version, taxonomy_version, prompt_version, model
        UNION ALL
        SELECT 'provenance_membership', family, canonical_key, contract_version,
               taxonomy_version, prompt_version, model, NULL,
               count(*)::bigint, NULL, NULL, NULL, NULL
        FROM exact_memberships
        GROUP BY contract_version, taxonomy_version, prompt_version, model,
                 family, canonical_key
        UNION ALL
        SELECT 'invalid_summary', NULL, NULL, NULL, NULL, NULL, NULL, NULL,
               count(DISTINCT post_id)::bigint, count(*)::bigint,
               NULL, NULL, NULL
        FROM invalid_states
        UNION ALL
        SELECT 'invalid_state', NULL, NULL, contract_version,
               taxonomy_version, prompt_version, model, outcome,
               count(DISTINCT post_id)::bigint, count(*)::bigint,
               NULL, min(classified_at), max(classified_at)
        FROM invalid_states
        GROUP BY contract_version, taxonomy_version, prompt_version, model, outcome
        UNION ALL
        SELECT 'unknown_edge', family, source_key, NULL, NULL, NULL, NULL, NULL,
               count(DISTINCT post_id)::bigint,
               count(DISTINCT (post_id, brand_id))::bigint,
               NULL, NULL, NULL
        FROM exact_raw_edges
        WHERE canonical_key IS NULL
        GROUP BY family, source_key
        UNION ALL
        SELECT 'unversioned_edge_exclusion', edge.family, edge.source_key,
               NULL, NULL, NULL, NULL, NULL,
               count(DISTINCT edge.post_id)::bigint,
               count(DISTINCT (edge.post_id, edge.brand_id))::bigint,
               NULL, NULL, NULL
        FROM unversioned_raw_edges edge
        LEFT JOIN legacy_source_keys legacy
          ON edge.family = 'post_type' AND legacy.source_key = edge.source_key
        WHERE legacy.source_key IS NULL
        GROUP BY edge.family, edge.source_key
        UNION ALL
        SELECT 'legacy_summary', NULL, NULL, NULL, NULL, NULL, NULL, NULL,
               count(DISTINCT post_id)::bigint,
               count(DISTINCT (post_id, brand_id))::bigint,
               NULL, NULL, NULL
        FROM legacy_memberships
        UNION ALL
        SELECT 'legacy_membership', 'post_type', canonical_key,
               NULL, NULL, NULL, NULL, NULL,
               count(*)::bigint, NULL, NULL, NULL, NULL
        FROM legacy_memberships
        GROUP BY canonical_key
        UNION ALL
        SELECT 'null_timestamp', NULL, NULL, NULL, NULL, NULL, NULL, NULL,
               count(DISTINCT post_id)::bigint, count(*)::bigint,
               NULL, NULL, NULL
        FROM null_timestamp_pairs
        ORDER BY row_kind, family NULLS FIRST, key NULLS FIRST,
                 contract_version NULLS FIRST, taxonomy_version NULLS FIRST,
                 prompt_version NULLS FIRST, model NULLS FIRST,
                 outcome NULLS FIRST
    """
    params: list[Any] = [
        *post_params,
        *product_params,
        list(LEGACY_DASHBOARD_POST_TYPE_KEYS),
        request.start,
        request.end,
        all_brands,
        brands,
        all_brands,
        brands,
        CONTRACT_VERSION,
        list(COMPATIBLE_TAXONOMY_VERSIONS),
        CONTRACT_VERSION,
        list(COMPATIBLE_TAXONOMY_VERSIONS),
    ]
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _crosswalk_payload() -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {
        "post_type": [],
        "product_label": [],
    }
    for family, source_key, canonical_key in TAXONOMY_KEY_CROSSWALK:
        result[family].append(
            {"source_key": source_key, "canonical_key": canonical_key}
        )
    return result


def _query_identity(request: AnalysisRequest) -> str:
    material = {
        "schema_version": request.schema_version,
        "history_policy": request.history_policy,
        "start": _utc_iso(request.start),
        "end": _utc_iso(request.end),
        "brands": list(request.brands) if request.brands else "__all__",
        "contract_version": CONTRACT_VERSION,
        "compatible_taxonomy_versions": list(COMPATIBLE_TAXONOMY_VERSIONS),
        "output_taxonomy_version": CANONICAL_TAXONOMY_VERSION,
        "crosswalk": list(TAXONOMY_KEY_CROSSWALK),
        "legacy_dashboard_post_type_keys": list(LEGACY_DASHBOARD_POST_TYPE_KEYS),
    }
    encoded = json.dumps(material, separators=(",", ":"), sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def analyze_classifications(request: AnalysisRequest) -> dict[str, Any]:
    """Return one complete deterministic analysis document.

    The query describes state visible now. ``PostBrandClassificationState`` is
    a latest-state table, so this function never claims point-in-time state.
    """

    request = _validate_request(request)
    source_identity = _resolve_source_identity()
    rows = _query_rows(request)
    exact = {
        "population": "recognized_versioned_stage1_latest_state",
        "unique_posts": 0,
        "classified_post_brand_denominator": 0,
        "context_missing_post_brands": 0,
        "memberships": {
            "post_types": {"total": 0, "by_key": {}},
            "product_labels": {"total": 0, "by_key": {}},
        },
        "by_stored_provenance": [],
    }
    exclusions = {
        "unrecognized_or_invalid_state": {
            "unique_posts": 0,
            "post_brand_states": 0,
            "by_stored_provenance": [],
        },
        "unknown_edge_keys": [],
        "unversioned_edges_outside_legacy_population": [],
        "null_post_created_at": {
            "scope": "brand_scope_all_dates_missing_timestamp",
            "unique_posts": 0,
            "post_brand_pairs": 0,
        },
    }
    legacy = {
        "population": "legacy_unversioned_approximate",
        "mapping_source": ("af272b6fe0b43be3276429792508749b9ddc8194:monitor/views.py"),
        "mapping": [
            {"source_key": source, "canonical_key": canonical}
            for source, canonical in taxonomy_crosswalk_rows("post_type")
            if source in LEGACY_DASHBOARD_POST_TYPE_KEYS
        ],
        "unique_posts": 0,
        "approximate_post_brand_pairs": 0,
        "post_types": {"total": 0, "by_key": {}},
        "product_labels": {"availability": "unavailable"},
    }
    provenance_index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    observed_at: str | None = None

    for row in rows:
        kind = row["row_kind"]
        if kind == "observation":
            observed_at = _utc_iso(row["min_at"])
        elif kind == "exact_summary":
            exact["unique_posts"] = row["count_a"]
            exact["classified_post_brand_denominator"] = row["count_b"]
            exact["context_missing_post_brands"] = row["count_c"]
        elif kind == "exact_membership":
            family = "post_types" if row["family"] == "post_type" else "product_labels"
            exact["memberships"][family]["by_key"][row["key"]] = row["count_a"]
            exact["memberships"][family]["total"] += row["count_a"]
        elif kind == "exact_provenance":
            identity = (
                row["contract_version"],
                row["taxonomy_version"],
                row["prompt_version"],
                row["model"],
            )
            entry = {
                "contract_version": identity[0],
                "taxonomy_version": identity[1],
                "prompt_version": identity[2],
                "model": identity[3],
                "unique_posts": row["count_a"],
                "classified_post_brands": row["count_b"],
                "context_missing_post_brands": row["count_c"],
                "memberships": {
                    "post_types": {"total": 0, "by_key": {}},
                    "product_labels": {"total": 0, "by_key": {}},
                },
                "classified_at": {
                    "min": _utc_iso(row["min_at"]) if row["min_at"] else None,
                    "max": _utc_iso(row["max_at"]) if row["max_at"] else None,
                    "role": "provenance_only",
                },
            }
            provenance_index[identity] = entry
            exact["by_stored_provenance"].append(entry)
        elif kind == "provenance_membership":
            identity = (
                row["contract_version"],
                row["taxonomy_version"],
                row["prompt_version"],
                row["model"],
            )
            family = "post_types" if row["family"] == "post_type" else "product_labels"
            membership = provenance_index[identity]["memberships"][family]
            membership["by_key"][row["key"]] = row["count_a"]
            membership["total"] += row["count_a"]
        elif kind == "invalid_summary":
            exclusions["unrecognized_or_invalid_state"]["unique_posts"] = row["count_a"]
            exclusions["unrecognized_or_invalid_state"]["post_brand_states"] = row[
                "count_b"
            ]
        elif kind == "invalid_state":
            entry = {
                "contract_version": row["contract_version"],
                "taxonomy_version": row["taxonomy_version"],
                "prompt_version": row["prompt_version"],
                "model": row["model"],
                "outcome": row["outcome"],
                "unique_posts": row["count_a"],
                "post_brand_states": row["count_b"],
                "classified_at_min": _utc_iso(row["min_at"]) if row["min_at"] else None,
                "classified_at_max": _utc_iso(row["max_at"]) if row["max_at"] else None,
            }
            exclusions["unrecognized_or_invalid_state"]["by_stored_provenance"].append(
                entry
            )
        elif kind == "unknown_edge":
            exclusions["unknown_edge_keys"].append(
                {
                    "family": row["family"],
                    "source_key": row["key"],
                    "unique_posts": row["count_a"],
                    "post_brand_pairs": row["count_b"],
                }
            )
        elif kind == "unversioned_edge_exclusion":
            exclusions["unversioned_edges_outside_legacy_population"].append(
                {
                    "family": row["family"],
                    "source_key": row["key"],
                    "unique_posts": row["count_a"],
                    "post_brand_pairs": row["count_b"],
                }
            )
        elif kind == "legacy_summary":
            legacy["unique_posts"] = row["count_a"]
            legacy["approximate_post_brand_pairs"] = row["count_b"]
        elif kind == "legacy_membership":
            legacy["post_types"]["by_key"][row["key"]] = row["count_a"]
            legacy["post_types"]["total"] += row["count_a"]
        elif kind == "null_timestamp":
            exclusions["null_post_created_at"]["unique_posts"] = row["count_a"]
            exclusions["null_post_created_at"]["post_brand_pairs"] = row["count_b"]

    warnings: list[dict[str, Any]] = []
    if exclusions["null_post_created_at"]["post_brand_pairs"]:
        warnings.append(
            {
                "code": "null_post_created_at_excluded",
                "scope": "brand_scope_all_dates_missing_timestamp",
                "count": exclusions["null_post_created_at"]["post_brand_pairs"],
            }
        )
    if exclusions["unrecognized_or_invalid_state"]["post_brand_states"]:
        warnings.append(
            {
                "code": "unrecognized_or_invalid_state_excluded",
                "count": exclusions["unrecognized_or_invalid_state"][
                    "post_brand_states"
                ],
            }
        )
    if exclusions["unknown_edge_keys"]:
        warnings.append(
            {
                "code": "unknown_edge_keys_excluded",
                "count": sum(
                    item["post_brand_pairs"] for item in exclusions["unknown_edge_keys"]
                ),
            }
        )
    if exclusions["unversioned_edges_outside_legacy_population"]:
        warnings.append(
            {
                "code": "unversioned_edges_outside_legacy_population_excluded",
                "count": sum(
                    item["post_brand_pairs"]
                    for item in exclusions[
                        "unversioned_edges_outside_legacy_population"
                    ]
                ),
            }
        )
    if source_identity.revision == "unavailable":
        warning_code = (
            "source_revision_parent_repository_ignored"
            if source_identity.kind == "parent_git_repository_ignored"
            else "source_revision_unavailable"
        )
        warnings.append({"code": warning_code})
    if source_identity.worktree_dirty:
        warnings.append({"code": "source_worktree_dirty"})
    if (
        request.history_policy == "current_definition"
        and legacy["approximate_post_brand_pairs"]
    ):
        exclusions["legacy_unversioned_omitted"] = {
            "population": "legacy_unversioned_approximate",
            "reason": "history_policy_current_definition",
            "unique_posts": legacy["unique_posts"],
            "post_brand_pairs": legacy["approximate_post_brand_pairs"],
        }
        warnings.append(
            {
                "code": "legacy_unversioned_omitted_by_policy",
                "count": legacy["approximate_post_brand_pairs"],
            }
        )

    result: dict[str, Any] = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": "empty"
        if exact["unique_posts"] == 0
        and (
            request.history_policy == "current_definition"
            or legacy["unique_posts"] == 0
        )
        else "ok",
        "query": {
            "history_policy": request.history_policy,
            "range": {
                "start": _utc_iso(request.start),
                "end": _utc_iso(request.end),
                "interval": "[start,end)",
                "timezone": "UTC",
            },
            "range_basis": "post_created_at",
            "brands": list(request.brands) if request.brands else "__all__",
            "output_taxonomy_version": CANONICAL_TAXONOMY_VERSION,
        },
        "identity": {
            "source_revision": source_identity.revision,
            "source_revision_kind": source_identity.kind,
            "source_worktree_dirty": source_identity.worktree_dirty,
            "query_identity": _query_identity(request),
        },
        "observation": {
            "observed_at": observed_at,
            "clock": "postgresql_statement_timestamp",
            "database_snapshot_identity": "not_recorded",
        },
        "identifier_equivalence": {
            "kind": "identifier_only",
            "crosswalk": _crosswalk_payload(),
        },
        "exact_stage1": exact,
        "exclusions": exclusions,
        "warnings": warnings,
        "latest_state_limitation": (
            "PostBrandClassificationState stores only the latest state visible at query "
            "time; this result cannot reconstruct classification state as of an earlier date."
        ),
    }
    if request.history_policy == "historical_inclusive":
        result["legacy_unversioned_approximate"] = legacy
    exact["by_stored_provenance"].sort(
        key=lambda item: (
            item["contract_version"],
            item["taxonomy_version"],
            item["prompt_version"],
            item["model"],
        )
    )
    exclusions["unrecognized_or_invalid_state"]["by_stored_provenance"].sort(
        key=lambda item: (
            item["contract_version"],
            item["taxonomy_version"],
            item["prompt_version"],
            item["model"],
            item["outcome"],
        )
    )
    exclusions["unknown_edge_keys"].sort(
        key=lambda item: (item["family"], item["source_key"])
    )
    exclusions["unversioned_edges_outside_legacy_population"].sort(
        key=lambda item: (item["family"], item["source_key"])
    )
    warnings.sort(key=lambda item: item["code"])
    return result


def safe_error_document(error: AnalysisInputError) -> dict[str, Any]:
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "status": "error",
        "error": error.as_dict(),
    }
