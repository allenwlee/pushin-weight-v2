"""Closed provider projections. Private snapshots remain the audit authority.

Every nested object has an explicit field set. Adding a private field therefore
cannot silently change provider input. Source text is never paraphrased here.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

PROJECTION_VERSION = "headline-packet-v2"
FAMILIES = (
    "volume", "engagement", "post_type", "product_label", "sentiment",
    "china_nationalism", "us_nationalism", "language", "unsanctioned_flags",
    "account_role", "corpus_phrases",
)
TAXONOMY_AXES = (
    "post_types", "product_labels", "sentiment", "china_nationalism",
    "us_nationalism", "unsanctioned_flags", "language", "account_role",
)
COVERAGE_FIELDS = ("state", "status", "fraction", "known_backlog_overlap")
ENRICHMENT_FIELDS = (
    "total_post_count", "translation_succeeded_count", "classification_succeeded_count",
    "fully_enriched_count", "translation_status", "classification_status",
)


def evidence_support_spans(evidence: Mapping[str, Any]) -> list[dict[str, str]]:
    """Name exact source passages without asking the model to reproduce them.

    Concatenating a field's spans recovers its text exactly. Equal translated
    fields are represented once; existing text_aliases retain their provenance.
    """
    spans = []
    seen_text = set()
    for field in ("excerpt", "original_text", "text_en", "text_zh_cn"):
        value = evidence.get(field)
        if not isinstance(value, str) or not value or value in seen_text:
            continue
        seen_text.add(value)
        start = 0
        while start < len(value):
            end = min(len(value), start + 400)
            if end < len(value):
                # A whitespace cut can detach "it ran 4.3x faster" from the
                # preceding product name. Prefer a complete sentence while
                # keeping concatenation byte-for-byte identical.
                sentence_ends = [
                    start + match.end()
                    for match in re.finditer(r"[.!?]\s+|[。！？]\s*", value[start:end])
                    if start + match.end() >= start + 200
                ]
                if sentence_ends:
                    end = sentence_ends[-1]
                else:
                    boundary = value.rfind(" ", start + 200, end)
                    if boundary >= 0:
                        end = boundary + 1
            text = value[start:end]
            identity = json.dumps([evidence["evidence_id"], field, start, text], ensure_ascii=False)
            spans.append({"span_id": "s:" + hashlib.sha256(identity.encode()).hexdigest()[:20],
                          "source_field": field, "text": text})
            start = end
    return spans


def pick(source: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in fields if key in source}


def project_evidence(evidence: Mapping[str, Any]) -> dict[str, Any]:
    row = pick(evidence, (
        "evidence_id", "excerpt", "created_at", "source_language",
        "translation_status", "classification_status", "first_party_role",
        "roles", "role", "evidence_role", "occurrence_source", "is_quote", "is_retweet",
        "excerpt_truncated",
    ))
    aliases = {}
    for field in ("original_text", "text_en", "text_zh_cn"):
        value = evidence.get(field)
        if not value:
            continue
        identical = next((key for key in ("excerpt", "original_text", "text_en")
                          if key in row and row[key] == value), None)
        if identical:
            aliases[field] = identical
        else:
            row[field] = value
    if aliases:
        row["text_aliases"] = aliases
    if row.get("first_party_role") in {"official", "staff"}:
        row.update(pick(evidence, ("handle_snapshot",)))
    if "taxonomy" in evidence:
        row["taxonomy"] = {
            key: pick(value, ("status", "values", "provenance"))
            for key, value in evidence["taxonomy"].items()
            if key in TAXONOMY_AXES
        }
    if "brand_relevance" in evidence:
        row["brand_relevance"] = pick(evidence["brand_relevance"], (
            "status", "matched_aliases", "other_brand_keys", "reason",
        ))
    if "source_flags" in evidence:
        row["source_flags"] = pick(evidence["source_flags"], ("official", "post_kind", "occurrence_source"))
    return row


def project_baseline_context(value: Mapping[str, Any]) -> dict[str, Any]:
    return pick(value, ("kind", "start_at", "end_at", "historic_norm_wording_allowed"))


def project_shape(shape: Mapping[str, Any]) -> dict[str, Any]:
    # Legacy shape is retained until the typed finance facts supersede it.
    row = pick(shape, ("direction", "start_segment_post_count", "end_segment_post_count",
                       "total_change_pct", "comparison_state"))
    for field in ("peak", "trough"):
        if isinstance(shape.get(field), Mapping):
            row[field] = pick(shape[field], ("at", "post_count"))
    if isinstance(shape.get("dominant_transition"), Mapping):
        row["dominant_transition"] = pick(shape["dominant_transition"], (
            "from", "to", "post_count_change", "net_change_share_pct",
        ))
    if row:
        row["basis"] = "within_window_buckets_not_prior_period"
    return row


def project_dossier(dossier: Mapping[str, Any], *, rank: bool = False) -> dict[str, Any]:
    result = pick(dossier, (
        "brand_key", "display_name_en", "display_name_zh_cn", "outcome",
        "corpus_signals_status",
    ))
    result["projection_version"] = PROJECTION_VERSION
    comparison = dossier.get("comparison_status") or {}
    allowed = comparison.get("allowed") is True
    result["comparison_status"] = pick(comparison, ("allowed", "suppression_reasons"))
    for field in ("selected_coverage", "prior_coverage"):
        if field in comparison and (field != "prior_coverage" or allowed):
            result["comparison_status"][field] = pick(comparison[field], COVERAGE_FIELDS)
    coverage = dossier.get("enrichment_coverage") or {}
    result["enrichment_coverage"] = pick(coverage, ENRICHMENT_FIELDS)
    if isinstance(coverage.get("newest_30m"), Mapping):
        result["enrichment_coverage"]["newest_30m"] = pick(coverage["newest_30m"], ENRICHMENT_FIELDS)

    result["family_summaries"] = {}
    for family, summary in (dossier.get("family_summaries") or {}).items():
        if family not in FAMILIES:
            continue
        fields = ("status", "covered_post_count", "current_leader", "unavailable_reason")
        if allowed:
            fields += ("largest_change",)
        result["family_summaries"][family] = pick(summary, fields)

    scopes: dict[str, dict[str, Any]] = {}
    scope_ids: dict[str, str] = {}
    facts = []
    interval = dossier.get("source_row_provenance") or {}
    finance = dossier.get("finance_context") or {}
    for fact in [*dossier.get("facts", []), *finance.get("facts", [])]:
        metric = str(fact.get("metric") or "")
        is_change = metric.endswith(("_change_pct", "_change_pp"))
        supplied_scope = fact.get("fact_scope") or {}
        if is_change and not supplied_scope and not allowed:
            continue
        current_coverage = fact.get("coverage_scope") or {}
        scope = {
            "brand_key": str(dossier["brand_key"]),
            **pick(interval, ("start_at", "end_at")),
            "basis": "prior_period_change" if is_change else "selected_window",
            "denominator": current_coverage.get("covered_post_count"),
            "coverage": pick(current_coverage, ("status", "covered_post_count", "total_post_count")),
        }
        if supplied_scope:
            scope = pick(supplied_scope, ("brand_key", "start_at", "end_at", "basis", "denominator"))
            scope["coverage"] = pick(supplied_scope.get("coverage") or {},
                                     ("status", "covered_post_count", "total_post_count"))
        elif is_change and scope.get("start_at") and scope.get("end_at"):
            start = datetime.fromisoformat(str(scope["start_at"]))
            end = datetime.fromisoformat(str(scope["end_at"]))
            scope["baseline_start_at"] = (start - (end - start)).isoformat()
            scope["baseline_end_at"] = scope["start_at"]
        scope_json = json.dumps(scope, sort_keys=True)
        scope_ref = scope_ids.setdefault(scope_json, f"s{len(scope_ids) + 1}")
        scopes[scope_ref] = scope
        projected = pick(fact, ("fact_id", "family", "metric", "label_key", "unit"))
        projected.update(value=fact.get("source_value", fact.get("current_value")), scope_ref=scope_ref)
        if is_change:
            projected.update(pick(fact, ("current_value", "baseline_value", "direction")))
        facts.append(projected)
    if rank:
        # The complete source/measurement context stays in editor and critic.
        # Keep one fact per family, giving every brand a volume citation even
        # when it has zero evidence or incomplete collection.
        seen = set()
        salient = []
        for fact in facts:
            if fact.get("family") not in seen:
                salient.append(fact)
                seen.add(fact.get("family"))
        activity = [fact for fact in facts if fact.get("family") == "activity" and fact.get("metric") in {
            "distinct_authors", "overall_rate_change_pct", "recent_rate_change_pct",
        }]
        facts = (salient[:1] + activity + [fact for fact in salient[1:] if fact.get("family") != "activity"])[:8]
        refs = {fact["scope_ref"] for fact in facts}
        scopes = {key: value for key, value in scopes.items() if key in refs}
    result["scopes"] = scopes
    result["facts"] = facts
    if finance:
        result["finance_context"] = {
            "version": finance.get("version"),
            "historical_status": pick(finance.get("historical_status") or {}, (
                "policy", "timezone", "state", "reason", "sample_size", "start_at", "end_at",
            )),
            "shape_status": pick(finance.get("shape_status") or {}, ("state", "reason", "completed_bucket_count")),
        }
        if not rank:
            result["finance_context"]["phases"] = [
                pick(phase, ("kind", "start_at", "end_at", "fact_ids", "provisional"))
                for phase in finance.get("phases", [])[:3]
            ]

    result["corpus_signals"] = []
    for signal in dossier.get("corpus_signals", [])[:(3 if rank else 8)]:
        row = pick(signal, (
            "corpus_signal_id", "phrase", "prevalence", "peer_brand_count",
            "representative_evidence_ids", "representative_excerpt",
        ))
        if allowed:
            row.update(pick(signal, ("prior_prevalence",)))
        if isinstance(signal.get("burst_interval"), Mapping):
            row["burst_interval"] = pick(signal["burst_interval"], ("start_bucket", "end_bucket"))
        result["corpus_signals"].append(row)
    result["evidence"] = [project_evidence(row) for row in dossier.get("evidence", [])]
    if rank:
        result["evidence"] = [pick(row, (
            "evidence_id", "excerpt", "source_language", "created_at", "first_party_role",
            "brand_relevance",
        )) for row in result["evidence"][:2]]
    elif not finance and dossier.get("shape_summary"):
        result["shape_summary"] = project_shape(dossier["shape_summary"])
    result["evidence_scope"] = {
        "selected_source_count": len(result["evidence"]),
        "collected_post_count": next((fact["value"] for fact in facts
                                      if fact.get("metric") == "post_count"), None),
        "selection": "bounded_nonrandom_examples",
        "population_inference_allowed": False,
    }
    return result
