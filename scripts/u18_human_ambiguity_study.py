"""Build and validate the candidate-blind U18 human ambiguity study.

The command reads ignored development artifacts and writes review packets under
``.context/u18``. It never calls a provider, queries a database, or writes
application data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.classification_contract import (
    CANONICAL_POST_TYPE_KEYS,
    NATIONALISM_KEYS,
    OUTCOMES,
    PRODUCT_LABEL_KEYS,
    SENTIMENT_KEYS,
)

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".context" / "u18"
DEFAULT_OUTPUT = PRIVATE / "human-ambiguity-study-v1"
DEFAULT_SOURCE = PRIVATE / "cohort-source.json"
DEFAULT_GOLD = PRIVATE / "gold-v3-v25-coupled-outcome-replay.json"
DEFAULT_CANDIDATES = (
    PRIVATE / "candidate-v18-runtime-base.json",
    PRIVATE / "candidate-v18-runtime-secondary.json",
    PRIVATE / "candidate-v25-primary-diagnostic.json",
    PRIVATE / "candidate-v26-exhaustive-verdict-review.json",
)

STUDY_ID = "u18-human-ambiguity-study-v1"
SEED = "u18-human-ambiguity-study-2026-09-12-v1"
LANGUAGES = ("en", "ja", "zh-cn")
BUCKETS = ("stable_model_vs_gold", "model_run_conflict", "agreement_control")
PER_BUCKET_PER_LANGUAGE = 5
EXPECTED_DEVELOPMENT_ROWS = 120
ISSUE_CODES = (
    "release_vs_marketing",
    "usage_vs_evaluation",
    "result_vs_opinion",
    "research_vs_other",
    "event_vs_opportunity",
    "job_vs_opportunity",
    "personnel_vs_biography",
    "context_missing",
    "brand_attribution",
    "product_label",
    "sentiment",
    "nationalism",
    "other",
)

SOURCE_COLUMNS = (
    "case_id",
    "source_language",
    "target_brand_id",
    "source_text",
    "context_json",
)
ANSWER_COLUMNS = (
    "outcome",
    "post_types_pipe",
    "product_labels_pipe",
    "sentiment",
    "china_nationalism",
    "us_nationalism",
    "job_discovery_relevant",
    "personnel_discovery_relevant",
    "confidence_1_to_5",
    "taxonomy_issue",
    "taxonomy_issue_code",
    "ambiguity_notes",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key(row: Mapping[str, Any]) -> tuple[str, str]:
    return str(row["example_id"]), str(row["brand_id"])


def _rows_by_key(document: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise TypeError("artifact must contain a rows array")
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for value in rows:
        if not isinstance(value, dict):
            raise TypeError("artifact rows must be objects")
        key = _key(value)
        if key in output:
            raise ValueError(f"duplicate artifact row {key}")
        output[key] = value
    return output


def _post_signature(row: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    classification = row.get("classification")
    if not isinstance(classification, Mapping):
        raise TypeError(f"row {_key(row)} has no classification object")
    outcome = classification.get("outcome")
    post_types = classification.get("post_types")
    if outcome not in OUTCOMES or not isinstance(post_types, list):
        raise ValueError(f"row {_key(row)} has an invalid post-type judgment")
    if any(value not in CANONICAL_POST_TYPE_KEYS for value in post_types):
        raise ValueError(f"row {_key(row)} contains an unknown post type")
    return str(outcome), tuple(sorted(str(value) for value in post_types))


def _rank(*parts: str) -> str:
    return hashlib.sha256(":".join((SEED, *parts)).encode()).hexdigest()


def _case_id(key: tuple[str, str]) -> str:
    return f"H{_rank('case', *key)[:11].upper()}"


def _selection_bucket(
    gold: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> tuple[str | None, tuple[str, tuple[str, ...]], int, int]:
    gold_signature = _post_signature(gold)
    signatures = [_post_signature(candidate) for candidate in candidates]
    counts = Counter(signatures)
    consensus, consensus_count = counts.most_common(1)[0]
    distinct_count = len(counts)
    if consensus_count >= 3 and consensus != gold_signature:
        bucket = "stable_model_vs_gold"
    elif distinct_count >= 2:
        bucket = "model_run_conflict"
    elif signatures[0] == gold_signature:
        bucket = "agreement_control"
    else:
        bucket = None
    return bucket, consensus, consensus_count, distinct_count


def _review_source(row: Mapping[str, Any], case_id: str) -> dict[str, str]:
    source = row.get("input")
    if not isinstance(source, Mapping):
        raise TypeError(f"source row {_key(row)} has no input object")
    contexts = []
    for value in source.get("context", []):
        if not isinstance(value, Mapping):
            raise TypeError(f"source row {_key(row)} has invalid context")
        contexts.append(
            {
                "kind": value.get("kind", value.get("provenance")),
                "text": value.get("text"),
            }
        )
    return {
        "case_id": case_id,
        "source_language": str(row["source_language"]),
        "target_brand_id": str(row["brand_id"]),
        "source_text": str(source["text"]),
        "context_json": json.dumps(
            contexts, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build(
    *,
    source_path: Path,
    gold_path: Path,
    candidate_paths: Sequence[Path],
    output_dir: Path,
    force: bool = False,
    expected_development_rows: int = EXPECTED_DEVELOPMENT_ROWS,
) -> dict[str, Any]:
    if len(candidate_paths) < 3:
        raise ValueError("at least three preserved candidate runs are required")
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise FileExistsError(f"{output_dir} is not empty; pass --force to rebuild")
    if output_dir.exists() and force:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_document = _read_json(source_path)
    gold_document = _read_json(gold_path)
    candidate_documents = [_read_json(path) for path in candidate_paths]
    sources = _rows_by_key(source_document)
    gold = _rows_by_key(gold_document)
    candidates = [_rows_by_key(document) for document in candidate_documents]
    gold_keys = set(gold)
    if len(gold_keys) != expected_development_rows:
        raise ValueError(
            f"model reference has {len(gold_keys)} rows; "
            f"expected {expected_development_rows}"
        )
    if not gold_keys <= set(sources):
        raise ValueError("source cohort is missing model-reference rows")
    for index, rows in enumerate(candidates):
        if set(rows) != gold_keys:
            raise ValueError(
                f"candidate {index + 1} keys do not exactly match the model reference"
            )

    available: dict[tuple[str, str], dict[str, Any]] = {}
    for key in sorted(gold_keys):
        gold_row = gold[key]
        source_row = sources[key]
        artifact_rows = [gold_row, *(rows[key] for rows in candidates)]
        for artifact_row in artifact_rows:
            for field in (
                "example_id",
                "brand_id",
                "source_language",
                "input_context_fingerprint",
            ):
                if artifact_row.get(field) != source_row.get(field):
                    raise ValueError(
                        f"row {key} has mismatched {field} across study artifacts"
                    )
        language = str(gold_row.get("source_language"))
        if language not in LANGUAGES:
            continue
        candidate_rows = [rows[key] for rows in candidates]
        bucket, consensus, consensus_count, distinct_count = _selection_bucket(
            gold_row, candidate_rows
        )
        if bucket is None:
            continue
        available[key] = {
            "bucket": bucket,
            "language": language,
            "consensus": consensus,
            "consensus_count": consensus_count,
            "distinct_count": distinct_count,
            "gold_signature": _post_signature(gold_row),
            "candidate_signatures": [_post_signature(row) for row in candidate_rows],
        }

    selected: list[tuple[str, str]] = []
    for language in LANGUAGES:
        for bucket in BUCKETS:
            choices = [
                key
                for key, value in available.items()
                if value["language"] == language and value["bucket"] == bucket
            ]
            if bucket == "stable_model_vs_gold":
                choices.sort(
                    key=lambda key: (
                        -available[key]["consensus_count"],
                        _rank(language, bucket, *key),
                    )
                )
            elif bucket == "model_run_conflict":
                choices.sort(
                    key=lambda key: (
                        -available[key]["distinct_count"],
                        _rank(language, bucket, *key),
                    )
                )
            else:
                choices.sort(key=lambda key: _rank(language, bucket, *key))
            if len(choices) < PER_BUCKET_PER_LANGUAGE:
                raise RuntimeError(
                    f"{language}/{bucket} supplied {len(choices)} eligible rows; "
                    f"required {PER_BUCKET_PER_LANGUAGE}"
                )
            selected.extend(choices[:PER_BUCKET_PER_LANGUAGE])

    manifest_rows = []
    review_rows = []
    for key in selected:
        case_id = _case_id(key)
        source = sources[key]
        evidence = available[key]
        review_rows.append({**_review_source(source, case_id), **dict.fromkeys(ANSWER_COLUMNS, "")})
        manifest_rows.append(
            {
                "case_id": case_id,
                "example_id": key[0],
                "brand_id": key[1],
                "source_language": evidence["language"],
                "selection_bucket": evidence["bucket"],
                "selection_evidence": {
                    "candidate_signatures": evidence["candidate_signatures"],
                    "consensus_count": evidence["consensus_count"],
                    "distinct_candidate_signatures": evidence["distinct_count"],
                    "gold_signature": evidence["gold_signature"],
                },
                "source_row": source,
            }
        )

    paths = {}
    for reviewer in ("a", "b"):
        ordered = sorted(
            review_rows,
            key=lambda row: _rank(f"reviewer-{reviewer}", row["case_id"]),
        )
        path = output_dir / f"reviewer-{reviewer}.csv"
        _write_csv(path, ordered, (*SOURCE_COLUMNS, *ANSWER_COLUMNS))
        paths[reviewer] = path

    manifest = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "seed": SEED,
        "candidate_blind": True,
        "development_only": True,
        "selection_basis": {
            "dimension": "outcome_and_exact_post_type_set",
            "languages": list(LANGUAGES),
            "buckets": list(BUCKETS),
            "per_bucket_per_language": PER_BUCKET_PER_LANGUAGE,
            "preserved_candidate_count": len(candidate_paths),
        },
        "inputs": {
            "source": {"path": str(source_path), "sha256": _sha256(source_path)},
            "model_gold": {"path": str(gold_path), "sha256": _sha256(gold_path)},
            "candidates": [
                {"path": str(path), "sha256": _sha256(path)}
                for path in candidate_paths
            ],
        },
        "packets": {
            reviewer: {"path": str(path), "sha256": _sha256(path)}
            for reviewer, path in paths.items()
        },
        "rows": sorted(manifest_rows, key=lambda row: row["case_id"]),
    }
    manifest_path = output_dir / "selection-manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(
        output_dir / "human-attestation.template.json",
        {
            "schema_version": 1,
            "study_id": STUDY_ID,
            "attested_by": "",
            "attested_at": "",
            "reviewers": {
                slot: {
                    language: {
                        "reviewer_ref": "",
                        "source_language_proficiency": "",
                        "independent_review": False,
                        "no_model_assistance": False,
                        "completed_at": "",
                    }
                    for language in LANGUAGES
                }
                for slot in ("a", "b")
            },
            "adjudicators": {
                language: {
                    "adjudicator_ref": "",
                    "source_language_proficiency": "",
                    "independent_of_reviewers": False,
                    "no_model_answers_seen": False,
                    "completed_at": "",
                }
                for language in LANGUAGES
            },
        },
    )
    return manifest


def _parse_pipe(value: str, allowed: Sequence[str], field: str) -> list[str]:
    output = [part.strip() for part in value.split("|") if part.strip()]
    if len(output) != len(set(output)):
        raise ValueError(f"{field} contains duplicate values")
    unknown = set(output) - set(allowed)
    if unknown:
        raise ValueError(f"{field} contains unknown values: {sorted(unknown)}")
    return [item for item in allowed if item in output]


def _parse_bool(value: str, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{field} must be true or false")
    return normalized == "true"


def _parse_optional(value: str, allowed: Sequence[str], field: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized not in allowed:
        raise ValueError(f"{field} has invalid value {normalized!r}")
    return normalized


def _parse_answer(row: Mapping[str, str]) -> dict[str, Any]:
    outcome = row["outcome"].strip()
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome has invalid value {outcome!r}")
    post_types = _parse_pipe(
        row["post_types_pipe"], CANONICAL_POST_TYPE_KEYS, "post_types_pipe"
    )
    product_labels = _parse_pipe(
        row["product_labels_pipe"], PRODUCT_LABEL_KEYS, "product_labels_pipe"
    )
    sentiment = _parse_optional(row["sentiment"], SENTIMENT_KEYS, "sentiment")
    china = _parse_optional(
        row["china_nationalism"], NATIONALISM_KEYS, "china_nationalism"
    )
    us = _parse_optional(row["us_nationalism"], NATIONALISM_KEYS, "us_nationalism")
    if outcome == "classified":
        if not post_types or sentiment is None or china is None or us is None:
            raise ValueError(
                "classified requires a post type, sentiment, and both nationalism fields"
            )
        if "other" in post_types and len(post_types) > 1:
            raise ValueError("other is exclusive")
    elif post_types or product_labels:
        raise ValueError("context_missing requires empty post and product labels")
    try:
        confidence = int(row["confidence_1_to_5"])
    except ValueError as exc:
        raise ValueError("confidence_1_to_5 must be an integer") from exc
    if confidence not in range(1, 6):
        raise ValueError("confidence_1_to_5 must be between 1 and 5")
    taxonomy_issue = _parse_bool(row["taxonomy_issue"], "taxonomy_issue")
    issue_code = row["taxonomy_issue_code"].strip()
    if taxonomy_issue and issue_code not in ISSUE_CODES:
        raise ValueError("taxonomy_issue_code is required for a taxonomy issue")
    if not taxonomy_issue and issue_code:
        raise ValueError("taxonomy_issue_code must be empty when taxonomy_issue is false")
    notes = row["ambiguity_notes"].strip()
    if taxonomy_issue and not notes:
        raise ValueError("ambiguity_notes are required for a taxonomy issue")
    return {
        "classification": {
            "outcome": outcome,
            "post_types": post_types,
            "product_labels": product_labels,
            "sentiment": sentiment,
            "china_nationalism": china,
            "us_nationalism": us,
        },
        "job_discovery_relevant": _parse_bool(
            row["job_discovery_relevant"], "job_discovery_relevant"
        ),
        "personnel_discovery_relevant": _parse_bool(
            row["personnel_discovery_relevant"], "personnel_discovery_relevant"
        ),
        "confidence": confidence,
        "taxonomy_issue": taxonomy_issue,
        "taxonomy_issue_code": issue_code or None,
        "ambiguity_notes": notes or None,
    }


def _expected_review_sources(manifest: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    output = {}
    for value in manifest["rows"]:
        output[value["case_id"]] = _review_source(value["source_row"], value["case_id"])
    return output


def load_reviews(path: Path, manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    expected = _expected_review_sources(manifest)
    output = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != [*SOURCE_COLUMNS, *ANSWER_COLUMNS]:
            raise ValueError(f"{path}: columns do not exactly match the review schema")
        for row in reader:
            case_id = row.get("case_id", "")
            if case_id not in expected:
                raise ValueError(f"{path}: unknown case_id {case_id!r}")
            if case_id in output:
                raise ValueError(f"{path}: duplicate case_id {case_id}")
            for field, value in expected[case_id].items():
                if row.get(field) != value:
                    raise ValueError(f"{path}: {case_id} changed source field {field}")
            try:
                output[case_id] = _parse_answer(row)
            except (KeyError, ValueError) as exc:
                raise ValueError(f"{path}: {case_id}: {exc}") from exc
    missing = set(expected) - set(output)
    if missing:
        raise ValueError(f"{path}: missing {len(missing)} cases")
    return output


def _adjudication_signature(answer: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: answer[key]
        for key in (
            "classification",
            "job_discovery_relevant",
            "personnel_discovery_relevant",
            "taxonomy_issue",
            "taxonomy_issue_code",
        )
    }


def prepare_adjudication(
    *, output_dir: Path, reviewer_a_path: Path, reviewer_b_path: Path
) -> dict[str, Any]:
    manifest = _read_json(output_dir / "selection-manifest.json")
    reviewer_a = load_reviews(reviewer_a_path, manifest)
    reviewer_b = load_reviews(reviewer_b_path, manifest)
    expected = _expected_review_sources(manifest)
    disagreements = []
    for case_id in sorted(expected):
        if _adjudication_signature(reviewer_a[case_id]) == _adjudication_signature(
            reviewer_b[case_id]
        ):
            continue
        disagreements.append(
            {
                **expected[case_id],
                "reviewer_a_json": json.dumps(
                    reviewer_a[case_id], ensure_ascii=False, sort_keys=True
                ),
                "reviewer_b_json": json.dumps(
                    reviewer_b[case_id], ensure_ascii=False, sort_keys=True
                ),
                **dict.fromkeys(ANSWER_COLUMNS, ""),
            }
        )
    path = output_dir / "adjudicator.csv"
    _write_csv(
        path,
        disagreements,
        (*SOURCE_COLUMNS, "reviewer_a_json", "reviewer_b_json", *ANSWER_COLUMNS),
    )
    result = {
        "schema_version": 1,
        "study_id": manifest["study_id"],
        "reviewer_a_sha256": _sha256(reviewer_a_path),
        "reviewer_b_sha256": _sha256(reviewer_b_path),
        "agreement_count": len(expected) - len(disagreements),
        "disagreement_count": len(disagreements),
        "adjudicator_packet": {"path": str(path), "sha256": _sha256(path)},
    }
    _write_json(output_dir / "adjudication-manifest.json", result)
    return result


def _load_adjudications(
    path: Path,
    manifest: Mapping[str, Any],
    disagreement_ids: set[str],
    reviewer_a: Mapping[str, Mapping[str, Any]],
    reviewer_b: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    expected = _expected_review_sources(manifest)
    output = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        expected_columns = [
            *SOURCE_COLUMNS,
            "reviewer_a_json",
            "reviewer_b_json",
            *ANSWER_COLUMNS,
        ]
        if reader.fieldnames != expected_columns:
            raise ValueError(
                f"{path}: columns do not exactly match the adjudication schema"
            )
        for row in reader:
            case_id = row.get("case_id", "")
            if case_id not in disagreement_ids:
                raise ValueError(f"{path}: unexpected adjudication case {case_id!r}")
            if case_id in output:
                raise ValueError(f"{path}: duplicate adjudication case {case_id}")
            for field, value in expected[case_id].items():
                if row.get(field) != value:
                    raise ValueError(f"{path}: {case_id} changed source field {field}")
            try:
                packet_a = json.loads(row["reviewer_a_json"])
                packet_b = json.loads(row["reviewer_b_json"])
            except (KeyError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"{path}: {case_id} has malformed reviewer evidence"
                ) from exc
            if packet_a != reviewer_a[case_id] or packet_b != reviewer_b[case_id]:
                raise ValueError(
                    f"{path}: {case_id} changed the locked reviewer evidence"
                )
            output[case_id] = _parse_answer(row)
    missing = disagreement_ids - set(output)
    if missing:
        raise ValueError(f"{path}: missing {len(missing)} adjudications")
    return output


def _load_human_attestation(path: Path, study_id: str) -> dict[str, Any]:
    attestation = _read_json(path)
    if attestation.get("schema_version") != 1 or attestation.get("study_id") != study_id:
        raise ValueError("human attestation does not match this study")
    if not attestation.get("attested_by") or not attestation.get("attested_at"):
        raise ValueError("human attestation must name its attestor and time")
    reviewers = attestation.get("reviewers")
    adjudicators = attestation.get("adjudicators")
    if not isinstance(reviewers, Mapping) or not isinstance(adjudicators, Mapping):
        raise TypeError("human attestation is missing reviewer assignments")
    for language in LANGUAGES:
        refs = []
        for slot in ("a", "b"):
            slot_assignments = reviewers.get(slot)
            assignment = (
                slot_assignments.get(language)
                if isinstance(slot_assignments, Mapping)
                else None
            )
            if not isinstance(assignment, Mapping):
                raise TypeError(
                    f"human attestation is missing {language} reviewer-{slot}"
                )
            ref = assignment.get("reviewer_ref")
            if (
                not ref
                or assignment.get("source_language_proficiency")
                not in {"native", "professional", "fluent"}
                or assignment.get("independent_review") is not True
                or assignment.get("no_model_assistance") is not True
                or not assignment.get("completed_at")
            ):
                raise ValueError(
                    f"human attestation has an incomplete {language} "
                    f"reviewer-{slot} assignment"
                )
            refs.append(str(ref))
        adjudicator = adjudicators.get(language)
        if not isinstance(adjudicator, Mapping):
            raise TypeError(f"human attestation is missing {language} adjudicator")
        adjudicator_ref = adjudicator.get("adjudicator_ref")
        if (
            not adjudicator_ref
            or adjudicator.get("source_language_proficiency")
            not in {"native", "professional", "fluent"}
            or adjudicator.get("independent_of_reviewers") is not True
            or adjudicator.get("no_model_answers_seen") is not True
            or not adjudicator.get("completed_at")
        ):
            raise ValueError(
                f"human attestation has an incomplete {language} adjudicator assignment"
            )
        if len({*refs, str(adjudicator_ref)}) != 3:
            raise ValueError(f"{language} requires three distinct human references")
    return attestation


def _post_answer_signature(answer: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    classification = answer["classification"]
    return classification["outcome"], tuple(classification["post_types"])


def finalize(
    *,
    output_dir: Path,
    reviewer_a_path: Path,
    reviewer_b_path: Path,
    adjudicator_path: Path,
    attestation_path: Path,
) -> dict[str, Any]:
    manifest = _read_json(output_dir / "selection-manifest.json")
    attestation = _load_human_attestation(attestation_path, manifest["study_id"])
    adjudication_manifest = _read_json(output_dir / "adjudication-manifest.json")
    if adjudication_manifest.get("study_id") != manifest["study_id"]:
        raise ValueError("adjudication manifest does not match this study")
    if adjudication_manifest.get("reviewer_a_sha256") != _sha256(reviewer_a_path):
        raise ValueError("reviewer A changed after adjudication preparation")
    if adjudication_manifest.get("reviewer_b_sha256") != _sha256(reviewer_b_path):
        raise ValueError("reviewer B changed after adjudication preparation")
    reviewer_a = load_reviews(reviewer_a_path, manifest)
    reviewer_b = load_reviews(reviewer_b_path, manifest)
    disagreements = {
        case_id
        for case_id in reviewer_a
        if _adjudication_signature(reviewer_a[case_id])
        != _adjudication_signature(reviewer_b[case_id])
    }
    adjudicated = _load_adjudications(
        adjudicator_path,
        manifest,
        disagreements,
        reviewer_a,
        reviewer_b,
    )
    manifest_by_id = {row["case_id"]: row for row in manifest["rows"]}

    exact_by_language: dict[str, list[bool]] = {language: [] for language in LANGUAGES}
    issue_cases: dict[str, set[str]] = {}
    gold_rows = []
    for case_id in sorted(reviewer_a):
        row = manifest_by_id[case_id]
        language = row["source_language"]
        exact_by_language[language].append(
            _post_answer_signature(reviewer_a[case_id])
            == _post_answer_signature(reviewer_b[case_id])
        )
        final = adjudicated.get(case_id, reviewer_a[case_id])
        issue_code = final["taxonomy_issue_code"]
        if issue_code:
            issue_cases.setdefault(issue_code, set()).add(case_id)
        source = row["source_row"]
        gold_rows.append(
            {
                **{
                    key: source[key]
                    for key in (
                        "example_id",
                        "brand_id",
                        "source_language",
                        "context_provenance",
                        "input_context_fingerprint",
                        "stratum",
                        "source_role",
                        "source_hint",
                    )
                },
                "classification": final["classification"],
                "job_discovery_relevant": final["job_discovery_relevant"],
                "personnel_discovery_relevant": final[
                    "personnel_discovery_relevant"
                ],
            }
        )

    exact_all = [value for values in exact_by_language.values() for value in values]
    overall_rate = sum(exact_all) / len(exact_all)
    locale_rates = {
        language: sum(values) / len(values)
        for language, values in exact_by_language.items()
    }
    recurring_issues = {
        code: len(case_ids)
        for code, case_ids in sorted(issue_cases.items())
        if len(case_ids) >= 3
    }
    passed = (
        overall_rate >= 0.80
        and all(rate >= 0.70 for rate in locale_rates.values())
        and not recurring_issues
    )
    post_exact_count = sum(exact_all)
    adjudicated_document = {
        "schema_version": 1,
        "provenance": {
            "kind": (
                "human_adjudicated_development_gold"
                if passed
                else "human_adjudicated_taxonomy_diagnostic"
            ),
            "gold": passed,
            "human_grounded": True,
            "development_only": True,
            "human_reliability_gate_passed": passed,
            "study_id": manifest["study_id"],
            "candidate_blind": True,
            "human_attestation_sha256": _sha256(attestation_path),
            "human_assignments": {
                "reviewers": attestation["reviewers"],
                "adjudicators": attestation["adjudicators"],
            },
            "adjudication_method": "two_independent_candidate_blind_human_reviews_then_separate_human_disagreement_adjudication",
            "adjudicated_at": datetime.now(UTC).isoformat(),
        },
        "rows": sorted(gold_rows, key=_key),
    }
    gold_path = output_dir / "human-gold.json"
    diagnostic_path = output_dir / "human-adjudicated-diagnostic.json"
    gold_path.unlink(missing_ok=True)
    diagnostic_path.unlink(missing_ok=True)
    adjudicated_path = gold_path if passed else diagnostic_path
    _write_json(adjudicated_path, adjudicated_document)
    result = {
        "schema_version": 1,
        "study_id": manifest["study_id"],
        "decision": "pass" if passed else "taxonomy_review_required",
        "pre_adjudication_post_type_outcome_exact": {
            "overall": overall_rate,
            "by_language": locale_rates,
        },
        "floors": {"overall": 0.80, "per_language": 0.70},
        "recurring_taxonomy_issues": recurring_issues,
        "adjudicated_judgment_agreement_count": len(exact_all) - len(disagreements),
        "adjudicated_judgment_disagreement_count": len(disagreements),
        "post_type_outcome_exact_count": post_exact_count,
        "artifacts": {
            "reviewer_a_sha256": _sha256(reviewer_a_path),
            "reviewer_b_sha256": _sha256(reviewer_b_path),
            "adjudicator_sha256": _sha256(adjudicator_path),
            "human_attestation_sha256": _sha256(attestation_path),
            "adjudicated_output": str(adjudicated_path),
            "adjudicated_output_sha256": _sha256(adjudicated_path),
        },
    }
    _write_json(output_dir / "result.json", result)
    return result


def _paths(values: Sequence[str] | None) -> tuple[Path, ...]:
    return tuple(Path(value).expanduser().resolve() for value in values or ())


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    build_parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    build_parser.add_argument("--candidate", action="append")
    build_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    build_parser.add_argument("--force", action="store_true")

    adjudicate_parser = subparsers.add_parser("prepare-adjudication")
    adjudicate_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    adjudicate_parser.add_argument("--reviewer-a", type=Path)
    adjudicate_parser.add_argument("--reviewer-b", type=Path)

    final_parser = subparsers.add_parser("finalize")
    final_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    final_parser.add_argument("--reviewer-a", type=Path)
    final_parser.add_argument("--reviewer-b", type=Path)
    final_parser.add_argument("--adjudicator", type=Path)
    final_parser.add_argument("--attestation", type=Path)

    args = parser.parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    if args.command == "build":
        candidate_paths = _paths(args.candidate) or DEFAULT_CANDIDATES
        result = build(
            source_path=args.source.expanduser().resolve(),
            gold_path=args.gold.expanduser().resolve(),
            candidate_paths=candidate_paths,
            output_dir=output_dir,
            force=args.force,
        )
        print(
            f"wrote {len(result['rows'])} blinded cases to {output_dir}; "
            f"manifest_sha256={_sha256(output_dir / 'selection-manifest.json')}"
        )
    elif args.command == "prepare-adjudication":
        result = prepare_adjudication(
            output_dir=output_dir,
            reviewer_a_path=(args.reviewer_a or output_dir / "reviewer-a.csv"),
            reviewer_b_path=(args.reviewer_b or output_dir / "reviewer-b.csv"),
        )
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        result = finalize(
            output_dir=output_dir,
            reviewer_a_path=(args.reviewer_a or output_dir / "reviewer-a.csv"),
            reviewer_b_path=(args.reviewer_b or output_dir / "reviewer-b.csv"),
            adjudicator_path=(args.adjudicator or output_dir / "adjudicator.csv"),
            attestation_path=(
                args.attestation or output_dir / "human-attestation.json"
            ),
        )
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
