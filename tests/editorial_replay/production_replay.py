"""Replay one saved writer call through the deployed production code.

Run on the owning Render worker after Django setup, using authenticated SSH.
The default is a read-only preflight. --execute allows exactly one paid call,
with normal global accounting, and never invokes publication. stdout is a
private JSON evidence artifact; it contains source snapshots, never credentials.
"""

import argparse
import copy
import hashlib
import json
import os
from decimal import ROUND_CEILING, Decimal
from pathlib import Path


def encoded_wire(body):
    # Match production json_call, including serialization and key order.
    return json.dumps(body, ensure_ascii=False).encode()


def require_exact_wire(body, recorded_body, recorded_hash):
    if body != recorded_body:
        raise ValueError("complete production request differs")
    if hashlib.sha256(encoded_wire(body)).hexdigest() != recorded_hash:
        raise ValueError("complete production wire hash differs")


def verify_negative_controls(body, recorded_hash):
    variants = {}
    changed = copy.deepcopy(body)
    changed["messages"][0]["content"] += "\nWrite a generic news headline."
    variants["extra_instruction_after_identical_locked_opening"] = changed
    changed = copy.deepcopy(body)
    changed["messages"][0]["role"] = "user"
    variants["message_role_changed"] = changed
    changed = copy.deepcopy(body)
    content = changed["messages"][1]["content"]
    if isinstance(content, list):
        content[0]["text"] += "\nMissing or changed historical context."
    else:
        changed["messages"][1]["content"] += "\nMissing or changed historical context."
    variants["source_context_changed"] = changed
    changed = copy.deepcopy(body)
    field = "max_completion_tokens" if "max_completion_tokens" in body else "max_tokens"
    changed[field] += 1
    variants["completion_limit_changed"] = changed
    results = {}
    for name, changed in variants.items():
        try:
            require_exact_wire(changed, body, recorded_hash)
        except ValueError:
            results[name] = "rejected before send"
        else:
            raise AssertionError("request comparison accepted " + name)
    return results


def replay(args):
    from django.db import transaction
    from django.utils import timezone
    from monitor.editorial import (
        config,
        grounding,
        persistence,
        providers,
        selection,
        voices,
        writing,
    )
    from monitor.editorial.config import load_editorial_config
    from monitor.editorial.contracts import digest
    from monitor.editorial.persistence import (
        claim_assessment,
        finish_assessment,
        require_fence,
    )
    from monitor.editorial.providers import json_call, request_payload
    from monitor.editorial.selection import validate_decisions
    from monitor.editorial.voices import load_voice
    from monitor.editorial.writing import validate_copy, writer_request

    from core.models import (
        EditorialAssessment,
        EditorialCall,
        EditorialEdition,
        OriginalContentCall,
        OriginalContentText,
    )

    if os.environ.get("RENDER_SERVICE_ID") != "srv-d9ufj4e417fc73d93g20":
        raise ValueError("run on the owning production headline worker")
    revision = os.environ.get("RENDER_GIT_COMMIT")
    if revision != args.expected_revision:
        raise ValueError("deployed revision differs from the frozen test target")
    edition = EditorialEdition.objects.select_related("assessment").get(pk=args.edition)
    text = OriginalContentText.objects.select_related("producing_call__run").get(public_id=edition.id)
    original = text.producing_call
    if original.state != "completed" or edition.track != "chatter":
        raise ValueError("expected a completed Chatter producing call")
    cfg = load_editorial_config()
    if cfg.model_dump(mode="json") != original.run.config_snapshot:
        raise ValueError("effective production configuration changed since the source call")
    route = cfg.writer_route("chatter", edition.locale)
    voice = load_voice(cfg.voices["chatter:" + edition.locale])
    if voice.id != edition.voice["id"] or voice.digest != edition.voice["hash"]:
        raise ValueError("voice or resolved instructions changed")
    if route.model != original.model or route.model != edition.model:
        raise ValueError("model differs from the source call")
    if route.endpoint != "https://api.openai.com/v1/chat/completions":
        raise ValueError("expected the actual direct OpenAI production endpoint")
    event = validate_decisions({"events": [edition.selection]}, edition.assessment.packet).events[0]
    packet = edition.assessment.packet["story_packets"][event.key]
    request = writer_request(event, packet, voice, cfg)
    recorded_body = original.request_packet
    recorded_content = recorded_body["messages"][1]["content"]
    recorded_user = recorded_content[0]["text"] if isinstance(recorded_content, list) else recorded_content
    if json.loads(request["user"]) != json.loads(recorded_user):
        raise ValueError("rebuilt evidence/context/schema differs from the saved production packet")
    # PostgreSQL JSON storage can reorder object keys. Restore only serialization
    # after proving identical payload contents; never alter evidence or schema.
    serialization_restored = request["user"] != recorded_user
    request["user"] = recorded_user
    body = request_payload(route, request)
    require_exact_wire(body, recorded_body, original.request_hash)
    negative_controls = verify_negative_controls(body, original.request_hash)
    input_bound = len(encoded_wire(body)) + 1024 + (
        len(request.get("images", [])) * route.image_token_ceiling if route.vision else 0
    )
    ceiling = (
        Decimal(input_bound) * Decimal(str(route.input_usd_per_million))
        + Decimal(route.max_output_tokens) * Decimal(str(route.output_usd_per_million))
    ) / Decimal(1000000)
    ceiling = ceiling.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)
    if ceiling > Decimal("0.25"):
        raise ValueError("one-call test reservation exceeds USD0.25")
    marker = "g2-production-parity-" + args.run_id
    report = {
        "status": "preflight_passed",
        "revision": revision,
        "original_edition": str(edition.id),
        "original_assessment": edition.assessment_id,
        "original_producing_call": original.pk,
        "original_headline": edition.headline,
        "original": {
            "edition": str(edition.id),
            "call": original.pk,
            "copy": original.response_payload["data"],
            "diagnostics": original.response_payload["diagnostics"],
            "url": (
                f"https://pushinweight-web.onrender.com/stories/{edition.story_id}/"
                f"?track=chatter&lang={edition.locale}&edition={edition.id}"
            ),
        },
        "locale": edition.locale,
        "voice": edition.voice,
        "endpoint": route.endpoint,
        "model": route.model,
        "reasoning_effort": route.reasoning,
        "service_tier": body.get("service_tier"),
        "max_completion_tokens": route.max_output_tokens,
        "timeout_seconds": route.timeout_seconds,
        "request_hash": original.request_hash,
        "complete_request_equal": True,
        "recorded_user_serialization_restored": serialization_restored,
        "negative_controls": negative_controls,
        "one_call_reservation_usd": str(ceiling),
        "maximum_provider_calls": 1,
        "automatic_or_quality_retries": 0,
        "published": 0,
        "code_hashes": {
            mod.__name__: hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest()
            for mod in (config, grounding, persistence, providers, selection, voices, writing)
        },
        "snapshot": {
            "wire_request": body,
            "response_schema": request["response_schema"],
            "source_bindings": request["source_bindings"],
            "source_ids": request["source_ids"],
            "source_packet": packet,
            "event": event.model_dump(mode="json"),
        },
    }
    if not args.execute:
        return report
    if EditorialAssessment.objects.filter(source_cycle_id=marker).exists():
        raise ValueError("test already attempted; no redispatch")
    row = claim_assessment(timezone.now(), marker, scope="g2-production-parity")
    if row is None:
        raise ValueError("test assessment could not be claimed")
    with transaction.atomic():
        owned = require_fence(row)
        owned.packet = packet
        owned.decisions = {"events": [event.model_dump(mode="json")]}
        owned.save(update_fields=["packet", "decisions"])
    report["assessment"] = row.pk
    stage = f"writer:chatter:{edition.locale}:{digest([event.key, voice.digest])}"
    try:
        response = json_call(row, stage, route, request, cfg)
        result = validate_copy(response["data"], event, edition.locale, packet=packet)
        report.update(
            status="replay_passed",
            returned_model=response["model"],
            copy=result.model_dump(mode="json"),
            diagnostics=response["diagnostics"],
            usage=response["usage"],
        )
    except (ValueError, OSError) as exc:
        report.update(status="held_or_failed", error_type=type(exc).__name__)
    finally:
        finish_assessment(row, {
            "status": report["status"],
            "published": 0,
            "kind": "production-faithful writer replay; no publication",
            "original_call": original.pk,
            "request_hash": original.request_hash,
            "error_type": report.get("error_type"),
        })
    call = EditorialCall.objects.filter(assessment=row, stage=stage).first()
    canonical = OriginalContentCall.objects.filter(
        request_identity=f"legacy-editorial-call:{call.pk}"
    ).first() if call else None
    if call and canonical is None:
        raise AssertionError("saved test call is missing its canonical accounting record")
    report["provider_calls"] = row.calls.count()
    if report["provider_calls"] > 1:
        raise AssertionError("one-call limit exceeded")
    report["provider_call_state"] = call.state if call else "not sent"
    report["charged_or_reserved_usd"] = str(call.reserved_usd) if call else "0"
    report["test_producing_call"] = canonical.pk if canonical else None
    report["test_text_publications"] = OriginalContentText.objects.filter(
        producing_call_id=canonical.pk
    ).count() if canonical else 0
    if row.editions.exists() or report["test_text_publications"]:
        raise AssertionError("replay published content")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", required=True)
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--run-id", default="20261013-mistral-en-01")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        report = replay(args)
    except Exception as exc:  # noqa: BLE001 - sanitize CLI failures before a nonzero exit
        # Deliberately do not print raw transport exceptions or credentials.
        report = {"status": "preflight_failed", "error_type": type(exc).__name__}
        if isinstance(exc, (ValueError, AssertionError)):
            report["reason"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, default=str))
        raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, default=str))
    if report["status"] not in ("preflight_passed", "replay_passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
