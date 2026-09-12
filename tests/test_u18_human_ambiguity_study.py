from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.u18_human_ambiguity_study import (
    build,
    finalize,
    prepare_adjudication,
)


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _classification(post_types: list[str]) -> dict[str, object]:
    return {
        "outcome": "classified",
        "post_types": post_types,
        "product_labels": [],
        "sentiment": "neutral",
        "china_nationalism": "none",
        "us_nationalism": "none",
    }


def _artifacts(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    source_rows = []
    gold_rows = []
    candidate_rows = [[] for _ in range(4)]
    for language in ("en", "ja", "zh-cn"):
        for bucket in ("stable", "conflict", "control"):
            for index in range(5):
                example_id = f"{language}-{bucket}-{index}"
                base = {
                    "example_id": example_id,
                    "brand_id": "example_brand",
                    "source_language": language,
                    "context_provenance": ["stored_quote"],
                    "input_context_fingerprint": f"fingerprint-{example_id}",
                    "stratum": "private-selection-hint",
                    "source_role": "third_party",
                    "source_hint": "must-not-leak",
                }
                source_rows.append(
                    {
                        **base,
                        "input": {
                            "brand_ids": ["example_brand"],
                            "context": [
                                {
                                    "kind": "stored_quote",
                                    "post_id": "hidden-context-id",
                                    "text": f"Context {example_id}",
                                }
                            ],
                            "text": f"Source {example_id}",
                            "tweet_id": example_id,
                        },
                    }
                )
                gold_rows.append(
                    {**base, "classification": _classification(["releases_updates"])}
                )
                if bucket == "stable":
                    values = [["opinions_reactions"]] * 4
                elif bucket == "conflict":
                    values = [
                        ["releases_updates"],
                        ["opinions_reactions"],
                        ["research_explanations"],
                        ["business_finance"],
                    ]
                else:
                    values = [["releases_updates"]] * 4
                for rows, value in zip(candidate_rows, values, strict=True):
                    rows.append({**base, "classification": _classification(value)})

    source_path = tmp_path / "source.json"
    gold_path = tmp_path / "gold.json"
    candidate_paths = [tmp_path / f"candidate-{index}.json" for index in range(4)]
    _write(source_path, {"rows": source_rows})
    _write(gold_path, {"rows": gold_rows})
    for path, rows in zip(candidate_paths, candidate_rows, strict=True):
        _write(path, {"rows": rows})
    return source_path, gold_path, candidate_paths


def _fill_review(
    path: Path,
    *,
    change_first: bool = False,
    change_all: bool = False,
    change_second_confidence: bool = False,
) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert fieldnames is not None
    for index, row in enumerate(rows):
        row.update(
            {
                "outcome": "classified",
                "post_types_pipe": (
                    "opinions_reactions"
                    if change_all or (change_first and index == 0)
                    else "releases_updates"
                ),
                "product_labels_pipe": "",
                "sentiment": "neutral",
                "china_nationalism": "none",
                "us_nationalism": "none",
                "job_discovery_relevant": "false",
                "personnel_discovery_relevant": "false",
                "confidence_1_to_5": (
                    "2" if change_second_confidence and index == 1 else "4"
                ),
                "taxonomy_issue": "false",
                "taxonomy_issue_code": "",
                "ambiguity_notes": "",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_attestation(output: Path) -> Path:
    path = output / "human-attestation.json"
    attestation = json.loads(
        (output / "human-attestation.template.json").read_text(encoding="utf-8")
    )
    attestation["attested_by"] = "study-owner"
    attestation["attested_at"] = "2026-09-12T00:00:00Z"
    for language in ("en", "ja", "zh-cn"):
        for slot in ("a", "b"):
            attestation["reviewers"][slot][language].update(
                {
                    "reviewer_ref": f"{language}-reviewer-{slot}",
                    "source_language_proficiency": "fluent",
                    "independent_review": True,
                    "no_model_assistance": True,
                    "completed_at": "2026-09-12T00:00:00Z",
                }
            )
        attestation["adjudicators"][language].update(
            {
                "adjudicator_ref": f"{language}-adjudicator",
                "source_language_proficiency": "fluent",
                "independent_of_reviewers": True,
                "no_model_answers_seen": True,
                "completed_at": "2026-09-12T00:00:00Z",
            }
        )
    _write(path, attestation)
    return path


def test_build_is_deterministic_balanced_and_candidate_blind(tmp_path: Path) -> None:
    source, gold, candidates = _artifacts(tmp_path)
    output = tmp_path / "study"
    manifest = build(
        source_path=source,
        gold_path=gold,
        candidate_paths=candidates,
        output_dir=output,
        expected_development_rows=45,
    )

    assert len(manifest["rows"]) == 45
    counts = {}
    for row in manifest["rows"]:
        key = (row["source_language"], row["selection_bucket"])
        counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {5}

    packet_a = (output / "reviewer-a.csv").read_bytes()
    packet_b = (output / "reviewer-b.csv").read_bytes()
    assert packet_a != packet_b
    assert b"source_hint" not in packet_a
    assert b"selection_bucket" not in packet_a
    assert b"must-not-leak" not in packet_a
    assert b"candidate" not in packet_a
    assert b"hidden-context-id" not in packet_a

    build(
        source_path=source,
        gold_path=gold,
        candidate_paths=candidates,
        output_dir=output,
        force=True,
        expected_development_rows=45,
    )
    assert (output / "reviewer-a.csv").read_bytes() == packet_a
    assert (output / "reviewer-b.csv").read_bytes() == packet_b


def test_build_rejects_candidate_key_drift(tmp_path: Path) -> None:
    source, gold, candidates = _artifacts(tmp_path)
    changed = json.loads(candidates[0].read_text(encoding="utf-8"))
    changed["rows"].pop()
    _write(candidates[0], changed)

    with pytest.raises(ValueError, match="do not exactly match"):
        build(
            source_path=source,
            gold_path=gold,
            candidate_paths=candidates,
            output_dir=tmp_path / "study",
            expected_development_rows=45,
        )


def test_build_rejects_cross_artifact_language_drift(tmp_path: Path) -> None:
    source, gold, candidates = _artifacts(tmp_path)
    changed = json.loads(candidates[0].read_text(encoding="utf-8"))
    changed["rows"][0]["source_language"] = "wrong-language"
    _write(candidates[0], changed)

    with pytest.raises(ValueError, match="mismatched source_language"):
        build(
            source_path=source,
            gold_path=gold,
            candidate_paths=candidates,
            output_dir=tmp_path / "study",
            expected_development_rows=45,
        )


def test_review_rejects_extra_columns_that_can_leak_candidates(
    tmp_path: Path,
) -> None:
    source, gold, candidates = _artifacts(tmp_path)
    output = tmp_path / "study"
    build(
        source_path=source,
        gold_path=gold,
        candidate_paths=candidates,
        output_dir=output,
        expected_development_rows=45,
    )
    _fill_review(output / "reviewer-a.csv")
    _fill_review(output / "reviewer-b.csv")
    path = output / "reviewer-a.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = [*(reader.fieldnames or []), "candidate_label"]
    for row in rows:
        row["candidate_label"] = "releases_updates"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="columns do not exactly match"):
        prepare_adjudication(
            output_dir=output,
            reviewer_a_path=path,
            reviewer_b_path=output / "reviewer-b.csv",
        )


def test_review_adjudication_and_finalization(tmp_path: Path) -> None:
    source, gold, candidates = _artifacts(tmp_path)
    output = tmp_path / "study"
    build(
        source_path=source,
        gold_path=gold,
        candidate_paths=candidates,
        output_dir=output,
        expected_development_rows=45,
    )
    _fill_review(output / "reviewer-a.csv")
    _fill_review(
        output / "reviewer-b.csv",
        change_first=True,
        change_second_confidence=True,
    )

    adjudication = prepare_adjudication(
        output_dir=output,
        reviewer_a_path=output / "reviewer-a.csv",
        reviewer_b_path=output / "reviewer-b.csv",
    )
    assert adjudication["agreement_count"] == 44
    assert adjudication["disagreement_count"] == 1

    adjudicator_path = output / "adjudicator.csv"
    _fill_review(adjudicator_path)
    attestation_path = _write_attestation(output)
    tampered_path = output / "adjudicator-tampered.csv"
    with adjudicator_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        tampered_rows = list(reader)
    assert fieldnames is not None
    tampered_rows[0]["reviewer_a_json"] = "{}"
    with tampered_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(tampered_rows)
    with pytest.raises(ValueError, match="changed the locked reviewer evidence"):
        finalize(
            output_dir=output,
            reviewer_a_path=output / "reviewer-a.csv",
            reviewer_b_path=output / "reviewer-b.csv",
            adjudicator_path=tampered_path,
            attestation_path=attestation_path,
        )
    result = finalize(
        output_dir=output,
        reviewer_a_path=output / "reviewer-a.csv",
        reviewer_b_path=output / "reviewer-b.csv",
        adjudicator_path=adjudicator_path,
        attestation_path=attestation_path,
    )

    assert result["decision"] == "pass"
    assert result["post_type_outcome_exact_count"] == 44
    assert result["adjudicated_judgment_disagreement_count"] == 1
    human_gold = json.loads((output / "human-gold.json").read_text())
    assert human_gold["provenance"]["human_grounded"] is True
    assert len(human_gold["rows"]) == 45


def test_failed_human_gate_does_not_emit_gold(tmp_path: Path) -> None:
    source, gold, candidates = _artifacts(tmp_path)
    output = tmp_path / "study"
    build(
        source_path=source,
        gold_path=gold,
        candidate_paths=candidates,
        output_dir=output,
        expected_development_rows=45,
    )
    _fill_review(output / "reviewer-a.csv")
    _fill_review(output / "reviewer-b.csv", change_all=True)
    prepare_adjudication(
        output_dir=output,
        reviewer_a_path=output / "reviewer-a.csv",
        reviewer_b_path=output / "reviewer-b.csv",
    )
    _fill_review(output / "adjudicator.csv")
    result = finalize(
        output_dir=output,
        reviewer_a_path=output / "reviewer-a.csv",
        reviewer_b_path=output / "reviewer-b.csv",
        adjudicator_path=output / "adjudicator.csv",
        attestation_path=_write_attestation(output),
    )

    assert result["decision"] == "taxonomy_review_required"
    assert not (output / "human-gold.json").exists()
    diagnostic = json.loads(
        (output / "human-adjudicated-diagnostic.json").read_text(encoding="utf-8")
    )
    assert diagnostic["provenance"]["gold"] is False
    assert diagnostic["provenance"]["human_reliability_gate_passed"] is False
