"""Test low reasoning after R117 high reasoning exhausted the output ceiling."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts import u18_fresh40_v4_0731_deepinfra as baseline
from scripts import u18_fresh40_v4_0731_reasoning as high
from scripts import u18_fresh45_sol_compare as sol


ROOT = sol.ROOT
PRIVATE = ROOT / ".context/u18/fresh40-v4-0731-reasoning-low-r118-v1"
CONTRACT = PRIVATE / "contract.json"


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def prepare() -> None:
    if CONTRACT.exists():
        raise ValueError("contract already exists")
    packets = json.loads((baseline.PRIVATE / "packets.json").read_text(encoding="utf-8"))
    requests = deepcopy(json.loads((baseline.PRIVATE / "requests.json").read_text(encoding="utf-8")))
    for values in requests.values():
        for body in values:
            if body.get("reasoning") != {"enabled": False, "exclude": True}:
                raise ValueError("R116 reasoning baseline changed")
            body["reasoning"] = {"effort": "low", "exclude": True}
    dump(PRIVATE / "packets.json", packets)
    dump(PRIVATE / "requests.json", requests)
    dump(PRIVATE / "endpoint-receipt.json", baseline.endpoint_receipt())
    sources = [Path(__file__), Path(high.__file__), Path(baseline.__file__), baseline.CONTRACT, PRIVATE / "packets.json", PRIVATE / "requests.json", PRIVATE / "endpoint-receipt.json"]
    reservation = Decimal("0")
    for values in requests.values():
        for body in values:
            input_bound = Decimal(len(json.dumps(body, ensure_ascii=False).encode()) + 2048)
            reservation += (input_bound * baseline.INPUT_PRICE + Decimal(body["max_tokens"]) * baseline.OUTPUT_PRICE) / Decimal(1_000_000) * high.FEE_FACTOR
    contract = {
        "schema_version": "u18-fresh40-v4-0731-reasoning-low-r118/v1",
        "frozen_at": high.now(),
        "purpose": "Test low reasoning under the original 6000-token ceiling after high reasoning used the entire ceiling before producing content.",
        "model": baseline.MODEL, "provider": baseline.PROVIDER, "endpoint_tag": baseline.ENDPOINT_TAG,
        "cases": 40, "batch_sizes": [20, 20], "roles": ["content", "brand"], "calls": 4,
        "only_inference_change_from_r116": "reasoning changes from disabled to effort=low; exclude=true. Everything else is byte-equivalent.",
        "caps": {"retries": 0, "repairs_by_llm": 0, "fallbacks": 0, "reserved_usd_with_fee": str(reservation), "hard_cap_usd": str(high.HARD_CAP)},
        "scoring": "Same deterministic representation adapter as R117 and R116 diagnostics.",
        "blindness": "Owner answers and comments are absent from packets and requests.",
        "source_sha256": {str(path if not path.is_relative_to(ROOT) else path.relative_to(ROOT)): sol.digest(path) for path in sources},
    }
    dump(CONTRACT, contract)
    print(json.dumps({"contract": str(CONTRACT), "calls": 4, "reserved_usd_with_fee": str(reservation)}))


def run() -> None:
    original_private, original_contract = high.PRIVATE, high.CONTRACT
    try:
        high.PRIVATE, high.CONTRACT = PRIVATE, CONTRACT
        high.run()
    finally:
        high.PRIVATE, high.CONTRACT = original_private, original_contract


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run}[args.command]()


if __name__ == "__main__":
    main()
