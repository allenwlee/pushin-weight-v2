"""Bounded standard-library worker for the isolated 0731 diagnostic job."""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import http.client
import json
import os
import time
import zlib

MODEL = "deepseek-ai/DeepSeek-V4-Flash-0731"
MAX_CALLS = 117
LIMIT = Decimal("0.25")


def enc(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(kind, value):
    blob = base64.b64encode(zlib.compress(enc({"kind": kind, "value": value}))).decode()
    chunks = [blob[n:n + 2200] for n in range(0, len(blob), 2200)]
    for index, part in enumerate(chunks, 1):
        print(f"PW_POLITICAL_0731 {kind}:{index}/{len(chunks)}:{part}", flush=True)


def request_for(packet, item):
    return {**packet["profile"], "messages": [
        {"role": "system", "content": packet["system"]},
        {"role": "user", "content": enc({"state": item["state"], "questions": packet["questions"]}).decode()},
    ]}


def reservation(body):
    # Reserve two input tokens per byte and the full output ceiling at current standard rates.
    return (Decimal((len(body) + 4096) * 2) * Decimal("0.06")
            + Decimal(4096) * Decimal("0.18")) / Decimal(1000000)


def run_packet(packet, key, event_emit=emit):
    assert len(packet["items"]) == MAX_CALLS
    assert packet["profile"] == {"model": MODEL, "temperature": 1.0,
        "top_p": 1.0, "seed": 42, "reasoning_effort": "none", "max_tokens": 4096}
    event_emit("preflight", {"at": now(), "credential_present": bool(key), "model": MODEL,
        "requests": len(packet["items"]), "packet_sha256": hashlib.sha256(enc(packet)).hexdigest()})
    if not key:
        raise SystemExit("missing_deepinfra_credential_no_calls")
    spent = Decimal(0)
    deadline = time.monotonic() + 3600
    for index, item in enumerate(packet["items"]):
        body = enc(request_for(packet, item))
        assert hashlib.sha256(body).hexdigest() == item["sha256"]
        reserve = reservation(body)
        if spent + reserve > LIMIT or time.monotonic() >= deadline:
            event_emit("stopped", {"at": now(), "completed_calls": index,
                "reason": "budget_or_deadline", "cost_usd": str(spent),
                "next_reservation_usd": str(reserve)})
            raise SystemExit("budget_or_deadline_no_retry")
        event_emit(f"started_{index}", {"id": item["request_id"], "at": now(),
            "request_sha256": item["sha256"], "reservation_usd": str(reserve)})
        started = time.monotonic()
        conn = http.client.HTTPSConnection("api.deepinfra.com", timeout=45)
        try:
            conn.request("POST", "/v1/openai/chat/completions", body=body,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read(1000001).decode()
            status = response.status
            assert len(raw) <= 1000000
        except Exception as exc:
            event_emit(f"error_{index}", {"id": item["request_id"], "at": now(),
                "error_type": type(exc).__name__, "completion": "unknown",
                "retained_reservation_usd": str(reserve)})
            raise SystemExit("transport_error_stop_no_retry") from None
        finally:
            conn.close()
        event_emit(f"finished_{index}", {"id": item["request_id"], "at": now(),
            "http_status": status, "elapsed_seconds": time.monotonic() - started,
            "raw_body": raw.replace(key, "[REDACTED]")})
        try:
            accounting_data = json.loads(raw)
            usage = accounting_data.get("usage") if isinstance(accounting_data, dict) else None
            if not isinstance(usage, dict):
                raise ValueError("missing_usage")
            reported_cost = usage.get("estimated_cost")
            accounting = {"status": "usage_present", "estimated_cost": str(reported_cost),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens")}
        except (ValueError, TypeError, json.JSONDecodeError):
            accounting = {"status": "usage_unavailable", "estimated_cost": None,
                "prompt_tokens": None, "completion_tokens": None}
        event_emit(f"accounting_{index}", {"id": item["request_id"], "at": now(),
            "http_status": status, **accounting,
            "retained_reservation_usd": str(reserve)})
        if status != 200:
            raise SystemExit("provider_http_error_stop_no_retry")
        data = json.loads(raw)
        if data.get("model") != MODEL or not isinstance(data.get("usage"), dict):
            raise SystemExit("unexpected_provider_model_or_usage_no_retry")
        usage = data["usage"]
        for field in ("prompt_tokens", "completion_tokens"):
            value = usage.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SystemExit("invalid_provider_usage_no_retry")
        cost = Decimal(str(usage.get("estimated_cost")))
        if not cost.is_finite() or cost < 0 or cost > reserve or spent + cost > LIMIT:
            raise SystemExit("provider_cost_outside_bound_no_retry")
        spent += cost
    event_emit("complete", {"calls": MAX_CALLS, "cost_usd": str(spent), "at": now()})


if "PACKET" in globals():
    run_packet(PACKET, os.environ.get("DEEPINFRA_API_KEY"))
