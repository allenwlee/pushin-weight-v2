"""Build a portable Chatter review from private, recorded production replays."""

import argparse
import hashlib
import json
from pathlib import Path


def build_payload(fixture, original, replays):
    wire = fixture["snapshot"]["wire_request"]
    encoded = json.dumps(wire, ensure_ascii=False).encode()
    if hashlib.sha256(encoded).hexdigest() != fixture["request_hash"]:
        raise ValueError("fixture no longer matches the production wire hash")
    if original["call"] != fixture["original_producing_call"]:
        raise ValueError("original copy belongs to another producing call")
    conditions = {key: fixture[key] for key in (
        "revision", "endpoint", "model", "reasoning_effort", "service_tier",
        "max_completion_tokens", "timeout_seconds", "request_hash",
    )}
    runs = [{
        "id": "original", "label": "Published baseline", "kind": "Published edition",
        "copy": original["copy"], "call": original["call"], "url": original["url"],
        "diagnostics": original["diagnostics"], "conditions": conditions,
    }]
    for result in replays:
        if result.get("status") != "replay_passed" or result.get("complete_request_equal") is not True:
            raise ValueError("only completed production-matched replays belong in this review")
        if any(result.get(key) != value for key, value in conditions.items()):
            raise ValueError("replay conditions differ from the frozen baseline")
        if result.get("returned_model") != conditions["model"]:
            raise ValueError("returned model differs from the baseline")
        run_id = "replay-" + str(result["assessment"])
        if any(run["id"] == run_id for run in runs):
            raise ValueError("duplicate replay assessment")
        runs.append({
            "id": run_id, "label": "Replay #" + str(result["assessment"]),
            "kind": "Test copy · unpublished", "copy": result["copy"],
            "call": result["test_producing_call"], "conditions": conditions,
            "diagnostics": result["diagnostics"],
            "cost": result["charged_or_reserved_usd"],
        })
    packet = fixture["snapshot"]["source_packet"]
    return {
        "kind": "exact_replay", "title": "Published Mistral · exact replay",
        "runs": runs, "defaultRun": runs[-1]["id"], "conditions": conditions,
        "wire": wire, "packet": packet,
        "sources": packet.get("posts", []) + packet.get("context", []),
        "sourceCounts": {"primary": len(packet.get("posts", [])), "context": len(packet.get("context", []))},
        "negativeControls": fixture["negative_controls"],
    }


def build_scenario_payload(fixture, result, comparison=None):
    wire = fixture["snapshot"]["wire_request"]
    if hashlib.sha256(json.dumps(wire, ensure_ascii=False).encode()).hexdigest() != fixture["request_hash"]:
        raise ValueError("scenario fixture no longer matches its wire hash")
    conditions = {key: fixture[key] for key in (
        "revision", "endpoint", "model", "reasoning_effort", "service_tier",
        "max_completion_tokens", "timeout_seconds", "request_hash",
    )}
    if result.get("status") != "scenario_passed" or result.get("complete_request_equal") is not True:
        raise ValueError("scenario did not pass the production writer path")
    if any(result.get(key) != value for key, value in conditions.items()):
        raise ValueError("scenario conditions differ from the frozen fixture")
    if result.get("case_id") != fixture["case_id"] or result.get("returned_model") != conditions["model"]:
        raise ValueError("scenario case or returned model differs")
    if result.get("snapshot") != fixture["snapshot"]:
        raise ValueError("scenario snapshot differs from the frozen fixture")
    if result.get("test_text_publications") != 0 or result.get("published") != 0:
        raise ValueError("scenario unexpectedly published")
    packet = fixture["snapshot"]["source_packet"]
    run_id = "db-" + fixture["case_id"] + "-" + str(result["assessment"])
    return {
        "kind": "database_scenario", "title": fixture["case_title"],
        "runs": [{"id": run_id, "label": "Database simulation #" + str(result["assessment"]),
                  "kind": "Test copy · unpublished", "copy": result["copy"],
                  "call": result["test_producing_call"], "conditions": conditions,
                  "diagnostics": result["diagnostics"], "cost": result["charged_or_reserved_usd"]}],
        "defaultRun": run_id, "conditions": conditions, "wire": wire, "packet": packet,
        "sources": packet.get("posts", []) + packet.get("context", []),
        "sourceCounts": {"primary": len(packet.get("posts", [])), "context": len(packet.get("context", []))},
        "negativeControls": fixture["negative_controls"],
        "reconstruction": fixture["reconstruction"], "comparison": comparison,
        "promptVariant": fixture.get("prompt_variant"),
        "modelVariant": fixture.get("model_variant"),
        "repairVariant": fixture.get("repair_variant"),
    }


def build_manifest(path):
    manifest = json.loads(path.read_text())
    root = path.parent

    def read(name):
        return json.loads((root / name).read_text())

    cases = []
    for case in manifest["cases"]:
        fixture = read(case["fixture"])
        if case["kind"] == "exact_replay":
            original = read(case["original"]) if case.get("original") else fixture["original"]
            payload = build_payload(fixture, original, [read(p) for p in case["replays"]])
        elif case["kind"] == "database_scenario":
            comparison = read(case["comparison"]) if case.get("comparison") else None
            payload = build_scenario_payload(fixture, read(case["result"]), comparison)
        else:
            raise ValueError("unknown review case kind")
        cases.append(payload)
    ids = [run["id"] for case in cases for run in case["runs"]]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("review cases are empty or reuse run IDs")
    return {"cases": cases, "defaultRun": cases[-1]["defaultRun"]}


def render_html(payload):
    # Source text is untrusted. Keep it out of HTML/JavaScript syntax, then use
    # textContent in the template. A source's </script> cannot close this block.
    serialized = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c").replace(
        ">", "\\u003e"
    ).replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = Path(__file__).with_name("review.html").read_text()
    if template.count("__REPLAY_DATA__") != 1:
        raise ValueError("review template needs exactly one data placeholder")
    return template.replace("__REPLAY_DATA__", serialized)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--replay", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.manifest:
        if args.fixture or args.original or args.replay:
            raise ValueError("use a manifest or single-fixture arguments")
        payload = build_manifest(args.manifest)
    else:
        if not args.fixture:
            raise ValueError("provide --fixture or --manifest")
        fixture = json.loads(args.fixture.read_text())
        original = json.loads(args.original.read_text()) if args.original else fixture.get("original")
        if original is None:
            raise ValueError("older fixture requires --original; current preflight captures it")
        payload = build_payload(
            fixture, original,
            [json.loads(path.read_text()) for path in args.replay],
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(payload))
    cases = payload.get("cases", [payload])
    print(json.dumps({"output": str(args.output), "cases": len(cases),
                      "runs": sum(len(case["runs"]) for case in cases)}))


if __name__ == "__main__":
    main()
