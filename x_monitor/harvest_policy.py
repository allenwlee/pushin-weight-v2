"""Harvest policy loader + types.

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U2 (R1-R5, R22).

The policy is the AUTHORING surface for harvest search paths; the
planner in x_monitor.query_plan.derive_specs (U3) consumes a loaded
``HarvestPolicy`` and produces XQuerySpec entries via the existing
``_build_query`` renderer (M7 DRY).

File shape (per-brand):

    brands:
      <nickname>:
        paths: [bare, handle]            # SET (multi-path allowed)
        tokens: [MiMo, Xiaomi MiMo]      # for bare/versioned_bare paths
        versioned_tokens: [Llama 4]      # optional alt for versioned_bare
        co: [llm, model, api]            # for co path
        c_bare_aliases: ["Ox Alpha"]    # bare OR branch on the C call
        handles: [@MiniMaxAI]            # for handle path (no @ here; loader adds it)
        not_include: [f1, antonelli]     # brand-local (Kimi F1 hijack, etc.)
        notes: |
          Optional operator-facing commentary; not parsed.

    co_packs:
      - [mimo, mistral, moonshot_kimi, yi, llama]
      - [ernie, upstage]
      - [doubao, sensechat, kuaishou]
    # Co packs are planner-internal in 3/5. The schema does NOT
    # encode "brand forever on C1" as a permanent field; 4/5 may
    # replace fixed packs with auto-pack_co_brands(max_len).

3/5 schema is the API 4/5 writes; do not invent a second policy model
in 4/5.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

# Authoritative path names (R1, R2). Adding a new path requires:
#   (a) extending _VALID_PATH_NAMES
#   (b) extending _partition_brands (U3) to assign it
#   (c) updating test_harvest_policy_load coverage
# Exclusive single-mode enums are forbidden (R3); `paths` is always a set.
_VALID_PATH_NAMES: frozenset[str] = frozenset({
    "bare",            # bare keyword tokens, no co
    "versioned_bare",  # bare keyword tokens with version markers (Llama 4, etc.)
    "co",              # co-occurrence constrained polyseme resolution
    "handle",          # @official handle OR-group
    # `none` is the explicit empty-state marker (AE1); only allowed when
    # the brand opts out of search entirely (rare; document reason in notes).
    "none",
})


PathName = Literal["bare", "versioned_bare", "co", "handle", "none"]


# Handle tier names (R9). 3/5 ships two tiers (top-presence, other) to
# preserve the legacy B2/B3 split needed to stay under the 512-char
# X advanced-search cap when many handle brands are configured. 4/5 may
# extend or compute this dynamically.
HANDLE_TIER_TOP = "top-presence"
HANDLE_TIER_OTHER = "other"
_HANDLE_TIERS: frozenset[str] = frozenset({HANDLE_TIER_TOP, HANDLE_TIER_OTHER})


@dataclass(frozen=True)
class VersionFamily:
    """Validated declaration for adjacent numbered model names.

    ``lookback`` and ``lookahead`` describe the numeric range around
    ``current_major``.  ``extra_suffixes`` are emitted for the current and
    lookahead majors only; previous majors retain their plain numeric token.
    Expansion itself lives in ``specs_from_policy`` so every call shape uses
    the same token derivation.
    """

    prefix: str
    current_major: int
    lookback: int = 1
    lookahead: int = 1
    extra_suffixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.prefix, str) or not self.prefix.strip():
            raise ValueError("version_family prefix must be non-empty")
        if self.prefix != self.prefix.strip():
            raise ValueError(
                "version_family prefix must not have surrounding whitespace"
            )
        for field_name in ("current_major", "lookback", "lookahead"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(
                    f"version_family {field_name} must be an integer"
                )
            if value < 0:
                raise ValueError(
                    f"version_family {field_name} must be non-negative"
                )
        if self.lookback > self.current_major:
            raise ValueError(
                "version_family lookback cannot exceed current_major"
            )
        if any(not isinstance(suffix, str) for suffix in self.extra_suffixes):
            raise TypeError("version_family extra_suffixes must be list[str]")


@dataclass(frozen=True)
class BrandPolicy:
    """Per-brand authoring block.

    `paths` is the SET of search-path modes this brand uses (R2, R3).
    Tokens/co/handles are validated against `paths` (R2): a brand with
    `bare` in paths must have non-empty `tokens`; a brand with `handle`
    must have non-empty `handles`. Multiple paths coexist; the planner
    emits the brand on each matching call shape (U3).

    `handle_tier` (optional, R9): names which handle-tier the brand's
    handles contribute to ("top-presence" or "other"). Defaults to
    "top-presence" for any brand with `handle` in paths. Operators
    must assign "other" for brands that would otherwise push the
    top-presence handle spec over the 512-char cap (live config splits
    handles into B2/B3 for exactly this reason). 4/5 may add more
    tiers or compute this dynamically.
    """
    nickname: str
    paths: frozenset[str]
    tokens: tuple[str, ...] = ()
    versioned_tokens: tuple[str, ...] = ()
    co: tuple[str, ...] = ()
    c_bare_aliases: tuple[str, ...] = ()
    handles: tuple[str, ...] = ()
    not_include: tuple[str, ...] = ()
    notes: str = ""
    handle_tier: str = HANDLE_TIER_TOP
    version_family: VersionFamily | None = None

    def __post_init__(self) -> None:
        if self.version_family is not None and not isinstance(
            self.version_family, VersionFamily
        ):
            raise TypeError(
                f"brand {self.nickname!r} version_family must be VersionFamily"
            )
        unknown = self.paths - _VALID_PATH_NAMES
        if unknown:
            raise ValueError(
                f"brand {self.nickname!r} has unknown paths: {sorted(unknown)}. "
                f"Valid: {sorted(_VALID_PATH_NAMES)}."
            )
        # `none` is mutually exclusive with any other path. A brand opted
        # out of search has `paths: [none]` and nothing else.
        if "none" in self.paths and len(self.paths) > 1:
            raise ValueError(
                f"brand {self.nickname!r}: 'none' path is mutually exclusive "
                f"with other paths; got {sorted(self.paths)}."
            )
        # bare / versioned_bare require tokens (R2), unless the version family
        # itself supplies the numbered tokens.
        if "bare" in self.paths and not (self.tokens or self.version_family):
            raise ValueError(
                f"brand {self.nickname!r}: 'bare' path requires non-empty tokens."
            )
        if "versioned_bare" in self.paths and not (
            self.tokens or self.versioned_tokens or self.version_family
        ):
            raise ValueError(
                f"brand {self.nickname!r}: 'versioned_bare' path requires "
                "non-empty tokens or versioned_tokens."
            )
        # co path requires co list (R2). Prefer fail over warn (R2/test edge).
        if "co" in self.paths and not self.co:
            raise ValueError(
                f"brand {self.nickname!r}: 'co' path requires non-empty co list."
            )
        if self.c_bare_aliases and "co" not in self.paths:
            raise ValueError(
                f"brand {self.nickname!r}: c_bare_aliases requires the 'co' path."
            )
        # handle path requires ≥1 handle (R2).
        if "handle" in self.paths and not self.handles:
            raise ValueError(
                f"brand {self.nickname!r}: 'handle' path requires non-empty handles."
            )
        if self.handle_tier not in _HANDLE_TIERS:
            raise ValueError(
                f"brand {self.nickname!r} handle_tier {self.handle_tier!r} "
                f"not in {sorted(_HANDLE_TIERS)}"
            )


@dataclass(frozen=True)
class CoPack:
    """One fixed co-pack: a list of brand nicknames that share a co call."""
    brand_nicknames: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.brand_nicknames:
            raise ValueError("CoPack must contain at least one brand nickname")


@dataclass(frozen=True)
class HarvestPolicy:
    """The whole loaded policy document.

    `co_packs` is the fixed-pack table for 3/5 (R7). 4/5 replaces it with
    auto-pack_co_brands(max_len). Do not encode "brand forever on C1" as
    a permanent field — packs are planner-internal.
    """
    brands: dict[str, BrandPolicy]
    co_packs: tuple[CoPack, ...] = ()

    def brand(self, nickname: str) -> BrandPolicy:
        try:
            return self.brands[nickname]
        except KeyError as e:
            raise KeyError(
                f"brand {nickname!r} not present in policy. Known: "
                f"{sorted(self.brands)}"
            ) from e


# -------------------------------------------------------------------------
# Loader
# -------------------------------------------------------------------------

def _coerce_str_list(value: Any, field_name: str, nickname: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        # YAML allows scalar→list coercion for single tokens; only accept
        # this for the handle field (operators often write `- @foo` as a
        # single string by mistake). For tokens/co we want the list shape.
        return (value,)
    if isinstance(value, list):
        for v in value:
            if not isinstance(v, str):
                raise TypeError(
                    f"brand {nickname!r} {field_name} must be list[str]; "
                    f"got {type(v).__name__}"
                )
        return tuple(value)
    raise TypeError(
        f"brand {nickname!r} {field_name} must be list or string; "
        f"got {type(value).__name__}"
    )


def _load_brand_policy(nickname: str, raw: dict[str, Any]) -> BrandPolicy:
    if not isinstance(raw, dict):
        raise TypeError(
            f"brand {nickname!r} entry must be a mapping; got {type(raw).__name__}"
        )
    paths_raw = raw.get("paths")
    if not paths_raw:
        raise ValueError(
            f"brand {nickname!r}: 'paths' is required and non-empty. "
            "Use ['none'] for an explicit opt-out with documented reason."
        )
    paths = frozenset(paths_raw)
    version_family = _load_version_family(
        nickname, raw.get("version_family")
    )
    return BrandPolicy(
        nickname=nickname,
        paths=paths,
        tokens=_coerce_str_list(raw.get("tokens", []), "tokens", nickname),
        versioned_tokens=_coerce_str_list(
            raw.get("versioned_tokens", []), "versioned_tokens", nickname
        ),
        co=_coerce_str_list(raw.get("co", []), "co", nickname),
        c_bare_aliases=_coerce_str_list(
            raw.get("c_bare_aliases", []), "c_bare_aliases", nickname
        ),
        handles=_coerce_str_list(raw.get("handles", []), "handles", nickname),
        not_include=_coerce_str_list(
            raw.get("not_include", []), "not_include", nickname
        ),
        notes=str(raw.get("notes", "") or ""),
        handle_tier=str(raw.get("handle_tier", HANDLE_TIER_TOP) or HANDLE_TIER_TOP),
        version_family=version_family,
    )


def _load_version_family(
    nickname: str, raw: Any
) -> VersionFamily | None:
    """Load an optional, strictly typed version-family declaration."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError(
            f"brand {nickname!r} version_family must be a mapping; "
            f"got {type(raw).__name__}"
        )
    if "prefix" not in raw or "current_major" not in raw:
        raise ValueError(
            f"brand {nickname!r} version_family requires prefix and current_major"
        )
    prefix = raw["prefix"]
    current_major = raw["current_major"]
    lookback = raw.get("lookback", 1)
    lookahead = raw.get("lookahead", 1)
    suffixes = _coerce_str_list(
        raw.get("extra_suffixes", []), "version_family.extra_suffixes", nickname
    )
    try:
        return VersionFamily(
            prefix=prefix,
            current_major=current_major,
            lookback=lookback,
            lookahead=lookahead,
            extra_suffixes=suffixes,
        )
    except (TypeError, ValueError) as exc:
        raise type(exc)(
            f"brand {nickname!r} {exc}"
        ) from exc


def _load_co_packs(raw: Any) -> tuple[CoPack, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise TypeError(
            f"co_packs must be a list; got {type(raw).__name__}"
        )
    packs = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, list):
            raise TypeError(
                f"co_packs[{i}] must be a list of brand nicknames; got "
                f"{type(entry).__name__}"
            )
        for n in entry:
            if not isinstance(n, str):
                raise TypeError(
                    f"co_packs[{i}] entries must be strings; got {type(n).__name__}"
                )
        packs.append(CoPack(brand_nicknames=tuple(entry)))
    return tuple(packs)


def load_policy(path: str | Path) -> HarvestPolicy:
    """Load harvest policy from a YAML file.

    Validates (R2):
      - unknown path names fail
      - bare/versioned_bare without tokens fail
      - co without co list fails (prefer fail over warn)
      - handle without handles fails
      - 'none' is mutually exclusive with other paths
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raise ValueError(f"policy file {path} is empty")
    if not isinstance(raw, dict):
        raise TypeError(
            f"policy file {path} must contain a YAML mapping at top level; "
            f"got {type(raw).__name__}"
        )

    brands_raw = raw.get("brands", {})
    if not isinstance(brands_raw, dict):
        raise TypeError(
            f"policy file {path} 'brands' must be a mapping; got "
            f"{type(brands_raw).__name__}"
        )

    brands: dict[str, BrandPolicy] = {}
    for nickname, entry in brands_raw.items():
        brands[nickname] = _load_brand_policy(nickname, entry)

    co_packs = _load_co_packs(raw.get("co_packs"))

    # Cross-check: every brand listed in a co_pack must exist in brands.
    for pack in co_packs:
        for n in pack.brand_nicknames:
            if n not in brands:
                raise ValueError(
                    f"co_pack references unknown brand {n!r}. "
                    f"Known: {sorted(brands)}"
                )

    # Cross-check: every brand that opts in to 'co' must appear in at
    # least one co_pack (R2 / U5 hint). If a co brand is not packed, the
    # planner would silently drop it — fail loud at load.
    co_brand_nicknames = {
        n for n, b in brands.items() if "co" in b.paths
    }
    packed_brands: set[str] = set()
    for pack in co_packs:
        packed_brands.update(pack.brand_nicknames)
    unpacked = co_brand_nicknames - packed_brands
    if unpacked:
        raise ValueError(
            f"brands use 'co' path but are not in any co_pack: "
            f"{sorted(unpacked)}. Add to a co_pack, or change the path. "
            "(3/5 has fixed co packs; 4/5 may auto-pack.)"
        )

    return HarvestPolicy(brands=brands, co_packs=co_packs)
