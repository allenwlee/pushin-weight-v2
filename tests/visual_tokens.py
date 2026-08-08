"""
Visual tokens — single source of truth for pinned computed-style values.

Per plan § "Visual-drift detection: Element Audit + Chrome DevTools MCP
(added 2026-08-08)": every visible region on the v22-master mockup gets a row
here pinning its expected computed CSS value. `tests/element_audit.py`
reads from this dict and fails when live values drift from the pinned ones.

When a value is INTENTIONALLY changed, update both the plan body (changelog
row) and the BEFORE comment in this file's pinned row to preserve audit
trail. NEVER remove a pinned row without plan-body update.

Format:
    "selector": {
        "css_property": expected_value,  # exact string match
        "_before": "BEFORE: <previous value + defect description>",
    }

Run via tests/element_audit.py — do not call this file directly.
"""

VISUAL_TOKENS = {
    ".pulse-chip .name": {
        "color": "rgb(243, 244, 246)",
        "_before": "BEFORE 2026-08-08: rgb(0, 0, 0) — black text invisible on dark pulse-card fill. User-reported defect.",
    },
    ".voice-chip": {
        "background-color": "rgba(124, 58, 237, 0.18)",
        "color": "rgb(233, 213, 255)",
        "padding": "1px 6px",
        "border-radius": "8px",
        "_note": "iter 4 addition; mockup-lag is acceptable (region not yet in v22-master). Pin from live iter 4 verified values.",
    },
    ".feed-handle": {
        "color": "rgb(243, 244, 246)",
        "text-decoration-line": "none",
        "font-weight": "600",
        "_before": "BEFORE 2026-08-08: color rgb(0, 0, 238) (browser link blue), text-decoration underline, font-weight 400 — feed handle rendered as default underlined link instead of styled author chip.",
    },
    ".filter-button.is-active": {
        "color": "rgb(255, 255, 255)",
        "background-color": "rgb(59, 130, 246)",
        "_note": "iter 4 verified; mockup pin pending — capture from mockup next iter.",
    },
    ".delta.up::before": {
        "content": "\"▲ \"",
        "color": "rgb(34, 197, 94)",
        "_note": "Pin only asserted when at least one .delta.up exists in current window. Otherwise tolerate absence (data-dependent).",
    },
}


def regions() -> list[str]:
    """Return pinned CSS selectors (excluding metadata keys)."""
    return [k for k in VISUAL_TOKENS.keys() if not k.startswith("_")]


def pinned(selector: str) -> dict[str, str]:
    """Return the pinned CSS-property → expected-value mapping for a selector."""
    return {k: v for k, v in VISUAL_TOKENS[selector].items() if not k.startswith("_")}
