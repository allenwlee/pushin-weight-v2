"""Frozen U18A trial contract sourced from the 2026-09-16 prompt exhibit."""
from __future__ import annotations
import re, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/research/2026-09-16-151113-u18a-two-role-classifier-prompts.md"
POST_TYPES = ("releases_updates", "hands_on_usage", "results_analysis", "questions_requests", "advertising_marketing", "events", "opportunities", "job_listings", "personnel_changes", "opinions_reactions", "research_explanations", "business_finance", "news_reporting", "other")
PRODUCT_LABELS = ("bug", "complaint", "testimonial", "ideas_requests", "investigate_claim", "none")
TOPICS = ("local_inference", "cost_performance", "model_distillation", "evals_benchmarks", "openness_license", "agents_tools", "api_developer_surface", "none", "unavailable")
PROMOTIONS = ("general", "spam", "scam", "crypto", "unauthorized", "none")
GEO = ("reporting", "framework", "nationalism", "none", "unavailable")
STANCE = ("none", "mild_pro", "pro", "constructive_critical", "anti", "mixed", "unknown")
SENTIMENT = ("positive", "neutral", "negative", "mixed", "unknown")

def _prompt(number: int) -> str:
    text = SOURCE.read_text(encoding="utf-8")
    match = re.search(rf"## Prompt {number}[^\n]*\n\n```text\n(.*?)\n```", text, re.S)
    if not match: raise ValueError("canonical prompt exhibit missing")
    value = match.group(1)
    # Accepted September 16 amendments, applied only to the named sentences.
    value = value.replace(
        "a named person joining, leaving, being appointed, or explicitly describing an\n  employment transition.",
        "a named person's formal role start, end, or change: employment, internships,\n  executive/research appointments, or formally announced adviser/ambassador roles. Exclude static\n  biographies, unchanged affiliations, generic programs, employee spotlights, and quotes without a\n  role transition.",
    )
    value = value.replace(
        "score, ranking, or reported evaluation\n  result. A broad claim that one country's or company's models are better is insufficient by itself.",
        "score, ranking, reported evaluation\n  result, or source-visible comparative assessment.",
    )
    value = value.replace("open weights, source availability", "open weights, open source, source availability")
    value = value.replace("a desired capability, improvement, unmet need, or product idea", "an explicitly stated or clearly implied gap, desired outcome, capability, improvement, unmet need, or product idea")
    value = value.replace("Official or staff self-praise", "Same-brand official or staff self-praise")
    value = value.replace("Official/staff self-praise", "Same-brand official/staff self-praise")
    return value

CONTENT_PROMPT, BRAND_PROMPT = _prompt(1), _prompt(2)

def tracked_brands() -> list[str]:
    lines = (ROOT / "config.yaml").read_text(encoding="utf-8").splitlines(); start = lines.index("enabled_models:") + 1; result=[]
    for line in lines[start:]:
        if line.startswith("  - "): result.append(line[4:].strip())
        elif line and not line.startswith((" ", "#")): break
    if len(result) < 20: raise ValueError("tracked brand registry incomplete")
    return result

def compact_catalog() -> list[dict[str, Any]]:
    """Frozen active catalog: canonical IDs plus source-maintained aliases/handles."""
    enabled = tracked_brands(); aliases={brand: [] for brand in enabled}; handles={brand: [] for brand in enabled}
    for row in json.loads((ROOT / "data/brand_keywords.json").read_text(encoding="utf-8")):
        if row.get("brand_id") in aliases and isinstance(row.get("pattern"), str) and not row.get("is_regex"):
            aliases[row["brand_id"]].append(row["pattern"].strip('"'))
    for row in json.loads((ROOT / "data/brands_accounts.json").read_text(encoding="utf-8")):
        if row.get("brand_id") in handles and isinstance(row.get("handle"), str): handles[row["brand_id"]].append(row["handle"])
    return [{"brand_id": brand, "aliases": sorted(set([brand, *aliases[brand]])), "handles": sorted(set(handles[brand])), "domains": [], "products": []} for brand in enabled]

def valid_array(value: Any, allowed: tuple[str,...], exclusive: set[str]) -> bool:
    return isinstance(value,list) and all(isinstance(x,str) and x in allowed for x in value) and len(value)==len(set(value)) and not (set(value)&exclusive and len(value)!=1)

def parse(response: Any, decisions: dict[str,tuple[str,str]], posts: dict[str,str], role: str) -> dict[str,Any]:
    root={"decisions","post_promotions","promoted_subjects"} if role=="content" else {"decisions"}
    if not isinstance(response,dict) or set(response)!=root or not isinstance(response.get("decisions"),dict) or set(response["decisions"])!=set(decisions): return {}
    if role=="content" and (not isinstance(response["post_promotions"],dict) or not isinstance(response["promoted_subjects"],dict) or set(response["post_promotions"])!=set(posts) or set(response["promoted_subjects"])!=set(posts)): return {}
    output={tweet:[] for tweet in posts.values()}
    for slot,(tweet,brand) in decisions.items():
        value=response["decisions"][slot]
        if not isinstance(value,dict): return {}
        if role=="content":
            if set(value)!={"outcome","post_types","audience_topics"} or value.get("outcome") not in {"classified","context_missing"} or not valid_array(value.get("post_types"),POST_TYPES,{"other"}) or not valid_array(value.get("audience_topics"),TOPICS,{"none","unavailable"}): return {}
            if not value["audience_topics"]: return {}
            if (value["outcome"]=="classified" and not value["post_types"]) or (value["outcome"]=="context_missing" and (value["post_types"] or value["audience_topics"] != ["unavailable"])): return {}
        else:
            if set(value)!={"product_labels","sentiment","geopolitical_modes","china_national_stance","us_national_stance"} or not valid_array(value.get("product_labels"),PRODUCT_LABELS,{"none"}) or not valid_array(value.get("geopolitical_modes"),GEO,{"none","unavailable"}) or value.get("sentiment") not in SENTIMENT or value.get("china_national_stance") not in STANCE or value.get("us_national_stance") not in STANCE: return {}
            if not value["product_labels"] or not value["geopolitical_modes"]: return {}
            if value["geopolitical_modes"] == ["unavailable"]:
                if (value["china_national_stance"], value["us_national_stance"]) != ("unknown", "unknown"): return {}
            elif "nationalism" not in value["geopolitical_modes"] and (value["china_national_stance"]!="none" or value["us_national_stance"]!="none"): return {}
        output[tweet].append({"brand_id":brand,**value})
    if role=="content":
        for slot in posts:
            keys=response["post_promotions"][slot]; subjects=response["promoted_subjects"][slot]
            if not keys or not valid_array(keys,PROMOTIONS,{"none","general"}) or not isinstance(subjects,list) or ((keys==["none"]) != (subjects==[])): return {}
            if any(not isinstance(x,dict) or set(x)!={"name","handle","domain","account_handle","evidence"} or not isinstance(x.get("name"),str) or not x["name"] or not isinstance(x.get("evidence"),str) or not x["evidence"] for x in subjects): return {}
            if any(x[field] is not None and (not isinstance(x[field], str) or not x[field].strip()) for x in subjects for field in ("handle", "domain", "account_handle")): return {}
    return output
