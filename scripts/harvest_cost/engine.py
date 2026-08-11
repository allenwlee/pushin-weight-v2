"""Pure cost math for harvester cycle summaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .pricing import PricingRates


@dataclass(frozen=True)
class CostLine:
    source: str  # search | metrics | qt | residual | floor
    label: str
    n_results: int
    credits: float
    notes: str = ""

    def usd(self, rates: PricingRates) -> float:
        return rates.usd(self.credits)


@dataclass
class CycleCost:
    run_id: str
    finished_at: str | None
    lines: list[CostLine] = field(default_factory=list)
    raw_summary: Mapping[str, Any] | None = None

    @property
    def total_credits(self) -> float:
        return sum(ln.credits for ln in self.lines)

    def total_usd(self, rates: PricingRates) -> float:
        return rates.usd(self.total_credits)

    def search_credits(self) -> float:
        return sum(ln.credits for ln in self.lines if ln.source in ("search", "residual"))

    def metrics_credits(self) -> float:
        return sum(ln.credits for ln in self.lines if ln.source == "metrics")


@dataclass
class PeriodCost:
    cycles: list[CycleCost]
    rates: PricingRates

    @property
    def total_credits(self) -> float:
        return sum(c.total_credits for c in self.cycles)

    def total_usd(self) -> float:
        return self.rates.usd(self.total_credits)

    def mean_cycle_credits(self) -> float:
        if not self.cycles:
            return 0.0
        return self.total_credits / len(self.cycles)


def credits_for_tweet_units(n: int, rates: PricingRates, *, apply_floor: bool = False) -> float:
    """Bill tweet-shaped results.

    When apply_floor is True and n is 0 or 1, charge the per-call floor
    (pricing page: 0–1 tweet → floor). Unique search rows typically set
    apply_floor=False and bill n * tweet_credits (n can be 0).
    """
    n = max(int(n), 0)
    if apply_floor and n <= 1:
        return float(rates.call_floor_credits)
    return float(n) * float(rates.tweet_credits)


def _pick_int(d: Mapping[str, Any], *keys: str, default: int = 0) -> int:
    for k in keys:
        if k in d and d[k] is not None:
            try:
                return int(d[k])
            except (TypeError, ValueError):
                continue
    return default


def cost_cycle_from_summary(
    summary: Mapping[str, Any],
    rates: PricingRates,
    *,
    residual_label: str = "A+B2+B3+C1+C2+C3 residual",
) -> CycleCost:
    """Build CycleCost from a CycleRunner (or compatible) summary dict."""
    source_summary = summary
    if (
        isinstance(summary.get("summary"), Mapping)
        and summary.get("schema_version")
        and summary.get("hash")
    ):
        summary = summary["summary"]
        if "run_id" not in summary and source_summary.get("run_id"):
            summary = {**summary, "run_id": source_summary["run_id"]}
    run_id = str(summary.get("run_id") or summary.get("id") or "unknown")
    finished = summary.get("finished_at") or summary.get("started_at")
    finished_s = str(finished) if finished else None
    lines: list[CostLine] = []

    calls = summary.get("calls") or []
    if isinstance(calls, list) and calls:
        for c in calls:
            if not isinstance(c, Mapping):
                continue
            cid = str(c.get("call_id") or c.get("id") or "?")
            n = _pick_int(c, "n_results", "fetch_n", default=0)
            credits = credits_for_tweet_units(n, rates, apply_floor=False)
            status = c.get("status") or ""
            note = f"status={status}" if status else ""
            lines.append(
                CostLine(
                    source="search",
                    label=cid,
                    n_results=n,
                    credits=credits,
                    notes=note,
                )
            )
    else:
        # Residual-only / log fallback shape
        totals = summary.get("totals") or {}
        seen = _pick_int(totals, "n_results", default=0)
        b1 = summary.get("b1_n_results")
        if b1 is not None:
            b1_n = int(b1)
            lines.append(
                CostLine(
                    source="search",
                    label="B1",
                    n_results=b1_n,
                    credits=credits_for_tweet_units(b1_n, rates),
                    notes="exact from log total_items",
                )
            )
            resid = max(seen - b1_n, 0)
            if resid or seen == 0:
                lines.append(
                    CostLine(
                        source="residual",
                        label=residual_label,
                        n_results=resid,
                        credits=credits_for_tweet_units(resid, rates),
                        notes="posts_seen - B1; per-call split unknown",
                    )
                )
        elif seen:
            lines.append(
                CostLine(
                    source="residual",
                    label="search_all",
                    n_results=seen,
                    credits=credits_for_tweet_units(seen, rates),
                    notes="aggregate posts seen only",
                )
            )

    mr = summary.get("metrics_refresh") or {}
    if isinstance(mr, Mapping) and mr:
        refreshed = _pick_int(mr, "n_refreshed", "refreshed", default=0)
        due = _pick_int(mr, "n_due", "due", default=0)
        missing = _pick_int(mr, "n_missing", "missing", default=0)
        credits = credits_for_tweet_units(refreshed, rates)
        lines.append(
            CostLine(
                source="metrics",
                label="metrics_refresh",
                n_results=refreshed,
                credits=credits,
                notes=f"due={due} missing={missing} (bill refreshed)",
            )
        )

    qt = summary.get("quote_tweets") or {}
    if isinstance(qt, Mapping) and qt.get("disabled"):
        lines.append(
            CostLine(
                source="qt",
                label="quote_tweets",
                n_results=0,
                credits=0.0,
                notes="channel no-op / disabled",
            )
        )

    # http_log is retained on summary for operators; billing uses unique
    # n_results lines (walk page inflation is a documented limitation).

    return CycleCost(
        run_id=run_id,
        finished_at=finished_s,
        lines=lines,
        # Keep the versioned envelope available to callers that need
        # provenance/hash context while pricing its redacted inner summary.
        raw_summary=source_summary,
    )


def cost_period(
    summaries: Sequence[Mapping[str, Any]],
    rates: PricingRates,
) -> PeriodCost:
    cycles = [cost_cycle_from_summary(s, rates) for s in summaries]
    return PeriodCost(cycles=cycles, rates=rates)


def extrapolate(mean_cycle_credits: float) -> dict[str, float]:
    """If every cycle matched the mean: hour / day / month at 4 / 96 / 2880 cycles."""
    return {
        "per_cycle": mean_cycle_credits,
        "per_hour_4_cycles": mean_cycle_credits * 4,
        "per_day_96_cycles": mean_cycle_credits * 96,
        "per_month_30d": mean_cycle_credits * 96 * 30,
    }


def render_markdown(period: PeriodCost) -> str:
    """Markdown report shaped like the harvester cycle cost table."""
    rates = period.rates
    lines_out: list[str] = []
    lines_out.append("---")
    lines_out.append("generated_by: scripts.harvest_cost")
    lines_out.append(f"tweet_credits: {rates.tweet_credits}")
    lines_out.append(f"call_floor_credits: {rates.call_floor_credits}")
    lines_out.append(f"credits_per_usd: {rates.credits_per_usd}")
    lines_out.append(f"pricing_source: {rates.source_path or 'overrides'}")
    lines_out.append(f"n_cycles: {len(period.cycles)}")
    lines_out.append("---")
    lines_out.append("")
    lines_out.append("# Harvester cycle cost report")
    lines_out.append("")
    lines_out.append("## Rates used")
    lines_out.append("")
    lines_out.append("| Field | Value |")
    lines_out.append("|---|---:|")
    lines_out.append(f"| Tweet credits / result | {rates.tweet_credits} |")
    lines_out.append(f"| Per-call floor | {rates.call_floor_credits} |")
    lines_out.append(f"| Credits per USD | {rates.credits_per_usd} |")
    lines_out.append(f"| Source | `{rates.source_path or 'CLI overrides'}` |")
    if rates.parse_notes:
        lines_out.append("")
        lines_out.append("Parse notes: " + "; ".join(rates.parse_notes))
    lines_out.append("")

    for cy in period.cycles:
        lines_out.append(f"## Cycle `{cy.run_id}`")
        lines_out.append("")
        if cy.finished_at:
            lines_out.append(f"**Finished:** {cy.finished_at}")
            lines_out.append("")
        lines_out.append(
            "| (a) Line | (b) Source | (c) # results | (d) credits | (e) USD | Notes |"
        )
        lines_out.append("|---|---|---:|---:|---:|---|")
        for ln in cy.lines:
            usd = ln.usd(rates)
            lines_out.append(
                f"| **{ln.label}** | {ln.source} | {ln.n_results} | "
                f"**{ln.credits:.0f}** | ${usd:.4f} | {ln.notes} |"
            )
        lines_out.append(
            f"| **TOTAL** | — | — | **{cy.total_credits:.0f}** | "
            f"**${cy.total_usd(rates):.4f}** | one cycle |"
        )
        lines_out.append("")
        lines_out.append(
            f"Search-shaped: {cy.search_credits():.0f} cr · "
            f"Metrics: {cy.metrics_credits():.0f} cr"
        )
        lines_out.append("")

    if len(period.cycles) > 1 or period.cycles:
        lines_out.append("## Period rollup")
        lines_out.append("")
        lines_out.append(f"- Cycles: **{len(period.cycles)}**")
        lines_out.append(
            f"- Total credits: **{period.total_credits:.0f}** "
            f"(${period.total_usd():.4f})"
        )
        mean = period.mean_cycle_credits()
        lines_out.append(f"- Mean credits / cycle: **{mean:.0f}**")
        ext = extrapolate(mean)
        lines_out.append("")
        lines_out.append(
            "### Extrapolation (if every cycle matched the mean)"
        )
        lines_out.append("")
        lines_out.append("| Period | Credits | USD |")
        lines_out.append("|---|---:|---:|")
        lines_out.append(
            f"| Per cycle | {ext['per_cycle']:.0f} | ${rates.usd(ext['per_cycle']):.4f} |"
        )
        lines_out.append(
            f"| Per hour (×4) | {ext['per_hour_4_cycles']:.0f} | "
            f"${rates.usd(ext['per_hour_4_cycles']):.4f} |"
        )
        lines_out.append(
            f"| Per day (×96) | {ext['per_day_96_cycles']:.0f} | "
            f"${rates.usd(ext['per_day_96_cycles']):.4f} |"
        )
        lines_out.append(
            f"| Per month (30d) | {ext['per_month_30d']:.0f} | "
            f"${rates.usd(ext['per_month_30d']):.4f} |"
        )
        lines_out.append("")

    lines_out.append("## Methodology")
    lines_out.append("")
    lines_out.append(
        "- Search lines use unique `n_results` / `fetch_n` from the cycle summary "
        "(not walk-inflated HTTP page sums unless a separate floor line appears)."
    )
    lines_out.append(
        "- Metrics line bills `n_refreshed` (or `refreshed`) × tweet credits."
    )
    lines_out.append(
        "- Continuous QT recheck is zero when the channel is disabled/no-op."
    )
    lines_out.append("")
    return "\n".join(lines_out)
