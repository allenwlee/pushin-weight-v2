"""harvest_preview library: produce the per-cycle preview report.

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U4 (R10, R11, R21).

This module is the OFFLINE preview builder. It loads the harvest policy
+ the enabled-models list from config.yaml, derives specs via
`specs_from_policy`, and returns a structured report. NO network calls
to TwitterAPI / LLM / Apify / Render / prod DB (R21 / M8).

The Django management command in `core/management/commands/harvest_preview.py`
wraps this module and prints the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

import yaml

from .harvest_policy import HarvestPolicy, load_policy
from .query_plan import PlannedCall, XQuerySpec, plan_calls
from .specs_from_policy import primary_keywords_from_policy, specs_from_policy


DEFAULT_LENGTH_CAP = 512  # x.com advanced-search cap (queries.X_LENGTH_CAP)


@dataclass(frozen=True)
class CallPreview:
    call_id: str
    call_kind: str
    length: int
    headroom: int  # DEFAULT_LENGTH_CAP - length
    query: str  # full query (truncation is the caller's concern)


@dataclass(frozen=True)
class CoveragePreview:
    """For each enabled brand: the set of call_ids it appears on."""
    nickname: str
    call_ids: frozenset[str]
    is_explicit_none: bool = False  # paths: [none] with documented reason


@dataclass(frozen=True)
class HarvestPreviewReport:
    calls: tuple[CallPreview, ...]
    coverage: tuple[CoveragePreview, ...]
    unmapped_enabled: tuple[str, ...] = ()  # enabled_models not in policy
    warnings: tuple[str, ...] = ()


def _load_enabled_models(config_path: Path) -> list[str]:
    """Read enabled_models list from config.yaml.

    The source of truth for enabled models is config.yaml's
    `enabled_models:` block (matches what the harvest cycle uses).
    """
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    enabled = cfg.get("enabled_models") or []
    if not isinstance(enabled, list):
        raise TypeError(
            f"config.yaml `enabled_models` must be a list; got {type(enabled).__name__}"
        )
    return [m for m in enabled if isinstance(m, str)]


def _build_brand_to_call_id(
    calls: list[PlannedCall],
    policy: HarvestPolicy,
) -> dict[str, set[str]]:
    """Map each brand to the call_ids it appears on.

    For bare/versioned_bare/handle brands we look at the wide_net_brands
    / handles in the source spec. For co brands we look at brands dict.
    """
    # Reverse: spec -> {nickname: call_id}
    coverage: dict[str, set[str]] = {}
    specs = specs_from_policy(policy)
    spec_by_call_id = {s.call_id: s for s in specs}

    for c in calls:
        spec = spec_by_call_id.get(c.call_id)
        if spec is None:
            continue
        # Wide-net (B1)
        for nick in spec.wide_net_brands:
            coverage.setdefault(nick, set()).add(c.call_id)
        # Co (C*)
        for nick in spec.brands:
            coverage.setdefault(nick, set()).add(c.call_id)
        # Handle (B2/B3)
        # Handles don't carry the brand nickname in the rendered query;
        # we reconstruct via the policy.
        if spec.handles:
            for nick, brand in policy.brands.items():
                if "handle" not in brand.paths:
                    continue
                if any(h in spec.handles for h in brand.handles):
                    coverage.setdefault(nick, set()).add(c.call_id)
    return coverage


def build_preview(
    *,
    config_path: Path | str = Path("config.yaml"),
    policy_path: Path | str | None = Path("config/harvest_policy.yaml"),
    x_monitor_list_id: int | str | None = None,
) -> HarvestPreviewReport:
    """Build the offline preview report.

    Args:
        config_path: path to config.yaml (enabled_models + list ID).
        policy_path: path to harvest policy. Falls back to None if absent;
            preview still works against the live x_query_specs in that case.
        x_monitor_list_id: override the list ID (for tests). Defaults to
            `x_monitor_list_id` from config.yaml.

    Returns:
        HarvestPreviewReport with calls + coverage + warnings.
    """
    config_path = Path(config_path)
    enabled_models = _load_enabled_models(config_path)

    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    list_id = x_monitor_list_id if x_monitor_list_id is not None else cfg.get("x_monitor_list_id")

    warnings: list[str] = []

    policy: HarvestPolicy | None = None
    if policy_path is not None and Path(policy_path).exists():
        policy = load_policy(Path(policy_path))
        specs = specs_from_policy(policy)
        pkws = primary_keywords_from_policy(policy)
        calls = plan_calls(
            x_monitor_list_id=list_id,
            x_query_specs=specs,
            primary_keywords=pkws,
        )
    else:
        # Fall back to live config.x_query_specs (U5 cutover: this branch
        # disappears; preview always reads policy). For pre-U5 use we
        # still surface a warning.
        warnings.append(
            f"policy file not found at {policy_path}; falling back to "
            "config.x_query_specs. After U5 cutover this fallback is removed."
        )
        specs = []
        for raw in (cfg.get("x_query_specs") or []):
            # Convert config dict to XQuerySpec so plan_calls can render.
            specs.append(XQuerySpec(
                call_id=raw.get("call_id", ""),
                brands=dict(raw.get("brands") or {}),
                co_occurrence=list(raw.get("co_occurrence") or []),
                min_faves=int(raw.get("min_faves", 0)),
                is_wide_net=bool(raw.get("is_wide_net", False)),
                wide_net_brands=tuple(raw.get("wide_net_brands") or ()),
                handles=tuple(raw.get("handles") or ()),
                not_include=list(raw.get("not_include") or []),
            ))
        # Build minimal primary_keywords stub for wide-net specs
        pkws = {}
        for s in specs:
            for nick in (s.wide_net_brands or ()):
                pkws.setdefault(nick, [nick])
        calls = plan_calls(
            x_monitor_list_id=list_id,
            x_query_specs=specs,
            primary_keywords=pkws,
        )

    call_previews = tuple(
        CallPreview(
            call_id=c.call_id,
            call_kind=c.call_kind,
            length=c.query_length,
            headroom=DEFAULT_LENGTH_CAP - c.query_length,
            query=c.query_string,
        )
        for c in calls
    )

    # Coverage
    coverage_pairs: dict[str, set[str]] = {}
    if policy is not None:
        coverage_pairs = _build_brand_to_call_id(calls, policy)

    coverage_list: list[CoveragePreview] = []
    unmapped: list[str] = []

    # Walk enabled_models (the canonical list of brands that should collect)
    for nick in enabled_models:
        if policy is None:
            # Pre-U5: no policy file to map from
            unmapped.append(nick)
            continue
        if nick in policy.brands:
            brand = policy.brands[nick]
            call_ids = coverage_pairs.get(nick, frozenset())
            is_none = brand.paths == frozenset({"none"})
            coverage_list.append(CoveragePreview(
                nickname=nick,
                call_ids=frozenset(call_ids),
                is_explicit_none=is_none,
            ))
            if not call_ids and not is_none:
                warnings.append(
                    f"brand {nick!r} is enabled but has NO call_ids and "
                    "is not explicit 'none' (R11 invariant violation; collection = 0)."
                )
            if is_none and not brand.notes:
                warnings.append(
                    f"brand {nick!r} opted out with paths: [none] but has "
                    "no `notes:` documenting the reason. Per AE1, the "
                    "operator should record why this brand is silent."
                )
        else:
            unmapped.append(nick)
            warnings.append(
                f"brand {nick!r} is in enabled_models but not in policy "
                "(R11 invariant violation)."
            )

    return HarvestPreviewReport(
        calls=call_previews,
        coverage=tuple(coverage_list),
        unmapped_enabled=tuple(unmapped),
        warnings=tuple(warnings),
    )


def render_preview(
    report: HarvestPreviewReport,
    out: TextIO,
    *,
    truncate_query_at: int = 120,
) -> None:
    """Pretty-print the preview report to a text stream."""
    out.write(f"# harvest_preview ({len(report.calls)} calls, "
              f"{len(report.coverage)} brands mapped)\n\n")

    out.write("## Calls\n\n")
    out.write("| call_id | kind | length | headroom | query |\n")
    out.write("|---|---|---:|---:|---|\n")
    for c in report.calls:
        q = c.query if len(c.query) <= truncate_query_at else c.query[:truncate_query_at] + "…"
        out.write(f"| {c.call_id} | {c.call_kind} | {c.length} | {c.headroom} | `{q}` |\n")
    out.write("\n")

    out.write("## Coverage\n\n")
    out.write("| brand | call_ids | explicit_none |\n")
    out.write("|---|---|---|\n")
    for cov in sorted(report.coverage, key=lambda c: c.nickname):
        cids = ", ".join(sorted(cov.call_ids)) if cov.call_ids else "—"
        out.write(f"| {cov.nickname} | {cids} | {cov.is_explicit_none} |\n")
    out.write("\n")

    if report.unmapped_enabled:
        out.write(f"## Unmapped enabled_models: "
                  f"{', '.join(report.unmapped_enabled)}\n\n")

    if report.warnings:
        out.write("## Warnings\n\n")
        for w in report.warnings:
            out.write(f"- {w}\n")
        out.write("\n")


def coverage_invariant_holds(report: HarvestPreviewReport) -> bool:
    """R11 invariant: every enabled brand has ≥1 path OR explicit none.

    Returns True when the report has no R11 violations. Use this in CI
    / pytest to fail when an enabled brand has no call_ids and is not
    opted out explicitly.
    """
    for cov in report.coverage:
        if not cov.call_ids and not cov.is_explicit_none:
            return False
    for unmapped in report.unmapped_enabled:
        # enabled_models brand absent from policy = violation
        return False
    return True