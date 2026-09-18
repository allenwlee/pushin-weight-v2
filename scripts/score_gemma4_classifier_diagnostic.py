"""Score Gemma and V4.1 classifier outputs against nonblank owner controls."""
from __future__ import annotations

import json
import re
import argparse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GEMMA = ROOT / ".context/model-task-20260918/gemma4-classifier-diagnostic24-direct-deepinfra-tagged-v1-2026-09-18-172000"
V41 = ROOT / ".context/model-task-20260917/deepseek-v41-incumbent-classification-v1-diagnostic24"
CORPUS = ROOT / ".context/model-task-20260917/classifier-input.json"
H_OWNER = ROOT / ".context/u18/human-ambiguity-study-v1/owner-accepted-reference.json"
L_OWNER = ROOT / ".context/u18/fresh-human-review-45-v1/2026-09-15-173009-owner-review-answers-materialized.json"
FIELDS = ("outcome", "post_types", "audience_topics", "product_labels", "sentiment", "geopolitical_modes", "china_national_stance", "us_national_stance")


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canon(field: str, value: Any) -> Any:
    if isinstance(value, list):
        mapped = [
            "results_analysis" if item == "results_evaluations"
            else "investigate_claim" if item == "misinformation"
            else "nationalism" if item == "nationalistic_stance"
            else item
            for item in value
        ]
        return tuple(sorted(mapped))
    return value


def model_rows(gemma_path: Path) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    gemma_out = read(gemma_path / "outputs.json")
    v41_out = read(V41 / "attempt-1.consumed.json")["calls"]
    gemma: dict[tuple[str, str], dict[str, Any]] = {}
    v41: dict[tuple[str, str], dict[str, Any]] = {}
    for source, rows in ((gemma, gemma_out), (v41, v41_out)):
        for row in rows:
            post_id = row.get("source_post_id") or row["source_post_ids"][0]
            for item in row.get("parsed", {}).get(post_id, []):
                key = (post_id, item["brand_id"])
                source.setdefault(key, {}).update({name: value for name, value in item.items() if name != "brand_id"})
    g_promotions: dict[str, tuple[str, ...]] = {}
    entries = read(gemma_path / "requests.json")
    for index, entry in enumerate(entries):
        if entry["role"] != "content":
            continue
        attempt = read(gemma_path / "attempt-records" / f"{index:04d}-attempt-1.json")
        content = attempt["response"]["choices"][0]["message"]["content"]
        keys = re.findall(r"\[\[KEYS\]\](.*?)\[\[/KEYS\]\]", content, re.DOTALL)
        g_promotions[entry["source_post_id"]] = tuple(sorted(value.strip() for raw in keys for value in raw.split(",") if value.strip()))
    v_promotions: dict[str, tuple[str, ...]] = {}
    for row in v41_out:
        if row["role"] != "content":
            continue
        post_id = row["source_post_ids"][0]
        values = [value for group in row["structured_output"]["post_promotions"].values() for value in group]
        v_promotions[post_id] = tuple(sorted(values))
    return gemma, v41, g_promotions, v_promotions


def owner_controls() -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, tuple[str, ...]]]:
    controls: dict[tuple[str, str], dict[str, Any]] = {}
    promotions: dict[str, tuple[str, ...]] = {}
    for row in read(H_OWNER)["rows"]:
        trial = "H-" + row["case_id"]
        classification = row["classification"]
        record = {
            "outcome": classification.get("outcome"),
            "post_types": classification.get("post_types"),
            "product_labels": classification.get("product_labels") or ["none"],
            "sentiment": classification.get("sentiment"),
            "china_national_stance": classification.get("china_nationalism"),
            "us_national_stance": classification.get("us_nationalism"),
        }
        controls[(trial, row["brand_id"])] = {key: value for key, value in record.items() if value not in (None, "", [])}
    for case_id, case in read(L_OWNER)["cases"].items():
        trial = "L-" + case_id
        for brand, record in case["per_brand"].items():
            controls[(trial, brand)] = {key: record[key] for key in FIELDS if record.get(key) not in (None, "", [])}
        values = case.get("post_level", {}).get("untracked_brand_promotions")
        if values:
            promotions[trial] = tuple(sorted(values))
    return controls, promotions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", type=Path, default=DEFAULT_GEMMA)
    args = parser.parse_args()
    gemma_path = args.trial.resolve()
    gemma, v41, g_promotions, v_promotions = model_rows(gemma_path)
    controls, owner_promotions = owner_controls()
    selected = set(read(V41 / "contract.json")["source_post_ids"])
    findings = []
    totals = {name: {"reviewed_fields": 0, "matching_fields": 0, "error_sources": set()} for name in ("gemma", "v41")}
    for key, expected in controls.items():
        post_id, brand = key
        if post_id not in selected:
            continue
        row = {"source_post_id": post_id, "brand_id": brand, "fields": {}}
        for field, owner in expected.items():
            row["fields"][field] = {"owner": owner}
            for name, model in (("gemma", gemma), ("v41", v41)):
                actual = model.get(key, {}).get(field)
                match = canon(field, owner) == canon(field, actual)
                row["fields"][field][name] = actual
                row["fields"][field][name + "_match"] = match
                totals[name]["reviewed_fields"] += 1
                totals[name]["matching_fields"] += int(match)
                if not match:
                    totals[name]["error_sources"].add(post_id)
        findings.append(row)
    promotion_findings = []
    for post_id, expected in owner_promotions.items():
        if post_id not in selected:
            continue
        row = {"source_post_id": post_id, "owner": expected, "gemma": g_promotions.get(post_id), "v41": v_promotions.get(post_id)}
        for name in ("gemma", "v41"):
            match = row[name] == expected
            row[name + "_match"] = match
            totals[name]["reviewed_fields"] += 1
            totals[name]["matching_fields"] += int(match)
            if not match:
                totals[name]["error_sources"].add(post_id)
        promotion_findings.append(row)
    result = {
        "schema": "gemma4-classifier-owner-control-score/v1",
        "policy": "Only nonblank owner entries are controls. Arrays compare as sets. Legacy results_evaluations/misinformation map to results_analysis/investigate_claim. This consumed development corpus is not blinded gold or a production accuracy estimate.",
        "totals": {name: {**values, "error_sources": sorted(values["error_sources"]), "error_source_count": len(values["error_sources"]), "field_accuracy": values["matching_fields"] / values["reviewed_fields"] if values["reviewed_fields"] else None} for name, values in totals.items()},
        "per_brand": findings,
        "post_promotions": promotion_findings,
    }
    out = gemma_path / "owner-control-score.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["totals"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
