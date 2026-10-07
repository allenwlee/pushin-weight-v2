"""Present the shared database comparison in the retained four-panel report."""

from collections import Counter

from core.measurement_taxonomy import require

PANELS = {
    ("x", "post_volume"): "posts",
    ("hf", "downloads"): "hf",
    ("openrouter", "total_tokens"): "openrouter",
    ("arena", "rating"): "arena",
    ("arena", "rank"): "rank",
}


def report_from_comparison(comparison):
    """Adapt presentation only; never recalculate measurements or baselines."""
    selected = {}
    for line in comparison["lines"]:
        panel = PANELS.get((line["source"], line["metric_key"]))
        if panel:
            require(panel not in selected, f"offline report needs one {panel} line")
            selected[panel] = line
    points = {
        p["date"]: {"date": p["date"], **dict.fromkeys(PANELS.values())}
        for p in comparison["lines"][0]["points"]
    }
    source_dates = set()
    for panel, line in selected.items():
        for p in line["points"]:
            raw = p["raw_value"]
            evidence = p.get("evidence", [])
            identifiers = [
                e["source_identifier"] for e in evidence if "source_identifier" in e
            ]
            revisions = [e["source_as_of"] for e in evidence if e.get("source_as_of")]
            if panel == "posts":
                value = raw
            elif panel == "hf":
                value = {
                    "value": raw,
                    "selected": p.get("selected_count", len(line["mapping_ids"])),
                    "successful": p.get("reported_count", 0),
                    "observed_at": p.get("observed_at"),
                }
            elif panel == "openrouter":
                source_dates.update(revisions)
                value = {
                    "value": raw,
                    "models": identifiers,
                    "as_of": max(revisions) if revisions else None,
                    "other_tokens": None,
                    "unmapped_models": None,
                }
            else:
                related = p.get("related_values", {})
                value = (
                    None
                    if raw is None
                    else {
                        "value": raw,
                        "model": p.get("selected_source_identifier")
                        or next(iter(identifiers), None),
                        "published_at": p.get("source_date"),
                        "lower": related.get("rating_lower"),
                        "upper": related.get("rating_upper"),
                        "votes": related.get("vote_count"),
                        "proxy_label": p.get("proxy_label"),
                        "segment": p.get("segment"),
                        "model_changed": p.get("model_changed", False),
                        "measured_subject": p.get("measured_subject"),
                        "percent_change": p.get("percent_change"),
                    }
                )
            points[p["date"]][panel] = value
    statuses = [
        {
            "source": source,
            "observed_at": row["last_attempt_at"],
            "status": row["status"],
            "error": row["error_code"],
        }
        for source, row in comparison["collection_status"].items()
    ]
    for line in comparison["lines"]:
        coverage = Counter(p["coverage"] for p in line["points"])
        statuses.append(
            {
                "source": f"{line['label']} / {line['subject_id']}",
                "observed_at": "scope",
                "status": f"{line['scope']}; {line['measurement_kind']}; {line['window_mode']}; "
                + ", ".join(f"{k}={v}" for k, v in sorted(coverage.items()))
                + "; timing unknown where source does not publish it",
                "error": None,
            }
        )
    return {
        "schema_version": 1,
        "synthetic": False,
        "generated_at": comparison["generated_at"],
        "start_date": comparison["start_date"],
        "end_date": comparison["end_date"],
        "series": [
            {
                "brand_id": comparison["contract_id"],
                "label": comparison["title"],
                "label_zh": comparison["title"],
                "hf_selected": len(selected.get("hf", {}).get("mapping_ids", [])),
                "points": list(points.values()),
            }
        ],
        "statuses": statuses,
        "unresolved": {
            "note": "This report uses reviewed per-line scopes. Unmapped platform totals are unavailable here, not zero.",
            "line_scopes": [
                {k: line[k] for k in ("label", "subject", "scope", "baseline")}
                for line in comparison["lines"]
            ],
        },
        "openrouter_as_of": sorted(source_dates),
        "arena_config": selected.get("arena", {})
        .get("source_configuration", {})
        .get("config"),
        "database_comparison": comparison,
    }
