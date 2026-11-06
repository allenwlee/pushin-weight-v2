"""Compose named brand/family groups within explicit query budgets.

Aliases stay in the brand policy. Only named groups may split a brand. The
existing renderer owns query syntax; packing measures exactly that output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .harvest_policy import (
    AliasContext,
    BrandPolicy,
    HarvestPolicy,
    active_excluded_author_handles,
    normalize_policy_token,
)
from .queries import X_LENGTH_CAP, query_size_bytes
from .query_plan import XQuerySpec, _build_query

# CycleRunner injects these two epoch bounds after planning. Reserve ten digits
# each, and still let its actual-wire length check reject longer future bounds.
TIME_BOUNDS = " since_time:9999999999 until_time:9999999999"


@dataclass(frozen=True)
class BrandQueryBlock:
    name: str
    spec: XQuerySpec


def brand_query_blocks(brand: BrandPolicy) -> list[BrandQueryBlock]:
    from .specs_from_policy import (
        _bare_token_list,
        _expand_tokens,
        effective_alias_context,
    )

    if brand.c_bare_alias_groups:
        groups = list(
            zip(brand.alias_group_names, brand.c_bare_alias_groups, strict=True)
        )
    else:
        tokens = (
            _bare_token_list(brand) if brand.paths & {"bare", "versioned_bare"} else []
        )
        if "co" in brand.paths:
            tokens.extend(_expand_tokens(brand.tokens, brand.version_family))
            tokens.extend(brand.c_bare_aliases)
        groups = [("", tuple(dict.fromkeys(tokens)))]

    contexts = {
        normalize_policy_token(rule.alias): rule.any_of for rule in effective_alias_context(brand)
    }
    all_tokens = [token for _, tokens in groups for token in tokens]

    def context(token: str) -> tuple[str, ...]:
        return contexts.get(normalize_policy_token(token), ())

    def redundant_phrase(token: str) -> bool:
        # Internal hyphens separate search words: a live Hy4/Hy4-preview
        # comparison retrieved the same two hyphen-only controls. Preserve
        # aliases for attribution; omit only dominated search alternatives.
        def words_of(value: str) -> list[str]:
            return re.sub(r"(?<=\w)-(?=\w)", " ", normalize_policy_token(value)).split()

        words = words_of(token)
        if len(words) < 2:
            return False
        required = {normalize_policy_token(c) for c in context(token)}
        for other in all_tokens:
            if other == token:
                continue
            shorter = words_of(other)
            other_phrase = bool(brand.c_bare_alias_groups) or other.startswith('"')
            single_word = len(shorter) == 1 and shorter[0] in words
            same_words = shorter == words
            broader_conjunction = not other_phrase and set(shorter) < set(words)
            if not single_word and not same_words and not broader_conjunction:
                continue
            if same_words:
                phrase = bool(brand.c_bare_alias_groups) or token.startswith('"')
                # An unquoted conjunction covers the quoted phrase. Equal
                # alternatives retain their first declaration deterministically.
                if other_phrase and not phrase:
                    continue
                if phrase == other_phrase and all_tokens.index(
                    other
                ) > all_tokens.index(token):
                    continue
            other_context = {normalize_policy_token(c) for c in context(other)}
            if (
                not other_context
                or other_context.intersection(words)
                or required
                and required <= other_context
            ):
                return True
        return False

    blocks = []
    for position, (name, tokens) in enumerate(groups):
        kept = [token for token in tokens if not redundant_phrase(token)]
        # Keep existing unquoted aliases unchanged. Newly authored phrase aliases
        # are quoted in policy; compaction never changes their meaning.
        if brand.c_bare_alias_groups:
            kept = [f'"{t}"' if " " in t else t for t in kept]
        handles = (
            [f"@{h}" for h in brand.handles]
            if (name == brand.handle_group if brand.handle_group else position == 0)
            and "handle" in brand.paths
            else []
        )
        if not kept and not handles:
            continue
        rules = tuple(
            AliasContext(normalize_policy_token(t), context(t))
            for t in kept
            if context(t)
        )
        spec = XQuerySpec(
            brands={brand.nickname: kept},
            alias_context={brand.nickname: rules} if rules else {},
            c_bare_aliases=handles,
            not_include=list(brand.not_include),
        )
        if not kept:
            spec = XQuerySpec(handles=list(brand.handles))
        blocks.append(
            BrandQueryBlock(brand.nickname + (f"/{name}" if name else ""), spec)
        )
    if not blocks and brand.paths != frozenset({"none"}):
        raise ValueError(
            f"active brand {brand.nickname!r} has no searchable aliases or handles"
        )
    return blocks


def _group_spec(call_id: str, blocks: list[BrandQueryBlock]) -> XQuerySpec:
    return XQuerySpec(
        call_id=call_id,
        components=tuple(block.spec for block in blocks),
        component_names=tuple(block.name for block in blocks),
        brand_not_include={
            brand: list(block.spec.not_include)
            for block in blocks
            for brand in block.spec.brands
            if block.spec.not_include
        },
        unfiltered_handles=tuple(
            token[1:]
            for block in blocks
            for token in block.spec.c_bare_aliases
            if token.startswith("@")
        ),
    )


def packed_specs(policy: HarvestPolicy, selected: set[str]) -> list[XQuerySpec]:
    suffix = (
        "".join(f" -from:{h}" for h in active_excluded_author_handles(policy))
        + TIME_BOUNDS
    )
    result = []
    for pool in policy.query_pools:
        blocks = {
            block.name: block
            for brand in policy.brands.values()
            if brand.query_pool == pool.name and brand.paths != frozenset({"none"})
            for block in brand_query_blocks(brand)
        }
        oversized = [
            name
            for name, block in blocks.items()
            if query_size_bytes(_build_query(_group_spec("", [block])) + suffix) > X_LENGTH_CAP
        ]
        if oversized:
            raise ValueError(
                f"brand blocks exceed query length; split into named groups: {oversized}"
            )
        declared = [name for group in pool.groups for name in group.blocks]
        if len(declared) != len(set(declared)):
            raise ValueError(
                f"query pool {pool.name} assigns a brand/family block more than once"
            )
        if set(declared) != set(blocks):
            raise ValueError(
                f"query pool {pool.name} ownership mismatch: "
                f"unassigned={sorted(set(blocks) - set(declared))}; "
                f"unknown={sorted(set(declared) - set(blocks))}"
            )
        for group in pool.groups:
            owned = [blocks[name] for name in group.blocks]
            full = _group_spec(group.call_id, owned)
            length = query_size_bytes(_build_query(full) + suffix)
            if length > X_LENGTH_CAP:
                raise ValueError(
                    f"query {group.call_id} ({group.name}) exceeds {X_LENGTH_CAP} "
                    f"UTF-8 bytes with time bounds: {length}; revise its explicit group"
                )
            chosen = [
                block for block in owned if block.name.split("/", 1)[0] in selected
            ]
            if chosen:
                result.append(_group_spec(group.call_id, chosen))
    return result
