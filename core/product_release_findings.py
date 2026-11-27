"""Validate source-backed findings from the initial classifier, without I/O.

This is a transport/evidence contract, not proof of novelty, ownership or exact
Product identity. A finding key identifies an evidence packet, never a Product.
The caller supplies tested resource limits and the selected channel vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.official_company_offerings import TYPES

SCHEMA = "pulse-release-findings-v1"
CATEGORIES = frozenset(TYPES)
NOVELTIES = frozenset({"new_release", "availability_update", "historical_release", "unresolved"})
# Verification/ownership claims belong to the independently evidenced resolver.
CLAIM_KINDS = frozenset({
    "announcement", "availability", "repository_created", "release_report",
    "release_signal", "source_stated_release", "first_observed_usage", "rumor", "release_context",
})
_FINDING_FIELDS = {"observed_name", "version", "variant", "novelty", "category", "assertions"}
_ASSERTION_FIELDS = {
    "claim_kind", "assertion_text", "source_excerpt", "source_locator", "access_channel", "effective",
}
_TEMPORAL_FIELDS = {
    "effective_at", "effective_date", "effective_year", "effective_month", "not_before", "not_after",
}


def discussion_only_reason(finding):
    """Recognize explicit ranking-only or training-base assertions for the named offering."""
    name = finding.get("observed_name")
    excerpts = {a["source_excerpt"].strip() for a in finding["assertions"]}
    if not name or not excerpts:
        return None
    subject = re.escape(name)
    ranking = re.compile(r"(?:most[ -]used|top[ -]ranked)\s+(?:model|llm)\s*:\s*(?:[\w.-]+/)?" + subject + r"[.!]?", re.IGNORECASE)
    training = re.compile(r"\b(?:released|launched|introduced)\s+[^,;!?\n]+?,\s*"
                          r"(?:trained|fine[- ]?tuned)\s+(?:with [^,;.!?]+? )?on\s+(?P<subject>" + subject + r")[.!]?$", re.IGNORECASE)
    for excerpt in excerpts:
        if ranking.fullmatch(excerpt):
            continue
        match = training.search(excerpt)
        if not match or name.casefold() in excerpt[:match.start("subject")].casefold():
            return None
    return "The saved source identifies this offering only as a ranking entry or the training base of another release."


@dataclass(frozen=True)
class FindingLimits:
    """Explicit caller policy; fixture limits do not select production budgets."""

    max_findings: int
    max_assertions: int
    max_text_chars: int

    def __post_init__(self):
        for value in (self.max_findings, self.max_assertions, self.max_text_chars):
            if type(value) is not int or value < 1:
                raise ValueError("invalid_finding_limits")


def _shape(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid_finding_shape")


def _text(value, maximum, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("invalid_finding_text")
    return value


def _choice(value, choices, *, nullable=False):
    if value is None and nullable:
        return None
    if not isinstance(value, str) or value not in choices:
        raise ValueError("unsupported_finding_value")
    return value


def _instant(value):
    _text(value, 64)
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("finding_datetime_needs_offset")
    return parsed


def _effective(value):
    _shape(value, {"precision", "value", "timezone"})
    precision = _choice(value["precision"], {"unknown", "datetime", "day", "month", "year", "range"})
    zone = _text(value["timezone"], 128, nullable=True)
    if zone is not None:
        try:
            ZoneInfo(zone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("unknown_finding_timezone") from exc
    result = dict.fromkeys(_TEMPORAL_FIELDS)
    result.update(effective_precision=precision, event_timezone=zone)
    raw = value["value"]
    if precision == "unknown":
        if raw is not None:
            raise ValueError("unknown_finding_date_has_value")
    elif precision == "datetime":
        result["effective_at"] = _instant(raw).isoformat()
    elif precision == "day":
        if not isinstance(raw, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) is None:
            raise ValueError("invalid_finding_day")
        result["effective_date"] = date.fromisoformat(raw).isoformat()
    elif precision in {"month", "year"}:
        pattern = r"\d{4}-\d{2}" if precision == "month" else r"\d{4}"
        if not isinstance(raw, str) or re.fullmatch(pattern, raw) is None:
            raise ValueError("invalid_finding_period")
        year = int(raw[:4])
        month = int(raw[5:]) if precision == "month" else 1
        date(year, month, 1)
        result["effective_year"] = year
        if precision == "month":
            result["effective_month"] = month
    else:
        _shape(raw, {"not_before", "not_after"})
        if all(item is None for item in raw.values()):
            raise ValueError("empty_finding_date_range")
        bounds = {key: None if item is None else _instant(item) for key, item in raw.items()}
        if bounds["not_before"] is not None and bounds["not_after"] is not None and bounds["not_before"] > bounds["not_after"]:
            raise ValueError("reversed_finding_date_range")
        result.update({key: item.isoformat() if item is not None else None for key, item in bounds.items()})
    return result


def _source(value):
    _shape(value, {"kind", "id"})
    kind = _choice(value["kind"], {"post", "observation"})
    if kind == "post":
        _text(value["id"], 64)
    elif type(value["id"]) is not int or value["id"] <= 0:
        raise ValueError("invalid_finding_observation")
    return dict(value)


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def finding_identity(source, *, observed_name, version, variant, assertions):
    """Identity of validated source passages, before mapping keys to URLs."""
    anchors = sorted({(fact["source_locator"], fact["source_excerpt"], fact["claim_kind"]) for fact in assertions})
    packet = {"schema": SCHEMA, "source": _source(source), "observed_name": observed_name,
              "version": version, "variant": variant, "anchors": anchors}
    return hashlib.sha256(_encoded(packet).encode()).hexdigest()


def cited_publisher_handle(name, excerpt):
    """A handle directly paired with the cited publisher in its source passage."""
    if not isinstance(name, str) or not name or not isinstance(excerpt, str):
        return None
    matches = {handle.lower() for handle in re.findall(
        rf"(?<![\w@]){re.escape(name)}\s*\(@([A-Za-z0-9_]{{1,15}})\)", excerpt
    )}
    return matches.pop() if len(matches) == 1 else None


def _issuer(value, *, passages, limits):
    if value is None:
        return None
    _shape(value, {"relation", "source_locator", "source_excerpt", "observed_name"})
    relation = _choice(value["relation"], {"source_author", "attributed_party"})
    locator = _text(value["source_locator"], limits.max_text_chars)
    excerpt = _text(value["source_excerpt"], limits.max_text_chars)
    name = _text(value["observed_name"], limits.max_text_chars, nullable=True)
    if locator not in passages or excerpt not in passages[locator]:
        raise ValueError("issuer_evidence_not_supplied")
    if name is not None and name not in excerpt:
        raise ValueError("issuer_name_not_supplied")
    if relation == "source_author" and locator not in {"post", "translation"}:
        raise ValueError("issuer_author_is_not_primary_source")
    if relation == "attributed_party" and name is None:
        raise ValueError("issuer_party_needs_source_name")
    return {"relation": relation, "source_locator": locator, "source_excerpt": excerpt, "observed_name": name}


def _lineage(value, *, observed_name, passages, limits):
    if not isinstance(value, list) or len(value) > limits.max_assertions:
        raise ValueError("finding_lineage_limit")
    records = []
    keys = set()
    for relation in value:
        _shape(relation, {"relationship_kind", "parent_observed_name", "source_locator", "source_excerpt"})
        kind = _choice(relation["relationship_kind"], {"new_version", "finetune", "adapter", "quantized", "merge"})
        parent = _text(relation["parent_observed_name"], limits.max_text_chars)
        locator = _text(relation["source_locator"], limits.max_text_chars)
        excerpt = _text(relation["source_excerpt"], limits.max_text_chars)
        if locator not in passages or excerpt not in passages[locator]:
            raise ValueError("lineage_evidence_not_supplied")
        if not observed_name or observed_name not in excerpt or parent not in excerpt:
            raise ValueError("lineage_names_not_supplied")
        record = {"relationship_kind": kind, "parent_observed_name": parent,
                  "source_locator": locator, "source_excerpt": excerpt}
        key = _encoded(record)
        if key in keys:
            raise ValueError("duplicate_lineage_evidence")
        keys.add(key)
        records.append(record)
    return records


def parse_release_findings(value, *, source, passages, allowed_channels, limits):
    """Return strict, JSON-compatible records for the shared evidence writer.

    ``passages`` contains only evidence actually supplied to the classifier;
    locators are keys in that map, not model-selected URLs to fetch. Expanded
    date fields are ISO strings/integers for deterministic archive serialization.
    The database writer converts them to typed values and validates live codes.
    """
    if not isinstance(limits, FindingLimits):
        raise TypeError("missing_finding_limits")
    canonical_source = _source(source)
    if not isinstance(passages, dict) or any(
        not isinstance(key, str) or not key or not isinstance(text, str)
        for key, text in passages.items()
    ):
        raise ValueError("invalid_finding_passages")
    if not isinstance(allowed_channels, (tuple, list, set, frozenset)):
        raise TypeError("invalid_channel_vocabulary")
    channels = {_text(code, 64) for code in allowed_channels}
    _shape(value, {"schema", "findings"})
    if value["schema"] != SCHEMA or not isinstance(value["findings"], list):
        raise ValueError("unknown_finding_contract")
    if len(value["findings"]) > limits.max_findings:
        raise ValueError("finding_count_limit")
    normalized = []
    keys = set()
    for finding in value["findings"]:
        if not isinstance(finding, dict):
            raise TypeError("invalid_finding_shape")
        _shape({key: value for key, value in finding.items() if key not in {"issuer_evidence", "lineage_evidence", "family_evidence"}}, _FINDING_FIELDS)
        issuer = _issuer(finding.get("issuer_evidence"), passages=passages, limits=limits)
        names = {key: _text(finding[key], limits.max_text_chars, nullable=True)
                 for key in ("observed_name", "version", "variant")}
        lineage = _lineage(finding.get("lineage_evidence", []), observed_name=names["observed_name"],
                           passages=passages, limits=limits)
        family = finding.get("family_evidence")
        if family is not None:
            _shape(family, {"name", "source_locator", "source_excerpt"})
            family_name = _text(family["name"], limits.max_text_chars)
            locator = _text(family["source_locator"], limits.max_text_chars)
            excerpt = _text(family["source_excerpt"], limits.max_text_chars)
            if (locator not in passages or excerpt not in passages[locator] or family_name not in excerpt
                    or not names["observed_name"] or names["observed_name"] not in excerpt):
                raise ValueError("family_evidence_not_supplied")
            family = {"name": family_name, "source_locator": locator, "source_excerpt": excerpt}
        novelty = _choice(finding["novelty"], NOVELTIES)
        category = _choice(finding["category"], CATEGORIES, nullable=True)
        assertions = finding["assertions"]
        if not isinstance(assertions, list) or not assertions or len(assertions) > limits.max_assertions:
            raise ValueError("finding_assertion_limit")
        facts = []
        fact_keys = set()
        cited_passages = []
        for assertion in assertions:
            _shape(assertion, _ASSERTION_FIELDS)
            locator = _text(assertion["source_locator"], limits.max_text_chars)
            excerpt = _text(assertion["source_excerpt"], limits.max_text_chars)
            if locator not in passages or excerpt not in passages[locator]:
                raise ValueError("finding_evidence_not_supplied")
            cited_passages.append(passages[locator])
            fact = {
                "claim_kind": _choice(assertion["claim_kind"], CLAIM_KINDS),
                "assertion_text": _text(assertion["assertion_text"], limits.max_text_chars),
                "source_excerpt": excerpt, "source_locator": locator,
                "access_channel": _choice(assertion["access_channel"], channels, nullable=True),
                **_effective(assertion["effective"]),
            }
            fact_key = _encoded(fact)
            if fact_key in fact_keys:
                raise ValueError("duplicate_finding_assertion")
            fact_keys.add(fact_key)
            facts.append(fact)
        for name in names.values():
            if name is not None and not any(name in passage for passage in cited_passages):
                raise ValueError("finding_name_not_supplied")
        finding_key = finding_identity(canonical_source, **names, assertions=facts)
        if finding_key in keys:
            raise ValueError("duplicate_finding_key")
        keys.add(finding_key)
        normalized.append({
            "finding_key": finding_key, **names, "novelty": novelty, "category": category,
            "issuer_evidence": issuer,
            "lineage_evidence": lineage, "family_evidence": family,
            "brand_id": None, "brand_candidate_id": None, "candidate_repo_id": None,
            "assertions": tuple(facts),
        })
    return tuple(normalized)
