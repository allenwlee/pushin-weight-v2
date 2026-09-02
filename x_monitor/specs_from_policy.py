"""specs_from_policy: derive XQuerySpec list from a loaded HarvestPolicy.

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U3 (R6-R9, R12, R20).

M7 DRY: this function BUILDS XQuerySpec objects; rendering stays in
x_monitor.query_plan._build_query / plan_calls. No second renderer is
added here.

What this function does
-----------------------
- B1: one wide-net spec covering every brand whose `paths` includes
  `bare` or `versioned_bare` (R8). Tokens come from policy (versioned_bare
  brands contribute tokens + versioned_tokens; bare brands contribute
  tokens only). Uses is_wide_net=True so the renderer reads tokens from
  the wide_net_brands list at render time — the planner passes them via
  `primary_keywords` (which in 3/5 is seeded from policy tokens, not the
  DB keyword table; that swap is part of cutover U5).

- Co packs: emit one C-style spec per co_pack. The pack's brands
  contribute their `co` list to the secondary group (union — brands in a
  pack share the co chunk; per KTD5 this is intentional for 3/5, 4/5
  may refine). The pack's brands contribute their `tokens` to the
  primary group (one paren per brand). `not_include` is the union of
  brand-local `not_include` across brands in the pack (R4 — brand-local
  bleed is contained because packs are operator-chosen).

- Handle: emit one B-style spec per handle *tier* (R9). Two tiers for 3/5:
  "top-presence" (default) and "other". A brand declares its tier via
  the `handle_tier` field on its BrandPolicy (defaults to "top-presence"
  if omitted). Spec handles are the union of `handles` across brands in
  the tier.

- Skips: brands with `paths: [none]` are not emitted (they opted out,
  per AE1).

- A single brand can appear on multiple specs (R3 multi-path): a brand
  with `paths: [bare, handle]` shows up on B1 (bare fan-out) AND on the
  handle spec for its tier.

Output
------
A list of XQuerySpec instances in deterministic order:
  [B1, ...C-specs in co_pack order..., B-handle-top, B-handle-other]

Determinism matters for the regression net: sorted iteration over brand
sets and stable co_pack order keep the rendered queries byte-stable.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from .harvest_policy import (
    HANDLE_TIER_OTHER,
    HANDLE_TIER_TOP,
    BrandPolicy,
    HarvestPolicy,
    VersionFamily,
)
from .query_plan import XQuerySpec

# Handle tier names (R9). 3/5 has two tiers matching the legacy B2/B3 split;
# 4/5 may add more. Re-exported for tests.
__all__ = [
    "HANDLE_TIER_OTHER",
    "HANDLE_TIER_TOP",
    "expand_version_family",
    "primary_keywords_from_policy",
    "specs_from_policy",
]


def expand_version_family(family: VersionFamily | None) -> list[str]:
    """Expand one version-family declaration in stable, duplicate-free order."""
    if family is None:
        return []

    tokens: list[str] = [
        f"{family.prefix}{major}"
        for major in range(
            family.current_major - family.lookback,
            family.current_major + family.lookahead + 1,
        )
    ]
    for major in range(
        family.current_major, family.current_major + family.lookahead + 1
    ):
        tokens.extend(
            f"{family.prefix}{major}{suffix}"
            for suffix in family.extra_suffixes
        )

    deduplicated: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            deduplicated.append(token)
            seen.add(token)
    return deduplicated


def _dedupe_tokens(tokens: Iterable[str]) -> list[str]:
    """Keep the first occurrence of each token while preserving policy order."""
    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in seen:
            result.append(token)
            seen.add(token)
    return result


def _expand_tokens(tokens: Iterable[str], family: VersionFamily | None) -> list[str]:
    """Append family tokens to declared tokens with stable first-win dedupe."""
    if family is None:
        # Preserve the pre-family policy behavior byte-for-byte when the
        # optional declaration is absent, including its declared ordering.
        return list(tokens)
    return _dedupe_tokens([*tokens, *expand_version_family(family)])


def _bare_token_list(brand: BrandPolicy) -> list[str]:
    """Tokens for the bare/versioned_bare fan-out (R8).

    versioned_bare brands contribute their versioned_tokens first (so the
    more specific token matches first), then bare tokens. Bare brands
    contribute just tokens.
    """
    if "versioned_bare" in brand.paths:
        base_tokens = [*brand.versioned_tokens, *brand.tokens]
    elif "bare" in brand.paths:
        base_tokens = list(brand.tokens)
    else:
        base_tokens = []
    return _expand_tokens(base_tokens, brand.version_family)


def _brand_handle_tier(brand: BrandPolicy) -> str:
    """Read handle_tier from the brand block.

    BrandPolicy carries handle_tier as a first-class field (R9); the
    default is HANDLE_TIER_TOP. The live config splits handles into
    B2/B3 to stay under the 512-char X advanced-search cap; the policy
    preserves that split by emitting one spec per tier.
    """
    return brand.handle_tier


def _is_skipped(brand: BrandPolicy) -> bool:
    return brand.paths == frozenset({"none"})


def specs_from_policy(policy: HarvestPolicy) -> list[XQuerySpec]:
    """Derive XQuerySpec list from a loaded HarvestPolicy.

    See module docstring for ordering and tier semantics. Does NOT load
    primary keywords — those are passed at render time by the caller
    (same pattern as the current `_load_primary_keywords` call in
    plan_calls_for_cycle).
    """
    specs: list[XQuerySpec] = []
    eligible_brands: list[BrandPolicy] = [
        b for b in policy.brands.values() if not _is_skipped(b)
    ]

    # --- B1 (wide-net bare/versioned_bare fan-out) ----------------------------
    b1_brands: list[BrandPolicy] = [
        b for b in eligible_brands
        if ("bare" in b.paths) or ("versioned_bare" in b.paths)
    ]
    if b1_brands:
        specs.append(XQuerySpec(
            call_id="B1",
            is_wide_net=True,
            wide_net_brands=tuple(sorted(b.nickname for b in b1_brands)),
            co_occurrence=[],
            min_faves=0,
            not_include=[],
        ))

    # --- C-specs (one per co_pack) -------------------------------------------
    for idx, pack in enumerate(policy.co_packs, start=1):
        pack_brands: list[BrandPolicy] = [
            policy.brands[n] for n in pack.brand_nicknames
        ]
        # Primary group: one paren per brand, OR-joined into the outer paren.
        # Tokens per brand = declared tokens plus any version-family expansion;
        # the planner joins them via _build_query's existing OR-of-paren path.
        primary_brands: dict[str, list[str]] = {}
        for b in pack_brands:
            primary_brands[b.nickname] = _expand_tokens(
                b.tokens, b.version_family
            )
        # Co group: union of brand.co across the pack (R4 + KTD5).
        co_terms: list[str] = []
        seen: set[str] = set()
        for b in pack_brands:
            for term in b.co:
                if term not in seen:
                    co_terms.append(term)
                    seen.add(term)
        # not_include: union across the pack (R4 brand-local bleed control).
        not_include: list[str] = []
        seen_ni: set[str] = set()
        for b in pack_brands:
            for term in b.not_include:
                if term not in seen_ni:
                    not_include.append(term)
                    seen_ni.add(term)

        specs.append(XQuerySpec(
            call_id=f"C{idx}",
            brands=primary_brands,
            co_occurrence=co_terms,
            min_faves=0,
            not_include=not_include,
        ))

    # --- Handle specs (one per tier) -----------------------------------------
    # 3/5 collapses to a single tier by default; multi-tier lands in 4/5.
    handle_brands_by_tier: dict[str, list[BrandPolicy]] = defaultdict(list)
    for b in eligible_brands:
        if "handle" in b.paths:
            handle_brands_by_tier[_brand_handle_tier(b)].append(b)

    # Stable tier order: top-presence first, then other
    for tier in (HANDLE_TIER_TOP, HANDLE_TIER_OTHER):
        brands = handle_brands_by_tier.get(tier, [])
        if not brands:
            continue
        all_handles: list[str] = []
        seen_h: set[str] = set()
        for b in brands:
            for h in b.handles:
                if h not in seen_h:
                    all_handles.append(h)
                    seen_h.add(h)
        specs.append(XQuerySpec(
            call_id="B2" if tier == HANDLE_TIER_TOP else "B3",
            handles=tuple(all_handles),
            co_occurrence=[],
            min_faves=0,
        ))

    return specs


def primary_keywords_from_policy(policy: HarvestPolicy) -> dict[str, list[str]]:
    """Build the `primary_keywords` dict the renderer needs for wide-net specs.

    For 3/5 the source is the policy file (R8); the DB keyword table
    remains for attribution. Order is alphabetical for determinism.
    """
    out: dict[str, list[str]] = {}
    for b in policy.brands.values():
        if _is_skipped(b):
            continue
        if ("bare" in b.paths) or ("versioned_bare" in b.paths):
            out[b.nickname] = _bare_token_list(b)
    return out
