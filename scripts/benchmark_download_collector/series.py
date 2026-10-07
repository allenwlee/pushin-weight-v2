"""Daily comparisons with source-specific meaning and missingness."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from .collect import contract
from .identity import count, days, require, timestamp, validate_inputs


def build_report(snapshots, start_date, end_date):
    window = days(start_date, end_date)
    require(bool(snapshots), "no snapshots")
    snapshots = sorted(snapshots, key=lambda s: timestamp(s["observed_at"]))
    first = snapshots[0]
    synthetic = first.get("synthetic") is True
    require(
        all((s.get("synthetic") is True) == synthetic for s in snapshots),
        "cannot mix synthetic and live snapshots",
    )
    brands, products = validate_inputs(first["catalog"], first["mapping"])
    frozen = contract(first["catalog"], first["mapping"])
    by_source = {source: {} for source in ("arena", "openrouter")}
    for row in first["mapping"]["mappings"]:
        by_source[row["source"]][row["source_id"]] = products[row["product_key"]][
            "brand_id"
        ]
    hf_cohorts = {
        brand: {
            p
            for p in first["mapping"]["hf_product_keys"]
            if products[p]["brand_id"] == brand
        }
        for brand in brands
    }
    posts, publications, hf_daily, or_daily = {}, {}, {}, {}
    post_revisions = {}
    unresolved = {"arena": set(), "openrouter": set()}
    statuses, score_contracts, or_as_of = [], set(), set()
    for snapshot in snapshots:
        validate_inputs(snapshot["catalog"], snapshot["mapping"])
        require(
            contract(snapshot["catalog"], snapshot["mapping"]) == frozen
            and all(snapshot.get(k) == v for k, v in frozen.items()),
            "mixed or corrupt identity contracts; use separate collection directories",
        )
        observed = snapshot["observed_at"]
        require(snapshot["schema_version"] == 1, "unsupported snapshot version")
        post_data = snapshot["catalog"]["posts"]
        exported = timestamp(snapshot["catalog"]["exported_at"])
        refreshed_dates = {
            date
            for date in days(post_data["start_date"], post_data["end_date"])
            if date not in post_revisions or exported >= post_revisions[date]
        }
        for date in refreshed_dates:
            post_revisions[date] = exported
            for brand in brands:
                posts[brand, date] = 0
        for row in post_data["counts"]:
            if row["date"] in refreshed_dates:
                posts[row["brand_id"], row["date"]] = count(row["count"])
        for source, result in snapshot["sources"].items():
            statuses.append(
                {
                    "source": source,
                    "observed_at": observed,
                    "status": result["status"],
                    "error": result.get("error"),
                }
            )
            if source == "arena" and result["status"] == "ok":
                score_contracts.add(result["score_contract"])
                grouped = defaultdict(list)
                for row in result["rows"]:
                    grouped[row["leaderboard_publish_date"]].append(row)
                    if row["model_name"] not in by_source["arena"]:
                        unresolved["arena"].add(row["model_name"])
                for date, rows in grouped.items():
                    publications[date] = {"rows": rows, "observed_at": observed}
            elif source == "hf" and result["status"] in {"ok", "partial"}:
                rows = {r["product_key"]: r for r in result["rows"]}
                require(len(rows) == len(result["rows"]), "duplicate HF observation")
                for brand, cohort in hf_cohorts.items():
                    if not cohort:
                        continue
                    own = [rows[p] for p in cohort if p in rows]
                    observation_days = {
                        timestamp(r["observed_at"]).astimezone(UTC).date().isoformat()
                        for r in own
                    }
                    for date in observation_days:
                        good = [
                            r
                            for r in own
                            if r["status"] == "ok"
                            and timestamp(r["observed_at"])
                            .astimezone(UTC)
                            .date()
                            .isoformat()
                            == date
                        ]
                        value = (
                            sum(count(r["raw"]["downloads"]) for r in good)
                            if len(good) == len(cohort)
                            else None
                        )
                        detail = {
                            "value": value,
                            "successful": len(good),
                            "selected": len(cohort),
                            "observed_at": max(r["observed_at"] for r in own),
                            "repos": sorted(products[p]["repo_id"] for p in cohort),
                        }
                        previous = hf_daily.get((brand, date))
                        if (
                            value is not None
                            or previous is None
                            or previous["value"] is None
                        ):
                            hf_daily[brand, date] = detail
            elif source == "openrouter" and result["status"] == "ok":
                grouped = defaultdict(list)
                or_as_of.add(result["as_of"])
                for row in result["rows"]:
                    grouped[row["date"]].append(row)
                    if (
                        row["model_permaslug"] != "other"
                        and row["model_permaslug"] not in by_source["openrouter"]
                    ):
                        unresolved["openrouter"].add(row["model_permaslug"])
                for date, rows in grouped.items():
                    previous = or_daily.get(date)
                    if previous is None or timestamp(result["as_of"]) >= timestamp(
                        previous["as_of"]
                    ):
                        or_daily[date] = {"rows": rows, "as_of": result["as_of"]}
    require(
        len(score_contracts) <= 1,
        "Arena methodology/config changed; use separate reports",
    )
    series = []
    for brand, info in brands.items():
        points = []
        for date in window:
            publication = max((d for d in publications if d <= date), default=None)
            arena_score = None
            if publication:
                eligible = [
                    r
                    for r in publications[publication]["rows"]
                    if by_source["arena"].get(r["model_name"]) == brand
                ]
                if eligible:
                    best = max(eligible, key=lambda r: (r["rating"], r["model_name"]))
                    arena_score = {
                        "value": best["rating"],
                        "model": best["model_name"],
                        "published_at": publication,
                        "observed_at": publications[publication]["observed_at"],
                        "lower": best["rating_lower"],
                        "upper": best["rating_upper"],
                        "votes": best["vote_count"],
                    }
            usage = or_daily.get(date)
            tokens = None
            if usage:
                matched = [
                    r
                    for r in usage["rows"]
                    if by_source["openrouter"].get(r["model_permaslug"]) == brand
                ]
                total = sum(int(r["total_tokens"]) for r in usage["rows"])
                other = sum(
                    int(r["total_tokens"])
                    for r in usage["rows"]
                    if r["model_permaslug"] == "other"
                )
                tokens = {
                    "value": str(sum(int(r["total_tokens"]) for r in matched))
                    if matched
                    else None,
                    "models": [r["model_permaslug"] for r in matched],
                    "as_of": usage["as_of"],
                    "other_tokens": str(other),
                    "platform_tokens": str(total),
                    "unmapped_models": sum(
                        r["model_permaslug"] != "other"
                        and r["model_permaslug"] not in by_source["openrouter"]
                        for r in usage["rows"]
                    ),
                }
            points.append(
                {
                    "date": date,
                    "posts": posts.get((brand, date)),
                    "arena": arena_score,
                    "hf": hf_daily.get((brand, date)),
                    "openrouter": tokens,
                }
            )
        series.append(
            {
                "brand_id": brand,
                "label": info.get("label", brand),
                "label_zh": info.get("label_zh", info.get("label", brand)),
                "hf_selected": len(hf_cohorts[brand]),
                "points": points,
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "synthetic": synthetic,
        "start_date": start_date,
        "end_date": end_date,
        "series": series,
        "statuses": statuses,
        "unresolved": {k: sorted(v) for k, v in unresolved.items()},
        "openrouter_as_of": sorted(or_as_of),
        "arena_config": {
            "arena-overall-text-v1": "text",
            "arena-overall-text-style-control-v1": "text_style_control",
        }.get(next(iter(score_contracts), None)),
        "contract": frozen,
    }
