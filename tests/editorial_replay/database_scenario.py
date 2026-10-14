"""Reconstruct owner-selected historical stories with deployed packet/writer code.

Unlike an exact edition replay, these fixtures read today's stored database rows
with historical created/fetched cutoffs. Editor ranking and publication are not
simulated. Prepare once, freeze the full request, then execute that exact fixture.
"""

import copy
import hashlib
import json
import os
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from production_replay import (
    encoded_wire,
    execute_writer,
    require_exact_wire,
    verify_negative_controls,
)

STYLE_LINE = "Write a catchy, punny, tongue-in-cheek print headline and supporting byline."
MODEL_VARIANT = {"id": "gpt61-high", "model": "gpt-6.1-sol", "reasoning_effort": "high"}


def model_route(cfg, route):
    template = cfg.writer_route("chatter", "ja")
    if template.model != MODEL_VARIANT["model"] or template.reasoning != MODEL_VARIANT["reasoning_effort"]:
        raise ValueError("deployed model/rate template differs from the requested test model")
    return route.model_copy(update={field: getattr(template, field) for field in (
        "model", "reasoning", "input_usd_per_million", "output_usd_per_million",
    )})


def add_style_line(request, opening):
    variant = copy.deepcopy(request)
    if not variant["system"].startswith(opening + "\n"):
        raise ValueError("production voice opening differs")
    variant["system"] = opening + "\n" + STYLE_LINE + variant["system"][len(opening):]
    return variant


def reservation(route, request, body):
    input_bound = len(encoded_wire(body)) + 1024 + (
        len(request.get("images", [])) * route.image_token_ceiling if route.vision else 0
    )
    ceiling = ((Decimal(input_bound) * Decimal(str(route.input_usd_per_million))
                + Decimal(route.max_output_tokens) * Decimal(str(route.output_usd_per_million)))
               / Decimal(1000000)).quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    if ceiling > Decimal("0.25"):
        raise ValueError("one-call test reservation exceeds USD0.25")
    return str(ceiling)


CASES = {
    "wang": {
        "anchor": "2103127068318089313",
        "cutoff": "2026-09-24T14:45:00+00:00",
        "title": "Wang’s wardrobe correction",
        "key": "wang-wardrobe-correction",
        "kind": "person",
        "visual": True,
    },
    "mistral-first": {
        "anchor": "2107457414387622310",
        "cutoff": "2026-10-06T13:30:00+00:00",
        "title": "First Mistral Le Chonk announcement",
        "key": "mistral-large-4-le-chonk-release",
        "kind": "model_release",
        "visual": False,
    },
}


def validate_availability(observations, source_ids, cutoff):
    if {p["id"] for p in observations} != set(source_ids) or any(
        datetime.fromisoformat(p[field]) > cutoff
        for p in observations for field in ("created_at", "fetched_at")
    ):
        raise ValueError("source availability exceeds the historical cutoff")


def runtime(expected_revision):
    from monitor import packet_maker
    from monitor.editorial import (
        config,
        context,
        evidence,
        grounding,
        persistence,
        providers,
        selection,
        voices,
        writing,
    )

    if os.environ.get("RENDER_SERVICE_ID") != "srv-d9ufj4e417fc73d93g20":
        raise ValueError("run on the owning production headline worker")
    if os.environ.get("RENDER_GIT_COMMIT") != expected_revision:
        raise ValueError("deployed revision differs from the test target")
    cfg = config.load_editorial_config()
    route = cfg.writer_route("chatter", "en")
    voice = voices.load_voice(cfg.voices["chatter:en"])
    if route.model != "gpt-6-sol" or route.reasoning != "medium":
        raise ValueError("current English route differs from the selected writer")
    hashes = {
        m.__name__: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
        for m in (config, context, evidence, grounding, persistence, providers, selection, voices, writing, packet_maker)
    }
    return cfg, route, voice, hashes


def prepare(case_id, expected_revision):
    from django.db import connection, transaction

    from core.models import Post
    from monitor.editorial.context import story_packet
    from monitor.editorial.evidence import build_packet, post_evidence
    from monitor.editorial.grounding import source_spans
    from monitor.editorial.providers import request_payload
    from monitor.editorial.selection import validate_decisions
    from monitor.editorial.writing import writer_request

    cfg, route, voice, hashes = runtime(expected_revision)
    case = CASES[case_id]
    cutoff = datetime.fromisoformat(case["cutoff"])
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout='15000ms'")
        post = Post.objects.prefetch_related("brands", "enrichment_state", "classification_states").get(
            pk=case["anchor"], created_at__lte=cutoff, fetched_at__lte=cutoff,
        )
        dispatch = build_packet(cutoff, cfg)
        selected = next((p for p in dispatch["posts"] if p["id"] == case["anchor"]), None)
        sampled = selected is not None
        if selected is None:
            selected = post_evidence(post)
            dispatch["posts"].append(selected)
        spans = [s for s in source_spans(selected) if s["source_field"] == "original_text"]
        event = validate_decisions({"events": [{
            "key": case["key"], "summary": "Owner-selected stored source.",
            "reason": "Owner-selected writer simulation; no automatic ranking claim.",
            "post_ids": [case["anchor"]], "brand_keys": selected["brand_keys"],
            "occurred_at": post.created_at.isoformat(), "importance": 100,
            "chatter": True, "pulse": False, "subject_kind": case["kind"],
            "visual_essential": case["visual"],
            "source_image_url": selected["images"][0] if case["visual"] else "",
            "source_check": [{
                "post_id": case["anchor"], "span_ids": [spans[0]["span_id"]],
                "source_field": "original_text", "brand_keys": selected["brand_keys"],
                "actor": selected["author_handle"], "action": "posts",
                "target": "stored original source", "status": "unknown",
            }],
        }]}, dispatch).events[0]
        packet = story_packet(event, dispatch, cfg)
        source_ids = [p["id"] for p in packet["posts"] + packet.get("context", [])]
        observations = [
            {"id": str(p.pk), "created_at": p.created_at.isoformat(), "fetched_at": p.fetched_at.isoformat()}
            for p in Post.objects.filter(pk__in=source_ids).order_by("tweet_id")
        ]
        validate_availability(observations, source_ids, cutoff)
    request = writer_request(event, packet, voice, cfg)
    body = request_payload(route, request)
    wire_hash = hashlib.sha256(encoded_wire(body)).hexdigest()
    ceiling = reservation(route, request, body)
    return {
        "status": "preflight_passed", "test_kind": "database_scenario",
        "case_id": case_id, "case_title": case["title"], "locale": "en",
        "revision": expected_revision, "voice": {"id": voice.id, "hash": voice.digest},
        "endpoint": route.endpoint, "model": route.model, "reasoning_effort": route.reasoning,
        "service_tier": body.get("service_tier"), "max_completion_tokens": route.max_output_tokens,
        "timeout_seconds": route.timeout_seconds, "request_hash": wire_hash,
        "one_call_reservation_usd": str(ceiling), "maximum_provider_calls": 1,
        "automatic_or_quality_retries": 0, "published": 0, "code_hashes": hashes,
        "config_snapshot": cfg.model_dump(mode="json"),
        "negative_controls": verify_negative_controls(body, wire_hash),
        "reconstruction": {
            "cutoff": case["cutoff"], "anchor_in_dispatch_sample": sampled,
            "selection": "Owner nominates the original post; no editor model call.",
            "availability": observations,
            "limits": "Today's stored rows, with original created/fetched cutoffs; historical profile/classification revisions are not recoverable. Editor metadata is not factual writer input. Images are the stored production URLs, not archived historical pixels.",
        },
        "snapshot": {
            "wire_request": body, "source_packet": packet, "dispatch_packet": dispatch,
            "event": event.model_dump(mode="json"), "response_schema": request["response_schema"],
            "source_bindings": request["source_bindings"], "source_ids": request["source_ids"],
        },
    }


def frozen_request(fixture, case_id, expected_revision):
    from monitor.editorial.providers import request_payload
    from monitor.editorial.selection import validate_decisions
    from monitor.editorial.writing import writer_request

    cfg, route, voice, hashes = runtime(expected_revision)
    if fixture.get("status") != "preflight_passed" or fixture.get("case_id") != case_id:
        raise ValueError("expected a frozen preflight for this case")
    if fixture.get("model_variant"):
        if fixture["model_variant"] != MODEL_VARIANT:
            raise ValueError("unknown model variant")
        route = model_route(cfg, route)
    if fixture["revision"] != expected_revision:
        raise ValueError("fixture revision differs")
    if fixture["code_hashes"] != hashes or fixture["config_snapshot"] != cfg.model_dump(mode="json"):
        raise ValueError("production code or effective configuration changed after preflight")
    if fixture["voice"] != {"id": voice.id, "hash": voice.digest}:
        raise ValueError("voice changed after preflight")
    packet = fixture["snapshot"]["source_packet"]
    event = validate_decisions({"events": [fixture["snapshot"]["event"]]}, packet).events[0]
    if event.post_ids != [CASES[case_id]["anchor"]] or packet["cutoff"] != CASES[case_id]["cutoff"]:
        raise ValueError("case source or cutoff differs")
    request = writer_request(event, packet, voice, cfg)
    body = fixture["snapshot"]["wire_request"]
    content = body["messages"][1]["content"]
    recorded_user = content[0]["text"] if isinstance(content, list) else content
    if json.loads(request["user"]) != json.loads(recorded_user):
        raise ValueError("rebuilt production evidence differs from the frozen request")
    request["user"] = recorded_user
    variant = fixture.get("prompt_variant")
    if variant:
        if variant != {"id": "catchy-punny", "line": STYLE_LINE}:
            raise ValueError("unknown prompt variant")
        if hashlib.sha256(encoded_wire(request_payload(route, request))).hexdigest() != fixture["baseline_request_hash"]:
            raise ValueError("production baseline request differs before the one-line addition")
        request = add_style_line(request, voice.instructions)
    require_exact_wire(request_payload(route, request), body, fixture["request_hash"])
    if fixture.get("model_variant"):
        previous = copy.deepcopy(body)
        previous.update(model="gpt-6-sol", reasoning_effort="medium")
        if hashlib.sha256(encoded_wire(previous)).hexdigest() != fixture["model_baseline_request_hash"]:
            raise ValueError("other wire conditions changed with the model")
    reservation(route, request, body)
    return cfg, route, voice, request, event, packet


def prepare_variant(fixture, case_id, expected_revision):
    from django.conf import settings

    from monitor.editorial.providers import request_payload

    if fixture.get("prompt_variant"):
        raise ValueError("start a variant from the unmodified database preflight")
    _, route, voice, request, _, _ = frozen_request(fixture, case_id, expected_revision)
    legacy = json.loads((Path(settings.BASE_DIR) / "config/editorial_voices/chatter-en-v1.json").read_text())
    if STYLE_LINE not in legacy["instructions"]:
        raise ValueError("legacy style sentence differs from the verified source")
    request = add_style_line(request, voice.instructions)
    body = request_payload(route, request)
    report = copy.deepcopy(fixture)
    report.update(
        case_title=fixture["case_title"] + " · catchy/punny",
        prompt_variant={"id": "catchy-punny", "line": STYLE_LINE},
        baseline_request_hash=fixture["request_hash"],
        request_hash=hashlib.sha256(encoded_wire(body)).hexdigest(),
        one_call_reservation_usd=reservation(route, request, body),
    )
    report["snapshot"]["wire_request"] = body
    report["negative_controls"] = verify_negative_controls(body, report["request_hash"])
    frozen_request(report, case_id, expected_revision)
    return report


def execute(fixture, case_id, expected_revision, run_id):
    cfg, route, _, request, event, packet = frozen_request(fixture, case_id, expected_revision)
    report = dict(fixture, complete_request_equal=True)
    return execute_writer(report, run_id, cfg, route, request, event, packet,
                          success_status="scenario_passed")


def prepare_model_variant(fixture, case_id, expected_revision):
    from monitor.editorial.providers import request_payload
    from monitor.editorial.writing import writer_request

    if fixture.get("model_variant") or not fixture.get("prompt_variant"):
        raise ValueError("start from the 6.0 catchy/punny preflight")
    cfg, route, voice, request, event, packet = frozen_request(fixture, case_id, expected_revision)
    route = model_route(cfg, route)
    body = request_payload(route, request)
    before_style = writer_request(event, packet, voice, cfg)
    before_style["user"] = request["user"]
    report = copy.deepcopy(fixture)
    report.update(
        model_variant=MODEL_VARIANT, model=route.model, reasoning_effort=route.reasoning,
        case_title=fixture["case_title"] + " · 6.1/high",
        model_baseline_request_hash=fixture["request_hash"],
        baseline_request_hash=hashlib.sha256(encoded_wire(request_payload(route, before_style))).hexdigest(),
        request_hash=hashlib.sha256(encoded_wire(body)).hexdigest(),
        one_call_reservation_usd=reservation(route, request, body),
    )
    report["snapshot"]["wire_request"] = body
    report["negative_controls"] = verify_negative_controls(body, report["request_hash"])
    frozen_request(report, case_id, expected_revision)
    return report
