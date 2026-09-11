"""Deterministic, offline scoring for held-out Stage 1 classifications.

The evaluator compares a provenance-bearing candidate artifact with an
independently adjudicated gold artifact.  It deliberately has no database,
provider, or sampling dependency: the cohort is fixed by the two input
artifacts and rows are paired by ``(example_id, brand_id)``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    CANONICAL_PROMPT_VERSION,
    CANONICAL_TAXONOMY_VERSION,
    CLASSIFICATION_FIELDS,
    CONTRACT_VERSION,
    NATIONALISM_KEYS,
    PRODUCT_LABEL_KEYS,
    SENTIMENT_KEYS,
    STAGE1_PROMPT_V3_VERSION,
    STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
    STAGE1_TAXONOMY_V2_VERSION,
    parse_stage1_classifications,
)

EVALUATION_SCHEMA_VERSION = "classification-evaluation/v1"
ARTIFACT_SCHEMA_VERSION = 1
REQUIRED_LANGUAGES = ("en", "zh-cn", "ja")
CONTEXT_KEYS = ("stored_quote", "local_parent")
REQUIRED_CONTEXTS = ("none", *CONTEXT_KEYS)
UNKNOWN = "unknown"
_FULL_REVISION = re.compile(r"^[0-9a-f]{40}$")
_FULL_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_SCALAR_VALUES = {
    "outcome": ("classified", "context_missing"),
    "sentiment": SENTIMENT_KEYS,
    "china_nationalism": ("none", UNKNOWN),
    "us_nationalism": ("none", UNKNOWN),
}
REQUIRED_SLICE_FLOOR_SUFFIXES = (
    "post_types.exact_set_accuracy.value",
    "product_labels.exact_set_accuracy.value",
    "outcome.accuracy",
    "sentiment.accuracy",
)
REQUIRED_FLOOR_PATHS = frozenset(
    {
        "all.post_types.exact_set_accuracy.value",
        "all.post_types.micro.f1",
        "all.product_labels.empty_set_accuracy.value",
        "all.product_labels.exact_set_accuracy.value",
        "all.product_labels.micro.f1",
        "all.outcome.accuracy",
        "all.sentiment.accuracy",
        "all.china_nationalism.accuracy",
        "all.us_nationalism.accuracy",
        *(
            f"all.post_types.labels.{label}.f1"
            for label in STAGE1_TAXONOMY_V2_POST_TYPE_KEYS
        ),
        *(f"all.product_labels.labels.{label}.f1" for label in PRODUCT_LABEL_KEYS),
        *(
            f"all.{dimension}.classes.{value}.recall"
            for dimension, values in REQUIRED_SCALAR_VALUES.items()
            for value in values
        ),
        *(
            f"by_language.{language}.{suffix}"
            for language in REQUIRED_LANGUAGES
            for suffix in REQUIRED_SLICE_FLOOR_SUFFIXES
        ),
        *(
            f"by_context.{context}.{suffix}"
            for context in REQUIRED_CONTEXTS
            for suffix in REQUIRED_SLICE_FLOOR_SUFFIXES
        ),
    }
)

SUPPORTED_TAXONOMIES = {
    STAGE1_TAXONOMY_V2_VERSION: {
        "prompt_version": STAGE1_PROMPT_V3_VERSION,
        "post_type_keys": STAGE1_TAXONOMY_V2_POST_TYPE_KEYS,
    },
    CANONICAL_TAXONOMY_VERSION: {
        "prompt_version": CANONICAL_PROMPT_VERSION,
        "post_type_keys": CANONICAL_POST_TYPE_KEYS,
    },
}


def required_floor_paths(
    required_contexts: Sequence[str],
    taxonomy_version: str = STAGE1_TAXONOMY_V2_VERSION,
) -> frozenset[str]:
    """Return mandatory paths, including any optional exact context slices."""
    taxonomy = SUPPORTED_TAXONOMIES.get(taxonomy_version)
    if taxonomy is None:
        raise ValueError(f"unsupported evaluation taxonomy: {taxonomy_version}")
    paths = REQUIRED_FLOOR_PATHS
    if taxonomy_version != STAGE1_TAXONOMY_V2_VERSION:
        paths = frozenset(
            path
            for path in REQUIRED_FLOOR_PATHS
            if not path.startswith("all.post_types.labels.")
        ) | frozenset(
            f"all.post_types.labels.{label}.f1"
            for label in taxonomy["post_type_keys"]
        )
    return paths | frozenset(
        f"by_context.{context}.{suffix}"
        for context in required_contexts
        for suffix in REQUIRED_SLICE_FLOOR_SUFFIXES
    )


class EvaluationInputError(ValueError):
    """Input is malformed, untrusted, or cannot support a score."""

    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field

    def as_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": str(self)}
        if self.field is not None:
            result["field"] = self.field
        return result


def safe_error_document(error: EvaluationInputError) -> dict[str, Any]:
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "status": "error",
        "error": error.as_dict(),
    }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _resolve_source_identity() -> dict[str, Any]:
    """Resolve local or Render identity without importing Django settings."""

    deployed = os.environ.get("RENDER_GIT_COMMIT", "").strip().lower()
    if deployed:
        if _FULL_REVISION.fullmatch(deployed):
            return {
                "source_revision": deployed,
                "source_revision_kind": "render_deploy",
                "source_worktree_dirty": False,
            }
        return {
            "source_revision": "unavailable",
            "source_revision_kind": "invalid_render_environment",
            "source_worktree_dirty": None,
        }

    root = Path(__file__).resolve().parents[1]
    try:
        repository_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        if Path(repository_root).resolve() != root.resolve():
            return {
                "source_revision": "unavailable",
                "source_revision_kind": "parent_git_repository_ignored",
                "source_worktree_dirty": None,
            }
        revision = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
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
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {
            "source_revision": "unavailable",
            "source_revision_kind": "unavailable",
            "source_worktree_dirty": None,
        }
    if not _FULL_REVISION.fullmatch(revision):
        return {
            "source_revision": "unavailable",
            "source_revision_kind": "invalid_local_git_revision",
            "source_worktree_dirty": None,
        }
    return {
        "source_revision": revision,
        "source_revision_kind": "local_git_head",
        "source_worktree_dirty": bool(status.strip()),
    }


def _normalize_source_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "source_revision",
        "source_revision_kind",
        "source_worktree_dirty",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise EvaluationInputError(
            "identity_invalid",
            "source identity must contain only revision, revision kind, and dirty state",
            field="source_identity",
        )
    revision = value["source_revision"]
    kind = value["source_revision_kind"]
    dirty = value["source_worktree_dirty"]
    if revision != "unavailable" and (
        not isinstance(revision, str) or not _FULL_REVISION.fullmatch(revision)
    ):
        raise EvaluationInputError(
            "identity_invalid",
            "source identity revision must be a full 40-hex Git revision or unavailable",
            field="source_identity.source_revision",
        )
    allowed_kinds = {
        "local_git_head",
        "render_deploy",
        "unavailable",
        "invalid_render_environment",
        "invalid_local_git_revision",
        "parent_git_repository_ignored",
    }
    if kind not in allowed_kinds:
        raise EvaluationInputError(
            "identity_invalid",
            "source identity revision kind is unknown",
            field="source_identity.source_revision_kind",
        )
    if dirty is not None and not isinstance(dirty, bool):
        raise EvaluationInputError(
            "identity_invalid",
            "source identity dirty state must be true, false, or null",
            field="source_identity.source_worktree_dirty",
        )
    if revision == "unavailable" and kind in {"local_git_head", "render_deploy"}:
        raise EvaluationInputError(
            "identity_invalid",
            "available source identity kind requires a Git revision",
            field="source_identity",
        )
    if revision != "unavailable" and kind not in {"local_git_head", "render_deploy"}:
        raise EvaluationInputError(
            "identity_invalid",
            "Git revision requires a local or Render source identity kind",
            field="source_identity",
        )
    return {
        "source_revision": revision,
        "source_revision_kind": kind,
        "source_worktree_dirty": dirty,
    }


def _artifact_digest(value: str | None, document: Mapping[str, Any]) -> str:
    digest = value or _sha256(document)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise EvaluationInputError(
            "identity_invalid",
            "artifact digest must use sha256 followed by 64 lowercase hex characters",
            field="artifact_digest",
        )
    return digest


def _read_json(path: str | Path) -> tuple[dict[str, Any], str]:
    path = Path(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationInputError(
            "artifact_unreadable", f"could not read evaluation artifact: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise EvaluationInputError(
            "artifact_invalid", "evaluation artifact must be an object"
        )
    return value, _sha256_bytes(raw)


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationInputError(
            "artifact_invalid", f"{field} must be a nonblank string", field=field
        )
    return value.strip()


def _utc_timestamp(value: Any, field: str) -> str:
    text = _require_text(value, field)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EvaluationInputError(
            "provenance_invalid",
            f"{field} must be an ISO-8601 UTC timestamp",
            field=field,
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise EvaluationInputError(
            "provenance_invalid",
            f"{field} must be an ISO-8601 UTC timestamp",
            field=field,
        )
    return text


def _language(value: Any, field: str) -> str:
    raw = _require_text(value, field).casefold().replace("_", "-")
    aliases = {"zh-hans": "zh-cn", "zh-cn": "zh-cn", "zh": "zh-cn"}
    normalized = aliases.get(raw, raw)
    if normalized not in REQUIRED_LANGUAGES:
        raise EvaluationInputError(
            "unsupported_language",
            f"unsupported source language: {value!r}",
            field=field,
        )
    return normalized


def _context(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(item not in CONTEXT_KEYS for item in value):
        raise EvaluationInputError(
            "artifact_invalid",
            f"{field} must contain only known context provenance",
            field=field,
        )
    if len(set(value)) != len(value):
        raise EvaluationInputError(
            "artifact_invalid", f"{field} must not contain duplicates", field=field
        )
    return tuple(key for key in CONTEXT_KEYS if key in value)


def _validate_provenance(document: Mapping[str, Any], role: str) -> dict[str, Any]:
    provenance = document.get("provenance")
    if not isinstance(provenance, Mapping):
        raise EvaluationInputError(
            "provenance_missing",
            f"{role} artifact provenance is required",
            field="provenance",
        )
    if provenance.get("kind") != (
        "candidate_output" if role == "candidate" else "heldout_gold"
    ):
        raise EvaluationInputError(
            "provenance_invalid",
            f"{role} artifact has invalid provenance kind",
            field="provenance.kind",
        )
    if provenance.get("gold") is not (role == "gold"):
        raise EvaluationInputError(
            "provenance_invalid",
            f"{role} artifact has invalid gold marker",
            field="provenance.gold",
        )
    required = ["cohort_id", "contract_version", "taxonomy_version", "prompt_version"]
    if role == "candidate":
        required += ["model", "source_revision", "generated_at"]
    else:
        required += ["adjudicator", "adjudication_version", "adjudicated_at"]
    for field in required:
        _require_text(provenance.get(field), f"provenance.{field}")
    taxonomy = SUPPORTED_TAXONOMIES.get(provenance["taxonomy_version"])
    if provenance["contract_version"] != CONTRACT_VERSION or taxonomy is None:
        raise EvaluationInputError(
            "unsupported_contract",
            f"{role} artifact must use the frozen Stage 1 contract and taxonomy",
            field="provenance",
        )
    if provenance["prompt_version"] != taxonomy["prompt_version"]:
        raise EvaluationInputError(
            "unsupported_prompt",
            f"{role} artifact must use the frozen Stage 1 prompt",
            field="provenance.prompt_version",
        )
    if role == "candidate" and not _FULL_REVISION.fullmatch(
        provenance["source_revision"].lower()
    ):
        raise EvaluationInputError(
            "provenance_invalid",
            "candidate source_revision must be a full 40-hex Git revision",
            field="provenance.source_revision",
        )
    if role == "candidate":
        _utc_timestamp(provenance["generated_at"], "provenance.generated_at")
    if role == "gold":
        annotators = provenance.get("annotators")
        if (
            not isinstance(annotators, list)
            or len(annotators) < 2
            or any(not isinstance(item, str) or not item.strip() for item in annotators)
            or len(set(annotators)) != len(annotators)
        ):
            raise EvaluationInputError(
                "provenance_invalid",
                "gold requires at least two distinct annotator identities",
                field="provenance.annotators",
            )
        adjudicator = provenance["adjudicator"].strip()
        if adjudicator in {item.strip() for item in annotators}:
            raise EvaluationInputError(
                "provenance_invalid",
                "gold adjudicator must be independent from the two annotators",
                field="provenance.adjudicator",
            )
        if provenance.get("blind_to_candidate") is not True:
            raise EvaluationInputError(
                "provenance_invalid",
                "gold adjudication must be blind_to_candidate",
                field="provenance.blind_to_candidate",
            )
        _require_text(
            provenance.get("adjudication_method"), "provenance.adjudication_method"
        )
        _utc_timestamp(provenance["adjudicated_at"], "provenance.adjudicated_at")
    return dict(provenance)


def _validate_document(
    document: Mapping[str, Any], role: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if document.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise EvaluationInputError(
            "artifact_schema_unsupported",
            f"{role} artifact schema_version must be {ARTIFACT_SCHEMA_VERSION}",
            field="schema_version",
        )
    provenance = _validate_provenance(document, role)
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise EvaluationInputError(
            "artifact_invalid", f"{role} artifact rows must be an array", field="rows"
        )
    required = {
        "example_id",
        "brand_id",
        "source_language",
        "context_provenance",
        "input_context_fingerprint",
    }
    if role == "gold":
        required.add("classification")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or not required.issubset(row):
            raise EvaluationInputError(
                "artifact_invalid",
                f"{role} row {index} is incomplete",
                field=f"rows[{index}]",
            )
        example_id = _require_text(row["example_id"], f"rows[{index}].example_id")
        brand_id = _require_text(row["brand_id"], f"rows[{index}].brand_id")
        fingerprint = _require_text(
            row["input_context_fingerprint"],
            f"rows[{index}].input_context_fingerprint",
        ).lower()
        if not _FULL_FINGERPRINT.fullmatch(fingerprint):
            raise EvaluationInputError(
                "artifact_invalid",
                "input_context_fingerprint must be a 64-hex digest",
                field=f"rows[{index}].input_context_fingerprint",
            )
        pair = (example_id, brand_id)
        if pair in seen:
            raise EvaluationInputError(
                "duplicate_pair",
                f"duplicate {role} pair: {pair!r}",
                field=f"rows[{index}]",
            )
        seen.add(pair)
        result.append(
            {
                "example_id": example_id,
                "brand_id": brand_id,
                "source_language": _language(
                    row["source_language"], f"rows[{index}].source_language"
                ),
                "context_provenance": _context(
                    row["context_provenance"], f"rows[{index}].context_provenance"
                ),
                "input_context_fingerprint": fingerprint,
                "classification": row.get("classification"),
            }
        )
    return provenance, result


def _classification(
    raw: Any, brand_id: str, post_type_keys: Sequence[str]
) -> tuple[dict[str, Any] | None, str | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, Mapping):
        return None, "invalid_shape"
    row = dict(raw)
    if "brand_id" in row and row["brand_id"] != brand_id:
        return None, "brand_mismatch"
    row["brand_id"] = brand_id
    if set(row) != set(CLASSIFICATION_FIELDS):
        return None, "invalid_fields"
    parsed = parse_stage1_classifications(
        [row],
        [brand_id],
        post_type_keys=post_type_keys,
    )
    if parsed is None:
        return None, "invalid_contract"
    return parsed[brand_id], None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _classification_metric(
    counts: Mapping[str, tuple[int, int, int]],
) -> dict[str, Any]:
    labels: dict[str, Any] = {}
    for label in sorted(counts):
        tp, fp, fn = counts[label]
        labels[label] = {
            "support": tp + fn,
            "predicted_positive": tp + fp,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        }
    return labels


def _aggregate(labels: Mapping[str, Any], selected: Sequence[str]) -> dict[str, Any]:
    tp = sum(labels[label]["tp"] for label in selected)
    fp = sum(labels[label]["fp"] for label in selected)
    fn = sum(labels[label]["fn"] for label in selected)
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return {
        "labels": list(selected),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": _ratio(2 * tp, 2 * tp + fp + fn),
    }


def _multilabel(
    pairs: Sequence[tuple[set[str], set[str]]],
    vocabulary: Sequence[str],
    min_support: int,
) -> dict[str, Any]:
    counts: dict[str, list[int]] = {label: [0, 0, 0] for label in vocabulary}
    exact = 0
    jaccard_sum = 0.0
    empty_confusion = {
        "gold_empty": {"candidate_empty": 0, "candidate_nonempty": 0},
        "gold_nonempty": {"candidate_empty": 0, "candidate_nonempty": 0},
    }
    gold_empty = 0
    empty_exact = 0
    for gold, candidate in pairs:
        exact += gold == candidate
        union = gold | candidate
        jaccard_sum += 1.0 if not union else len(gold & candidate) / len(union)
        gold_key = "gold_empty" if not gold else "gold_nonempty"
        candidate_key = "candidate_empty" if not candidate else "candidate_nonempty"
        empty_confusion[gold_key][candidate_key] += 1
        gold_empty += not gold
        empty_exact += not gold and not candidate
        for label in vocabulary:
            counts[label][0] += label in gold and label in candidate
            counts[label][1] += label not in gold and label in candidate
            counts[label][2] += label in gold and label not in candidate
    frozen = {label: tuple(values) for label, values in counts.items()}
    labels = _classification_metric(frozen)
    supported = [
        label
        for label in vocabulary
        if labels[label]["support"] > 0 and labels[label]["support"] >= min_support
    ]
    return {
        "scored_pairs": len(pairs),
        "labels": labels,
        "exact_set_accuracy": {
            "correct": exact,
            "denominator": len(pairs),
            "value": _ratio(exact, len(pairs)),
        },
        "jaccard": {
            "sum": jaccard_sum,
            "denominator": len(pairs),
            "value": _ratio(jaccard_sum, len(pairs)),
        },
        "empty_set_accuracy": {
            "correct": empty_exact,
            "denominator": gold_empty,
            "value": _ratio(empty_exact, gold_empty),
        },
        "empty_nonempty_confusion": empty_confusion,
        "support_threshold": min_support,
        "supported_labels": supported,
        "support_gaps": [
            label for label in vocabulary if labels[label]["support"] < min_support
        ],
        "micro": _aggregate(labels, list(vocabulary)),
        "micro_supported": _aggregate(labels, supported),
        "macro_supported": {
            "labels": supported,
            "precision": _ratio(
                sum(labels[label]["precision"] or 0.0 for label in supported),
                len(supported),
            ),
            "recall": _ratio(
                sum(labels[label]["recall"] or 0.0 for label in supported),
                len(supported),
            ),
            "f1": _ratio(
                sum(labels[label]["f1"] or 0.0 for label in supported), len(supported)
            ),
        },
    }


def _confusion(
    pairs: Sequence[tuple[str | None, str | None]],
    vocabulary: Sequence[str],
) -> dict[str, Any]:
    labels = [*vocabulary, UNKNOWN]
    matrix = {actual: {predicted: 0 for predicted in labels} for actual in labels}
    for gold, candidate in pairs:
        matrix[gold if gold is not None else UNKNOWN][
            candidate if candidate is not None else UNKNOWN
        ] += 1
    total = len(pairs)
    correct = sum(matrix[label][label] for label in labels)
    classes: dict[str, dict[str, Any]] = {}
    for label in labels:
        tp = matrix[label][label]
        fp = sum(matrix[actual][label] for actual in labels if actual != label)
        fn = sum(matrix[label][predicted] for predicted in labels if predicted != label)
        classes[label] = {
            "support": tp + fn,
            "predicted_positive": tp + fp,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": _ratio(tp, tp + fp),
            "recall": _ratio(tp, tp + fn),
            "f1": _ratio(2 * tp, 2 * tp + fp + fn),
        }
    return {
        "labels": labels,
        "matrix": matrix,
        "classes": classes,
        "correct": correct,
        "denominator": total,
        "accuracy": _ratio(correct, total),
        "support": {label: sum(matrix[label].values()) for label in labels},
        "none_unknown_errors": {
            "gold_none_candidate_unknown": matrix.get("none", {}).get(UNKNOWN, 0),
            "gold_unknown_candidate_none": matrix.get(UNKNOWN, {}).get("none", 0),
            "total": matrix.get("none", {}).get(UNKNOWN, 0)
            + matrix.get(UNKNOWN, {}).get("none", 0),
        },
    }


def _population(
    rows: Sequence[dict[str, Any]],
    min_support: int,
    post_type_keys: Sequence[str],
) -> dict[str, Any]:
    type_pairs = [
        (set(row["gold"]["post_types"]), set(row["candidate"]["post_types"]))
        for row in rows
    ]
    product_pairs = [
        (set(row["gold"]["product_labels"]), set(row["candidate"]["product_labels"]))
        for row in rows
    ]
    return {
        "post_types": _multilabel(
            type_pairs, post_type_keys, min_support
        ),
        "product_labels": _multilabel(product_pairs, PRODUCT_LABEL_KEYS, min_support),
        "outcome": _confusion(
            [(row["gold"]["outcome"], row["candidate"]["outcome"]) for row in rows],
            ("classified", "context_missing"),
        ),
        "sentiment": _confusion(
            [(row["gold"]["sentiment"], row["candidate"]["sentiment"]) for row in rows],
            SENTIMENT_KEYS,
        ),
        "china_nationalism": _confusion(
            [
                (
                    row["gold"]["china_nationalism"],
                    row["candidate"]["china_nationalism"],
                )
                for row in rows
            ],
            NATIONALISM_KEYS,
        ),
        "us_nationalism": _confusion(
            [
                (row["gold"]["us_nationalism"], row["candidate"]["us_nationalism"])
                for row in rows
            ],
            NATIONALISM_KEYS,
        ),
    }


def _gold_support(
    gold_rows: Sequence[dict[str, Any]],
    *,
    min_support: int,
    min_slice_support: int,
    required_contexts: Sequence[str],
    post_type_keys: Sequence[str],
) -> tuple[dict[str, Any], list[str]]:
    post_types = Counter(
        label
        for row in gold_rows
        for label in row["parsed_classification"]["post_types"]
    )
    product_labels = Counter(
        label
        for row in gold_rows
        for label in row["parsed_classification"]["product_labels"]
    )
    scalars = {
        dimension: Counter(
            row["parsed_classification"][dimension]
            if row["parsed_classification"][dimension] is not None
            else UNKNOWN
            for row in gold_rows
        )
        for dimension in REQUIRED_SCALAR_VALUES
    }
    structures = {
        "post_types.multiple": sum(
            len(row["parsed_classification"]["post_types"]) > 1 for row in gold_rows
        ),
        "product_labels.empty": sum(
            not row["parsed_classification"]["product_labels"] for row in gold_rows
        ),
        "product_labels.multiple": sum(
            len(row["parsed_classification"]["product_labels"]) > 1 for row in gold_rows
        ),
    }
    languages = Counter(row["source_language"] for row in gold_rows)
    contexts = Counter(
        "+".join(row["context_provenance"]) or "none" for row in gold_rows
    )
    gaps: list[str] = []
    if min_support:
        gaps.extend(
            f"post_types.{label}"
            for label in post_type_keys
            if post_types[label] < min_support
        )
        gaps.extend(
            f"product_labels.{label}"
            for label in PRODUCT_LABEL_KEYS
            if product_labels[label] < min_support
        )
        gaps.extend(
            f"{dimension}.{value}"
            for dimension, values in REQUIRED_SCALAR_VALUES.items()
            for value in values
            if scalars[dimension][value] < min_support
        )
        gaps.extend(
            f"structures.{name}"
            for name, count in structures.items()
            if count < min_support
        )
    if min_slice_support:
        gaps.extend(
            f"by_language.{language}"
            for language in REQUIRED_LANGUAGES
            if languages[language] < min_slice_support
        )
        gaps.extend(
            f"by_context.{context}"
            for context in required_contexts
            if contexts[context] < min_slice_support
        )
    return (
        {
            "label_and_scalar_threshold": min_support,
            "slice_threshold": min_slice_support,
            "post_types": {
                label: post_types[label] for label in post_type_keys
            },
            "product_labels": {
                label: product_labels[label] for label in PRODUCT_LABEL_KEYS
            },
            "scalars": {
                dimension: {value: scalars[dimension][value] for value in values}
                for dimension, values in REQUIRED_SCALAR_VALUES.items()
            },
            "structures": structures,
            "languages": {
                language: languages[language] for language in REQUIRED_LANGUAGES
            },
            "contexts": {
                context: contexts[context]
                for context in sorted({"none", *CONTEXT_KEYS, "+".join(CONTEXT_KEYS)})
            },
        },
        sorted(gaps),
    )


def _validate_policy(
    policy: Mapping[str, Any] | None,
    taxonomy_version: str = STAGE1_TAXONOMY_V2_VERSION,
) -> dict[str, Any]:
    if policy is None:
        return {}
    if not isinstance(policy, Mapping):
        raise EvaluationInputError(
            "policy_invalid", "policy must be an object", field="policy"
        )
    allowed_fields = {
        "policy_version",
        "taxonomy_version",
        "min_support",
        "min_slice_support",
        "required_contexts",
        "floors",
    }
    unknown_fields = sorted(set(policy) - allowed_fields)
    if unknown_fields:
        raise EvaluationInputError(
            "policy_invalid",
            f"policy contains unknown fields: {', '.join(unknown_fields)}",
            field="policy",
        )
    if policy.get("policy_version") != 1:
        raise EvaluationInputError(
            "policy_invalid",
            "policy.policy_version must be 1",
            field="policy.policy_version",
        )
    declared_taxonomy = policy.get("taxonomy_version", taxonomy_version)
    if declared_taxonomy != taxonomy_version:
        raise EvaluationInputError(
            "policy_invalid",
            "policy taxonomy_version must match the evaluated artifacts",
            field="policy.taxonomy_version",
        )
    minimum = policy.get("min_support")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise EvaluationInputError(
            "policy_invalid",
            "policy.min_support must be a positive integer",
            field="policy.min_support",
        )
    minimum_slice = policy.get("min_slice_support")
    if (
        isinstance(minimum_slice, bool)
        or not isinstance(minimum_slice, int)
        or minimum_slice < 1
    ):
        raise EvaluationInputError(
            "policy_invalid",
            "policy.min_slice_support must be a positive integer",
            field="policy.min_slice_support",
        )
    raw_floors = policy.get("floors", {})
    if not isinstance(raw_floors, Mapping):
        raise EvaluationInputError(
            "policy_invalid", "policy.floors must be an object", field="policy.floors"
        )
    floors: dict[str, float] = {}
    for path, value in raw_floors.items():
        if (
            not isinstance(path, str)
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not 0 <= float(value) <= 1
        ):
            raise EvaluationInputError(
                "policy_invalid",
                "floor values must be finite numbers from 0 through 1",
                field="policy.floors",
            )
        floors[path] = float(value)
    required_contexts = policy.get("required_contexts")
    if (
        not isinstance(required_contexts, list)
        or any(
            not isinstance(value, str) or not value.strip()
            for value in required_contexts
        )
        or len(set(required_contexts)) != len(required_contexts)
    ):
        raise EvaluationInputError(
            "policy_invalid",
            "policy.required_contexts must be a unique string array",
            field="policy.required_contexts",
        )
    allowed_contexts = {"none", *CONTEXT_KEYS, "+".join(CONTEXT_KEYS)}
    if not set(required_contexts).issubset(allowed_contexts):
        raise EvaluationInputError(
            "policy_invalid",
            "policy.required_contexts contains an unknown context slice",
            field="policy.required_contexts",
        )
    missing_contexts = sorted(set(REQUIRED_CONTEXTS) - set(required_contexts))
    if missing_contexts:
        raise EvaluationInputError(
            "policy_invalid",
            "policy.required_contexts must include none, stored_quote, and local_parent",
            field="policy.required_contexts",
        )
    missing_floors = sorted(
        required_floor_paths(required_contexts, taxonomy_version) - set(floors)
    )
    if missing_floors:
        raise EvaluationInputError(
            "policy_invalid",
            "policy.floors is incomplete; missing: " + ", ".join(missing_floors),
            field="policy.floors",
        )
    return {
        "policy_version": 1,
        "taxonomy_version": taxonomy_version,
        "min_support": minimum,
        "min_slice_support": minimum_slice,
        "required_contexts": list(required_contexts),
        "floors": dict(sorted(floors.items())),
    }


def _floor_value(populations: Mapping[str, Any], path: str) -> float | None:
    current: Any = populations
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            return None
        current = current[component]
    return current if isinstance(current, (int, float)) else None


def _assessment(
    populations: Mapping[str, Any],
    policy: Mapping[str, Any] | None,
    coverage: Mapping[str, Any],
    support_gaps: Sequence[str],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    if policy is None:
        return {"status": "unassessed", "reason": "no_policy"}
    if coverage["missing_candidates"] or coverage["invalid_candidates"]:
        return {"status": "blocked", "reason": "incomplete_candidate_coverage"}
    if support_gaps:
        return {
            "status": "blocked",
            "reason": "insufficient_support",
            "support_gaps": list(support_gaps),
        }
    if (
        identity["source_revision"] == "unavailable"
        or identity["source_worktree_dirty"] is not False
    ):
        return {"status": "blocked", "reason": "unreproducible_evaluator_source"}
    floors = policy.get("floors", {})
    checks = []
    for path, minimum in sorted(floors.items()):
        actual = _floor_value(populations, path)
        checks.append(
            {
                "metric": path,
                "minimum": minimum,
                "actual": actual,
                "pass": actual is not None and actual >= minimum,
            }
        )
    return {
        "status": "pass" if all(item["pass"] for item in checks) else "fail",
        "checks": checks,
    }


def evaluate_classification_artifacts(
    candidate: Mapping[str, Any],
    gold: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
    source_identity: Mapping[str, Any] | None = None,
    candidate_sha256: str | None = None,
    gold_sha256: str | None = None,
) -> dict[str, Any]:
    """Score paired candidate/gold artifacts without external side effects."""

    candidate_provenance, candidate_rows = _validate_document(candidate, "candidate")
    gold_provenance, gold_rows = _validate_document(gold, "gold")
    if (
        candidate_provenance["taxonomy_version"]
        != gold_provenance["taxonomy_version"]
        or candidate_provenance["prompt_version"]
        != gold_provenance["prompt_version"]
    ):
        raise EvaluationInputError(
            "taxonomy_mismatch",
            "candidate and gold taxonomy/prompt identities differ",
            field="provenance",
        )
    taxonomy_version = candidate_provenance["taxonomy_version"]
    post_type_keys = SUPPORTED_TAXONOMIES[taxonomy_version]["post_type_keys"]
    normalized_policy = _validate_policy(policy, taxonomy_version)
    min_support = normalized_policy.get("min_support", 0)
    min_slice_support = normalized_policy.get("min_slice_support", 0)
    required_contexts = normalized_policy.get("required_contexts", [])
    if candidate_provenance["cohort_id"] != gold_provenance["cohort_id"]:
        raise EvaluationInputError(
            "cohort_mismatch",
            "candidate and gold cohorts differ",
            field="provenance.cohort_id",
        )
    candidate_index = {
        (row["example_id"], row["brand_id"]): row for row in candidate_rows
    }
    gold_index = {(row["example_id"], row["brand_id"]): row for row in gold_rows}
    extra = sorted(set(candidate_index) - set(gold_index))
    if extra:
        raise EvaluationInputError(
            "candidate_scope_mismatch",
            "candidate contains rows absent from gold",
            field="rows",
        )

    scored: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for pair in sorted(gold_index):
        gold_row = gold_index[pair]
        gold_classification, gold_error = _classification(
            gold_row["classification"], pair[1], post_type_keys
        )
        if gold_error or gold_classification is None:
            raise EvaluationInputError(
                "invalid_gold_classification",
                f"gold classification is invalid for {pair!r}",
                field="rows",
            )
        gold_row["parsed_classification"] = gold_classification
        candidate_row = candidate_index.get(pair)
        if candidate_row is None:
            missing.append(
                {"example_id": pair[0], "brand_id": pair[1], "reason": "missing_row"}
            )
            continue
        if (
            candidate_row["source_language"] != gold_row["source_language"]
            or candidate_row["context_provenance"] != gold_row["context_provenance"]
        ):
            invalid.append(
                {
                    "example_id": pair[0],
                    "brand_id": pair[1],
                    "reason": "provenance_mismatch",
                }
            )
            continue
        if (
            candidate_row["input_context_fingerprint"]
            != gold_row["input_context_fingerprint"]
        ):
            invalid.append(
                {
                    "example_id": pair[0],
                    "brand_id": pair[1],
                    "reason": "input_context_fingerprint_mismatch",
                }
            )
            continue
        candidate_classification, candidate_error = _classification(
            candidate_row["classification"], pair[1], post_type_keys
        )
        if candidate_error or candidate_classification is None:
            missing_reason = (
                "missing_classification"
                if candidate_classification is None and candidate_error is None
                else None
            )
            if missing_reason:
                missing.append(
                    {
                        "example_id": pair[0],
                        "brand_id": pair[1],
                        "reason": missing_reason,
                    }
                )
            else:
                invalid.append(
                    {
                        "example_id": pair[0],
                        "brand_id": pair[1],
                        "reason": candidate_error,
                    }
                )
            continue
        scored.append(
            {
                "example_id": pair[0],
                "brand_id": pair[1],
                "language": gold_row["source_language"],
                "context": gold_row["context_provenance"],
                "gold": gold_classification,
                "candidate": candidate_classification,
            }
        )

    coverage = {
        "gold_pairs": len(gold_rows),
        "candidate_pairs": len(candidate_rows),
        "scored_pairs": len(scored),
        "missing_candidates": len(missing),
        "invalid_candidates": len(invalid),
        "coverage_rate": _ratio(len(scored), len(gold_rows)),
        "missing_by_reason": dict(
            sorted(Counter(row["reason"] for row in missing).items())
        ),
        "invalid_by_reason": dict(
            sorted(Counter(row["reason"] for row in invalid).items())
        ),
    }
    populations: dict[str, Any] = {
        "all": _population(scored, min_support, post_type_keys)
    }
    languages = sorted(
        {row["language"] for row in scored}
        | {row["source_language"] for row in gold_rows}
    )
    contexts = sorted(
        {"+".join(row["context"]) or "none" for row in scored}
        | {"+".join(row["context_provenance"]) or "none" for row in gold_rows}
    )
    populations["by_language"] = {
        language: _population(
            [row for row in scored if row["language"] == language],
            min_support,
            post_type_keys,
        )
        for language in languages
    }
    populations["by_context"] = {
        context: _population(
            [row for row in scored if ("+".join(row["context"]) or "none") == context],
            min_support,
            post_type_keys,
        )
        for context in contexts
    }
    support, support_gaps = _gold_support(
        gold_rows,
        min_support=min_support,
        min_slice_support=min_slice_support,
        required_contexts=required_contexts,
        post_type_keys=post_type_keys,
    )
    evaluator_source = _normalize_source_identity(
        source_identity or _resolve_source_identity()
    )
    identity_material = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "candidate_digest": _artifact_digest(candidate_sha256, candidate),
        "gold_digest": _artifact_digest(gold_sha256, gold),
        "policy": normalized_policy,
        "cohort_id": candidate_provenance["cohort_id"],
        "candidate_provenance": candidate_provenance,
        "gold_provenance": gold_provenance,
        "source_identity": evaluator_source,
    }
    identity = {
        **identity_material["source_identity"],
        "candidate_digest": identity_material["candidate_digest"],
        "gold_digest": identity_material["gold_digest"],
        "evaluation_identity": _sha256(identity_material),
    }
    warnings: list[dict[str, Any]] = []
    absent_languages = sorted(
        set(REQUIRED_LANGUAGES) - {row["source_language"] for row in gold_rows}
    )
    if absent_languages:
        warnings.append(
            {"code": "required_language_stratum_missing", "languages": absent_languages}
        )
    if identity["source_revision"] == "unavailable":
        warnings.append({"code": "source_revision_unavailable"})
    if identity.get("source_worktree_dirty"):
        warnings.append({"code": "source_worktree_dirty"})
    result = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "status": "empty"
        if not gold_rows
        else "incomplete"
        if missing or invalid
        else "ok",
        "cohort": {
            "cohort_id": candidate_provenance["cohort_id"],
            "required_languages": list(REQUIRED_LANGUAGES),
            "gold_languages": sorted({row["source_language"] for row in gold_rows}),
            "taxonomy_version": taxonomy_version,
        },
        "policy": normalized_policy or None,
        "coverage": coverage,
        "metric_conventions": {
            "undefined_metric": None,
            "jaccard_empty_vs_empty": 1.0,
            "scalar_null_bucket": UNKNOWN,
        },
        "metrics": populations,
        "support": support,
        "support_gaps": support_gaps,
        "assessment": _assessment(
            populations,
            normalized_policy if policy is not None else None,
            coverage,
            support_gaps,
            identity,
        ),
        "invalid_candidates": sorted(
            invalid, key=lambda row: (row["example_id"], row["brand_id"], row["reason"])
        ),
        "missing_candidates": sorted(
            missing, key=lambda row: (row["example_id"], row["brand_id"], row["reason"])
        ),
        "identity": identity,
        "warnings": sorted(warnings, key=lambda row: row["code"]),
    }
    return result


def evaluate_classification_files(
    candidate_path: str | Path,
    gold_path: str | Path,
    *,
    policy: Mapping[str, Any] | None = None,
    source_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_document, candidate_digest = _read_json(candidate_path)
    gold_document, gold_digest = _read_json(gold_path)
    return evaluate_classification_artifacts(
        candidate_document,
        gold_document,
        policy=policy,
        source_identity=source_identity,
        candidate_sha256=candidate_digest,
        gold_sha256=gold_digest,
    )


def evaluate_classifications(
    candidate_document: Mapping[str, Any],
    gold_document: Mapping[str, Any],
    *,
    policy: Mapping[str, Any] | None = None,
    candidate_sha256: str | None = None,
    gold_sha256: str | None = None,
    source_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stable public entry point for callers with already loaded documents."""

    return evaluate_classification_artifacts(
        candidate_document,
        gold_document,
        policy=policy,
        candidate_sha256=candidate_sha256,
        gold_sha256=gold_sha256,
        source_identity=source_identity,
    )
