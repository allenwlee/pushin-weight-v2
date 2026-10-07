"""Code-owned source labels and passages; shared by selection and writing."""

import re
from copy import deepcopy

from monitor.headline_grounding import SOURCE_READING_RULES
from monitor.trend_narrative_packet import evidence_support_spans
from x_monitor.structured_output import closed_object

GROUNDING_INSTRUCTIONS = (
    """Read the closed evidence packet FIRST, then choose claims.
Use no event facts from memory or unread links. Select source IDs before writing.
Source labels such as S001 are exact, code-owned references: copy only supplied
labels into source_check.support.post_id. Never reconstruct X post numbers.
Code derives post_ids from source_check; do not generate a second source list.
For every worthy event or written article, return a nonempty source_check BEFORE
summary/copy: support, action, target, status and number_ownership. Code supplies
actor from the exact source field's author; do not generate actor yourself.
Each support object chooses ONE supplied post and ONE source_field, with exact
span_ids from that field and brand_keys from that post's collected matches.
Use [] for brand_keys when no supplied brand is relevant. Never add a mentioned
brand absent from that post's supplied choices. Code assembles event brand_keys
from these support objects; do not generate a separate event brand_keys list.
Each source_check entry is one claim owned by one post and its exact passages.
A story can combine posts, but never transfer one post's actor/action/numbers to
another. Keep conflicts and uncertainty explicit. Do not invent facts to fill fields.
source_spans preserve original_text (current author), stored_quote (quoted speaker)
and local_parent (reply context). The latter two are not the current author's words.
Unknown quoted/parent identity stays unknown. brand_keys are collected matches,
not proof of which company performed an action. Preserve exact model/version names.
An original author's comparison or benchmark claim is not the quoted developer's
announcement. Use separate source checks for separate speakers or source fields.
Repeated posts by one account, or unread links to different outlets, do not
establish independent confirmation. Describe the supplied reports as reports.
Platform/API availability, a reseller promotion and a developer's model launch are
different developments. A recent post is not proof its subject launched that day.
Use an explicit event date if supplied; otherwise occurred_at is first-observed
posting time for depreciation, not a claimed launch date. Image URLs are not pixels.
For source-reported numbers, record owner, meaning, units and qualifiers in
number_ownership for EVERY figure used in the event summary or final copy;
use 'none' only when that claim contributes no numeric figure. Include model
version/size ownership too: numeric copy with an all-'none' audit is rejected.
Write each number note as owner, source figure, meaning, unit and qualifier.
The supplied posts have no verified independence assessment. Never call their
reports or sources independent in summary, editorial reason or final copy.
Chart measurements
remain separate. A third-party post reporting someone else's announcement has
status=source_report, not announcement. Reserve announcement for the originating
speaker's own action, including a supplied quote from that speaker.
"""
    + SOURCE_READING_RULES
)


def source_spans(source):
    spans = []
    for field in ("original_text", "stored_quote", "local_parent"):
        text = source.get(field)
        if not text:
            continue
        rows = evidence_support_spans(
            {
                "evidence_id": f"{source['id']}:{field}",
                "original_text": text,
            }
        )
        spans.extend({**row, "source_field": field} for row in rows)
    return spans


def source_projection(sources):
    projected, mapping = [], {}
    fields = {
        "created_at",
        "source_language",
        "author_handle",
        "author_id",
        "brand_keys",
        "images",
        "is_quote",
        "is_retweet",
        "is_reply",
        "parent_post_id",
        "parent_author_handle",
        "quoted_post_id",
        "quoted_author_handle",
        "excerpt_truncated",
        "first_party_role",
        "roles",
        "evidence_role",
        "brand_relevance",
    }
    for index, source in enumerate(sources, 1):
        label = f"S{index:03d}"
        mapping[label] = source["id"]
        row = {
            key: value
            for key, value in source.items()
            if key in fields and value not in (None, "", [])
        }
        row.update(id=label, source_spans=source_spans(source))
        projected.append(row)
    return projected, mapping


def support_options(projected):
    return [
        {
            "post_id": source["id"],
            "source_field": field,
            "span_ids": [
                s["span_id"]
                for s in source["source_spans"]
                if s["source_field"] == field
            ],
            "brand_keys": source.get("brand_keys", []),
            "speaker": source.get(
                {
                    "original_text": "author_handle",
                    "stored_quote": "quoted_author_handle",
                    "local_parent": "parent_author_handle",
                }[field]
            )
            or "unknown speaker",
        }
        for source in projected
        for field in dict.fromkeys(s["source_field"] for s in source["source_spans"])
    ]


def source_provenance(projected):
    groups = {}
    for source in projected:
        author = source.get("author_id") or source.get("author_handle")
        if author:
            groups.setdefault(author, []).append(source["id"])
    return {
        "independent_confirmation": "not_assessed",
        "same_author_post_groups": [ids for ids in groups.values() if len(ids) > 1],
        "rule": "Repeated posts in a group are one reporting source. Different groups do not establish independent confirmation.",
    }


def bound_schema(model, options):
    schema = deepcopy(model.model_json_schema())
    root = schema["$defs"]["Event"] if "Event" in schema.get("$defs", {}) else schema
    root["properties"].pop("post_ids")
    root["properties"] = {
        "source_check": root["properties"]["source_check"],
        **{
            key: value
            for key, value in root["properties"].items()
            if key != "source_check"
        },
    }
    if "source_check" not in root["required"]:
        root["required"].append("source_check")
    # Bind the complete support object, as headline schemas bind a complete
    # brand/source alternative. A packet-wide enum cannot express ownership.
    variants = []
    for option in options:
        brands = {"type": "array", "maxItems": 10, "items": {"type": "string"}}
        if option["brand_keys"]:
            brands["items"]["enum"] = option["brand_keys"]
        else:
            brands["maxItems"] = 0
        variants.append(
            closed_object(
                {
                    "post_id": {"type": "string", "enum": [option["post_id"]]},
                    "source_field": {
                        "type": "string",
                        "enum": [option["source_field"]],
                    },
                    "brand_keys": brands,
                    "span_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 4,
                        "items": {"type": "string", "enum": option["span_ids"]},
                    },
                }
            )
        )
    claim = schema["$defs"]["SourceClaim"]
    claim["properties"] = {
        "support": {"anyOf": variants} if variants else {"type": "null"},
        **{
            key: value
            for key, value in claim["properties"].items()
            if key not in {"post_id", "source_field", "brand_keys", "span_ids", "actor"}
        },
    }
    if not variants:
        root["properties"]["source_check"]["maxItems"] = 0
    else:
        root["properties"]["source_check"]["minItems"] = 1
    if "Event" in schema.get("$defs", {}):
        root["properties"].pop("brand_keys")
    else:
        root["properties"]["supported_copy"] = {"$ref": "#/$defs/SupportedCopy"}
        root["properties"] = {
            key: root["properties"][key]
            for key in (
                "source_check",
                "supported_copy",
                *(
                    k
                    for k in root["properties"]
                    if k not in {"source_check", "supported_copy"}
                ),
            )
        }
    return schema


def bind_editor_availability(schema, packet):
    """Unavailable facts/identities cannot become model-selected claims."""
    root = schema["$defs"]["Event"]["properties"]
    facts = [
        fact["fact_id"]
        for chart in packet.get("chart_context", [])
        for fact in chart["facts"]
    ]
    if facts:
        root["chart_fact_ids"]["items"]["enum"] = facts
    else:
        root["chart_fact_ids"]["maxItems"] = 0
        root["chart_support"]["enum"] = ["unavailable"]
    people = [str(person["id"]) for person in packet.get("people", [])]
    if people:
        root["person_ids"]["items"]["enum"] = people
    else:
        root["person_ids"]["maxItems"] = 0
    stories = [str(story["id"]) for story in packet.get("stories", [])]
    root["story_id"] = (
        {"anyOf": [{"type": "string", "enum": stories}, {"type": "null"}]}
        if stories
        else {"type": "null"}
    )
    if not stories:
        root["change"]["enum"] = ["new"]
    return schema


def normalize_reply(result, request, *, editor):
    """Validate wire ownership before restoring IDs; never repair guessed brands."""
    result = deepcopy(result)
    entries = result.get("events") if editor else [result]
    if not isinstance(entries, list) or any(not isinstance(e, dict) for e in entries):
        raise ValueError("malformed model entries")
    options = {(o["post_id"], o["source_field"]): o for o in request["source_bindings"]}
    for entry in entries:
        if "post_ids" in entry:
            raise ValueError("post IDs must come from source support")
        if editor and "brand_keys" in entry:
            raise ValueError("event brands must come from source support")
        checks = entry.get("source_check")
        if not isinstance(checks, list) or not checks:
            raise ValueError("missing source check")
        brands, cited = set(), []
        for claim in checks:
            if not isinstance(claim, dict):
                raise TypeError("invalid source support")
            support = claim.pop("support", None)
            if not isinstance(support, dict) or set(support) != {
                "post_id",
                "source_field",
                "brand_keys",
                "span_ids",
            }:
                raise ValueError("invalid source support")
            if any(k in claim for k in support):
                raise ValueError("duplicate source support fields")
            if not isinstance(support["post_id"], str) or not isinstance(
                support["source_field"], str
            ):
                raise TypeError("invalid source support")
            allowed = options.get((support["post_id"], support["source_field"]))
            if allowed is None:
                raise ValueError("unknown source support")
            if "actor" in claim:
                raise ValueError("claim actor is code-owned")
            for field, low, high in (("span_ids", 1, 4), ("brand_keys", 0, 10)):
                values = support[field]
                if (
                    not isinstance(values, list)
                    or not low <= len(values) <= high
                    or any(not isinstance(v, str) for v in values)
                    or len(set(values)) != len(values)
                    or not set(values) <= set(allowed[field])
                ):
                    raise ValueError("source support ownership mismatch")
            claim.update(support)
            claim["actor"] = allowed["speaker"]
            if support["post_id"] not in cited:
                cited.append(support["post_id"])
            brands.update(support["brand_keys"])
        entry["post_ids"] = cited
        if editor:
            entry["brand_keys"] = sorted(brands)
        elif not isinstance(entry.get("supported_copy"), dict):
            raise ValueError("missing supported copy")
    return restore_sources(result, request["source_ids"])


def strict_schema(schema):
    """Close every object and require explicit values, including defaulted fields."""
    if isinstance(schema, list):
        return [strict_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    result = {
        key: strict_schema(value) for key, value in schema.items() if key != "default"
    }
    if result.get("type") == "object":
        result["additionalProperties"] = False
        result["required"] = list(result.get("properties", {}))
    return result


def restore_sources(result, mapping):
    if isinstance(result, list):
        return [restore_sources(row, mapping) for row in result]
    if not isinstance(result, dict):
        return result
    return {
        key: (
            [mapping.get(value, value) for value in row]
            if key == "post_ids" and isinstance(row, list)
            else mapping.get(row, row)
            if key == "post_id" and isinstance(row, str)
            else restore_sources(row, mapping)
        )
        for key, row in result.items()
    }


def validate_support(checks, sources, allowed_ids):
    by_id = {source["id"]: source for source in sources}
    for claim in checks:
        if claim.post_id not in allowed_ids or claim.post_id not in by_id:
            raise ValueError("source claim outside cited posts")
        owned = {
            span["span_id"]
            for span in source_spans(by_id[claim.post_id])
            if claim.source_field is None or span["source_field"] == claim.source_field
        }
        if not set(claim.brand_keys) <= set(by_id[claim.post_id].get("brand_keys", [])):
            raise ValueError("source claim cites unowned brand")
        if not set(claim.span_ids) <= owned:
            raise ValueError("source claim cites unowned passage")


def validate_claim_audit(checks, texts):
    """Narrow fail-closed checks for observed audit contradictions."""
    if not any(claim.source_field is not None for claim in checks):
        return  # Historical saved responses predate the source-field contract.
    prose = " ".join(texts)
    if re.search(
        r"\b(?:multiple|several|two|three|four|\d+) independent (?:reports|sources|accounts)\b",
        prose,
        re.IGNORECASE,
    ):
        raise ValueError("unverified source independence")
    if any(char.isdigit() for char in prose) and all(
        claim.number_ownership.strip().casefold() in {"", "none"} for claim in checks
    ):
        raise ValueError("numeric copy without number ownership")
