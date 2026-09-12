#!/usr/bin/env python3
"""Read-only health report for the newest persisted production posts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_PRODUCT_LABEL_KEYS,
    CANONICAL_PROMPT_VERSION,
    CANONICAL_TAXONOMY_VERSION,
    COMPATIBLE_TAXONOMY_VERSIONS,
    CONTRACT_VERSION,
    NATIONALISM_KEYS,
    PROMPT_VERSION,
    SENTIMENT_KEYS,
    TAXONOMY_VERSION,
    canonicalize_taxonomy_key,
    taxonomy_crosswalk_rows,
)

DATABASE_RESOURCE = "pushinweight-db-shadow"
DEFAULT_LATEST = 20
MAX_COHORT = 200
QUERY_TIMEOUT_SECONDS = 30
REPORT_RELATIVE_DIR = Path("docs/analysis/harvester")
LLM_BATCH_SIZE = 20
_TWEET_ID_RE = re.compile(r"^[0-9]{1,32}$")
_SAFE_ERROR_CODE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_VALID_STAGE_STATUSES = {"pending", "succeeded", "failed"}
_CANONICAL_LANG_CODES = {"en", "zh-Hans", "zh-Hant", "ja", "ko", "other"}
_STAGE1_RELATIONS = (
    "posts_brands_classification_states",
    "posts_brands_product_labels",
    "product_label_keys",
    "product_label_labels",
)


class HealthCheckError(Exception):
    """A sanitized failure safe to expose in operator output."""

    def __init__(self, error_class: str, code: str):
        self.error_class = error_class
        self.code = code
        super().__init__(code)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise HealthCheckError("invocation", "invalid_arguments")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = _SafeArgumentParser(
        description="Inspect a bounded read-only cohort of production posts."
    )
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--latest", type=int)
    selector.add_argument("--tweet-id", action="append", dest="tweet_ids")
    parser.add_argument("--grace-hours", type=int)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--report",
        action="store_true",
        help="write an opt-in detailed Markdown evidence report",
    )
    args = parser.parse_args(argv)

    if args.latest is None and not args.tweet_ids:
        args.latest = DEFAULT_LATEST
    if args.latest is not None and not 1 <= args.latest <= MAX_COHORT:
        raise HealthCheckError("invocation", "invalid_arguments")
    if args.tweet_ids:
        if len(args.tweet_ids) > MAX_COHORT or len(set(args.tweet_ids)) != len(
            args.tweet_ids
        ):
            raise HealthCheckError("invocation", "invalid_arguments")
        if any(not _TWEET_ID_RE.fullmatch(tweet_id) for tweet_id in args.tweet_ids):
            raise HealthCheckError("invocation", "invalid_arguments")
    if args.grace_hours is not None and not 1 <= args.grace_hours <= 24 * 30:
        raise HealthCheckError("invocation", "invalid_arguments")
    if args.report and args.as_json:
        raise HealthCheckError("invocation", "invalid_arguments")
    return args


def _selected_cte(*, latest: int | None, tweet_ids: Sequence[str] | None) -> str:
    if tweet_ids:
        values = ",\n      ".join(
            f"('{tweet_id}', {ordinal})" for ordinal, tweet_id in enumerate(tweet_ids)
        )
        return f"""selected_ids(tweet_id, ordinal) AS (
    VALUES
      {values}
  ),
  selected AS (
    SELECT p.*, selected_ids.ordinal
    FROM posts p
    JOIN selected_ids ON selected_ids.tweet_id = p.tweet_id
    ORDER BY selected_ids.ordinal
  )"""

    assert latest is not None
    return f"""selected AS (
    SELECT
      p.*,
      ROW_NUMBER() OVER (
        ORDER BY p.fetched_at DESC, p.tweet_id DESC
      ) - 1 AS ordinal
    FROM posts p
    ORDER BY p.fetched_at DESC, p.tweet_id DESC
    LIMIT {latest}
  )"""


def _snapshot_select(
    *,
    selected_cte: str,
    detailed: bool,
    stage1: bool,
) -> str:
    def crosswalk_values(family: str) -> str:
        rows = taxonomy_crosswalk_rows(family)
        if any(not re.fullmatch(r"[a-z_]+", value) for row in rows for value in row):
            raise HealthCheckError("query", "invalid_taxonomy_crosswalk")
        return ", ".join(f"('{source}', '{canonical}')" for source, canonical in rows)

    post_type_crosswalk = crosswalk_values("post_type")
    product_crosswalk = crosswalk_values("product_label")
    post_detail_fields = ""
    brand_detail_fields = ""
    discourse_detail_fields = ""
    if detailed:
        post_detail_fields = """,
        'author_id', p.author_id,
        'author_handle', p.author_handle,
        'author_name', p.author_name,
        'source_query_id', p.source_query_id,
        'created_at', p.created_at,
        'text', p.text,
        'lang', p.lang,
        'text_en', p.text_en,
        'text_zh_cn', p.text_zh_cn,
        'commentary_en', p.commentary_en,
        'commentary_zh_cn', p.commentary_zh_cn,
        'tweet_url', COALESCE(p.tweet_url, p.tweet_twitter_url),
        'like_count', p.like_count,
        'retweet_count', p.retweet_count,
        'reply_count', p.reply_count,
        'quote_count', p.quote_count,
        'view_count', p.view_count,
        'metrics_refreshed_at', p.metrics_refreshed_at,
        'translation_attempts', es.translation_attempts,
        'translation_first_attempt_at', es.translation_first_attempt_at,
        'translation_last_attempt_at', es.translation_last_attempt_at,
        'translation_next_attempt_at', es.translation_next_attempt_at,
        'classification_attempts', es.classification_attempts,
        'classification_first_attempt_at', es.classification_first_attempt_at,
        'classification_last_attempt_at', es.classification_last_attempt_at,
        'classification_next_attempt_at', es.classification_next_attempt_at,
        'enrichment_created_at', es.created_at,
        'enrichment_updated_at', es.updated_at,
        'unsanctioned_flags', (
          SELECT jsonb_build_object(
            'flags', uf.flags,
            'flag_set', uf.flag_set,
            'evidence', uf.evidence,
            'decided_at', uf.decided_at
          )
          FROM posts_unsanctioned_flags uf
          WHERE uf.post_id = p.tweet_id
        )"""
        brand_detail_fields = """,
              'weight', pb.weight,
              'mentions', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'source', mention.source,
                    'raw_token', mention.raw_token,
                    'mentioned_at', mention.mentioned_at
                  )
                  ORDER BY mention.source, mention.mentioned_at
                )
                FROM posts_brands_mentions mention
                WHERE mention.post_id = p.tweet_id
                  AND mention.brand_id = pb.brand_id
              ), '[]'::jsonb)"""
        discourse_detail_fields = """,
                    'china_nationalism', discourse.china_nationalism,
                    'us_nationalism', discourse.us_nationalism"""
    classification_fields = ""
    if stage1:
        classification_fields = f""",
              'classification_state', CASE
                WHEN classification_state.post_id IS NULL THEN NULL
                ELSE jsonb_build_object(
                  'contract_version', classification_state.contract_version,
                  'taxonomy_version', classification_state.taxonomy_version,
                  'prompt_version', classification_state.prompt_version,
                  'prompt_version_active_write',
                    classification_state.prompt_version = '{PROMPT_VERSION}',
                  'taxonomy_version_current_compatible',
                    classification_state.contract_version = '{CONTRACT_VERSION}'
                    AND classification_state.taxonomy_version = ANY(
                      ARRAY[{", ".join(repr(value) for value in COMPATIBLE_TAXONOMY_VERSIONS)}]
                    ),
                  'active_write_taxonomy_version', '{TAXONOMY_VERSION}',
                  'active_write_prompt_version', '{PROMPT_VERSION}',
                  'latest_taxonomy_version', '{CANONICAL_TAXONOMY_VERSION}',
                  'latest_prompt_version', '{CANONICAL_PROMPT_VERSION}',
                  'outcome', classification_state.outcome,
                  'sentiment', classification_state.sentiment,
                  'china_nationalism',
                    classification_state.china_nationalism,
                  'us_nationalism', classification_state.us_nationalism
                )
              END,
              'product_labels', COALESCE((
                SELECT jsonb_agg(
                  canonical_key ORDER BY canonical_key
                )
                FROM (
                  SELECT DISTINCT mapping.canonical_key
                  FROM posts_brands_product_labels product
                  JOIN product_crosswalk mapping
                    ON mapping.source_key = product.product_label_key::text
                  WHERE product.post_id = p.tweet_id
                    AND product.brand_id = pb.brand_id
                ) canonical_products
              ), '[]'::jsonb),
              'stored_product_label_keys', COALESCE((
                SELECT jsonb_agg(product.product_label_key ORDER BY product.product_label_key)
                FROM posts_brands_product_labels product
                WHERE product.post_id = p.tweet_id
                  AND product.brand_id = pb.brand_id
              ), '[]'::jsonb),
              'stored_post_type_keys', COALESCE((
                SELECT jsonb_agg(signal.post_type_key ORDER BY signal.post_type_key)
                FROM posts_brands_signals signal
                WHERE signal.post_id = p.tweet_id
                  AND signal.brand_id = pb.brand_id
              ), '[]'::jsonb)"""
    else:
        classification_fields = """,
              'classification_state', NULL,
              'product_labels', '[]'::jsonb"""

    classification_join = ""
    if stage1:
        classification_join = """
            LEFT JOIN posts_brands_classification_states classification_state
              ON classification_state.post_id = p.tweet_id
             AND classification_state.brand_id = pb.brand_id"""

    schema_profile = "stage1" if stage1 else "legacy"
    return f"""WITH
  post_type_crosswalk(source_key, canonical_key) AS (
    VALUES {post_type_crosswalk}
  ),
  product_crosswalk(source_key, canonical_key) AS (
    VALUES {product_crosswalk}
  ),
  {selected_cte},
  post_rows AS (
    SELECT
      p.ordinal,
      jsonb_build_object(
        'tweet_id', p.tweet_id,
        'fetched_at', p.fetched_at{post_detail_fields},
        'age_seconds', CASE
          WHEN es.created_at IS NULL THEN NULL
          ELSE GREATEST(
            0,
            FLOOR(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - es.created_at)))
          )::bigint
        END,
        'has_text', NULLIF(BTRIM(p.text), '') IS NOT NULL,
        'lang_detected', NULLIF(BTRIM(p.lang_detected), ''),
        'has_lang_detected', BTRIM(p.lang_detected) IN (
          'en', 'zh-Hans', 'zh-Hant', 'ja', 'ko', 'other'
        ),
        'has_text_en', NULLIF(BTRIM(p.text_en), '') IS NOT NULL,
        'has_text_zh_cn', NULLIF(BTRIM(p.text_zh_cn), '') IS NOT NULL,
        'has_commentary_en', (
          NULLIF(BTRIM(p.commentary_en), '') IS NOT NULL
          AND LOWER(BTRIM(p.commentary_en)) NOT IN ('n/a', 'na')
          AND LOWER(BTRIM(p.commentary_en))
            IS DISTINCT FROM LOWER(BTRIM(p.text))
          AND LOWER(BTRIM(p.commentary_en))
            IS DISTINCT FROM LOWER(BTRIM(p.text_en))
          AND LOWER(BTRIM(p.commentary_en))
            IS DISTINCT FROM LOWER(BTRIM(p.text_zh_cn))
        ),
        'has_commentary_zh_cn', (
          NULLIF(BTRIM(p.commentary_zh_cn), '') IS NOT NULL
          AND LOWER(BTRIM(p.commentary_zh_cn)) NOT IN ('n/a', 'na')
          AND LOWER(BTRIM(p.commentary_zh_cn))
            IS DISTINCT FROM LOWER(BTRIM(p.text))
          AND LOWER(BTRIM(p.commentary_zh_cn))
            IS DISTINCT FROM LOWER(BTRIM(p.text_en))
          AND LOWER(BTRIM(p.commentary_zh_cn))
            IS DISTINCT FROM LOWER(BTRIM(p.text_zh_cn))
        ),
        'translation_status', es.translation_status,
        'translation_error_code', es.translation_error_code,
        'classification_status', es.classification_status,
        'classification_error_code', es.classification_error_code,
        'brands', COALESCE((
          SELECT jsonb_agg(
            jsonb_build_object(
              'brand_id', pb.brand_id{brand_detail_fields},
              'legacy_sentiments', COALESCE((
                SELECT jsonb_agg(value ORDER BY value)
                FROM (
                  SELECT DISTINCT NULLIF(BTRIM(signal.sentiment), '') AS value
                  FROM posts_brands_signals signal
                  WHERE signal.post_id = p.tweet_id
                    AND signal.brand_id = pb.brand_id
                ) distinct_values
                WHERE value IS NOT NULL
              ), '[]'::jsonb),
              'legacy_china_nationalisms', COALESCE((
                SELECT jsonb_agg(value ORDER BY value)
                FROM (
                  SELECT DISTINCT
                    NULLIF(BTRIM(discourse.china_nationalism), '') AS value
                  FROM posts_brands_discourse discourse
                  WHERE discourse.post_id = p.tweet_id
                    AND discourse.brand_id = pb.brand_id
                ) distinct_values
                WHERE value IS NOT NULL
              ), '[]'::jsonb),
              'legacy_us_nationalisms', COALESCE((
                SELECT jsonb_agg(value ORDER BY value)
                FROM (
                  SELECT DISTINCT
                    NULLIF(BTRIM(discourse.us_nationalism), '') AS value
                  FROM posts_brands_discourse discourse
                  WHERE discourse.post_id = p.tweet_id
                    AND discourse.brand_id = pb.brand_id
                ) distinct_values
                WHERE value IS NOT NULL
              ), '[]'::jsonb){classification_fields},
              'signals', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'post_type', canonical_signal.post_type,
                    'sentiment', canonical_signal.sentiment
                  )
                  ORDER BY canonical_signal.post_type, canonical_signal.sentiment
                )
                FROM (
                  SELECT DISTINCT mapping.canonical_key AS post_type,
                                  signal.sentiment
                  FROM posts_brands_signals signal
                  JOIN post_type_crosswalk mapping
                    ON mapping.source_key = signal.post_type_key::text
                  WHERE signal.post_id = p.tweet_id
                    AND signal.brand_id = pb.brand_id
                ) canonical_signal
              ), '[]'::jsonb),
              'discourses', COALESCE((
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'discourse', discourse.discourse_key,
                    'act_id', discourse.act_id{discourse_detail_fields}
                  )
                  ORDER BY discourse.discourse_key, discourse.act_id
                )
                FROM posts_brands_discourse discourse
                WHERE discourse.post_id = p.tweet_id
                  AND discourse.brand_id = pb.brand_id
              ), '[]'::jsonb)
            )
            ORDER BY pb.brand_id
          )
          FROM posts_brands pb
          {classification_join}
          WHERE pb.post_id = p.tweet_id
        ), '[]'::jsonb)
      ) AS post_data
    FROM selected p
    LEFT JOIN post_enrichment_states es ON es.post_id = p.tweet_id
  )
SELECT jsonb_build_object(
  'transaction_read_only', current_setting('transaction_read_only'),
  'schema_profile', '{schema_profile}',
  'posts', COALESCE(
    jsonb_agg(post_data ORDER BY ordinal),
    '[]'::jsonb
  )
) AS snapshot FROM post_rows"""


def build_query(
    *,
    latest: int | None,
    tweet_ids: Sequence[str] | None,
    detailed: bool = False,
) -> str:
    """Build one schema-aware, bounded, read-only PostgreSQL observation."""

    selected_cte = _selected_cte(latest=latest, tweet_ids=tweet_ids)
    legacy_select = _snapshot_select(
        selected_cte=selected_cte,
        detailed=detailed,
        stage1=False,
    )
    stage1_select = _snapshot_select(
        selected_cte=selected_cte,
        detailed=detailed,
        stage1=True,
    )
    relation_values = ", ".join(f"'{name}'" for name in _STAGE1_RELATIONS)
    relation_count = len(_STAGE1_RELATIONS)
    partial_select = """SELECT jsonb_build_object(
  'transaction_read_only', current_setting('transaction_read_only'),
  'schema_profile', 'partial',
  'posts', '[]'::jsonb
) AS snapshot"""
    return f"""BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '20s';
WITH schema_state AS (
  SELECT COUNT(*) FILTER (
    WHERE to_regclass('public.' || relation_name) IS NOT NULL
  ) AS stage1_relation_count
  FROM unnest(ARRAY[{relation_values}]) AS relation_name
), chosen_query AS (
  SELECT CASE
    WHEN stage1_relation_count = 0
      THEN $legacy_query${legacy_select}$legacy_query$
    WHEN stage1_relation_count = {relation_count}
      THEN $stage1_query${stage1_select}$stage1_query$
    ELSE $partial_query${partial_select}$partial_query$
  END AS sql
  FROM schema_state
)
SELECT snapshot
FROM chosen_query
CROSS JOIN LATERAL XMLTABLE(
  '/row'
  PASSING query_to_xml(chosen_query.sql, false, true, '')
  COLUMNS snapshot text PATH 'snapshot/text()'
) AS result;
COMMIT;"""


def build_command(sql: str) -> list[str]:
    return [
        "render",
        "psql",
        DATABASE_RESOURCE,
        "--command",
        sql,
        "--output",
        "text",
        "--",
        "--no-psqlrc",
        "--no-align",
        "--tuples-only",
        "--quiet",
        "--set=ON_ERROR_STOP=1",
    ]


def parse_snapshot(output: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            value = json.loads(stripped)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and isinstance(value.get("posts"), list):
            candidates.append(value)
    if len(candidates) != 1:
        raise HealthCheckError("transport", "render_output_invalid")
    return candidates[0]


def execute_query(
    sql: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = build_command(sql)
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            timeout=QUERY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HealthCheckError("transport", "render_timeout") from None
    except (FileNotFoundError, OSError):
        raise HealthCheckError("transport", "render_unavailable") from None
    if result.returncode != 0:
        raise HealthCheckError("transport", "render_command_failed")
    return parse_snapshot(result.stdout)


def load_grace_hours() -> int:
    try:
        import yaml
    except ImportError:
        raise HealthCheckError("configuration", "config_invalid") from None

    try:
        repo_root = Path(__file__).resolve().parents[4]
        data = yaml.safe_load((repo_root / "config.yaml").read_text()) or {}
        value = data["harvest"]["enrichment"]["max_age_hours"]
        if isinstance(value, bool):
            raise TypeError
        grace_hours = int(value)
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError):
        raise HealthCheckError("configuration", "config_invalid") from None
    if not 1 <= grace_hours <= 24 * 30:
        raise HealthCheckError("configuration", "config_invalid")
    return grace_hours


def _safe_error_code(value: Any) -> str | None:
    if isinstance(value, str) and _SAFE_ERROR_CODE_RE.fullmatch(value):
        return value
    return None


def _reason(
    stage: str,
    reason: str,
    *,
    brand_id: Any = None,
    error_code: Any = None,
) -> dict[str, str]:
    result = {"stage": stage, "reason": reason}
    if isinstance(brand_id, str) and brand_id:
        result["brand_id"] = brand_id[:128]
    safe_error_code = _safe_error_code(error_code)
    if safe_error_code:
        result["error_code"] = safe_error_code
    return result


def _stage_reasons(
    row: dict[str, Any], *, stage: str, grace_seconds: int
) -> list[dict[str, str]]:
    status_key = f"{stage}_status"
    error_key = f"{stage}_error_code"
    status = row.get(status_key)
    if status is None:
        return []
    if status not in _VALID_STAGE_STATUSES:
        return [_reason(stage, "invalid_status")]
    if status == "failed":
        return [_reason(stage, "failed", error_code=row.get(error_key))]
    if status == "pending":
        age_seconds = row.get("age_seconds")
        if not isinstance(age_seconds, (int, float)):
            return [_reason(stage, "pending_age_unknown")]
        if age_seconds > grace_seconds:
            return [_reason(stage, "pending_overdue")]
    return []


def _string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _legacy_axis(brand: dict[str, Any], field: str) -> tuple[str | None, bool]:
    values = set(_string_values(brand.get(field)))
    if len(values) == 1:
        return values.pop(), False
    return None, len(values) > 1


def _legacy_brand_summary(brand: dict[str, Any]) -> dict[str, Any]:
    sentiments = brand.get("legacy_sentiments")
    if not isinstance(sentiments, list):
        sentiments = [
            signal.get("sentiment")
            for signal in brand.get("signals", [])
            if isinstance(signal, dict)
        ]
        brand = {**brand, "legacy_sentiments": sentiments}
    for axis, discourse_key in (
        ("legacy_china_nationalisms", "china_nationalism"),
        ("legacy_us_nationalisms", "us_nationalism"),
    ):
        if not isinstance(brand.get(axis), list):
            brand = {
                **brand,
                axis: [
                    discourse.get(discourse_key)
                    for discourse in brand.get("discourses", [])
                    if isinstance(discourse, dict)
                ],
            }
    sentiment, sentiment_conflict = _legacy_axis(brand, "legacy_sentiments")
    china, china_conflict = _legacy_axis(brand, "legacy_china_nationalisms")
    us, us_conflict = _legacy_axis(brand, "legacy_us_nationalisms")
    conflicts = [
        name
        for name, conflict in (
            ("sentiment", sentiment_conflict),
            ("china_nationalism", china_conflict),
            ("us_nationalism", us_conflict),
        )
        if conflict
    ]
    return {
        "state": "historical_untyped",
        "contract_version": None,
        "taxonomy_version": None,
        "prompt_version": None,
        "outcome": None,
        "post_types": [],
        "product_labels": [],
        "sentiment": sentiment,
        "china_nationalism": china,
        "us_nationalism": us,
        "scalar_source": "historical" if any((sentiment, china, us)) else "unknown",
        "legacy_conflicts": conflicts,
    }


def _stage1_brand_health(
    brand: dict[str, Any], *, brand_id: str
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    state = brand.get("classification_state")
    if not isinstance(state, dict):
        return _legacy_brand_summary(brand), []

    signals = brand.get("signals") if isinstance(brand.get("signals"), list) else []
    product_labels = _string_values(brand.get("product_labels"))
    post_types = [
        signal.get("post_type")
        for signal in signals
        if isinstance(signal, dict) and isinstance(signal.get("post_type"), str)
    ]
    stored_post_types = _string_values(brand.get("stored_post_type_keys"))
    stored_products = _string_values(brand.get("stored_product_label_keys"))
    if (
        state.get("contract_version") != CONTRACT_VERSION
        or state.get("taxonomy_version") not in COMPATIBLE_TAXONOMY_VERSIONS
    ):
        summary = {
            "state": "stale",
            "contract_version": state.get("contract_version"),
            "taxonomy_version": state.get("taxonomy_version"),
            "prompt_version": state.get("prompt_version"),
            "stale_outcome": state.get("outcome"),
            "outcome": None,
            "post_types": [],
            "product_labels": [],
            "sentiment": None,
            "china_nationalism": None,
            "us_nationalism": None,
            "scalar_source": "unrecognized",
            "legacy_conflicts": [],
        }
        return summary, [
            _reason("classification", "stale_state", brand_id=brand_id)
        ]

    summary = {
        "state": "current",
        "contract_version": state.get("contract_version"),
        "taxonomy_version": state.get("taxonomy_version"),
        "prompt_version": state.get("prompt_version"),
        "taxonomy_version_current_compatible": True,
        "active_write_taxonomy_version": TAXONOMY_VERSION,
        "active_write_prompt_version": PROMPT_VERSION,
        "latest_taxonomy_version": CANONICAL_TAXONOMY_VERSION,
        "latest_prompt_version": CANONICAL_PROMPT_VERSION,
        "outcome": state.get("outcome"),
        "post_types": post_types,
        "product_labels": product_labels,
        "stored_post_type_keys": stored_post_types,
        "stored_product_label_keys": stored_products,
        "sentiment": state.get("sentiment"),
        "china_nationalism": state.get("china_nationalism"),
        "us_nationalism": state.get("us_nationalism"),
        "scalar_source": "current",
        "legacy_conflicts": [],
    }
    reasons: list[dict[str, str]] = []
    if not isinstance(state.get("prompt_version"), str) or not state["prompt_version"]:
        reasons.append(
            _reason("classification", "missing_prompt_version", brand_id=brand_id)
        )
    outcome = state.get("outcome")
    if outcome not in {"classified", "context_missing"}:
        reasons.append(_reason("classification", "invalid_outcome", brand_id=brand_id))
    for field in ("china_nationalism", "us_nationalism"):
        value = state.get(field)
        if value is not None and value not in NATIONALISM_KEYS:
            reasons.append(
                _reason("classification", f"invalid_{field}", brand_id=brand_id)
            )
    sentiment = state.get("sentiment")
    if sentiment is not None and sentiment not in SENTIMENT_KEYS:
        reasons.append(
            _reason("classification", "invalid_sentiment", brand_id=brand_id)
        )
    invalid_types = [value for value in post_types if value not in CANONICAL_POST_TYPE_KEYS]
    invalid_types.extend(
        value
        for value in stored_post_types
        if canonicalize_taxonomy_key("post_type", value) is None
    )
    if invalid_types or len(post_types) != len(signals):
        reasons.append(
            _reason("classification", "invalid_post_type", brand_id=brand_id)
        )
    invalid_products = any(
        label not in CANONICAL_PRODUCT_LABEL_KEYS for label in product_labels
    ) or any(
        canonicalize_taxonomy_key("product_label", label) is None
        for label in stored_products
    )
    if invalid_products:
        reasons.append(
            _reason("classification", "invalid_product_label", brand_id=brand_id)
        )

    if outcome == "classified":
        if not post_types:
            reasons.append(
                _reason("classification", "missing_post_type", brand_id=brand_id)
            )
        if sentiment is None:
            reasons.append(
                _reason("classification", "missing_sentiment", brand_id=brand_id)
            )
        if "other" in post_types and post_types != ["other"]:
            reasons.append(
                _reason("classification", "other_not_exclusive", brand_id=brand_id)
            )
        for signal in signals:
            if not isinstance(signal, dict) or signal.get("sentiment") != sentiment:
                reasons.append(
                    _reason(
                        "classification",
                        "signal_sentiment_mismatch",
                        brand_id=brand_id,
                    )
                )
                break
    elif outcome == "context_missing" and (post_types or product_labels):
        reasons.append(
            _reason(
                "classification", "context_missing_has_edges", brand_id=brand_id
            )
        )
    return summary, reasons


def _evaluate_post(row: dict[str, Any], *, grace_hours: int) -> dict[str, Any]:
    tweet_id = str(row.get("tweet_id") or "")
    translation_status = row.get("translation_status") or "missing"
    classification_status = row.get("classification_status") or "missing"
    brands = row.get("brands") if isinstance(row.get("brands"), list) else []
    reasons: list[dict[str, str]] = []
    brand_classifications: list[dict[str, Any]] = []

    if not tweet_id:
        reasons.append(_reason("persistence", "missing_tweet_id"))
    if not row.get("fetched_at"):
        reasons.append(_reason("persistence", "missing_fetched_at"))
    if not row.get("has_text"):
        reasons.append(_reason("persistence", "missing_text"))
    if (
        row.get("translation_status") is None
        or row.get("classification_status") is None
    ):
        reasons.append(_reason("persistence", "missing_enrichment_state"))
    if not brands:
        reasons.append(_reason("persistence", "missing_brand"))

    grace_seconds = grace_hours * 60 * 60
    reasons.extend(
        _stage_reasons(row, stage="translation", grace_seconds=grace_seconds)
    )
    reasons.extend(
        _stage_reasons(row, stage="classification", grace_seconds=grace_seconds)
    )

    if row.get("translation_status") == "succeeded":
        for field, reason in (
            ("has_lang_detected", "missing_lang_detected"),
            ("has_text_en", "missing_text_en"),
            ("has_text_zh_cn", "missing_text_zh_cn"),
            ("has_commentary_en", "missing_commentary_en"),
            ("has_commentary_zh_cn", "missing_commentary_zh_cn"),
        ):
            if not row.get(field):
                reasons.append(_reason("translation", reason))

    if row.get("classification_status") == "succeeded":
        for brand in brands:
            if not isinstance(brand, dict):
                reasons.append(_reason("classification", "invalid_brand"))
                continue
            brand_id = brand.get("brand_id")
            if not isinstance(brand_id, str) or not brand_id:
                reasons.append(_reason("classification", "missing_brand_id"))
                continue
            if row.get("schema_profile") == "stage1":
                brand_summary, brand_reasons = _stage1_brand_health(
                    brand, brand_id=brand_id
                )
                brand_classifications.append(
                    {"brand_id": brand_id, **brand_summary}
                )
                reasons.extend(brand_reasons)
                continue
            signals = (
                brand.get("signals") if isinstance(brand.get("signals"), list) else []
            )
            if not signals:
                reasons.append(
                    _reason("classification", "missing_signal", brand_id=brand_id)
                )
            for signal in signals:
                if not isinstance(signal, dict) or not signal.get("post_type"):
                    reasons.append(
                        _reason(
                            "classification", "missing_post_type", brand_id=brand_id
                        )
                    )
                if not isinstance(signal, dict) or not signal.get("sentiment"):
                    reasons.append(
                        _reason(
                            "classification", "missing_sentiment", brand_id=brand_id
                        )
                    )
            # No discourse row is the canonical persisted form of
            # ``uncategorized``; the UI supplies that fallback label.

    if row.get("classification_status") != "succeeded":
        for brand in brands:
            if not isinstance(brand, dict):
                continue
            brand_id = brand.get("brand_id")
            if not isinstance(brand_id, str) or not brand_id:
                continue
            if row.get("schema_profile") == "stage1":
                summary, _unused_reasons = _stage1_brand_health(
                    brand, brand_id=brand_id
                )
            else:
                summary = _legacy_brand_summary(brand)
            brand_classifications.append({"brand_id": brand_id, **summary})

    if reasons:
        state = "unhealthy"
    elif "pending" in {translation_status, classification_status}:
        state = "pending"
    else:
        state = "complete"
    return {
        "tweet_id": tweet_id,
        "fetched_at": row.get("fetched_at"),
        "state": state,
        "translation_status": translation_status,
        "classification_status": classification_status,
        "lang_detected": row.get("lang_detected"),
        "has_text_zh_cn": bool(row.get("has_text_zh_cn")),
        "has_commentary_en": bool(row.get("has_commentary_en")),
        "has_commentary_zh_cn": bool(row.get("has_commentary_zh_cn")),
        "brand_count": len(brands),
        "brand_classifications": brand_classifications,
        "reasons": reasons,
    }


def _missing_post(tweet_id: str) -> dict[str, Any]:
    return {
        "tweet_id": tweet_id,
        "state": "unhealthy",
        "translation_status": "missing",
        "classification_status": "missing",
        "lang_detected": None,
        "has_text_zh_cn": False,
        "has_commentary_en": False,
        "has_commentary_zh_cn": False,
        "brand_count": 0,
        "reasons": [_reason("persistence", "missing_post")],
    }


def _error_payload(error_class: str, code: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "error",
        "error": {"class": error_class, "code": code},
    }


def _rate_metric(
    numerator: int, denominator: int, *, threshold: float, empty_passes: bool = False
) -> dict[str, Any]:
    rate = None if denominator == 0 else round(numerator / denominator, 6)
    passed = empty_passes if rate is None else rate >= threshold
    return {
        "numerator": numerator,
        "denominator": denominator,
        "rate": rate,
        "percentage": None if rate is None else round(rate * 100, 4),
        "threshold": threshold,
        "passed": passed,
    }


def _acceptance_metrics(posts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Calculate the explicit latest-N enrichment completeness contract."""
    total = len(posts)
    with_language = [
        post
        for post in posts
        if isinstance(post.get("lang_detected"), str)
        and post["lang_detected"].strip() in _CANONICAL_LANG_CODES
    ]
    non_zh_hans = [
        post for post in with_language if post["lang_detected"].strip() != "zh-Hans"
    ]
    language = _rate_metric(len(with_language), total, threshold=1.0)
    translation = _rate_metric(
        sum(bool(post.get("has_text_zh_cn")) for post in non_zh_hans),
        len(non_zh_hans),
        threshold=0.99,
        empty_passes=True,
    )
    commentary_en = _rate_metric(
        sum(bool(post.get("has_commentary_en")) for post in posts),
        total,
        threshold=0.99,
    )
    commentary_zh_cn = _rate_metric(
        sum(bool(post.get("has_commentary_zh_cn")) for post in posts),
        total,
        threshold=0.99,
    )
    metrics = {
        "lang_detected_present": language,
        "non_zh_hans_text_zh_cn": translation,
        "commentary_en": commentary_en,
        "commentary_zh_cn": commentary_zh_cn,
    }
    metrics["passed"] = total > 0 and all(
        metric["passed"] for metric in metrics.values()
    )
    return metrics


def evaluate_snapshot(
    snapshot: dict[str, Any],
    *,
    latest: int | None,
    requested_ids: Sequence[str] | None,
    grace_hours: int,
) -> tuple[dict[str, Any], int]:
    if snapshot.get("transaction_read_only") != "on":
        return _error_payload("query", "transaction_not_read_only"), 2
    schema_profile = snapshot.get("schema_profile", "legacy")
    if schema_profile == "partial":
        return _error_payload("query", "stage1_schema_partial"), 2
    if schema_profile not in {"legacy", "stage1"}:
        return _error_payload("query", "snapshot_invalid"), 2
    rows = snapshot.get("posts")
    if not isinstance(rows, list):
        return _error_payload("query", "snapshot_invalid"), 2

    returned_tweet_ids = [
        str(row.get("tweet_id") or "") for row in rows if isinstance(row, dict)
    ]
    evaluated_by_id = {
        post["tweet_id"]: post
        for post in (
            _evaluate_post(
                {**row, "schema_profile": schema_profile}, grace_hours=grace_hours
            )
            for row in rows
            if isinstance(row, dict)
        )
    }
    if requested_ids is not None:
        cohort_tweet_ids = list(requested_ids)
        posts = [
            evaluated_by_id.get(tweet_id, _missing_post(tweet_id))
            for tweet_id in cohort_tweet_ids
        ]
        missing_tweet_ids = [
            tweet_id for tweet_id in cohort_tweet_ids if tweet_id not in evaluated_by_id
        ]
        mode = "exact"
    else:
        cohort_tweet_ids = returned_tweet_ids
        posts = [evaluated_by_id[tweet_id] for tweet_id in cohort_tweet_ids]
        missing_tweet_ids = []
        mode = "latest"

    summary = {
        "total": len(posts),
        "complete": sum(post["state"] == "complete" for post in posts),
        "pending": sum(post["state"] == "pending" for post in posts),
        "unhealthy": sum(post["state"] == "unhealthy" for post in posts),
    }
    acceptance = _acceptance_metrics(posts)
    acceptance_gate = "complete" if acceptance["passed"] else "failed"
    unhealthy = summary["total"] == 0 or summary["unhealthy"] > 0
    if unhealthy:
        status = "unhealthy"
        regression_gate = "failed"
    elif summary["pending"]:
        status = "healthy_with_pending"
        regression_gate = "inconclusive"
    else:
        status = "healthy"
        regression_gate = "complete"
    payload = {
        "schema_version": 1,
        "status": status,
        "regression_gate": regression_gate,
        "acceptance_gate": acceptance_gate,
        "acceptance": acceptance,
        "mode": mode,
        "database_resource": DATABASE_RESOURCE,
        "latest_limit": latest,
        "grace_hours": grace_hours,
        "transaction_read_only": True,
        "schema_profile": schema_profile,
        "summary": summary,
        "cohort_tweet_ids": cohort_tweet_ids,
        "returned_tweet_ids": returned_tweet_ids,
        "missing_tweet_ids": missing_tweet_ids,
        "posts": posts,
    }
    return payload, 1 if unhealthy or not acceptance["passed"] else 0


def _render_human(payload: dict[str, Any]) -> str:
    if payload.get("status") == "error":
        error = payload["error"]
        return f"harvester-health error class={error['class']} code={error['code']}"
    summary = payload["summary"]
    lines = [
        (
            "harvester-health "
            f"status={payload['status']} "
            f"schema_profile={payload.get('schema_profile', 'legacy')} "
            f"regression_gate={payload['regression_gate']} "
            f"acceptance_gate={payload['acceptance_gate']} "
            f"mode={payload['mode']} "
            f"grace_hours={payload['grace_hours']} "
            f"total={summary['total']} "
            f"complete={summary['complete']} "
            f"pending={summary['pending']} "
            f"unhealthy={summary['unhealthy']}"
        )
    ]
    acceptance = payload["acceptance"]
    metric_names = (
        "lang_detected_present",
        "non_zh_hans_text_zh_cn",
        "commentary_en",
        "commentary_zh_cn",
    )
    lines.append(
        "acceptance "
        + " ".join(
            (
                f"{name}={acceptance[name]['numerator']}/"
                f"{acceptance[name]['denominator']}"
                f"({acceptance[name]['percentage']}%)"
                if acceptance[name]["percentage"] is not None
                else (
                    f"{name}={acceptance[name]['numerator']}/"
                    f"{acceptance[name]['denominator']}(n/a)"
                )
            )
            for name in metric_names
        )
    )
    for post in payload["posts"]:
        reason_text = (
            ",".join(
                ":".join(
                    part
                    for part in (
                        reason["stage"],
                        reason["reason"],
                        reason.get("brand_id"),
                        reason.get("error_code"),
                    )
                    if part
                )
                for reason in post["reasons"]
            )
            or "-"
        )
        lines.append(
            f"tweet={post['tweet_id']} "
            f"state={post['state']} "
            f"translation={post['translation_status']} "
            f"classification={post['classification_status']} "
            f"brands={post['brand_count']} "
            f"reasons={reason_text}"
        )
    return "\n".join(lines)


def _load_report_config(repo_root: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        raise HealthCheckError("configuration", "config_invalid") from None
    try:
        data = yaml.safe_load((repo_root / "config.yaml").read_text()) or {}
    except (OSError, TypeError, ValueError, yaml.YAMLError):
        raise HealthCheckError("configuration", "config_invalid") from None
    if not isinstance(data, dict):
        raise HealthCheckError("configuration", "config_invalid")
    return data


def _prompt_builders(
    repo_root: Path,
) -> tuple[Callable[..., str], Callable[..., str], Callable[[int], int]]:
    inserted = str(repo_root) not in sys.path
    if inserted:
        sys.path.insert(0, str(repo_root))
    try:
        from x_monitor.attribution import build_batch_pragmatics_full_prompt
        from x_monitor.translator import (
            _max_tokens_for_batch_size,
            build_pragmatics_translation_prompt,
        )
    except (ImportError, OSError):
        raise HealthCheckError("report", "prompt_reconstruction_failed") from None
    finally:
        if inserted:
            try:
                sys.path.remove(str(repo_root))
            except ValueError:
                pass
    return (
        build_pragmatics_translation_prompt,
        build_batch_pragmatics_full_prompt,
        _max_tokens_for_batch_size,
    )


def build_request_reconstructions(
    rows: Sequence[dict[str, Any]],
    *,
    repo_root: Path,
    config_data: dict[str, Any] | None = None,
    prompt_builders: tuple[
        Callable[..., str], Callable[..., str], Callable[[int], int]
    ]
    | None = None,
) -> list[dict[str, Any]]:
    """Reconstruct current-code request kwargs without creating a client."""

    data = config_data if config_data is not None else _load_report_config(repo_root)
    llm = data.get("llm") if isinstance(data, dict) else None
    if not isinstance(llm, dict):
        raise HealthCheckError("configuration", "config_invalid")
    translator_model = llm.get("translator_model")
    classifier_model = llm.get("classifier_model")
    if not isinstance(translator_model, str) or not isinstance(
        classifier_model, str
    ):
        raise HealthCheckError("configuration", "config_invalid")

    if prompt_builders is None:
        prompt_builders = _prompt_builders(repo_root)
    translation_builder, classification_builder, translation_max_tokens_for = (
        prompt_builders
    )

    tweets: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tweet_id = str(row.get("tweet_id") or "")
        source_text = row.get("text")
        if not tweet_id or not isinstance(source_text, str) or not source_text:
            continue
        brands = row.get("brands") if isinstance(row.get("brands"), list) else []
        brand_ids = [
            brand["brand_id"]
            for brand in brands
            if isinstance(brand, dict)
            and isinstance(brand.get("brand_id"), str)
            and brand.get("brand_id")
        ]
        tweets.append(
            {"tweet_id": tweet_id, "text": source_text, "brand_ids": brand_ids}
        )

    calls: list[dict[str, Any]] = []
    for start in range(0, len(tweets), LLM_BATCH_SIZE):
        batch = tweets[start : start + LLM_BATCH_SIZE]
        batch_index = start // LLM_BATCH_SIZE + 1
        try:
            translation_prompt = translation_builder(batch, ["en", "zh_cn"])
        except Exception:  # noqa: BLE001 - sanitize the prompt-builder boundary
            raise HealthCheckError(
                "report", "prompt_reconstruction_failed"
            ) from None
        translation_max_tokens = translation_max_tokens_for(len(batch))
        calls.append(
            {
                "stage": "translation",
                "historical_wire_call": False,
                "evidence_class": "current_code_reconstruction",
                "batch_index": batch_index,
                "tweet_ids": [tweet["tweet_id"] for tweet in batch],
                "call_site": (
                    "monitor.cycle.CycleRunner._run_post_fetch -> "
                    "x_monitor.translator.translate_batch_pragmatics"
                ),
                "known_request_kwargs": {
                    "model": translator_model,
                    "max_tokens": translation_max_tokens,
                    "messages": [{"role": "user", "content": translation_prompt}],
                },
                "runtime_only_kwargs": {
                    "thinking": {
                        "status": "unavailable",
                        "reason": (
                            "resolved from production role-specific environment at "
                            "call time and not persisted"
                        ),
                    }
                },
            }
        )

        kept = [tweet for tweet in batch if tweet["brand_ids"]]
        if not kept:
            continue
        try:
            classification_prompt = classification_builder(kept)
        except Exception:  # noqa: BLE001 - sanitize the prompt-builder boundary
            raise HealthCheckError(
                "report", "prompt_reconstruction_failed"
            ) from None
        calls.append(
            {
                "stage": "classification",
                "historical_wire_call": False,
                "evidence_class": "current_code_reconstruction",
                "batch_index": batch_index,
                "tweet_ids": [tweet["tweet_id"] for tweet in kept],
                "call_site": (
                    "monitor.cycle.CycleRunner._run_post_fetch -> "
                    "x_monitor.attribution.classify_batch_pragmatics_full"
                ),
                "known_request_kwargs": {
                    "model": classifier_model,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": classification_prompt}],
                },
                "runtime_only_kwargs": {
                    "thinking": {
                        "status": "unavailable",
                        "reason": (
                            "resolved from production classifier environment at call "
                            "time and not persisted"
                        ),
                    }
                },
            }
        )
    return calls


def _code_block(language: str, value: str) -> str:
    longest_run = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest_run + 1)
    return f"{fence}{language}\n{value.rstrip()}\n{fence}"


def _json_block(value: Any) -> str:
    return _code_block(
        "json", json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
    )


def _markdown_cell(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _table(rows: Sequence[tuple[Any, Any]]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    lines.extend(
        f"| {_markdown_cell(key)} | {_markdown_cell(value)} |" for key, value in rows
    )
    return "\n".join(lines)


def _post_report_section(
    row: dict[str, Any], health: dict[str, Any], ordinal: int
) -> str:
    tweet_id = str(row.get("tweet_id") or "")
    metadata = _table(
        [
            ("Health state", health.get("state")),
            ("Translation status", health.get("translation_status")),
            ("Classification status", health.get("classification_status")),
            ("Author", row.get("author_handle")),
            ("Author ID", row.get("author_id")),
            ("Source query", row.get("source_query_id")),
            ("Tweet created", row.get("created_at")),
            ("Fetched", row.get("fetched_at")),
            ("Tweet URL", row.get("tweet_url")),
            ("Source language", row.get("lang")),
            ("Detected language", row.get("lang_detected")),
            ("Likes", row.get("like_count")),
            ("Reposts", row.get("retweet_count")),
            ("Replies", row.get("reply_count")),
            ("Quotes", row.get("quote_count")),
            ("Views", row.get("view_count")),
            ("Metrics refreshed", row.get("metrics_refreshed_at")),
        ]
    )
    enrichment = _table(
        [
            ("Translation attempts", row.get("translation_attempts")),
            ("Translation first attempt", row.get("translation_first_attempt_at")),
            ("Translation last attempt", row.get("translation_last_attempt_at")),
            ("Translation next attempt", row.get("translation_next_attempt_at")),
            ("Translation error code", row.get("translation_error_code")),
            ("Classification attempts", row.get("classification_attempts")),
            (
                "Classification first attempt",
                row.get("classification_first_attempt_at"),
            ),
            (
                "Classification last attempt",
                row.get("classification_last_attempt_at"),
            ),
            (
                "Classification next attempt",
                row.get("classification_next_attempt_at"),
            ),
            ("Classification error code", row.get("classification_error_code")),
            ("State created", row.get("enrichment_created_at")),
            ("State updated", row.get("enrichment_updated_at")),
        ]
    )

    parts = [
        f"## Post {ordinal}: `{tweet_id}`",
        "",
        metadata,
        "",
        "### Health findings",
        "",
        _json_block(health.get("reasons") or []),
        "",
        "### Full source text",
        "",
        _code_block("text", str(row.get("text") or "")),
        "",
        "### Persisted translations and commentary",
        "",
        "English translation:",
        "",
        _code_block("text", str(row.get("text_en") or "")),
        "",
        "Simplified Chinese translation:",
        "",
        _code_block("text", str(row.get("text_zh_cn") or "")),
        "",
        "English commentary:",
        "",
        _code_block("text", str(row.get("commentary_en") or "")),
        "",
        "Simplified Chinese commentary:",
        "",
        _code_block("text", str(row.get("commentary_zh_cn") or "")),
        "",
        "### Durable enrichment state",
        "",
        enrichment,
        "",
        "### Per-brand findings",
        "",
    ]
    brands = row.get("brands") if isinstance(row.get("brands"), list) else []
    if not brands:
        parts.append("No persisted brand rows.")
    for brand in brands:
        if not isinstance(brand, dict):
            continue
        parts.extend(
            [
                f"#### `{brand.get('brand_id') or 'missing-brand-id'}`",
                "",
                _table([("Weight", brand.get("weight"))]),
                "",
                "Mentions:",
                "",
                _json_block(brand.get("mentions") or []),
                "",
                "Post types and sentiment:",
                "",
                _json_block(brand.get("signals") or []),
                "",
                "Stage 1 classification state and prompt provenance:",
                "",
                _json_block(brand.get("classification_state")),
                "",
                "Product labels:",
                "",
                _json_block(brand.get("product_labels") or []),
                "",
                "Historical scalar fallback evidence:",
                "",
                _json_block(
                    {
                        "sentiments": brand.get("legacy_sentiments") or [],
                        "china_nationalisms": (
                            brand.get("legacy_china_nationalisms") or []
                        ),
                        "us_nationalisms": (
                            brand.get("legacy_us_nationalisms") or []
                        ),
                    }
                ),
                "",
                "Historical discourse evidence:",
                "",
                _json_block(brand.get("discourses") or []),
                "",
            ]
        )
    parts.extend(
        [
            "### Unsanctioned-flag evidence",
            "",
            _json_block(row.get("unsanctioned_flags")),
        ]
    )
    return "\n".join(parts)


def _missing_post_report_section(
    tweet_id: str, health: dict[str, Any], ordinal: int
) -> str:
    return "\n".join(
        [
            f"## Post {ordinal}: `{tweet_id}`",
            "",
            _table(
                [
                    ("Health state", health.get("state")),
                    ("Translation status", health.get("translation_status")),
                    ("Classification status", health.get("classification_status")),
                ]
            ),
            "",
            "### Health findings",
            "",
            _json_block(health.get("reasons") or []),
            "",
            (
                "No persisted post row was returned for this requested exact-cohort "
                "tweet ID, so source, translation, enrichment, brand, discourse, "
                "and flag evidence is unavailable."
            ),
        ]
    )


def render_detailed_report(
    snapshot: dict[str, Any],
    payload: dict[str, Any],
    *,
    sql: str,
    invocation: str,
    generated_at: datetime,
    repo_root: Path,
    request_reconstructions: Sequence[dict[str, Any]],
    script_source: str,
    script_sha256: str,
    repo_commit: str,
    python_version: str,
) -> str:
    """Render a durable, full-detail Markdown evidence report."""

    summary = payload["summary"]
    rows = snapshot.get("posts") if isinstance(snapshot.get("posts"), list) else []
    health_by_id = {
        str(post.get("tweet_id") or ""): post
        for post in payload.get("posts", [])
        if isinstance(post, dict)
    }
    parts = [
        "---",
        "title: Harvester latest-N health report",
        f"generated_at: {generated_at.isoformat()}",
        f"database_resource: {DATABASE_RESOURCE}",
        f"cohort_mode: {payload.get('mode')}",
        f"cohort_size: {summary.get('total')}",
        f"status: {payload.get('status')}",
        "database_access: read-only",
        f"checker_source_sha256: {script_sha256}",
        f"repo_commit: {repo_commit}",
        "---",
        "",
        "# Harvester latest-N health report",
        "",
        (
            "This report captures one bounded snapshot of persisted production "
            "post-fetch health. It is a diagnostic artifact, not a harvest, "
            "repair, retry, re-enrichment, or provider probe."
        ),
        "",
        "## Summary",
        "",
        _table(
            [
                ("Overall status", payload.get("status")),
                ("Regression gate", payload.get("regression_gate")),
                ("Acceptance gate", payload.get("acceptance_gate")),
                ("Schema profile", payload.get("schema_profile")),
                ("Cohort mode", payload.get("mode")),
                ("Total posts", summary.get("total")),
                ("Complete", summary.get("complete")),
                ("Pending", summary.get("pending")),
                ("Unhealthy", summary.get("unhealthy")),
                ("Grace period (hours)", payload.get("grace_hours")),
                ("Transaction read-only", payload.get("transaction_read_only")),
            ]
        ),
        "",
        "Ordered cohort tweet IDs:",
        "",
        _json_block(payload.get("cohort_tweet_ids") or []),
        "",
        "Acceptance metrics:",
        "",
        _json_block(payload.get("acceptance") or {}),
        "",
        "## Methodology and safety",
        "",
        (
            "The checker made one `render psql` call to the configured production "
            "database resource. The selected cohort was bounded before related "
            "facts were joined. The transaction declared read-only mode, applied "
            "statement/lock/idle timeouts, detected the complete Stage 1 schema "
            "before planning any Stage 1 table reference, and returned the "
            "transaction mode in the same snapshot. No production row was mutated."
        ),
        "",
        "The checker did not run harvesting, call TwitterAPI, or create an LLM client.",
        "",
        "Invocation:",
        "",
        _code_block("shell", invocation),
        "",
        "## LLM call evidence",
        "",
        "### Calls made by this health checker",
        "",
        _json_block([]),
        "",
        "### Current-code LLM request reconstructions",
        "",
        (
            "The following entries contain the verbatim prompt strings produced "
            "by the current pure prompt builders for this selected cohort and the "
            "request kwargs deterministically known from source-controlled code. "
            "They are not historical wire evidence. Production does not persist "
            "historical prompt payloads, response payloads, retry count, original "
            "batch membership, or runtime-resolved `thinking`; unavailable values "
            "are labeled instead of inferred."
        ),
        "",
    ]
    if request_reconstructions:
        for call in request_reconstructions:
            parts.extend(
                [
                    (
                        f"#### {call.get('stage', 'unknown').title()} batch "
                        f"{call.get('batch_index', '?')}"
                    ),
                    "",
                    _json_block(call),
                    "",
                ]
            )
    else:
        parts.extend(
            [
                (
                    "No current-code request is reconstructed because the selected "
                    "cohort contains no non-empty source text eligible for enrichment."
                ),
                "",
            ]
        )

    rows_by_id = {
        str(row.get("tweet_id") or ""): row
        for row in rows
        if isinstance(row, dict)
    }
    parts.extend(["# Per-post evidence", ""])
    for ordinal, tweet_id_value in enumerate(payload.get("cohort_tweet_ids", []), 1):
        tweet_id = str(tweet_id_value)
        health = health_by_id.get(tweet_id, _missing_post(tweet_id))
        row = rows_by_id.get(tweet_id)
        if row is None:
            section = _missing_post_report_section(tweet_id, health, ordinal)
        else:
            section = _post_report_section(row, health, ordinal)
        parts.extend([section, ""])

    parts.extend(
        [
            "# Reproducibility appendix",
            "",
            "## Exact read-only SQL",
            "",
            _code_block("sql", sql),
            "",
            "## Checker implementation",
            "",
            _table(
                [
                    (
                        "Checker path",
                        ".claude/skills/harvester-latest-n-health-check/scripts/check.py",
                    ),
                    ("Checker file-content SHA-256", script_sha256),
                    ("Repository commit", repo_commit),
                    ("Python version", python_version),
                    ("Repository root", repo_root),
                ]
            ),
            "",
            (
                "The complete checker source used to render this artifact follows. "
                "It includes cohort selection, health rules, SQL, request "
                "reconstruction, report rendering, atomic write behavior, and "
                "stable error handling."
            ),
            "",
            _code_block("python", script_source),
            "",
        ]
    )
    return "\n".join(parts)


def write_report_atomic(
    report: str, *, repo_root: Path, generated_at: datetime
) -> Path:
    report_dir = repo_root / REPORT_RELATIVE_DIR
    filename = (
        generated_at.strftime("%Y-%m-%d-%H%M%S")
        + "-harvester-latest-n-health-report.md"
    )
    target = report_dir / filename
    temporary: Path | None = None
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=report_dir,
            prefix=".harvester-report-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(report)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise HealthCheckError("report", "report_write_failed") from None
    return target


def _repo_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    value = result.stdout.strip()
    return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value) else "unavailable"


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    as_json = "--json" in raw_argv
    report_path: Path | None = None
    try:
        args = parse_args(raw_argv)
        configured_grace_hours = load_grace_hours()
        if args.grace_hours is not None and args.grace_hours > configured_grace_hours:
            raise HealthCheckError("invocation", "invalid_arguments")
        grace_hours = (
            args.grace_hours if args.grace_hours is not None else configured_grace_hours
        )
        sql = build_query(
            latest=args.latest,
            tweet_ids=args.tweet_ids,
            detailed=args.report,
        )
        snapshot = execute_query(sql, runner=runner)
        payload, exit_code = evaluate_snapshot(
            snapshot,
            latest=args.latest,
            requested_ids=args.tweet_ids,
            grace_hours=grace_hours,
        )
        if args.report and exit_code in {0, 1}:
            try:
                repo_root = Path(__file__).resolve().parents[4]
                script_path = Path(__file__).resolve()
                script_source = script_path.read_text()
                generated_at = datetime.now().astimezone()
                request_reconstructions = build_request_reconstructions(
                    snapshot["posts"], repo_root=repo_root
                )
                report = render_detailed_report(
                    snapshot,
                    payload,
                    sql=sql,
                    invocation=shlex.join(
                        [sys.executable, str(script_path), *raw_argv]
                    ),
                    generated_at=generated_at,
                    repo_root=repo_root,
                    request_reconstructions=request_reconstructions,
                    script_source=script_source,
                    script_sha256=hashlib.sha256(script_source.encode()).hexdigest(),
                    repo_commit=_repo_commit(repo_root),
                    python_version=sys.version.replace("\n", " "),
                )
                report_path = write_report_atomic(
                    report, repo_root=repo_root, generated_at=generated_at
                )
            except HealthCheckError:
                raise
            except OSError:
                raise HealthCheckError(
                    "report", "checker_source_unavailable"
                ) from None
            except Exception:  # noqa: BLE001 - sanitize the report boundary
                raise HealthCheckError("report", "report_generation_failed") from None
    except HealthCheckError as exc:
        payload = _error_payload(exc.error_class, exc.code)
        exit_code = 2

    if as_json:
        stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        target = stderr if exit_code == 2 else stdout
        target.write(_render_human(payload) + "\n")
        if report_path is not None:
            target.write(f"report={report_path}\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
