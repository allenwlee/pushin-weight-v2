"""Explicitly synthetic, deterministic example; never used for live collection."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from .collect import ensure_contract
from .identity import write_new
from .sources import ARENA_CONFIG, ARENA_CONTRACT, SOURCE_URLS


def demo(directory):
    first = datetime(2026, 9, 21, 12, tzinfo=UTC)
    dates = [(first + timedelta(days=i)).date().isoformat() for i in range(14)]
    alpha, beta = (
        "00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000002",
    )
    catalog = {
        "schema_version": 1,
        "exported_at": first.isoformat(),
        "brands": [
            {
                "id": name,
                "label": name.title(),
                "label_zh": label,
                "company_ids": ["example"],
            }
            for name, label in (("alpha", "示例 Alpha"), ("beta", "示例 Beta"))
        ],
        "companies": [{"id": "example", "label": "Example Company"}],
        "products": [
            {
                "product_key": alpha,
                "brand_id": "alpha",
                "label": "Alpha 1",
                "repo_id": "example/Alpha-1",
                "hf_namespace": "example",
                "hf_confirmed": True,
                "hf_company_id": "example",
            },
            {
                "product_key": beta,
                "brand_id": "beta",
                "label": "Beta 2",
                "repo_id": None,
                "hf_namespace": None,
                "hf_confirmed": False,
                "hf_company_id": None,
            },
        ],
        "posts": {
            "start_date": dates[0],
            "end_date": dates[-1],
            "scope": "collected_postbrand",
            "counts": [
                {
                    "date": date,
                    "brand_id": brand,
                    "count": (15 + i * 3 + (i % 5) * 7) * factor,
                }
                for i, date in enumerate(dates)
                for brand, factor in (("alpha", 2), ("beta", 1))
            ],
        },
    }
    mapping = {
        "schema_version": 1,
        "hf_product_keys": [alpha],
        "mappings": [
            {
                "source": source,
                "source_id": model,
                "product_key": key,
                "evidence": "https://example.com/synthetic-demo",
            }
            for source, model, key in (
                ("arena", "alpha-1-thinking", alpha),
                ("arena", "beta-2", beta),
                ("openrouter", "example/alpha-1", alpha),
                ("openrouter", "example/beta-2", beta),
            )
        ],
    }
    frozen = ensure_contract(directory, catalog, mapping)
    for i, date in enumerate(dates):
        observed = (first + timedelta(days=i)).isoformat()
        published = dates[(i // 5) * 5]
        arena_rows = [
            {
                "model_name": model,
                "category": "overall",
                "leaderboard_publish_date": published,
                "rating": score,
                "rating_lower": score - 9,
                "rating_upper": score + 9,
                "vote_count": 2500 + 100 * i,
            }
            for model, score in (
                ("alpha-1-thinking", 1370 + (i // 5) * 25),
                ("beta-2", 1395 + (i // 5) * 10),
            )
        ]
        hf_row = {
            "product_key": alpha,
            "repo_id": "example/Alpha-1",
            "observed_at": observed,
            "status": "error" if i == 6 else "ok",
        }
        if i != 6:
            hf_row["raw"] = {
                "id": "example/Alpha-1",
                "downloads": 140000 + i * 7800,
                "downloadsAllTime": 2000000 + i * 4000,
            }
        else:
            hf_row["error"] = "http_503"
        or_rows = [
            {"date": date, "model_permaslug": model, "total_tokens": str(tokens)}
            for model, tokens in (
                ("example/alpha-1", 13000000 + i * 920000),
                ("example/beta-2", 17000000 + i * 280000),
                ("unresolved/new-model", 1000000),
                ("other", 43000000),
            )
        ]
        sources = {
            "arena": {
                "status": "ok",
                "rows": arena_rows,
                "config": ARENA_CONFIG,
                "score_contract": ARENA_CONTRACT,
                "as_of": published,
                "start_date": published,
                "end_date": date,
            },
            "hf": {"status": "partial" if i == 6 else "ok", "rows": [hf_row]},
            "openrouter": {
                "status": "ok",
                "rows": or_rows,
                "as_of": observed,
                "meta": {
                    "version": "v1",
                    "start_date": date,
                    "end_date": date,
                    "as_of": observed,
                },
            },
        }
        for name, result in sources.items():
            result["source_url"] = SOURCE_URLS[name]
        write_new(
            Path(directory) / f"snapshot-demo-{date}.json",
            {
                **frozen,
                "synthetic": True,
                "observed_at": observed,
                "completed_at": observed,
                "catalog": catalog,
                "mapping": mapping,
                "sources": sources,
            },
        )
    return dates[0], dates[-1]
