"""Frozen Chatter input builders and lease-free request reconstruction."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone

from core.models import EditorialStory, OriginalContent, OriginalContentRun
from monitor.original_content import digest

from .chatter_discovery import attention, request
from .chatter_history import (
    WORKFLOW,
    appearance_history,
    development_history,
    locked_run,
    read_sources,
    resolved_sources,
)
from .config import EditorialConfig
from .providers import request_payload
from .voices import Voice
from .writing import writer_request


def _expanded_history(identities, run):
    if len(identities) > 3 or len(set(identities)) != len(identities):
        raise ValueError("history expansion limit exceeded")
    expanded = {}
    for identity in identities:
        rows = development_history(
            EditorialStory.objects.get(pk=identity), timezone.now(), limit=9
        )
        expanded[identity] = [
            {
                "consideration_id": row.pk,
                "decision": row.consideration_state,
                "reason": row.consideration_reason,
                "selection": row.selection,
                "attempted_at": row.attempted_at.isoformat(),
                "source_refs": list(
                    row.consideration_sources.values(
                        "post_id", "dossier_source_id", "source_hash"
                    )
                ),
                "coverage_memory_only": True,
            }
            for row in rows
            if row.run_id != run.pk
        ][:8]
    return expanded


def _selection_packet(run, cfg):
    rows = list(
        OriginalContent.objects.filter(run=run)
        .select_related("development")
        .prefetch_related("consideration_sources")
    )
    sources = resolved_sources(run.snapshot)
    previous = {}
    prior = (
        OriginalContentRun.objects.filter(
            workflow_key=WORKFLOW,
            discovery_state="complete",
            facts_as_of__lt=run.facts_as_of,
        )
        .only("snapshot")
        .order_by("-facts_as_of")
        .first()
    )
    if prior:
        previous = resolved_sources(prior.snapshot)
    candidates, measurements, languages = [], [], []
    for row in rows:
        identities = [
            s.post_id or f"dossier-source:{s.dossier_source_id}"
            for s in row.consideration_sources.all()
        ]
        evidence = [sources[identity] for identity in identities]
        ref = str(row.development_id)
        candidates.append(
            {
                "candidate_ref": ref,
                "subject_label": row.selection.get("subject", "Saved development"),
                "discovery_note": row.selection.get("angle", ""),
                "post_ids": identities,
                "eligible": bool(identities),
                "required_release_refs": [str(row.development.event_dossier_id)]
                if row.development.event_dossier_id
                else [],
                "evidence": evidence,
                "persistence": appearance_history(row.development, timezone.now()),
            }
        )
        measurements.append(
            {
                "measurement_ref": "measurement:" + ref,
                "candidate_ref": ref,
                **attention(evidence, previous),
            }
        )
        languages.append(
            {
                "language_evidence_ref": "language:" + ref,
                "candidate_ref": ref,
                "sources": [
                    {"source_id": s["id"], "language": s["source_language"]}
                    for s in evidence
                ],
            }
        )
    policy = {
        "policy_ref": "giants:" + digest(cfg.chatter.giant_brands)[:16],
        "giants": cfg.chatter.giant_brands,
        "aliases": {
            "openai": ["OpenAI", "ChatGPT"],
            "anthropic": ["Anthropic", "Claude"],
            "google": ["Google", "Google DeepMind", "Gemini"],
            "spacexai": ["SpaceXSI", "xAI", "Grok", "SpaceXAI"],
        },
    }
    payload = {
        "stage": "chatter.lead-selection.six-source-pools-v1",
        "cutoff": run.facts_as_of.isoformat(),
        "candidates": candidates,
        "measurements": measurements,
        "source_language_evidence": languages,
        "giant_group_policy": policy,
        "incumbents": run.outcome.get("incumbent_refs", {}),
        "comparison_window": "rolling two hours plus each incumbent",
        "coverage_board": [],
        "atomic_window": "one fresh discovery period",
        "asset_manifest": [],
        "prior_visual_observations": [],
        "required_release_refs": [
            ref for c in candidates for ref in c["required_release_refs"]
        ],
        "coverage": {
            "search_tool_results": run.outcome.get("tool_detail_visibility"),
            "board_may_be_capped": run.outcome.get("history_coverage", {}).get(
                "board_may_be_capped", True
            ),
            "lookup_omitted": run.outcome.get("lookup_omitted", 0),
            "all_x_totals": "unknown",
        },
    }
    requested = run.outcome.get("history_coverage", {}).get("history_requests", [])
    if requested:
        payload["expanded_history"] = _expanded_history(requested, run)
    return payload


def _selection_request(run, stage, payload, cfg):
    """Save comparison metadata once; render source passages from the frozen run packet."""
    with transaction.atomic():
        current = locked_run(run.pk, run.fence)
        stored = current.outcome.get("selection_inputs", {}).get(stage)
        if stored is None:
            compact = deepcopy(payload)
            for candidate in compact["candidates"]:
                candidate.pop("evidence")
            stored = {"schema_version": 1, "payload": compact}
            current.outcome = {
                **current.outcome,
                "selection_inputs": {
                    **current.outcome.get("selection_inputs", {}),
                    stage: stored,
                },
            }
            current.save(update_fields=["outcome", "updated_at"])
            run.outcome = current.outcome
    if set(stored) != {"schema_version", "payload"} or stored["schema_version"] != 1:
        raise ValueError("unsupported saved selection input")
    rendered = deepcopy(stored["payload"])
    sources = resolved_sources(OriginalContentRun.objects.get(pk=run.pk).snapshot)
    for candidate in rendered["candidates"]:
        candidate["evidence"] = [
            sources[identity] for identity in candidate["post_ids"]
        ]
    built = request("selection", rendered, cfg)
    built["input_reference"] = {
        "run_id": run.pk,
        "stage": stage,
        "builder": "chatter-selection-v1",
    }
    return built, rendered


def writer_input(content, locale, cfg):
    run = content.run
    voice = Voice.model_validate(run.config_snapshot["voices"][f"chatter:{locale}"])
    sources = read_sources(content, usage="consideration")
    subject = SimpleNamespace(
        post_ids=[s["id"] for s in sources],
        brand_keys=list(dict.fromkeys(b for s in sources for b in s["brand_keys"])),
        source_image_url="",
        visual_essential=False,
    )
    packet = {
        "cutoff": run.facts_as_of.isoformat(),
        "posts": sources,
        "context": [],
        "chart_context": [],
    }
    built = writer_request(subject, packet, voice, cfg)
    built["input_reference"] = {
        "content_id": content.pk,
        "locale": locale,
        "builder": "chatter-v1",
    }
    return built, subject, packet, voice


def reconstruct_writer_request(call):
    ref = call.request_packet["input_reference"]
    if ref.get("builder") != "chatter-v1":
        raise ValueError("unknown writer input builder")
    row = OriginalContent.objects.select_related("run").get(
        pk=ref["content_id"], run_id=call.run_id
    )
    cfg = EditorialConfig.model_validate(row.run.config_snapshot["editorial"])
    built, _, _, _ = writer_input(row, ref["locale"], cfg)
    body = request_payload(cfg.writer_route("chatter", ref["locale"]), built)
    if (
        hashlib.sha256(json.dumps(body, ensure_ascii=False).encode()).hexdigest()
        != call.request_hash
    ):
        raise ValueError("reconstructed writer request hash mismatch")
    return body


def reconstruct_selection_request(call):
    """A completed run needs no new lease or provider call to reconstruct its input."""
    ref = call.request_packet["input_reference"]
    if ref != {
        "run_id": call.run_id,
        "stage": call.stage,
        "builder": "chatter-selection-v1",
    }:
        raise ValueError("unknown selection input builder")
    run = call.run
    cfg = EditorialConfig.model_validate(run.config_snapshot["editorial"])
    stored = run.outcome["selection_inputs"][call.stage]
    if set(stored) != {"schema_version", "payload"} or stored["schema_version"] != 1:
        raise ValueError("unknown selection projection")
    payload = deepcopy(stored["payload"])
    sources = resolved_sources(run.snapshot)
    for candidate in payload["candidates"]:
        candidate["evidence"] = [
            sources[identity] for identity in candidate["post_ids"]
        ]
    body = request_payload(cfg.chatter.selector, request("selection", payload, cfg))
    if (
        hashlib.sha256(json.dumps(body, ensure_ascii=False).encode()).hexdigest()
        != call.request_hash
    ):
        raise ValueError("reconstructed selection request hash mismatch")
    return body
