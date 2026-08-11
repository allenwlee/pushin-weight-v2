"""Binary LLM relevancy gate for staff authors returned by Call A.

Plan: docs/plans/2026-07-30-002-feat-hybrid-funnel-then-reconcile-accounts-plan.md
Unit U6 (KTD6).

WHY THIS FILE EXISTS
--------------------
The hybrid funnel's bare B1 + handle-only B2/B3 + thin-co C1/C2/C3 still
admits some EN dictionary noise into the C* paths. The bare co ("model",
"api", etc.) overlaps with everyday English. U6 introduces a binary
LLM relevancy gate that fires only for C-path posts and C-tier brand
attributions. The gate is multilingual keep-biased per the system prompt
below.

This module is the gate + parser. The runtime wire-in (calling the LLM
inside monitor/cycle.py between attribute and translate) is a follow-up;
this unit ships the deterministic logic so the integration can land
safely.

See R19a for the prompt source-of-truth.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# R19a — Source-of-truth prompt constants
# ---------------------------------------------------------------------------

BINARY_RELEVANCY_SYSTEM: str = """\
You are a relevance filter for AI/LLM industry monitoring.

Decide if a social post is ABOUT an AI model, LLM product, lab, API, agent framework,
or related ML research/product discussion — not merely sharing a word that also names
a brand (sports, cars, animals, people, consumer gadgets, finance ticker noise).

Output EXACTLY one token on the first line: KEEP or DROP.
Optional second line: short reason (≤12 words), English ok.

Rules:
- KEEP when the post discusses the AI product/lab/model/API even if the language is
  Japanese, Korean, Chinese, Indonesian, Turkish, Spanish, etc. Latin brand tokens
  and loanwords (llm, model, api) often appear in non-English tech posts — that is fine.
- KEEP when uncertain but the post plausibly concerns AI/ML (multilingual keep bias).
- DROP pure sports/F1/racing, pure consumer phone/gadget unboxing with no AI product
  angle, pure name-homonym chatter, spam, or empty engagement bait.
- DROP if the only match is a bare ambiguous token with no AI product context.
- Do not translate the post. Do not classify sentiment or post type.
"""


def binary_relevancy_user_template(
    *,
    brand_hints: str,
    call_id: str,
    post_text: str,
) -> str:
    """R19a user template. Parameters match the plan body verbatim."""
    return f"""\
Brand context (may be empty): {brand_hints}
Call id: {call_id}
Post text:
---
{post_text}
---
Reply KEEP or DROP.
"""


# ---------------------------------------------------------------------------
# Verdict dataclass
# ---------------------------------------------------------------------------


@dataclass
class BinaryRelevancyVerdict:
    """Result of the binary gate.

    decision: "KEEP" | "DROP"
    reason: optional short reason from the LLM's second line
    raw: full LLM response for audit
    parse_failed: True if the LLM output didn't follow the KEEP/DROP
        protocol; per the keep-bias rule, parse_failed → KEEP.
    """

    decision: str
    reason: str
    raw: str
    parse_failed: bool


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_binary_relevancy(response: str) -> BinaryRelevancyVerdict:
    """Parse an LLM response into a BinaryRelevancyVerdict.

    Rules (from R19a):
      - First line MUST be KEEP or DROP (case-insensitive).
      - Optional second line: short reason (≤ 12 words, English OK).
      - Multilingual keep bias: any parse failure → KEEP (logged).

    The function is pure: no I/O, no LLM call. Wire the call site
    elsewhere; this is the deterministic shape.
    """
    raw = response or ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        # No output at all → keep bias
        return BinaryRelevancyVerdict(
            decision="KEEP",
            reason="empty response",
            raw=raw,
            parse_failed=True,
        )

    first = lines[0].strip().upper()
    if first == "KEEP":
        decision = "KEEP"
        reason = lines[1] if len(lines) > 1 else ""
        return BinaryRelevancyVerdict(
            decision=decision,
            reason=reason,
            raw=raw,
            parse_failed=False,
        )
    if first == "DROP":
        decision = "DROP"
        reason = lines[1] if len(lines) > 1 else ""
        return BinaryRelevancyVerdict(
            decision=decision,
            reason=reason,
            raw=raw,
            parse_failed=False,
        )

    # Unknown first-line token — keep bias
    return BinaryRelevancyVerdict(
        decision="KEEP",
        reason=f"unparseable first line: {lines[0][:40]!r}",
        raw=raw,
        parse_failed=True,
    )


# ---------------------------------------------------------------------------
# Gate: which call_ids + brand_hints trigger the binary gate
# ---------------------------------------------------------------------------


GATED_CALL_IDS: frozenset[str] = frozenset({"A"})


def should_apply_binary_gate(
    *,
    call_id: str,
    brand_hints: str,
    author_role: str | None = None,
) -> bool:
    """Only a current staff-only Call A author requires relevance."""

    del brand_hints  # brand tier never grants or triggers this gate
    return call_id == "A" and author_role == "staff"


# ---------------------------------------------------------------------------
# LLM caller (placeholder — wire the real Anthropic client in follow-up)
# ---------------------------------------------------------------------------


def call_binary_relevancy_llm(
    *,
    post_text: str,
    call_id: str,
    brand_hints: str,
    # The actual LLM client is injected by the wire-in. Default is a
    # stub that returns KEEP — production wire-in replaces this.
    llm_call=None,
) -> BinaryRelevancyVerdict:
    """Invoke the LLM with the system+user prompt and parse the response.

    `llm_call(system, user) -> str` is the injected dependency. Production
    wire-in constructs an Anthropic client; tests use a stub.
    """
    if llm_call is None:
        # Default stub: KEEP. Real wire-in MUST inject a non-None caller.
        return BinaryRelevancyVerdict(
            decision="KEEP",
            reason="no llm_call injected (stub)",
            raw="",
            parse_failed=True,
        )

    user = binary_relevancy_user_template(
        brand_hints=brand_hints,
        call_id=call_id,
        post_text=post_text,
    )
    response = llm_call(BINARY_RELEVANCY_SYSTEM, user)
    return parse_binary_relevancy(response)


# ---------------------------------------------------------------------------
# Production wire-in helper (U6 runtime)
# ---------------------------------------------------------------------------

# Default model for the binary relevancy gate. Sonnet-class — small,
# fast, cheap. The gate's prompt is tiny (one tweet + brand context)
# so a smaller model is fine.
DEFAULT_RELEVANCY_MODEL = "claude-haiku-4-5"


def build_binary_relevancy_llm_call(
    *,
    client=None,
    model: str = DEFAULT_RELEVANCY_MODEL,
    max_tokens: int = 32,
    timeout_seconds: int = 30,
):
    """Construct an `llm_call(system, user) -> str` factory for the
    binary relevancy gate, wired to the project's existing
    Anthropic-Claude client pattern (the same `messages_create`
    interface used by the translator + classifier).

    The returned closure is the dependency `monitor/cycle.py::CycleRunner`
    consumes via its `_relevancy_llm_call` injection point. When the
    Anthropic client is None (env not configured), returns None — the
    cycle then runs with the gate as a no-op (KEEP).

    Usage in management commands:
        from x_monitor.relevancy import build_binary_relevancy_llm_call
        client = build_anthropic_client_from_env()
        llm_call = build_binary_relevancy_llm_call(client=client)
        CycleRunner(..., _relevancy_llm_call=llm_call)
    """
    if client is None:
        return None

    def llm_call(system: str, user: str) -> str:
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "timeout": timeout_seconds,
        }
        result = client.messages_create(**kwargs)
        # Anthropic SDK returns {"content": [{"text": "...", ...}]} —
        # extract the first text block.
        content = result.get("content") or []
        if not content:
            return ""
        # content may be a list of blocks; pull the first text.
        first = content[0]
        if isinstance(first, dict):
            return first.get("text", "")
        return str(first)

    return llm_call
