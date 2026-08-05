"""Generate config/harvest_policy.yaml from the live planner + DB keyword cache.

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U5 (R8, R9, R15, R16-R18).

Reads:
  - config.yaml  (enabled_models, x_query_specs, x_monitor_list_id)
  - data/brand_keywords.json  (live primary token cache)

Emits:
  - config/harvest_policy.yaml — the AFTER-3/5 policy file

This script is OFFLINE (no DB, no network). It exists to make the
migration reproducible and re-runnable; the resulting YAML is hand-
reviewed before commit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

# Make x_monitor importable when run from anywhere in the repo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from x_monitor.harvest_policy import HANDLE_TIER_TOP  # noqa: E402


REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "config.yaml"
BRAND_KEYWORDS = REPO / "data" / "brand_keywords.json"
OUT = REPO / "config" / "harvest_policy.yaml"


# Handle -> brand mapping for B2/B3 handles.
#
# The live config.yaml x_query_specs comments enumerate which brand each
# handle covers, but data/brands_accounts.json (the DB cache) does NOT
# carry these mappings — it's stale on this surface. To keep the build
# reproducible offline, we mirror the operator-maintained associations
# here. This list is intentionally hard-coded and reviewed by hand; do
# not derive it from x_query_specs (circular) or brands_accounts.json
# (stale on this surface). If a handle is added or moved, update this
# table.
HANDLE_TO_BRAND: dict[str, str] = {
    # B2 — top-presence / global brands
    "deepseek_ai": "deepseek",
    "Ali_TongyiLab": "qwen",
    "Alibaba_Qwen": "qwen",
    "hailuo_ai": "minimax",
    "MiniMax_AI": "minimax",
    "MiniMaxAgent": "minimax",
    "StepFun_ai": "stepfun",
    "stepfunai": "stepfun",
    "MistralAI": "mistral",
    "TencentHunyuan": "hunyuan",
    "Zai_org": "glm",
    "ZhihuFrontier": "inclusionai",
    "AntLingAGI": "inclusionai",
    "robbyant_brain": "inclusionai",
    "TheInclusionAI": "inclusionai",
    "LG_AI_Research": "exaone",
    "SakanaAILabs": "sakana_ai",
    "NVIDIAAI": "nemo_megatron",
    "NVIDIAAIDev": "nemo_megatron",
    # B3 — other-brand handles
    "bytedanceoss": "doubao",
    "BytePlusGlobal": "doubao",
    "doubaoai": "doubao",
    "SenseTime_AI": "sensechat",
    "Kling_ai": "sensechat",
    "XiaomiMiMo": "mimo",
    "XiaomiMiMoDevs": "mimo",
    "Kimi_Moonshot": "moonshot_kimi",
    "01AI_Yi": "yi",
    "AIatMeta": "llama",
    "ErnieforDevs": "ernie",
    "PaddlePaddle": "ernie",
    "upstageai": "upstage",
}


def _primary_tokens_for(brand_id: str, rows: list[dict]) -> list[str]:
    return [r["pattern"] for r in rows if r["brand_id"] == brand_id and r["is_primary"] == 1]


def main() -> None:
    with CONFIG.open() as f:
        cfg = yaml.safe_load(f)
    enabled_models = cfg.get("enabled_models") or []
    specs = cfg.get("x_query_specs") or []

    # Build brand -> current spec assignment
    brand_to_spec_kind: dict[str, str] = {}
    # brand -> tokens (from C-specs' brands dict)
    brand_tokens_from_cspec: dict[str, list[str]] = {}
    # spec -> co_occurrence
    spec_co: dict[str, list[str]] = {}
    # spec -> not_include
    spec_not_include: dict[str, list[str]] = {}
    # B2/B3 -> handles (collected under handle spec)
    spec_handles: dict[str, list[str]] = {}
    # B1 -> wide_net_brands
    spec_wide_net_brands: dict[str, list[str]] = {}

    for s in specs:
        cid = s.get("call_id", "")
        spec_co[cid] = list(s.get("co_occurrence") or [])
        spec_not_include[cid] = list(s.get("not_include") or [])
        spec_handles[cid] = list(s.get("handles") or [])
        spec_wide_net_brands[cid] = list(s.get("wide_net_brands") or [])

        if s.get("is_wide_net"):
            for b in (s.get("wide_net_brands") or []):
                brand_to_spec_kind[b] = "bare"
        elif s.get("handles"):
            # Handle spec — but we don't know which brand owns which handle
            # without brands_accounts. We map by name later via the DB.
            brand_to_spec_kind.setdefault(f"_HANDLE_{cid}", "handle")
        else:
            for b, toks in (s.get("brands") or {}).items():
                brand_to_spec_kind[b] = "co"
                brand_tokens_from_cspec[b] = list(toks or [])

    # Pull primary tokens from brand_keywords.json for B1 brands
    with BRAND_KEYWORDS.open() as f:
        kw_rows = json.load(f)

    # Map B2/B3 handles back to brands via HANDLE_TO_BRAND (operator table).
    handle_to_brand: dict[str, str] = HANDLE_TO_BRAND

    # Build the policy doc
    brands_out: dict[str, dict] = {}

    for nick in enabled_models:
        kind = brand_to_spec_kind.get(nick)
        if kind == "bare":
            # B1 brand
            toks = _primary_tokens_for(nick, kw_rows)
            brands_out[nick] = {
                "paths": ["bare"],
                "tokens": toks,
                "notes": "B1 bare-keyword fan-out (live wire path).",
            }
        elif kind == "co":
            # C1/C2/C3 brand
            tokens = brand_tokens_from_cspec.get(nick, [])
            # Find which C spec owns this brand
            owning_cid = None
            for s in specs:
                if nick in (s.get("brands") or {}):
                    owning_cid = s.get("call_id")
                    break
            co = list(spec_co.get(owning_cid, []) or []) if owning_cid else []
            ni = list(spec_not_include.get(owning_cid, []) or []) if owning_cid else []
            entry: dict = {
                "paths": ["co"],
                "tokens": tokens,
                "co": co,
                "notes": f"Owning pack: {owning_cid or '?'}.",
            }
            if ni:
                entry["not_include"] = ni
            brands_out[nick] = entry
        elif kind == "handle":
            # handled below
            pass
        else:
            # brand not assigned in current spec; record as explicit none
            brands_out[nick] = {
                "paths": ["none"],
                "notes": "Not present in any current spec; explicit opt-out pending review.",
            }

    # Now handle-spec brands. Walk B2 and B3 handle lists; for each handle,
    # find its owning brand via handle_to_brand; group by brand.
    handle_brands: dict[str, set[str]] = {}  # brand -> set of handles
    for cid in ("B2", "B3"):
        for h in spec_handles.get(cid, []):
            nick = handle_to_brand.get(h)
            if nick is None:
                continue
            handle_brands.setdefault(nick, set()).add(h)
    for nick, hs in handle_brands.items():
        # If the brand was previously classified as 'none', re-classify
        # as handle (the handles provide coverage). 'none' is for brands
        # with no spec at all, not for handle-only brands.
        existing = brands_out.get(nick)
        if existing is not None:
            # Brand was assigned a spec already (bare or co). Add handle.
            paths = list(existing.get("paths", []))
            if "none" in paths:
                paths.remove("none")
            if "handle" not in paths:
                paths.append("handle")
            existing["paths"] = paths
        else:
            # Brand was not in any spec; handle-only via B2/B3.
            existing = {
                "paths": ["handle"],
                "tokens": _primary_tokens_for(nick, kw_rows),
                "handles": sorted(hs),
                "notes": "Handle-only path (B2/B3).",
            }
            brands_out[nick] = existing
        existing["handles"] = sorted(hs)
        # Tier: B3 handles get handle_tier=other. Detect via the cid that
        # owns the handle in spec_handles.
        tier = HANDLE_TIER_TOP
        for h in hs:
            for cid in ("B3", "B2"):
                if h in (spec_handles.get(cid) or []):
                    tier = (
                        "other" if cid == "B3"
                        else "top-presence"
                    )
                    break
        if tier != "top-presence":
            existing["handle_tier"] = "other"

    # Per R17, versioned tokens for brands with explicit versioned patterns
    # (e.g., llama has "Llama 3", "Llama 4" — versioned_bare would carry
    # those, leaving "Llama" / "Meta Llama" as bare tokens). For 3/5 we
    # keep bare tokens in primary and put versioned patterns into
    # versioned_tokens so the derivation puts them first.
    versioned_patterns = {
        "llama": ["Llama 4", "Llama 3"],
    }
    for nick, vp in versioned_patterns.items():
        if nick in brands_out and "versioned_tokens" not in brands_out[nick]:
            brands_out[nick]["versioned_tokens"] = vp

    # Build co_packs from the live C-specs
    co_packs_out: list[list[str]] = []
    for s in specs:
        cid = s.get("call_id", "")
        if not cid.startswith("C"):
            continue
        # Sort brand ids inside the pack for stable output
        pack_brands = sorted((s.get("brands") or {}).keys())
        if pack_brands:
            co_packs_out.append(pack_brands)

    # Compose the policy doc
    policy_doc: dict = {
        "brands": brands_out,
        "co_packs": co_packs_out,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        yaml.safe_dump(policy_doc, f, sort_keys=False, allow_unicode=True, width=120)
    print(f"wrote {OUT} ({len(brands_out)} brands, {len(co_packs_out)} co_packs)")


if __name__ == "__main__":
    main()