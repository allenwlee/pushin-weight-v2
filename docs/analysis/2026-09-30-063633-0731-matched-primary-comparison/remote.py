"""Executed in an isolated Render job with frozen REQUESTS injected by run.py."""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import http.client
import json
import os
import time
import zlib


def enc(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def emit(kind, value):
    blob = base64.b64encode(zlib.compress(enc({"kind": kind, "value": value}))).decode()
    chunks = [blob[n:n + 2200] for n in range(0, len(blob), 2200)]
    for index, part in enumerate(chunks, 1):
        print("PW_0731_MATCH " + kind + ":" + str(index) + "/" + str(len(chunks)) + ":" + part, flush=True)


key = os.environ.get("DEEPINFRA_API_KEY")
model = "deepseek-ai/DeepSeek-V4-Flash-0731"
emit("preflight", {"credential_present": bool(key), "model": model, "requests": len(REQUESTS),
                   "at": datetime.now(timezone.utc).isoformat()})
if not key:
    raise SystemExit("missing_deepinfra_credential_no_calls")
assert len(REQUESTS) == 16
spent = Decimal(0)
deadline = time.monotonic() + 600
for index, item in enumerate(REQUESTS):
    request = item["request"]
    body = enc(request)
    assert hashlib.sha256(body).hexdigest() == item["sha256"]
    assert request["model"] == model and request["reasoning_effort"] == "none" and request["max_tokens"] == 1024
    reserve = Decimal((len(body) + 4096) * 2) * Decimal("0.06") / Decimal(1000000) + Decimal(1024) * Decimal("0.18") / Decimal(1000000)
    assert spent + reserve <= Decimal(".05") and time.monotonic() < deadline
    emit("started_" + str(index), {"id": item["id"], "request_sha256": item["sha256"],
         "reservation_usd": str(reserve), "at": datetime.now(timezone.utc).isoformat()})
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
        emit("error_" + str(index), {"id": item["id"], "error_type": type(exc).__name__,
             "completion": "unknown", "retained_reservation_usd": str(reserve)})
        raise SystemExit("transport_error_stop_no_retry") from None
    finally:
        conn.close()
    emit("finished_" + str(index), {"id": item["id"], "http_status": status,
         "raw_body": raw.replace(key, "[REDACTED]"), "elapsed_seconds": time.monotonic() - started,
         "at": datetime.now(timezone.utc).isoformat()})
    if status != 200:
        raise SystemExit("provider_http_error_stop_no_retry")
    data = json.loads(raw)
    assert data["model"] == model
    usage = data["usage"]
    cost = Decimal(str(usage["estimated_cost"]))
    assert cost.is_finite() and Decimal(0) <= cost <= reserve
    spent += cost
emit("complete", {"calls": 16, "cost_usd": str(spent), "at": datetime.now(timezone.utc).isoformat()})
