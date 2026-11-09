"""Local Graphics prompt trial, independent of Django and production storage.

Historical requests/outputs stay immutable. Run against a new explicit directory.
Search is an injected tool adapter: no provider or credentials are guessed here.
"""

import argparse
import base64
import copy
import fcntl
import hashlib
import io
import json
import math
import os
import re
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from monitor.editorial.graphics_contracts import (
    TERMINAL_MEDIA_FAILURES,
    build_publication,
    build_task,
    load_pack,
    validate_copy_fact_ids,
    validate_stage_output,
)
from scripts.graphics_reference_fetch import fetch_sources

ROOT = Path(__file__).resolve().parents[1]
JST = ZoneInfo("Asia/Tokyo")
MODEL = "openai/gpt-6-sol"
P = None
PACK = None
CALLS = None
KEYS = {}
ADMISSION = threading.Lock()


def now():
    return datetime.now(JST).isoformat(timespec="milliseconds")


def save(name, data):
    dest = P / (name + ".json")
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(dest)


def read(name):
    return json.loads((P / (name + ".json")).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def uri(path):
    with Image.open(path) as image:
        mime = Image.MIME[image.format]
    return (
        "data:" + mime + ";base64," + base64.b64encode(Path(path).read_bytes()).decode()
    )


def load_keys():
    names = {"OPENROUTER_API_KEY", "XAI_API_KEY_PW"}
    keys = {name: os.environ.get(name, "") for name in names}
    store = Path("/Users/fuchitalee/.env.secrets")
    if any(not v for v in keys.values()) and store.exists():
        for line in store.read_text().splitlines():
            match = re.fullmatch(
                r"\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*", line
            )
            if match and match[1] in names and not keys[match[1]]:
                words = shlex.split(match[2], comments=True)
                if len(words) == 1:
                    keys[match[1]] = words[0]
    for name in names:
        if not keys[name]:
            raise RuntimeError("Missing project credential " + name)
    return keys


def configure(directory):
    global P, PACK, CALLS
    P = Path(directory).resolve()
    P.mkdir(parents=True, exist_ok=True)
    source = P / "prompt-pack.json"
    if not source.exists():
        source = ROOT / "config/editorial_prompts/editorial-creative-roles-v1.json"
    PACK = load_pack(source)
    CALLS = {call["id"]: call for call in PACK["model_call_plan"]["calls"]}


@contextmanager
def run_lock():
    # A second CLI process must not advance the same run concurrently.
    with (P / "runner.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def initialize(handoff, identity, *, render_reserve=False):
    if (P / "attempt.json").exists():
        raise RuntimeError(
            "Use a new run directory; completed stages are never resubmitted"
        )
    for asset in identity:
        if (
            asset["role"] != "identity_reference"
            or sha(asset["file"]) != asset["sha256"]
        ):
            raise ValueError("Invalid identity reference")
    save("prompt-pack", PACK)
    save("handoff", handoff)
    save("identity", identity)
    save("source-assets", [])
    save(
        "attempt",
        {
            "started_at": now(),
            "started_epoch": time.time(),
            "ceiling_usd": 2,
            "max_paid_calls": 8,
            "no_rerolls": True,
            "render_reserve": render_reserve,
            "soft_package_target_seconds": 300,
            "hard_diagnostic_seconds": 1200,
            "production_integration_tested": False,
        },
    )


def post(stage, url, key_name, body, reserve):
    if stage not in CALLS:
        raise ValueError("Unknown paid stage")
    encoded = json.dumps(body, ensure_ascii=False).encode()
    # Hold admission only while claiming the stage and reserving spend, not over HTTP.
    with ADMISSION:
        attempt = read("attempt")
        remaining = attempt["hard_diagnostic_seconds"] - (
            time.time() - attempt["started_epoch"]
        )
        rows = [json.loads(path.read_text()) for path in P.glob("call-*.json")]
        if remaining <= 0 or len(rows) >= attempt["max_paid_calls"]:
            raise RuntimeError("Diagnostic call/deadline ceiling reached")
        if (
            sum(row.get("reserved_usd", 0) for row in rows) + reserve
            > attempt["ceiling_usd"]
        ):
            raise RuntimeError("Diagnostic spending ceiling reached")
        row = {
            "stage": stage,
            "model": body["model"],
            "endpoint": url,
            "started_at": now(),
            "started_epoch": time.time(),
            "state": "submission_started",
            "reserved_usd": reserve,
            "request_sha256": hashlib.sha256(encoded).hexdigest(),
        }
        with (P / ("call-" + stage + ".json")).open("x") as file:
            json.dump(row, file, indent=2)
        save("request-" + stage, body)
    print("START " + stage, flush=True)
    start = time.monotonic()
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Authorization": "Bearer " + KEYS[key_name],
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=min(120, remaining)) as response:
            result = json.load(response)
            row["http_status"] = response.status
        save("response-" + stage, result)
        row["state"] = "returned"
        row["usage"] = result.get("usage") or {}
        if "cost" in row["usage"]:
            row["reported_cost_usd"] = row["usage"]["cost"]
        elif "cost_in_usd_ticks" in row["usage"]:
            row["reported_cost_usd"] = row["usage"]["cost_in_usd_ticks"] / 1e10
        return result
    except urllib.error.HTTPError as error:
        row.update(
            state="failed"
            if 400 <= error.code < 500 and error.code != 408
            else "ambiguous",
            http_status=error.code,
            error=error.read(2000).decode("utf8", "replace"),
        )
        raise
    except Exception as error:
        row.update(state="ambiguous", error=type(error).__name__)
        raise
    finally:
        row.update(
            elapsed_seconds=round(time.monotonic() - start, 3), finished_at=now()
        )
        save("call-" + stage, row)


def normalize_treatments(result):
    """Repair only transport geometry; preserve the raw model output and exact copy."""
    result = copy.deepcopy(result)
    supported = PACK["media_capabilities"]["image_aspect_ratios"]
    adjustments = []
    for treatment in result.get("treatments", []):
        requested = treatment.get("aspect_ratio")
        if requested in supported:
            continue
        match = re.fullmatch(r"(\d+(?:\.\d+)?):(\d+(?:\.\d+)?)", str(requested))
        if match and all(0 < float(value) < 1e100 for value in match.groups()):
            ratio = float(match[1]) / float(match[2])

            def distance(candidate, target=ratio):
                w, h = map(float, candidate.split(":"))
                return abs(math.log((w / h) / target))

            resolved = min(
                (value for value in supported if value != "auto"), key=distance
            )
        else:
            resolved = "auto"
        treatment["aspect_ratio"] = resolved
        for field in ["still_prompt", "motion_prompt"]:
            if isinstance(requested, str) and requested:
                treatment[field] = re.sub(
                    r"(?i)(\b(?:locked|fixed)\s+)"
                    + re.escape(requested)
                    + r"(\s+frame\b)",
                    lambda match, value=resolved: match[1] + value + match[2],
                    treatment.get(field, ""),
                )
        adjustments.append(
            {
                "candidate_id": treatment.get("candidate_id"),
                "requested": requested,
                "submitted": resolved,
                "reason": "unsupported provider geometry; no regeneration",
            }
        )
    save("parameter-adjustments", adjustments)
    return result


def task(cid, instruction, data):
    return build_task(instruction, data, CALLS[cid]["response_schema"])


def llm(cid, instruction, data, attachments=()):
    user = task(cid, instruction, data)
    content = [{"type": "text", "text": user}]
    manifest = []
    for asset in attachments:
        assert sha(asset["file"]) == asset["sha256"]
        content.append(
            {
                "type": "text",
                "text": "Image "
                + str(len(manifest) + 1)
                + ": asset_ref="
                + asset["asset_ref"]
                + "; role="
                + asset["role"],
            }
        )
        content.append({"type": "image_url", "image_url": {"url": uri(asset["file"])}})
        manifest.append({k: v for k, v in asset.items() if k != "data"})
    if len(user) > 60000 or len(manifest) > 12:
        raise RuntimeError("Bounded request input exceeded")
    save(
        "messages-" + cid,
        {"system": CALLS[cid]["system"], "task": user, "attachments": manifest},
    )
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": CALLS[cid]["system"]},
            {"role": "user", "content": content if attachments else user},
        ],
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
        "reasoning": {"effort": "medium"},
        "provider": {
            "allow_fallbacks": False,
            "require_parameters": True,
            "max_price": {"prompt": 2.5, "completion": 10.0},
        },
    }
    response = post(
        cid,
        "https://openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
        body,
        0.25,
    )
    if response.get("model") != MODEL:
        raise RuntimeError("Unexpected model binding")
    choice = response["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise RuntimeError(cid + " incomplete: " + str(choice.get("finish_reason")))
    result = json.loads(choice["message"]["content"])
    save("output-" + cid, result)  # preserve actual response before validating
    if cid == "G1":
        result = normalize_treatments(result)
    validate_stage_output(PACK, cid, result)
    save("validated-output-" + cid, result)
    row = read("call-" + cid)
    row["state"] = "completed"
    row["input_assets"] = [a["asset_ref"] for a in manifest]
    save("call-" + cid, row)
    return result


def asset_manifest(assets):
    return [{k: v for k, v in a.items() if k != "file"} for a in assets]


def prepare():
    inputs = read("identity") + read("source-assets")
    c1 = read("output-C1")
    design = llm(
        "G1",
        CALLS["G1"]["user"],
        {
            "candidates": c1["candidates"],
            "visual_approaches": read("output-G0").get("approaches", [])
            if (P / "output-G0.json").exists()
            else [],
            "actual_asset_manifest": asset_manifest(inputs),
            "source_discovery": read("search-evidence"),
            "facts": read("handoff")["fact_items"],
            "constraints": {
                "one_still_per_candidate": True,
                "complete_native_lettering": True,
                "video_seconds": 5,
            },
        },
        inputs,
    )
    assert {t["candidate_id"] for t in design["treatments"]} == {"A", "B"}
    allowed = {a["asset_ref"] for a in inputs}
    for t in design["treatments"]:
        assert all(a["asset_ref"] in allowed for a in t["input_asset_refs"])
    print(
        "NEW TREATMENTS "
        + json.dumps(
            [
                {
                    "candidate": t["candidate_id"],
                    "idea": t["idea"],
                    "inputs": t["input_asset_refs"],
                }
                for t in design["treatments"]
            ],
            ensure_ascii=False,
        ),
        flush=True,
    )


def render_still(treatment, all_assets):
    label = treatment["candidate_id"]
    cid = "I-" + label
    try:
        inputs = [all_assets[a["asset_ref"]] for a in treatment["input_asset_refs"]]
        if len(inputs) > PACK["media_capabilities"]["max_image_inputs"]:
            raise RuntimeError("Too many selected image inputs")
        prefix = CALLS[cid]["system"]
        generated = treatment["still_prompt"]
        if generated.startswith(PACK["media_preamble"]):
            generated = generated[len(PACK["media_preamble"]) :].lstrip()
        role_note = "\n".join(
            "Input "
            + str(i + 1)
            + ": "
            + a["asset_ref"]
            + " ("
            + treatment["input_asset_refs"][i]["role"]
            + ")"
            for i, a in enumerate(inputs)
        )
        ratio = treatment["aspect_ratio"]
        if ratio not in PACK["media_capabilities"]["image_aspect_ratios"]:
            raise ValueError("Unsupported image ratio reached request construction")
        geometry = f"Output frame: {ratio}. This output setting overrides other canvas-size wording; preserve the headline exactly."
        prompt = prefix + "\n\n" + role_note + "\n\n" + generated + "\n\n" + geometry
        save(
            "messages-" + cid,
            {
                "prefix": prefix,
                "task": generated,
                "input_order": asset_manifest(inputs),
                "combined_prompt": prompt,
            },
        )
        body = {
            "model": "grok-imagine-image-2.0",
            "prompt": prompt,
            "n": 1,
            "aspect_ratio": treatment["aspect_ratio"],
            "resolution": "1k",
            "quality": "medium",
            "response_format": "b64_json",
        }
        if inputs:
            body["images"] = [
                {"type": "image_url", "url": uri(a["file"])} for a in inputs
            ]
        endpoint = "https://api.x.ai/v1/images/" + (
            "edits" if inputs else "generations"
        )
        data = post(cid, endpoint, "XAI_API_KEY_PW", body, 0.15)
        if len(data.get("data", [])) != 1 or not data["data"][0].get("b64_json"):
            raise RuntimeError("No single image returned")
        raw = base64.b64decode(data["data"][0]["b64_json"], validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            fmt = im.format
            size = list(im.size)
        ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt)
        if not ext:
            raise RuntimeError("Unsupported generated image format")
        out = P / ("candidate-" + label + "." + ext)
        out.write_bytes(raw)
        asset = {
            "asset_ref": "candidate:" + label,
            "candidate_id": label,
            "role": "candidate_still",
            "file": str(out),
            "sha256": sha(out),
            "dimensions": size,
            "input_asset_refs": [a["asset_ref"] for a in inputs],
        }
        # The caller writes the combined manifest after both independent jobs finish.
        row = read("call-" + cid)
        row.update(
            state="completed",
            output_sha256=asset["sha256"],
            dimensions=size,
            input_asset_refs=asset["input_asset_refs"],
        )
        save("call-" + cid, row)
        return asset
    except Exception as e:  # noqa: BLE001 -- record stage failure and keep saved copy
        if (P / ("call-" + cid + ".json")).exists():
            row = read("call-" + cid)
            if row["state"] == "returned":
                row.update(state="failed", failure_kind="invalid_output")
                save("call-" + cid, row)
        save(
            "stage-failure-" + cid,
            {"type": type(e).__name__, "message": str(e)[:1500], "no_retry": True},
        )
        print("IMAGE FAILURE " + cid + ": " + str(e)[:200], flush=True)
    return None


def stills(labels=("A",)):
    all_assets = {a["asset_ref"]: a for a in read("identity") + read("source-assets")}
    treatments = [
        t
        for t in read("validated-output-G1")["treatments"]
        if t["candidate_id"] in labels
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        outputs = [
            asset
            for asset in executor.map(lambda t: render_still(t, all_assets), treatments)
            if asset is not None
        ]
    existing = (
        read("candidate-assets") if (P / "candidate-assets.json").exists() else []
    )
    outputs = sorted(existing + outputs, key=lambda a: a["candidate_id"])
    save("candidate-assets", outputs)
    return outputs


TERMINAL_FAILURES = TERMINAL_MEDIA_FAILURES


def definite_failure(stage):
    path = P / ("call-" + stage + ".json")
    return path.exists() and read("call-" + stage)["state"] in TERMINAL_FAILURES


def choose_and_save(selected="A", fallback_stage=None):
    previous = (
        read("publication-receipt")
        if (P / "publication-receipt.json").exists()
        else None
    )
    failure_state = (
        read("call-" + fallback_stage)["state"]
        if fallback_stage and (P / ("call-" + fallback_stage + ".json")).exists()
        else None
    )
    assets = read("candidate-assets")
    publication = build_publication(
        PACK,
        read("output-C1"),
        assets,
        read("identity") + read("source-assets"),
        selected=selected,
        fallback_stage=fallback_stage,
        failure_state=failure_state,
        previous_selection=previous["selected_candidate_id"] if previous else None,
    )
    asset = next((item for item in assets if item["candidate_id"] == selected), None)
    # Immutable edition snapshots precede the explicit current-edition pointer update.
    save("edition-" + selected + "-copy", publication)
    if previous:
        save("edition-A-receipt", previous)
        save(
            "fallback",
            {
                "at": now(),
                "from_candidate": "A",
                "to_candidate": "B",
                "failure_stage": fallback_stage,
                "failure": read("call-" + fallback_stage),
                "previous_content_revision": previous["content_revision"],
            },
        )
    save("published-copy", publication)
    revision = sha(P / "published-copy.json")
    save(
        "publication-receipt",
        {
            "saved_at": now(),
            "elapsed_seconds": round(time.time() - read("attempt")["started_epoch"], 3),
            "record_namespace": "local-test-only",
            "text_id": 1,
            "content_revision": revision,
            "producing_call": "C1",
            "selection_call": None,
            "selection_policy": "primary-reserve/v1",
            "fallback_stage": fallback_stage,
            "selected_candidate_id": selected,
            "selected_asset": asset,
            "public_production_publication": False,
            "article_unchanged": True,
            "review_pending": True,
        },
    )
    print("LOCAL COPY SAVED " + selected + ": " + publication["headline"], flush=True)


def submit_video(stage="V1"):
    save("active-video", {"stage": stage})
    published = read("publication-receipt")
    asset = published["selected_asset"]
    if not asset:
        return
    treatment = next(
        t
        for t in read("validated-output-G1")["treatments"]
        if t["candidate_id"] == published["selected_candidate_id"]
    )
    prompt = CALLS[stage]["system"] + "\n\n" + treatment["motion_prompt"]
    body = {
        "model": "grok-imagine-video-1.5-lite",
        "prompt": prompt,
        "duration": 5,
        "resolution": "720p",
        "image": {"url": uri(asset["file"])},
    }
    save(
        "messages-" + stage,
        {
            "prefix": CALLS[stage]["system"],
            "task": treatment["motion_prompt"],
            "input_asset": asset,
            "combined_prompt": prompt,
        },
    )
    result = post(
        stage, "https://api.x.ai/v1/videos/generations", "XAI_API_KEY_PW", body, 0.20
    )
    row = read("call-" + stage)
    if not result.get("request_id"):
        row["state"] = "ambiguous"
        save("call-" + stage, row)
        return
    row.update(
        state="pending",
        provider_request_id=result["request_id"],
        input_sha256=asset["sha256"],
    )
    save("call-" + stage, row)
    print(
        "VIDEO ACCEPTED; polling existing ID without a second submission.", flush=True
    )


def review():
    published = read("publication-receipt")
    asset = published["selected_asset"]
    inputs = ([asset] if asset else []) + read("identity")
    if asset:
        inputs += [
            a
            for a in read("source-assets")
            if a["asset_ref"] in asset["input_asset_refs"]
        ]
    result = llm(
        "E1",
        "Review the exact saved local preview edition and source evidence. This is a local test record, not a publicly published production story; text_id=1 belongs only to this test. Score the supplied copy and actual still. Motion is not supplied. Return the scorecard; do not rewrite or stop the preview.",
        {
            "record_namespace": "local-test-only",
            "text_id": 1,
            "content_revision": published["content_revision"],
            "publication": read("published-copy"),
            "handoff": read("handoff"),
            "selected_asset_manifest": asset_manifest(inputs),
        },
        inputs,
    )
    assert (
        result["text_id"] == 1
        and result["content_revision"] == published["content_revision"]
    )
    published.update(review_pending=False, review_state="completed")
    save("publication-receipt", published)
    print("EIC SCORES " + json.dumps(result["scores"], ensure_ascii=False), flush=True)


def poll_video_once(stage="V1"):
    row = read("call-" + stage)
    if row["state"] in {
        "completed",
        "failed",
        "expired",
        "canceled",
        "cancelled",
        "moderated",
    }:
        return
    rid = row.get("provider_request_id")
    if not rid:
        raise RuntimeError("No saved video ID to poll; no submission allowed")
    req = urllib.request.Request(
        "https://api.x.ai/v1/videos/" + rid,
        headers={"Authorization": "Bearer " + KEYS["XAI_API_KEY_PW"]},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.load(r)
    save("video-latest-poll-" + stage, result)
    row["poll_count"] = row.get("poll_count", 0) + 1
    if result.get("status") in {
        "failed",
        "expired",
        "canceled",
        "cancelled",
        "moderated",
    }:
        row.update(state=result["status"], finished_at=now())
        save("call-" + stage, row)
        return
    if result.get("status") not in {"pending", "done"}:
        raise ValueError("Unknown video status; preserve job ID for later polling")
    url = result.get("video", {}).get("url")
    if result.get("status") == "done" and not url:
        raise ValueError("Completed video response has no video URL")
    if result.get("status") == "done" and url:
        with urllib.request.urlopen(url, timeout=60) as r:
            raw = r.read(50 * 1024 * 1024 + 1)
        if len(raw) > 50 * 1024 * 1024:
            raise RuntimeError("Video exceeds read limit")
        out = P / ("video-" + stage + ".mp4")
        out.write_bytes(raw)
        (P / "selected-video.mp4").write_bytes(raw)
        row.update(
            state="completed",
            finished_at=now(),
            output_sha256=sha(out),
            elapsed_seconds=round(time.time() - row["started_epoch"], 3),
            usage=result.get("usage") or {},
        )
        if "cost_in_usd_ticks" in row["usage"]:
            row["reported_cost_usd"] = row["usage"]["cost_in_usd_ticks"] / 1e10
            row["cost_basis"] = "provider usage ticks"
    save("call-" + stage, row)
    print("VIDEO " + row["state"], flush=True)


def first():
    c1 = llm(
        "C1",
        CALLS["C1"]["user"],
        read("handoff"),
    )
    validate_copy_fact_ids(c1, read("handoff")["fact_items"])
    save(
        "text-observations",
        [
            {
                "candidate_id": c["id"],
                "observation": "Headline exceeds preferred six-word print length",
            }
            for c in c1["candidates"]
            if len(c["headline"].split()) > 6
        ],
    )
    save("copy-ready", {"validated": True})
    return discover(c1)


def discover(c1):
    """Graphics makes its own approach decision; code forwards it unchanged."""
    manifest = [
        {k: r[k] for k in ["asset_ref", "role", "credit", "sha256"]}
        for r in read("identity")
    ]
    return llm(
        "G0",
        CALLS["G0"]["user"],
        {
            "candidates": c1["candidates"],
            "facts": read("handoff")["fact_items"],
            "available_assets": manifest,
            "prior_searches": [],
        },
    )


def record_failure(stage, error):
    save(
        "stage-failure-" + stage,
        {"type": type(error).__name__, "message": str(error)[:1200], "no_retry": True},
    )


def video_until_complete(poll_interval=2, sleep=time.sleep, stage="V1"):
    if not (P / ("call-" + stage + ".json")).exists():
        return
    while True:
        row = read("call-" + stage)
        if row["state"] != "pending" or not row.get("provider_request_id"):
            return
        attempt = read("attempt")
        if time.time() - attempt["started_epoch"] >= attempt["hard_diagnostic_seconds"]:
            save(
                "poll-deferred",
                {
                    "at": now(),
                    "reason": "diagnostic deadline; existing job remains resumable",
                    "provider_request_id": row["provider_request_id"],
                },
            )
            return
        try:
            poll_video_once(stage)
        except (urllib.error.URLError, TimeoutError) as error:
            record_failure("video-poll", error)
            # Status reads may fail; never turn them into another paid submission.
            return
        if read("call-" + stage)["state"] != "pending":
            return
        sleep(poll_interval)


def finish_creation():
    labels = ("A", "B") if read("attempt").get("render_reserve") else ("A",)
    try:
        stills(labels)
    except Exception as error:  # noqa: BLE001 -- preserve copy, no extra generation
        record_failure("stills", error)
        save("candidate-assets", [])
    choose_and_save()

    def video_job(stage):
        try:
            submit_video(stage)
            video_until_complete(stage=stage)
        except Exception as error:  # noqa: BLE001 -- preserve paid request state
            record_failure(stage, error)

    if read("publication-receipt")["selected_asset"]:
        video_job("V1")
    failure = next((s for s in ("I-A", "V1") if definite_failure(s)), None)
    if failure:
        if "B" not in labels:
            stills(("B",))
        if any(a["candidate_id"] == "B" for a in read("candidate-assets")):
            choose_and_save("B", failure)
            video_job("V-B" if failure == "V1" else "V1")
    # Review the final saved branch once. Copy was saved before waiting for video.
    try:
        review()
    except Exception as error:  # noqa: BLE001 -- advisory review never blocks publication
        record_failure("E1", error)
        published = read("publication-receipt")
        published.update(review_pending=False, review_state="failed")
        save("publication-receipt", published)
    save(
        "completion",
        {
            "completed_at": now(),
            "elapsed_seconds": round(time.time() - read("attempt")["started_epoch"], 3),
            "production_integration_tested": False,
        },
    )


def continue_creation(search_results):
    if (P / "call-G1.json").exists() or (P / "published-copy.json").exists():
        raise RuntimeError(
            "Creation already advanced; preserve its evidence and use poll for an accepted video"
        )
    try:
        fetch_sources(P, read("output-G0"), search_results)
    except Exception as error:  # noqa: BLE001 -- record stage failure without a new paid attempt
        record_failure("source-fetch", error)
        save("source-assets", [])
        save(
            "search-evidence",
            {
                "queries": read("output-G0")["queries"],
                "error": str(error)[:300],
                "images_downloaded": 0,
            },
        )
    try:
        prepare()
    except Exception as error:  # noqa: BLE001 -- record stage failure without a new paid attempt
        record_failure("G1", error)
        save("validated-output-G1", {"treatments": []})
    finish_creation()


def run_pipeline(search):
    """Search is a host-owned callable; no human/model choice between stages."""
    try:
        discovery = first()
    except Exception as error:
        if not (P / "copy-ready.json").exists():
            raise
        record_failure("G0", error)
        discovery = {"queries": [], "preferred_sites": [], "reuse_asset_refs": []}
        save("output-G0", discovery)
    try:
        results = search(discovery)
    except Exception as error:  # noqa: BLE001 -- record stage failure without a new paid attempt
        record_failure("search", error)
        results = {
            "provider": "failed adapter",
            "queries": [{"query": q, "results": []} for q in discovery["queries"]],
        }
    continue_creation(results)


def main():
    global KEYS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["first", "continue", "run", "poll"])
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--render-reserve",
        action="store_true",
        help="Test mode: render B for inspection even when A succeeds.",
    )
    parser.add_argument("--handoff")
    parser.add_argument("--identity")
    parser.add_argument("--search-results")
    parser.add_argument(
        "--search-command",
        nargs="+",
        help="Host-selected executable: G0 JSON on stdin, search-result JSON on stdout. No shell.",
    )
    args = parser.parse_args()
    if args.phase in {"first", "run"} and (not args.handoff or not args.identity):
        parser.error("first/run require --handoff and --identity")
    if args.phase == "continue" and not args.search_results:
        parser.error("continue requires --search-results")
    if args.phase == "run" and not args.search_command:
        parser.error("run requires an explicitly selected search adapter")
    configure(args.run_dir)
    with run_lock():
        KEYS = load_keys()
        if args.phase in {"first", "run"}:
            initialize(
                json.loads(Path(args.handoff).read_text()),
                json.loads(Path(args.identity).read_text()),
                render_reserve=args.render_reserve,
            )
        if args.phase == "first":
            first()
        elif args.phase == "continue":
            continue_creation(json.loads(Path(args.search_results).read_text()))
        elif args.phase == "poll":
            video_until_complete(stage=read("active-video")["stage"])
        else:

            def search(discovery):
                result = subprocess.run(
                    args.search_command,
                    input=json.dumps(discovery),
                    text=True,
                    capture_output=True,
                    timeout=45,
                    check=True,
                )
                if len(result.stdout) > 2_000_000:
                    raise ValueError("Search result exceeds size limit")
                return json.loads(result.stdout)

            run_pipeline(search)


if __name__ == "__main__":
    main()
