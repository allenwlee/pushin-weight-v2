"""Versioned semantic/selection packets and source-backed competition checks."""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from jsonschema import Draft202012Validator

from monitor.original_content import digest

from .contracts import ProviderReplyError

POOLS = tuple(
    f"{language}-{group}"
    for language in ("en", "zh-cn", "ja")
    for group in ("giant", "rest")
)


def prompts():
    return json.loads(
        (
            Path(settings.BASE_DIR) / "config/editorial_chatter_chain/prompts.json"
        ).read_text()
    )


def request(stage, payload, cfg):
    book = prompts()
    entry = book[stage]
    return {
        "system": entry["system"],
        "user": json.dumps(
            {**payload, "output_schema": entry["schema"]},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "packet_version": book["version"] + ":" + digest(entry),
        "reservation_usd": cfg.chatter.discovery_reservation_usd
        if stage == "semantic"
        else cfg.chatter.selector_reservation_usd,
    }


def semantic_request(cutoff, history, cfg):
    result = request(
        "semantic",
        {
            "cutoff": cutoff.isoformat(),
            "activity_window": {
                "start": (cutoff - timedelta(hours=24)).isoformat(),
                "end_exclusive": cutoff.isoformat(),
            },
            "context_envelope_start": (cutoff - timedelta(days=3)).date().isoformat(),
            "saved_history": history,
        },
        cfg,
    )
    result["server_tools"] = {
        "tools": [
            {
                "type": "x_search",
                "from_date": (cutoff - timedelta(days=3)).date().isoformat(),
                "to_date": (cutoff + timedelta(days=1)).date().isoformat(),
            }
        ],
        "max_turns": cfg.chatter.max_search_turns,
    }
    return result


def post_id(url):
    if not isinstance(url, str):
        raise TypeError("invalid source URL")
    parts = urlsplit(url)
    match = re.fullmatch(
        r"/(?:i/status|[a-zA-Z0-9_]{1,25}/status)/([0-9]{1,25})/?", parts.path
    )
    if (
        parts.scheme != "https"
        or parts.hostname
        not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
        or not match
        or parts.username
    ):
        raise ValueError("invalid original-post identity")
    return match[1]


def development_identity(story):
    """A post is evidence; a roundup can support several distinct developments."""
    return (
        " ".join(story["subject"].casefold().split()),
        tuple(sorted(story["post_ids"])),
    )


def validate_semantic(reply, history_ids):
    usage = reply.get("usage", {})
    activity = reply.get("search_activity", [])
    named = [row["name"] for row in activity]
    if (
        not (type(usage.get("x_search_calls")) is int and usage["x_search_calls"] > 0)
        and "x_semantic_search" not in named
    ) or (named and "x_semantic_search" not in named):
        raise ValueError("semantic search execution is unproven")
    raw = reply["data"]
    schema = prompts()["semantic"]["schema"]
    envelope = {
        **schema,
        "properties": {
            **schema["properties"],
            "stories": {"type": "array", "maxItems": 30},
        },
    }
    if list(Draft202012Validator(envelope).iter_errors(raw)):
        raise ValueError("invalid semantic envelope")
    if re.search(r"(?:since|until)(?:_time)?:", raw["keyword_query"], re.IGNORECASE):
        raise ValueError("keyword times are code-owned")
    valid, rejected, seen = [], [], set()
    item_validator = Draft202012Validator(schema["properties"]["stories"]["items"])
    for index, story in enumerate(raw["stories"]):
        try:
            if list(item_validator.iter_errors(story)) or story["story_ref"] in seen:
                raise ValueError("invalid semantic story")
            seen.add(story["story_ref"])
            prior = story["prior_development_id"]
            if prior is not None and prior not in history_ids:
                raise ValueError("unknown historical development")
            ids = list(
                dict.fromkeys(
                    post_id(p["url"])
                    for p in story["primary_posts"] + story["discussion_posts"]
                )
            )
            if not ids:
                raise ValueError("semantic story has no original source")
            if re.search(
                r"(?:since|until)(?:_time)?:", story["keyword_query"], re.IGNORECASE
            ):
                raise ValueError("keyword times are code-owned")
            valid.append({**story, "post_ids": ids})
        except (ValueError, KeyError, TypeError):
            rejected.append(
                {
                    "index": index,
                    "sha256": digest(story),
                    "reason": "invalid_semantic_story",
                }
            )
    if raw["stories"] and not valid:
        raise ValueError("all semantic candidates rejected")
    identities = [development_identity(story) for story in valid]
    prior_refs = [
        story["prior_development_id"]
        for story in valid
        if story["prior_development_id"]
    ]
    if len(set(identities)) != len(identities) or len(set(prior_refs)) != len(
        prior_refs
    ):
        raise ProviderReplyError("ambiguous_semantic_identity", {})
    if not set(raw["history_requests"]) <= history_ids:
        raise ValueError("unknown semantic history reference")
    return {
        **raw,
        "stories": valid,
        "rejections": rejected,
        "tool_detail_visibility": "observed_calls_results_hidden"
        if activity
        else "unavailable",
    }


def validate_selection(raw, candidates, incumbents, group_policy_ref):
    if list(Draft202012Validator(prompts()["selection"]["schema"]).iter_errors(raw)):
        raise ValueError("invalid selector schema or reason")
    by_ref = {row["candidate_ref"]: row for row in candidates}
    tags = {row["candidate_ref"]: row for row in raw["candidate_tags"]}
    if len(tags) != len(raw["candidate_tags"]) or set(tags) != set(by_ref):
        raise ValueError("selector must classify every considered development")
    for ref, tag in tags.items():
        language, group = tag["dominant_source_language"], tag["editorial_group"]
        expected = (
            f"{language}-{group}"
            if language in {"en", "zh-cn", "ja"} and group in {"giant", "rest"}
            else None
        )
        if tag["pool_ref"] != expected:
            raise ValueError("selector tag/pool mismatch")
        if (
            tag["language_evidence_ref"] != "language:" + ref
            or tag["group_policy_ref"] != group_policy_ref
        ):
            raise ValueError("unknown classification evidence")
        if not set(tag["group_evidence_post_ids"]) <= set(by_ref[ref]["post_ids"]):
            raise ValueError("unknown group source evidence")
    groups = {row["scope_ref"]: row for row in raw["group_decisions"]}
    if set(groups) != set(POOLS) or len(raw["group_decisions"]) != 6:
        raise ValueError("selector must return six distinct pools")
    for pool, decision in groups.items():
        eligible = {
            ref
            for ref, row in by_ref.items()
            if row["eligible"] and tags[ref]["pool_ref"] == pool
        }
        ranked = decision["ranked_candidates"]
        if {row["candidate_ref"] for row in ranked} != eligible or len(ranked) != len(
            eligible
        ):
            raise ValueError("ranked candidates do not match pool eligibility")
        if {row["rank"] for row in ranked} != set(range(1, len(ranked) + 1)) or any(
            type(row["rank"]) is not int for row in ranked
        ):
            raise ValueError("invalid pool ranking")
        for row in ranked:
            if not row["reason"].strip():
                raise ValueError("every candidate requires an editorial reason")
            allowed = {
                "measurement_refs": {"measurement:" + row["candidate_ref"]},
                "history_refs": {"history:" + row["candidate_ref"]},
                "asset_refs": set(),
            }
            if any(not set(row[key]) <= allowed[key] for key in allowed):
                raise ValueError("unknown selection evidence reference")
        action, lead = decision["lead_action"], decision["lead_ref"]
        incumbent = incumbents.get(pool)
        if decision["incumbent_ref"] != incumbent:
            raise ValueError("wrong pool incumbent")
        selected = [
            row["candidate_ref"] for row in ranked if row["outcome"] == "selected"
        ]
        if action == "none":
            if lead is not None or selected:
                raise ValueError("empty pool cannot borrow a lead")
        elif action == "keep":
            if (
                incumbent is None
                or lead != incumbent
                or any(ref != incumbent for ref in selected)
            ):
                raise ValueError("keep must retain its own pool incumbent")
        elif lead not in eligible or selected != [lead]:
            raise ValueError("selected lead is outside its eligible pool")
        if not decision["reason"].strip():
            raise ValueError("pool decision requires a reason")
    requested = raw.get("history_requests", [])
    if not set(requested) <= set(by_ref):
        raise ValueError("unknown read-only history reference")
    return raw


def attention(sources, previous):
    unique = {source["id"]: source for source in sources}
    authors = {
        source["author_id"] for source in unique.values() if source.get("author_id")
    }
    posts = []
    for identity, source in unique.items():
        current, old = (
            source.get("counters", {}),
            previous.get(identity, {}).get("counters", {}),
        )
        rate, delta, seconds = None, None, None
        if current.get("observed_at") and old.get("observed_at"):
            seconds = (
                datetime.fromisoformat(current["observed_at"])
                - datetime.fromisoformat(old["observed_at"])
            ).total_seconds()
            fields = ("likes", "replies", "reposts", "quotes")
            if seconds > 0 and all(
                type(current.get(k)) is int
                and type(old.get(k)) is int
                and current[k] >= old[k]
                for k in fields
            ):
                delta = {key: current[key] - old[key] for key in fields}
                rate = {
                    key: round(value * 900 / seconds, 4) for key, value in delta.items()
                }
        posts.append(
            {
                "source_id": identity,
                "observed_at": current.get("observed_at"),
                "previous_observed_at": old.get("observed_at"),
                "seconds": seconds,
                "cumulative": current,
                "delta": delta,
                "per_15_minutes": rate,
                "author_baseline": None,
                "acceleration": None,
            }
        )
    return {
        "observed_post_count": len(unique),
        "distinct_known_authors": len(authors),
        "all_x_discussion_total": None,
        "independent_confirmation_count": None,
        "posts": posts,
    }


def keep_fingerprint(payload):
    """Only freshly comparable supplied facts qualify; missing counters never mean unchanged."""
    coverage = payload["coverage"]
    if coverage.get("lookup_omitted") or coverage.get("board_may_be_capped"):
        return None
    candidates = []
    for candidate in payload["candidates"]:
        persistence = candidate["persistence"]
        if (
            not candidate["eligible"]
            or not persistence["continuity_known"]
            or persistence["unknown_periods"]
        ):
            return None
        evidence = []
        for source in candidate["evidence"]:
            if (
                source["verification_basis"] != "provider_receipt"
                or not source["created_at"]
                or not source["author_id"]
                or not source["source_language"]
            ):
                return None
            if any(
                source["counters"].get(key) is None
                for key in ("likes", "replies", "reposts", "quotes", "observed_at")
            ):
                return None
            # Receipt clocks change; measured values and immutable source facts must not.
            evidence.append(
                {
                    key: value
                    for key, value in source.items()
                    if key not in {"observed_at", "counters"}
                }
            )
        candidates.append(
            {
                "ref": candidate["candidate_ref"],
                "subject": candidate["subject_label"],
                "angle": candidate["discovery_note"],
                "evidence": evidence,
                "release_refs": candidate["required_release_refs"],
                "persistence": {
                    key: persistence[key]
                    for key in (
                        "consecutive_lower_bound",
                        "continuity_known",
                        "fresh_periods",
                        "unknown_periods",
                    )
                },
            }
        )
    measurements = []
    for measurement in payload["measurements"]:
        values = []
        for post in measurement["posts"]:
            if post["delta"] is None or post["per_15_minutes"] is None:
                return None
            values.append(
                {
                    "source_id": post["source_id"],
                    "delta": post["delta"],
                    "rate": post["per_15_minutes"],
                    "counters": {
                        key: value
                        for key, value in post["cumulative"].items()
                        if key != "observed_at"
                    },
                }
            )
        measurements.append(
            {
                "candidate_ref": measurement["candidate_ref"],
                "posts": values,
                "observed_post_count": measurement["observed_post_count"],
                "distinct_known_authors": measurement["distinct_known_authors"],
            }
        )
    return digest(
        {
            "candidates": candidates,
            "measurements": measurements,
            "policy": payload["giant_group_policy"],
            "releases": payload["required_release_refs"],
            "asset_manifest": payload["asset_manifest"],
            "observations": payload["prior_visual_observations"],
        }
    )
