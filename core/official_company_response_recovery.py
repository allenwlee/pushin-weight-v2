"""Conservative recovery of saved offering-screen responses.

The response remains available separately. Only typography and whitespace are
normalized for matching, and a recovered citation always quotes the supplied
source verbatim. Ambiguous or unsupported claims are left unresolved.
"""
from copy import deepcopy

from core.official_company_offerings import TYPES


def _normalized(text):
    chars, offsets = [], []
    equivalents = {"“": '"', "”": '"', "‘": "'", "’": "'"}
    for index, char in enumerate(text):
        item = equivalents.get(char, char)
        if item.isspace():
            if chars and chars[-1] != " ":
                chars.append(" ")
                offsets.append(index)
        else:
            chars.append(item)
            offsets.append(index)
    return "".join(chars).strip(), offsets


def recover_quote(quote, source):
    if not isinstance(quote, str) or len(quote.strip()) < 8 or not isinstance(source, str):
        return None
    if quote in source:
        return quote
    needle, _ = _normalized(quote.strip())
    haystack, offsets = _normalized(source)
    if len(needle) < 8:
        return None
    start = haystack.find(needle)
    if start < 0 or haystack.find(needle, start + 1) >= 0:
        return None
    return source[offsets[start]:offsets[start + len(needle) - 1] + 1]


def recover_screen(value, evidence):
    """Return a recoverable screen and an audit of unresolved source claims."""
    if not isinstance(value, dict):
        return value, []
    screen = deepcopy(value)
    sources = {s.get("id"): s.get("text") for s in evidence.get("sources", []) if isinstance(s, dict)}
    audit = []

    def citations(items, label):
        if not isinstance(items, list) or len(items) > 3:
            audit.append(f"{label}:invalid_citations")
            return None
        result = []
        for citation in items:
            if not isinstance(citation, dict) or set(citation) != {"source_id", "quote"}:
                audit.append(f"{label}:invalid_citation")
                return None
            source_id = citation["source_id"]
            recovered = recover_quote(citation["quote"], sources.get(source_id) if isinstance(source_id, str) else None)
            if recovered is None:
                audit.append(f"{label}:unresolved_citation")
                return None
            if recovered != citation["quote"]:
                audit.append(f"{label}:recovered_citation")
            result.append({"source_id": citation["source_id"], "quote": recovered})
        return result

    identity = citations(screen.get("identity_citations"), "identity")
    if identity is None or (not identity and screen.get("account_presentation") != "unclear"):
        screen["account_presentation"] = "unclear"
        screen["identity_citations"] = []
        audit.append("identity:unresolved")
    else:
        screen["identity_citations"] = identity
    products = screen.get("products")
    if not isinstance(products, list) or len(products) > 8:
        return screen, audit
    accepted = []
    allowed = {"model-llm": {"original_model", "derivative_model"},
               "model-other": {"original_model", "derivative_model"}, "agent": {"own_agent"},
               "harness": {"own_harness"}, "other": {"own_platform_service"}}
    for index, product in enumerate(products):
        label = f"product:{index}"
        if not isinstance(product, dict) or set(product) != {"name", "type", "contribution", "rationale", "citations"}:
            audit.append(f"{label}:invalid_fields")
            continue
        kind, contribution = product.get("type"), product.get("contribution")
        if isinstance(kind, str):
            kind = kind.strip().lower()
        if isinstance(contribution, str):
            contribution = contribution.strip().lower()
        if not isinstance(kind, str) or kind not in TYPES or not isinstance(contribution, str) or contribution not in allowed[kind] or not isinstance(product.get("name"), str) or not product["name"].strip() or not isinstance(product.get("rationale"), str) or not product["rationale"].strip():
            audit.append(f"{label}:unresolved_category_or_fields")
            continue
        found = citations(product["citations"], label)
        if not found:
            audit.append(f"{label}:unresolved")
            continue
        accepted.append({**product, "type": kind, "contribution": contribution, "citations": found})
    screen["products"] = accepted
    uncertainties = screen.get("uncertainties")
    if isinstance(uncertainties, list) and all(isinstance(item, str) for item in uncertainties):
        if any("unresolved" in item or "invalid" in item for item in audit):
            uncertainties.append("Some model claims could not be resolved against the supplied evidence.")
        if not accepted and not uncertainties:
            uncertainties.append("No supported product claim was supplied.")
    return screen, audit
