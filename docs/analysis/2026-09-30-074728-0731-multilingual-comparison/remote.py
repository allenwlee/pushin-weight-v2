"""Bounded, standard-library-only program for the isolated Render instance."""
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
MAX_CALLS = 185
LIMIT = Decimal("0.50")


def enc(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def emit(kind, value):
    blob = base64.b64encode(zlib.compress(enc({"kind": kind, "value": value}))).decode()
    chunks = [blob[n:n + 2200] for n in range(0, len(blob), 2200)]
    for index, part in enumerate(chunks, 1):
        print(f"PW_0731_MULTI {kind}:{index}/{len(chunks)}:{part}", flush=True)


def request_for(packet, item):
    return {**packet["profile"], "messages": [
        {"role": "system", "content": packet["system"]},
        {"role": "user", "content": enc({"state": item["state"], "questions": packet["questions"]}).decode()},
    ]}


def reservation(body):
    return (Decimal((len(body) + 4096) * 2) * Decimal("0.06") + Decimal(4096) * Decimal("0.18")) / Decimal(1000000)


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
                "reason": "budget_or_deadline", "cost_usd": str(spent)})
            raise SystemExit("budget_or_deadline_no_retry")
        event_emit(f"started_{index}", {"id": item["id"], "at": now(),
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
            event_emit(f"error_{index}", {"id": item["id"], "at": now(),
                "error_type": type(exc).__name__, "completion": "unknown",
                "retained_reservation_usd": str(reserve)})
            raise SystemExit("transport_error_stop_no_retry") from None
        finally:
            conn.close()
        event_emit(f"finished_{index}", {"id": item["id"], "at": now(), "http_status": status,
            "elapsed_seconds": time.monotonic() - started, "raw_body": raw.replace(key, "[REDACTED]")})
        if status != 200:
            raise SystemExit("provider_http_error_stop_no_retry")
        data = json.loads(raw)
        assert data["model"] == MODEL
        usage = data["usage"]
        for field in ("prompt_tokens", "completion_tokens"):
            assert isinstance(usage[field], int) and not isinstance(usage[field], bool) and usage[field] >= 0
        cost = Decimal(str(usage["estimated_cost"]))
        assert cost.is_finite() and 0 <= cost <= reserve
        spent += cost
    event_emit("complete", {"calls": len(packet["items"]), "cost_usd": str(spent), "at": now()})


if "PACKET" in globals():
    run_packet(PACKET, os.environ.get("DEEPINFRA_API_KEY"))
