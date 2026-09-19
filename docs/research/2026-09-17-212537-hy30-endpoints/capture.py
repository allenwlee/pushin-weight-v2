"""Capture public OpenRouter endpoint metadata for Hy-MT2-30B-A3B.

This uses no credentials and makes no inference request. Catalog pricing remains
the frozen authority; returned endpoint prices are retained only as metadata.
"""
import csv
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODEL_ID = "tencent/hy-mt2-30b-a3b"
URL = "https://openrouter.ai/api/v1/models/" + MODEL_ID + "/endpoints"
ROOT = Path(__file__).resolve().parent


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


started = now()
receipt = {"url": URL, "started_at_utc": started}
body = None
parsed = None
try:
    request = urllib.request.Request(
        URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "PushinWeight-hy30-endpoint-snapshot/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        parsed = json.loads(body)
        receipt.update(
            {
                "retrieved_at_utc": now(),
                "http_status": response.status,
                "http_version": getattr(response, "version", None),
                "http_date": response.headers.get("Date"),
                "etag": response.headers.get("ETag"),
                "cache_control": response.headers.get("Cache-Control"),
                "age": response.headers.get("Age"),
            }
        )
except urllib.error.HTTPError as error:
    receipt.update(
        {
            "retrieved_at_utc": now(),
            "http_status": error.code,
            "http_date": error.headers.get("Date") if error.headers else None,
        }
    )
except Exception as error:
    receipt.update({"retrieved_at_utc": now(), "error_type": type(error).__name__})

raw_path = ROOT / "raw" / "endpoints-tencent__hy-mt2-30b-a3b.json"
raw_path.parent.mkdir(parents=True, exist_ok=True)
if body is not None:
    raw_path.write_bytes(body)
    receipt["file"] = str(raw_path.relative_to(ROOT))

endpoints = ((parsed or {}).get("data") or {}).get("endpoints") or []
fields = [
    "model_id",
    "endpoint_name",
    "provider_name",
    "endpoint_tag",
    "quantization",
    "context_length",
    "max_completion_tokens",
    "supported_parameters",
    "pricing",
    "endpoint_json",
]
with (ROOT / "endpoint-metadata.csv").open("x", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()
    for endpoint in endpoints:
        writer.writerow(
            {
                "model_id": MODEL_ID,
                "endpoint_name": endpoint.get("name"),
                "provider_name": endpoint.get("provider_name"),
                "endpoint_tag": endpoint.get("tag"),
                "quantization": endpoint.get("quantization"),
                "context_length": endpoint.get("context_length"),
                "max_completion_tokens": endpoint.get("max_completion_tokens"),
                "supported_parameters": json.dumps(endpoint.get("supported_parameters"), separators=(",", ":")),
                "pricing": json.dumps(endpoint.get("pricing"), separators=(",", ":")),
                "endpoint_json": json.dumps(endpoint, separators=(",", ":")),
            }
        )

manifest = {
    "schema": "openrouter-model-endpoint-snapshot/v1",
    "started_at_utc": started,
    "finished_at_utc": now(),
    "candidate_model_count": 1,
    "endpoint_count": len(endpoints),
    "candidate_coverage": [
        {
            "model_id": MODEL_ID,
            "url": URL,
            "http_status": receipt.get("http_status"),
            "endpoint_count": len(endpoints),
            "error_type": receipt.get("error_type"),
            "raw_file": receipt.get("file"),
        }
    ],
    "requests": [receipt],
    "pricing_authority": {
        "path": "../2026-09-17-143812-openrouter-pricing-snapshot/models.csv",
        "model_id": MODEL_ID,
        "input_usd_per_million_cap": "0.074",
        "output_usd_per_million_cap": "0.295",
        "rule": "Endpoint prices are retained as observed metadata only and must not replace these frozen caps.",
    },
    "scope": "One public GET endpoint-metadata request for Hy-MT2-30B-A3B; no inference, credentials, or paid calls.",
    "warnings": [
        "An empty endpoint array means this API response returned no endpoint at capture time.",
        "Provider availability, tags, parameters, and endpoint prices may change after capture.",
    ],
}
manifest["sha256"] = {
    str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(ROOT.rglob("*"))
    if path.is_file() and path.name != "manifest.json"
}
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(
    json.dumps(
        {
            "directory": str(ROOT),
            "endpoints": len(endpoints),
            "coverage": manifest["candidate_coverage"],
            "verified": all(
                hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                for name, digest in manifest["sha256"].items()
            ),
        },
        indent=2,
    )
)
