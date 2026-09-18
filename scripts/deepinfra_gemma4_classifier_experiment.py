"""Run the frozen expanded classifier diagnostic on direct DeepInfra Gemma.

This is an isolated experiment helper. It reuses the exact retained V4.1
diagnostic24 source payloads and two semantic prompts, changing only the
provider/model envelope and the output serialization. It never imports Django
settings or writes application data.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import model_classifier_experiment as classifier

SOURCE = ROOT / ".context/model-task-20260917/deepseek-v41-incumbent-classification-v1-diagnostic24/contract.json"
COMMENTARY_RUNNER = ROOT / ".context/model-task-20260918/deepinfra-gemma4-commentary-tagged-runner.py"
LEDGER = ROOT / ".context/model-task-20260917/portfolio-ledger.json"
LOCK = ROOT / ".context/model-task-20260917/.portfolio.lock"
MODEL = "google/gemma-4-31B-it-turbo"
TASK_KEY = "google/gemma-4-31b-it|classification"
INPUT_PRICE = 0.09
OUTPUT_PRICE = 0.34
MAX_OUTPUT_TOKENS = 4096
MAX_ATTEMPTS = 3
WALL_SECONDS = 1800


def _load_transport_module() -> Any:
    spec = importlib.util.spec_from_file_location("gemma_commentary_transport", COMMENTARY_RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("direct DeepInfra transport unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


transport = _load_transport_module()


def now() -> str:
    return datetime.now(UTC).isoformat()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _field(block: str, name: str) -> str:
    matches = re.findall(rf"\[\[{name}\]\](.*?)\[\[/{name}\]\]", block, re.DOTALL)
    if len(matches) != 1:
        raise ValueError(f"tagged field {name} missing or duplicated")
    return matches[0].strip()


def _values(raw: str, allowed: tuple[str, ...], *, empty: bool = False) -> list[str]:
    if raw == "EMPTY" and empty:
        return []
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values or len(values) != len(set(values)) or any(value not in allowed for value in values):
        raise ValueError("tagged enum list invalid")
    return values


def tagged_contract(role: str) -> str:
    if role == "content":
        return f"""
TAGGED OUTPUT CONTRACT:
- Return only the blocks below. Do not return JSON, Markdown, explanations, brand IDs, or post IDs.
- Emit one DECISION block for every supplied D slot, one PROMOTION block for every supplied P slot,
  and one SUBJECT block for each promoted subject. Preserve each slot exactly.
- Comma-separated values use only the exact enums shown. Use EMPTY only for post_types when outcome
  is context_missing. Use the literal NULL for a missing optional subject identifier.

[[DECISION]]
[[SLOT]]D01[[/SLOT]]
[[OUTCOME]]classified[[/OUTCOME]]
[[POST_TYPES]]news_reporting[[/POST_TYPES]]
[[AUDIENCE_TOPICS]]none[[/AUDIENCE_TOPICS]]
[[/DECISION]]
[[PROMOTION]]
[[SLOT]]P01[[/SLOT]]
[[KEYS]]none[[/KEYS]]
[[/PROMOTION]]
[[SUBJECT]]
[[POST_SLOT]]P01[[/POST_SLOT]]
[[NAME]]visible name[[/NAME]]
[[HANDLE]]NULL[[/HANDLE]]
[[DOMAIN]]NULL[[/DOMAIN]]
[[ACCOUNT_HANDLE]]NULL[[/ACCOUNT_HANDLE]]
[[EVIDENCE]]exact visible supporting text[[/EVIDENCE]]
[[/SUBJECT]]

Allowed post_types: {','.join(classifier.taxonomy.POST_TYPES)}.
Allowed audience_topics: {','.join(classifier.taxonomy.TOPICS)}.
Allowed promotion keys: {','.join(classifier.taxonomy.PROMOTIONS)}.
Select only supported values for each slot.
If promotion keys are none, emit no SUBJECT block for that P slot.
"""
    return f"""
TAGGED OUTPUT CONTRACT:
- Return only one DECISION block for every supplied D slot. Do not return JSON, Markdown,
  explanations, brand IDs, or post IDs. Preserve each slot exactly.
- Comma-separated values use only the exact enums shown.

[[DECISION]]
[[SLOT]]D01[[/SLOT]]
[[PRODUCT_LABELS]]none[[/PRODUCT_LABELS]]
[[SENTIMENT]]neutral[[/SENTIMENT]]
[[GEOPOLITICAL_MODES]]none[[/GEOPOLITICAL_MODES]]
[[CHINA_NATIONAL_STANCE]]none[[/CHINA_NATIONAL_STANCE]]
[[US_NATIONAL_STANCE]]none[[/US_NATIONAL_STANCE]]
[[/DECISION]]

Allowed product_labels: {','.join(classifier.taxonomy.PRODUCT_LABELS)}.
Allowed geopolitical_modes: {','.join(classifier.taxonomy.GEO)}.
Select only supported values for each slot.
Sentiment must be one of {','.join(classifier.taxonomy.SENTIMENT)}. Each national stance must be one of
{','.join(classifier.taxonomy.STANCE)}.
"""


def correction_contract(role: str) -> str:
    if role == "content":
        return """
FINAL INDEPENDENT-AXIS CHECK:
1. Re-read every post-type definition separately; keep every supported type even when news_reporting,
   opinions_reactions, or another broad type already applies. A technical procedure can also be
   research_explanations; a stated measurement or comparative result can also be results_analysis;
   explicit use can also be hands_on_usage.
2. Re-read every Audience Topic independently. Explicit speed, resource, price, or efficiency evidence
   supports cost_performance; orchestration, agents, tools, or harnesses support agents_tools.
3. Evaluate untracked-brand promotion independently of target relevance. When an outside company,
   product, service, project, or provider is promoted, emit its promotion key and visible subject even
   if the tracked brand is only a comparison foil. Do not transfer that outside subject's release,
   promotion, API, openness, or product attributes to the tracked brand.
4. A factual report may coexist with business_finance for organization, competition, capital, strategy,
   or key-personnel evidence. Do not use geopolitical framework for an ordinary business framework.
"""
    return """
FINAL TARGET-BRAND AND STATE CHECK:
1. Judge each D slot only for that tracked brand. Praise, complaints, releases, and product attributes
   belonging to another company must not transfer through a comparison or mention.
2. Explicit favorable experience, admiration, or achievement for this brand supports testimonial and
   positive sentiment. A qualified positive/negative experience may be mixed. Do not require hands-on
   use for testimonial.
3. A neutrally attributed third-party allegation supports investigate_claim but does not by itself make
   the author's sentiment negative or adopt the allegation as nationalism.
4. When brand-specific evidence is absent, use unavailable with unknown sentiment and country stances.
   Otherwise never use unavailable. When nationalism is absent, both country stances must be none.
5. Before output, check that sentiment, product labels, geopolitical mode, and both stances all concern
   the same target brand named by the D slot.
"""


def direct_request(original: dict[str, Any], role: str, version: str = "v1") -> dict[str, Any]:
    system = original["system"]
    boundary = "FIXED NAMED OUTPUT MAP:"
    if boundary not in system:
        raise ValueError("retained named output contract missing")
    system = system.split(boundary, 1)[0]
    if version in ("v2", "v3"):
        system += correction_contract(role)
    elif version != "v1":
        raise ValueError("unknown Gemma classifier configuration")
    system += tagged_contract(role)
    request = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, *original["messages"]],
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0.2,
        "reasoning_effort": "none",
    }
    if version == "v3":
        # Gemma 4's own model documentation recommends its trained sampling
        # defaults and activates thinking with this system control token.
        request["messages"][0]["content"] = "<|think|>\n" + system
        request["temperature"] = 1.0
        request["top_p"] = 0.95
        request["top_k"] = 64
        request.pop("reasoning_effort")
    return request


def prepare_entries(version: str = "v1") -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = read(SOURCE)
    signed = dict(contract)
    signature = signed.pop("contract_sha256")
    if classifier.digest(signed) != signature:
        raise ValueError("retained classifier contract signature mismatch")
    if contract.get("suite") != "diagnostic" or len(contract.get("source_post_ids", [])) != 24:
        raise ValueError("retained classifier diagnostic incomplete")
    entries = []
    for batch in contract["batches"]:
        if len(batch["source_post_ids"]) != 1 or len(batch["roles"]) != 2:
            raise ValueError("retained classifier is not two-role singleton")
        for role in batch["roles"]:
            entries.append({
                "source_post_id": batch["source_post_ids"][0],
                "role": role["role"],
                "source_evidence": batch["source_evidence"],
                "original_request_sha256": role["request_sha256"],
                "request": direct_request(role["request"], role["role"], version),
            })
    if len(entries) != 48:
        raise ValueError("retained classifier request count changed")
    return contract, entries


def parse_tagged(content: str, entry: dict[str, Any]) -> dict[str, Any]:
    # Gemma 4 thinking mode may return its thought channel inline before the
    # final answer. Remove only that documented leading channel; all other
    # extra text remains a structural error.
    if content.lstrip().startswith("<|channel>thought"):
        close = content.find("<channel|>")
        if close < 0:
            raise ValueError("Gemma thought channel is unterminated")
        content = content[close + len("<channel|>"):].lstrip()
    decisions, posts, _ = classifier._slots(entry["source_evidence"])
    decision_blocks = re.findall(r"\[\[DECISION\]\](.*?)\[\[/DECISION\]\]", content, re.DOTALL)
    root: dict[str, Any] = {"decisions": {}}
    for block in decision_blocks:
        slot = _field(block, "SLOT")
        if slot in root["decisions"]:
            raise ValueError("duplicate decision slot")
        if entry["role"] == "content":
            root["decisions"][slot] = {
                "outcome": _field(block, "OUTCOME"),
                "post_types": _values(_field(block, "POST_TYPES"), classifier.taxonomy.POST_TYPES, empty=True),
                "audience_topics": _values(_field(block, "AUDIENCE_TOPICS"), classifier.taxonomy.TOPICS),
            }
        else:
            root["decisions"][slot] = {
                "product_labels": _values(_field(block, "PRODUCT_LABELS"), classifier.taxonomy.PRODUCT_LABELS),
                "sentiment": _field(block, "SENTIMENT"),
                "geopolitical_modes": _values(_field(block, "GEOPOLITICAL_MODES"), classifier.taxonomy.GEO),
                "china_national_stance": _field(block, "CHINA_NATIONAL_STANCE"),
                "us_national_stance": _field(block, "US_NATIONAL_STANCE"),
            }
    remainder = re.sub(r"\[\[DECISION\]\].*?\[\[/DECISION\]\]", "", content, flags=re.DOTALL)
    if entry["role"] == "content":
        root["post_promotions"] = {}
        promotion_blocks = re.findall(r"\[\[PROMOTION\]\](.*?)\[\[/PROMOTION\]\]", content, re.DOTALL)
        for block in promotion_blocks:
            slot = _field(block, "SLOT")
            if slot in root["post_promotions"]:
                raise ValueError("duplicate promotion slot")
            root["post_promotions"][slot] = _values(_field(block, "KEYS"), classifier.taxonomy.PROMOTIONS)
        root["promoted_subjects"] = {slot: [] for slot in posts}
        subject_blocks = re.findall(r"\[\[SUBJECT\]\](.*?)\[\[/SUBJECT\]\]", content, re.DOTALL)
        for block in subject_blocks:
            slot = _field(block, "POST_SLOT")
            if slot not in root["promoted_subjects"]:
                raise ValueError("unknown subject post slot")
            def optional(name: str) -> str | None:
                value = _field(block, name)
                return None if value == "NULL" else value
            root["promoted_subjects"][slot].append({
                "name": _field(block, "NAME"),
                "handle": optional("HANDLE"),
                "domain": optional("DOMAIN"),
                "account_handle": optional("ACCOUNT_HANDLE"),
                "evidence": _field(block, "EVIDENCE"),
            })
        remainder = re.sub(r"\[\[PROMOTION\]\].*?\[\[/PROMOTION\]\]", "", remainder, flags=re.DOTALL)
        remainder = re.sub(r"\[\[SUBJECT\]\].*?\[\[/SUBJECT\]\]", "", remainder, flags=re.DOTALL)
    if remainder.strip():
        raise ValueError("tagged response has extra text")
    parsed = classifier.taxonomy.parse(root, decisions, posts, entry["role"])
    if not parsed:
        raise ValueError("tagged response fails classifier contract")
    return parsed


def validate_response(response: Any, entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(response, dict) or response.get("model") != MODEL:
        raise ValueError("DeepInfra model identity mismatch")
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or choices[0].get("finish_reason") != "stop":
        raise ValueError("DeepInfra completion incomplete")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("DeepInfra completion content missing")
    parsed = parse_tagged(content, entry)
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    normalized = {
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cached_input_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
        "cost_usd": usage.get("estimated_cost"),
        "provider_request_id": response.get("id"),
    }
    if not all(isinstance(normalized[key], int) for key in ("input_tokens", "output_tokens", "total_tokens")):
        raise ValueError("DeepInfra token receipt missing")
    if not isinstance(normalized["cost_usd"], (int, float)):
        raise ValueError("DeepInfra cost receipt missing")
    return parsed, normalized


def reservation(entries: list[dict[str, Any]]) -> float:
    input_bound = sum((len(transport.canonical(entry["request"])) + 2) // 3 for entry in entries)
    one_attempt = input_bound * INPUT_PRICE / 1_000_000
    one_attempt += len(entries) * MAX_OUTPUT_TOKENS * OUTPUT_PRICE / 1_000_000
    return round(one_attempt * MAX_ATTEMPTS, 8)


def reserve(trial: Path, contract: dict[str, Any], entries: list[dict[str, Any]], version: str) -> dict[str, Any]:
    amount = reservation(entries)
    with LOCK.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        ledger = read(LEDGER)
        task = ledger["attempts"].setdefault(TASK_KEY, {"profiles": {}, "reserved_usd": 0.0})
        if float(ledger["reserved_usd"]) + amount > 30 or float(task["reserved_usd"]) + amount > 3:
            raise ValueError("experiment reservation exceeds cap")
        if trial.name in ledger.setdefault("direct_provider_reservations", {}):
            raise ValueError("trial already reserved")
        ledger["direct_provider_reservations"][trial.name] = {
            "reserved_usd": amount,
            "model_task": TASK_KEY,
            "original_contract_sha256": contract["contract_sha256"],
            "reason": "Delivery Exception 39 direct Gemma classifier diagnostic",
            "created_at": now(),
        }
        ledger["reserved_usd"] = float(ledger["reserved_usd"]) + amount
        task["reserved_usd"] = float(task["reserved_usd"]) + amount
        task["profiles"][f"gemma4_classifier_direct_{version}_tagged"] = 1
        write(LEDGER, ledger)
    result = {"reserved_usd": amount, "portfolio_after_usd": ledger["reserved_usd"], "task_after_usd": task["reserved_usd"]}
    write(trial / "reservation-check.json", result)
    return result


def prepare(trial: Path, version: str = "v1") -> dict[str, Any]:
    if trial.exists():
        raise ValueError("trial directory already exists")
    contract, entries = prepare_entries(version)
    manifest = {
        "schema": f"deepinfra-gemma4-classifier/{version}-tagged",
        "created_at": now(),
        "source_contract": str(SOURCE),
        "source_contract_sha256": contract["contract_sha256"],
        "source_post_ids": contract["source_post_ids"],
        "requests_sha256": classifier.digest(entries),
        "route": {"provider": "DeepInfra", "model": MODEL, "tier": "standard", "input_usd_per_million": INPUT_PRICE, "output_usd_per_million": OUTPUT_PRICE},
        "shape": {
            "posts": 24,
            "calls": 48,
            "roles": ["content", "brand_interpretation"],
            "batch_size": 1,
            "max_concurrency": 1,
            "reasoning_effort": "gemma_thinking_control_token" if version == "v3" else "none",
            "temperature": 1.0 if version == "v3" else 0.2,
            "top_p": 0.95 if version == "v3" else None,
            "top_k": 64 if version == "v3" else None,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "representation": "tagged fixed slots",
            "configuration": version,
            "correction_checklist": version in ("v2", "v3"),
        },
    }
    write(trial / "manifest.json", manifest)
    write(trial / "requests.json", entries)
    reserve(trial, contract, entries, version)
    return manifest


def probe(trial: Path) -> dict[str, Any]:
    entries = read(trial / "requests.json")
    manifest = read(trial / "manifest.json")
    if classifier.digest(entries) != manifest["requests_sha256"]:
        raise ValueError("frozen requests changed")
    if (trial / "probe-result.json").exists():
        raise ValueError("probe already consumed")
    sender = transport.Sender(transport.secret_from_env_file("DEEPINFRA_API_KEY"), trial, time.monotonic() + WALL_SECONDS)
    result = sender.send(0, entries[0]["request"])
    final = result["attempts"][-1]
    output: dict[str, Any] = {"status": "failed_transport", "result": result}
    if final["state"] == "received":
        try:
            parsed, usage = validate_response(final["response"], entries[0])
            output = {"status": "passed", "result": result, "parsed": parsed, "usage": usage}
        except (TypeError, ValueError) as exc:
            output = {"status": "failed_validation", "result": result, "error": str(exc)}
    write(trial / "probe-result.json", output)
    return output


def run(trial: Path) -> dict[str, Any]:
    if (trial / "run-report.json").exists():
        raise ValueError("run already completed")
    entries = read(trial / "requests.json")
    manifest = read(trial / "manifest.json")
    probe_result = read(trial / "probe-result.json")
    if classifier.digest(entries) != manifest["requests_sha256"] or probe_result.get("status") != "passed":
        raise ValueError("frozen probe contract invalid")
    started = time.monotonic()
    sender = transport.Sender(transport.secret_from_env_file("DEEPINFRA_API_KEY"), trial, started + WALL_SECONDS)
    results = {0: probe_result["result"]}
    for index in range(1, len(entries)):
        results[index] = sender.send(index, entries[index]["request"])
    outputs = []
    for index, entry in enumerate(entries):
        final = results[index]["attempts"][-1]
        record = {"source_post_id": entry["source_post_id"], "role": entry["role"], "status": "transport_error", "attempts": len(results[index]["attempts"]), "error": final.get("error")}
        if final["state"] == "received":
            try:
                parsed, usage = validate_response(final["response"], entry)
                record.update(status="complete", parsed=parsed, usage=usage, error=None)
            except (TypeError, ValueError) as exc:
                record.update(status="structural_error", error=str(exc))
        outputs.append(record)
        write(trial / "outputs.partial.json", outputs)
    complete = [row for row in outputs if row["status"] == "complete"]
    costs = [row["usage"]["cost_usd"] for row in complete]
    complete_sources = [post_id for post_id in manifest["source_post_ids"] if {row["role"] for row in complete if row["source_post_id"] == post_id} == {"content", "brand_interpretation"}]
    report = {
        "schema": manifest["schema"] + "/run-report",
        "finished_at": now(),
        "wall_seconds": round(time.monotonic() - started, 3),
        "delivery": {"calls": len(entries), "complete_calls": len(complete), "complete_sources": len(complete_sources), "structural_errors": sum(row["status"] == "structural_error" for row in outputs), "transport_errors": sum(row["status"] == "transport_error" for row in outputs), "retry_attempts": sum(row["attempts"] - 1 for row in outputs)},
        "usage": {"reported_cost_usd": round(sum(costs), 12), "cost_receipts": len(costs), "input_tokens": sum(row["usage"]["input_tokens"] for row in complete), "output_tokens": sum(row["usage"]["output_tokens"] for row in complete), "cached_input_tokens": sum(row["usage"]["cached_input_tokens"] for row in complete)},
        "complete_source_ids": complete_sources,
    }
    write(trial / "outputs.json", outputs)
    write(trial / "run-report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "probe", "run"))
    parser.add_argument("trial", type=Path)
    parser.add_argument("--version", choices=("v1", "v2", "v3"), default="v1")
    args = parser.parse_args()
    result = prepare(args.trial, args.version) if args.action == "prepare" else probe(args.trial) if args.action == "probe" else run(args.trial)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
