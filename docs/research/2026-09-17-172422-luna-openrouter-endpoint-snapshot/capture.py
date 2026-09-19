"""Capture only the public OpenRouter endpoint metadata for GPT-5.6 Luna.

The September 17 catalog snapshot remains the sole pricing evidence.  This
separate, timestamped receipt records routing and capability metadata without
overwriting that saved price snapshot or making an inference request.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen


MODEL_ID = "openai/gpt-5.6-luna"
URL = f"https://openrouter.ai/api/v1/models/{MODEL_ID}/endpoints"
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw" / "endpoints-openai__gpt-5.6-luna.json"


def main() -> None:
    if RAW.exists() or (ROOT / "manifest.json").exists():
        raise RuntimeError("immutable snapshot target already has captured artifacts")
    started = datetime.now(UTC)
    request = Request(URL, headers={"Accept": "application/json", "User-Agent": "pushinweight-model-research/1"})
    with urlopen(request, timeout=30) as response:
        payload = response.read()
        status = response.status
        headers = {key.lower(): value for key, value in response.headers.items()}
    json.loads(payload)
    RAW.parent.mkdir(parents=True, exist_ok=False)
    RAW.write_bytes(payload)
    manifest = {
        "schema": "openrouter-endpoint-snapshot/v1",
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "started_at_utc": started.isoformat(),
        "model_id": MODEL_ID,
        "request": {"method": "GET", "url": URL, "authorization": "none", "inference_calls": 0},
        "response": {
            "status": status,
            "headers": {key: headers[key] for key in ("date", "etag", "cache-control") if key in headers},
            "raw_path": str(RAW.relative_to(ROOT)),
            "raw_sha256": hashlib.sha256(payload).hexdigest(),
            "raw_bytes": len(payload),
        },
        "pricing": {
            "source": "docs/research/2026-09-17-143812-openrouter-pricing-snapshot/raw/models.json",
            "policy": "No pricing fields are copied or refreshed here; model-task pricing remains pinned to the September 17 saved catalog snapshot.",
        },
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
