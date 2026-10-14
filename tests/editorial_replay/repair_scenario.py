"""Owner-approved evidence repair and scoped headline-attribution experiment.

Supplemental records are reviewed image text and a dated official excerpt,
explicitly marked as evidence records rather than invented database/X posts.
They use production's existing generic original_text span bindings. No deployed
module, source database row, provider transport or copy validator is changed.
"""

import copy
import hashlib
from datetime import date, datetime

from database_scenario import (
    CASES,
    add_style_line,
    frozen_request,
    reservation,
    runtime,
)
from production_replay import (
    encoded_wire,
    execute_writer,
    require_exact_wire,
    verify_negative_controls,
)

OLD_RULE = "Preserve whose claim it is in every language and the headline."
NEW_RULE = (
    "Preserve whose claim it is in the supporting line and article in every language. "
    "The headline may use playful shorthand; preserve attribution or uncertainty "
    "in the headline whenever omitting it would mislead."
)
REPAIR_ID = "packet-attribution-v1"
REPAIR_MODEL = {"id": "gpt60-medium", "model": "gpt-6-sol", "reasoning_effort": "medium"}


def assert_model_only_delta(body, reference_hash):
    previous = copy.deepcopy(body)
    previous.update(model="gpt-6.1-sol", reasoning_effort="high")
    if hashlib.sha256(encoded_wire(previous)).hexdigest() != reference_hash:
        raise ValueError("instructions, evidence or other settings changed with the model")


def relax_attribution(request):
    result = copy.deepcopy(request)
    if result["system"].count(OLD_RULE) != 1:
        raise ValueError("expected exactly one production headline-attribution sentence")
    result["system"] = result["system"].replace(OLD_RULE, NEW_RULE, 1)
    return result


def repaired_packet(packet, supplements, case_id):
    result = copy.deepcopy(packet)
    if supplements.get("case_id") != case_id:
        raise ValueError("supplement belongs to another case")
    records = supplements["records"]
    expected = {"reviewed_image_transcription", "official_identity_background"} if case_id == "wang" else set()
    if {record["evidence_role"]["kind"] for record in records} != expected or len(records) != len(expected):
        raise ValueError("unexpected supplemental evidence types")
    ids = {p["id"] for p in packet["posts"] + packet.get("context", [])}
    cutoff = datetime.fromisoformat(packet["cutoff"])
    for row in records:
        if row["id"] in ids or not row["id"].startswith("supplement:"):
            raise ValueError("supplement is duplicated or masquerades as a database post")
        if row["platform"] != "supplemental_evidence" or not row.get("url", "").startswith("https://"):
            raise ValueError("supplement must retain its actual source URL and type")
        if date.fromisoformat(row["created_at"][:10]) > cutoff.date():
            raise ValueError("supplement source was published after the story cutoff")
        if row["evidence_role"]["kind"] == "reviewed_image_transcription" and (
            row["evidence_role"]["original_post_id"] != packet["posts"][0]["id"]
            or row["url"] not in packet["posts"][0]["images"]
        ):
            raise ValueError("image transcript is not bound to the original source photo")
        if hashlib.sha256(row["original_text"].encode()).hexdigest() != row["evidence_role"]["text_sha256"]:
            raise ValueError("reviewed supplement text changed")
        ids.add(row["id"])
    if records:
        result["context"].extend(copy.deepcopy(records))
        result["story_context"]["included_ids"].extend(row["id"] for row in records)
        result["story_context"]["supplemental_records"] = len(records)
        result["story_context"]["database_collector_evidence_bytes"] = result["story_context"]["evidence_bytes"]
        result["story_context"]["evidence_bytes"] = len(encoded_wire(result["posts"] + result["context"]))
    return result


def request_for_repair(base, supplements, case_id, expected_revision):
    from monitor.editorial.evidence import packet_bytes
    from monitor.editorial.writing import writer_request

    cfg, route, voice, _, event, packet = frozen_request(base, case_id, expected_revision)
    packet = repaired_packet(packet, supplements, case_id)
    if packet_bytes(packet["posts"] + packet.get("context", [])) > cfg.max_story_bytes:
        raise ValueError("repaired evidence exceeds the production story cap")
    request = add_style_line(writer_request(event, packet, voice, cfg), voice.instructions)
    request = relax_attribution(request)
    return cfg, route, request, event, packet


def prepare_repair(base, supplements, case_id, expected_revision):
    from monitor.editorial.providers import request_payload

    _cfg, route, request, event, packet = request_for_repair(base, supplements, case_id, expected_revision)
    body = request_payload(route, request)
    report = copy.deepcopy(base)
    report.update(
        case_title=base["case_title"] + " · evidence/attribution",
        baseline_fixture=base, supplemental_evidence=supplements,
        repair_variant={"id": REPAIR_ID, "old_rule": OLD_RULE, "new_rule": NEW_RULE,
                        "supplemental_records": len(supplements["records"])},
        request_hash=hashlib.sha256(encoded_wire(body)).hexdigest(),
        one_call_reservation_usd=reservation(route, request, body),
    )
    report["snapshot"] = {
        "wire_request": body, "source_packet": packet, "event": event.model_dump(mode="json"),
        "response_schema": request["response_schema"], "source_bindings": request["source_bindings"],
        "source_ids": request["source_ids"],
    }
    report["negative_controls"] = verify_negative_controls(body, report["request_hash"])
    verified_request(report, case_id, expected_revision)
    return report


def verified_request(fixture, case_id, expected_revision):
    from monitor.editorial.providers import request_payload

    if fixture.get("status") != "preflight_passed" or fixture.get("case_id") != case_id:
        raise ValueError("expected the repair preflight for this case")
    cfg, _, _, hashes = runtime(expected_revision)
    if fixture["code_hashes"] != hashes or fixture["config_snapshot"] != cfg.model_dump(mode="json"):
        raise ValueError("production code or configuration changed after repair preflight")
    if fixture["repair_variant"] != {
        "id": REPAIR_ID, "old_rule": OLD_RULE, "new_rule": NEW_RULE,
        "supplemental_records": len(fixture["supplemental_evidence"]["records"]),
    }:
        raise ValueError("unexpected repair instructions")
    cfg, route, request, event, packet = request_for_repair(
        fixture["baseline_fixture"], fixture["supplemental_evidence"], case_id, expected_revision,
    )
    if fixture.get("repair_model_variant"):
        if fixture["repair_model_variant"] != REPAIR_MODEL:
            raise ValueError("unknown repaired-packet model variant")
        template = cfg.writer_route("chatter", "en")
        if template.model != REPAIR_MODEL["model"] or template.reasoning != REPAIR_MODEL["reasoning_effort"]:
            raise ValueError("current English model/rate template differs")
        route = route.model_copy(update={field: getattr(template, field) for field in (
            "model", "reasoning", "input_usd_per_million", "output_usd_per_million",
        )})
    if packet != fixture["snapshot"]["source_packet"]:
        raise ValueError("repaired packet differs from the frozen snapshot")
    require_exact_wire(request_payload(route, request), fixture["snapshot"]["wire_request"], fixture["request_hash"])
    if fixture.get("repair_model_variant"):
        assert_model_only_delta(fixture["snapshot"]["wire_request"], fixture["repair_model_reference_hash"])
    return cfg, route, request, event, packet


def execute_repair(fixture, case_id, expected_revision, run_id):
    cfg, route, request, event, packet = verified_request(fixture, case_id, expected_revision)
    return execute_writer(dict(fixture, complete_request_equal=True), run_id, cfg, route,
                          request, event, packet, success_status="scenario_passed")


def prepare_repair_model(fixture, case_id, expected_revision):
    from monitor.editorial.providers import request_payload

    if fixture.get("repair_model_variant"):
        raise ValueError("start from the successful6.1/high repair preflight")
    cfg, route, request, _, _ = verified_request(fixture, case_id, expected_revision)
    template = cfg.writer_route("chatter", "en")
    route = route.model_copy(update={field: getattr(template, field) for field in (
        "model", "reasoning", "input_usd_per_million", "output_usd_per_million",
    )})
    body = request_payload(route, request)
    assert_model_only_delta(body, fixture["request_hash"])
    report = copy.deepcopy(fixture)
    report.update(
        model=route.model, reasoning_effort=route.reasoning,
        case_title=CASES[case_id]["title"] + " · evidence/attribution ·6.0/medium",
        repair_model_variant=REPAIR_MODEL, repair_model_reference_hash=fixture["request_hash"],
        request_hash=hashlib.sha256(encoded_wire(body)).hexdigest(),
        one_call_reservation_usd=reservation(route, request, body),
    )
    report["snapshot"]["wire_request"] = body
    report["negative_controls"] = verify_negative_controls(body, report["request_hash"])
    verified_request(report, case_id, expected_revision)
    return report
