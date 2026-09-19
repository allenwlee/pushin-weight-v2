"""Create the no-retry diagnostic report for failed DeepInfra R116."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_batch20_compare as control
from scripts import u18_fresh40_v4_0731_compare as v4
from scripts import u18_fresh40_v4_0731_deepinfra as run
from scripts import u18_fresh40_v4_0731_five_post as five
from scripts import u18_fresh45_sol_compare as sol


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def diagnostic_result() -> dict[str, Any]:
    partial = json.loads((run.PRIVATE / "partial-result.json").read_text(encoding="utf-8"))
    if partial["failures"] != [{"call": "1-content", "error": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)"}]:
        raise ValueError("unexpected R116 failure signature")
    raw = json.loads((run.PRIVATE / "1-content-raw-response.json").read_text(encoding="utf-8"))
    text = raw["choices"][0]["message"]["content"].strip()
    if not text.startswith("```json\n") or not text.endswith("```"):
        raise ValueError("failed response is not the expected fenced JSON")
    raw["choices"][0]["message"]["content"] = text[len("```json\n"):-len("```")].strip()
    packets = json.loads((run.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    rows, issues = run.parse(raw, packets[:20], "content")
    output = deepcopy(partial)
    output["roles"]["content"] = rows + output["roles"]["content"]
    output["semantic_issues"] = [{"call": "1-content", **issue} for issue in issues] + output["semantic_issues"]
    output["official_failures"] = output.pop("failures")
    output["diagnostic_normalization"] = "Removed one outer ```json fence from 1-content. No labels, slots, or values changed. This does not convert the official failed arm into a pass."
    output["actual_billed_usd"] = str(sum(Decimal(str((row.get("usage") or {}).get("cost", 0))) for row in output["measurements"]))
    output["actual_billed_with_fee_usd"] = str(Decimal(output["actual_billed_usd"]) * run.FEE_FACTOR)
    output["completed_at"] = datetime.now(timezone.utc).isoformat()
    if len(output["roles"]["content"]) != 40 or len(output["roles"]["brand"]) != 40:
        raise ValueError("diagnostic reconstruction incomplete")
    return output


def representation_normalized(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    changes = []
    for row in output["roles"]["content"]:
        for brand in row["by_brand"]:
            if brand["audience_topics"] == []:
                value = ["unavailable"] if brand["outcome"] == "context_missing" else ["none"]
                brand["audience_topics"] = value
                changes.append({"case_id": row["case_id"], "brand_id": brand["brand_id"], "field": "audience_topics", "to": value})
            if brand["post_types"] == [] and brand["outcome"] == "classified":
                brand["post_types"] = ["other"]
                changes.append({"case_id": row["case_id"], "brand_id": brand["brand_id"], "field": "post_types", "to": ["other"]})
        if row["untracked_brand_promotions"] == []:
            row["untracked_brand_promotions"] = ["none"]
            changes.append({"case_id": row["case_id"], "field": "untracked_brand_promotions", "to": ["none"]})
    output["representation_normalization"] = {
        "policy": "Map empty classification arrays to the contract's explicit no-label sentinel; map empty classified post_types to other. This is deterministic and uses no model call or owner answer.",
        "changes": changes,
    }
    output["semantic_issues_before_normalization"] = output.pop("semantic_issues")
    output["semantic_issues"] = []
    return output


def main() -> None:
    run.verify()
    if sol.digest(sol.OWNER) != sol.OWNER_SHA256:
        raise ValueError("owner answer SHA changed")
    owner = json.loads(sol.OWNER.read_text(encoding="utf-8"))
    current = diagnostic_result()
    diagnostic_path = run.PRIVATE / "diagnostic-result.json"
    dump(diagnostic_path, current)
    normalized = representation_normalized(current)
    normalized_path = run.PRIVATE / "representation-normalized-diagnostic-result.json"
    dump(normalized_path, normalized)
    results = {
        "deepinfra": current,
        "deepinfra_normalized": normalized,
        "openinference": json.loads((five.PRIVATE / "result.json").read_text(encoding="utf-8")),
        "v4_1": json.loads((control.DEEPSEEK_DIR / "result.json").read_text(encoding="utf-8")),
        "sol": json.loads((control.SOL_DIR / "result.json").read_text(encoding="utf-8")),
    }
    labels = {
        "deepinfra": "V4 0731 / DeepInfra / 20-post (raw diagnostic)",
        "deepinfra_normalized": "V4 0731 / DeepInfra / 20-post (representation-normalized)",
        "openinference": "V4 0731 / OpenInference / 5-post",
        "v4_1": "V4.1 Flash direct / 20-post",
        "sol": "GPT-5.6 Sol / 20-post",
    }
    models: dict[str, Any] = {}
    for key, result in results.items():
        models[key] = {
            "label": labels[key],
            "score": control.score(result, owner, control.EXPECTED_CASES),
            "timing": control.timing(result),
            "semantic_issues": result.get("semantic_issues", []),
            "multi_label": {field: v4.label_metrics(result, owner, field) for field in ("post_types", "product_labels", "audience_topics", "geopolitical_modes", "untracked_brand_promotions")},
        }
    models["deepinfra"].update(cost_with_fee_usd=current["actual_billed_with_fee_usd"], official_status="failed")
    models["deepinfra_normalized"].update(cost_with_fee_usd=current["actual_billed_with_fee_usd"], official_status="diagnostic only")
    models["openinference"].update(cost_with_fee_usd=results["openinference"]["actual_billed_with_fee_usd"], official_status="passed shape")
    models["v4_1"].update(offpeak_cost_usd=results["v4_1"]["offpeak_cost_usd"], peak_cost_usd=results["v4_1"]["peak_cost_usd"], official_status="passed shape")
    models["sol"].update(cost_with_fee_usd=results["sol"]["actual_billed_with_fee_usd"], official_status="passed shape")
    artifact = {
        "schema_version": "u18-fresh40-v4-0731-deepinfra-r116-diagnostic/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sol.digest(run.CONTRACT),
        "diagnostic_result_sha256": sol.digest(diagnostic_path),
        "normalized_diagnostic_result_sha256": sol.digest(normalized_path),
        "owner_sha256": sol.OWNER_SHA256,
        "verdict": "fail",
        "failure_reasons": [
            "1-content returned Markdown-fenced JSON instead of a JSON object.",
            "The two content calls used empty arrays 60 times where the contract requires an explicit sentinel.",
            "The arm does not meet the user's 10x cost-reduction target against the incumbent control.",
        ],
        "semantic_finding": "After deterministic representation normalization, exact owner agreement is 70.6%; semantic capability is therefore better than the raw contract score suggests.",
        "models": models,
    }
    receipt = run.PRIVATE / "report-artifacts.json"
    if receipt.exists():
        prior = json.loads(receipt.read_text(encoding="utf-8"))
        json_path, md_path = Path(prior["json"]), Path(prior["markdown"])
    else:
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        json_path = run.ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-deepinfra-batch20-comparison.json"
        md_path = run.ROOT / "docs/analysis" / f"{stamp}-u18-v4-0731-deepinfra-batch20-comparison.md"
    dump(json_path, artifact)
    lines = [
        "# U18 V4 Flash 0731: DeepInfra 20-post comparison", "",
        "The DeepInfra 20-post arm **failed its frozen no-repair contract**. All four calls returned, but the first content call wrapped its JSON in a Markdown fence, and the content calls repeatedly used empty arrays instead of explicit `none` sentinels. This is mainly an output-adapter failure: deterministic representation normalization recovers all 40 rows and raises exact owner agreement from 63.6% to 70.6%.", "",
        "## Results", "",
        "| Model and execution | Status | Exact owner agreement | Matches / reviewed | Cost for 40 | Role-parallel time | Semantic issues |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for key in ("deepinfra", "deepinfra_normalized", "openinference", "v4_1", "sol"):
        data = models[key]
        total = data["score"]["totals"]
        if key == "v4_1":
            cost = f"${float(data['offpeak_cost_usd']):.6f} off-peak / ${float(data['peak_cost_usd']):.6f} peak"
        else:
            cost = f"${float(data['cost_with_fee_usd']):.6f} with fee"
        lines.append(f"| {data['label']} | {data['official_status']} | {total['agreement_pct']:.1f}% | {total['matches']} / {total['reviewed']} | {cost} | {data['timing']['estimated_parallel_role_seconds']:.1f}s | {len(data['semantic_issues'])} |")
    lines.extend(["", "## Agreement by axis", "", "| Axis | 0731 DeepInfra | 0731 OpenInference | V4.1 Flash | Sol |", "|---|---:|---:|---:|---:|"])
    for field in [*sol.BRAND_FIELDS, "untracked_brand_promotions"]:
        values = [models[key]["score"]["by_field"][field] for key in ("deepinfra_normalized", "openinference", "v4_1", "sol")]
        cells = [f"{value['agreement_pct']:.1f}% ({value['matches']}/{value['reviewed']})" for value in values]
        lines.append(f"| `{field}` | " + " | ".join(cells) + " |")
    lines.extend(["", "## Multi-label recovery", "", "| Axis | Model | Recall | Precision | Missing | Extra |", "|---|---|---:|---:|---:|---:|"])
    for field in ("post_types", "product_labels", "audience_topics", "geopolitical_modes", "untracked_brand_promotions"):
        for key in ("deepinfra_normalized", "openinference", "v4_1", "sol"):
            value = models[key]["multi_label"][field]
            lines.append(f"| `{field}` | {labels[key]} | {100 * value['recall']:.1f}% | {100 * value['precision']:.1f}% | {value['missing_labels']} | {value['extra_labels']} |")
    lines.extend([
        "", "## What failed", "",
        "- `1-content` stopped normally but returned its complete object inside a `json` Markdown fence; the official arm therefore fails before semantic scoring.",
        "- Deterministic fence removal recovered 20 rows for diagnosis. Across both content calls, the model emitted 60 empty arrays where the contract requires an explicit sentinel such as `none`.",
        "- Mapping only those representation choices to the explicit sentinels raises agreement to 70.6%. This exceeds the raw V4.1 and Sol scores on the incomplete owner controls, so the weights are not the main failure here.",
        "- The normalized arm's weakest reviewed axis remains post types at 19.6%; normalization improves audience topics to 46.2% and untracked-brand promotions to 71.0%.",
        "- DeepInfra was much faster than the earlier OpenInference route. It cost $0.003933 for 40 posts: about 3.1x cheaper than V4.1 off-peak and 6.2x cheaper at peak, short of the required 10x reduction.",
        "- No retry, label repair, fallback provider, media fetch, or database write occurred.",
        "", "## Decision", "",
        "Do not advance V4 Flash 0731 as-is: it fails strict output compliance and the 10x cost target. Its normalized semantic score is strong enough to retain as a fallback candidate if a 3–6x saving becomes acceptable. For the current requirement, test the next cheaper model with the same two-role workload and permit only a declared deterministic output adapter.",
        "", "## Limits", "",
        "Owner blanks are excluded, and some selected checkbox sets may be incomplete. This enriched, already-consumed challenge set measures development agreement rather than live prevalence-weighted accuracy.", "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    dump(run.PRIVATE / "report-artifacts.json", {"markdown": str(md_path), "json": str(json_path)})
    print(json.dumps({"markdown": str(md_path), "json": str(json_path), "verdict": "fail", "deepinfra": models["deepinfra"]}))


if __name__ == "__main__":
    main()
