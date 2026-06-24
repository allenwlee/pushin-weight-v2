# {{AGENT_ATTRIBUTION}}
"""HuggingFace products crawler: brand→org resolution + model collection.

Three-stage pipeline (plan:
docs/plans/2026-06-21-001-feat-hf-products-crawler-plan.md):
  resolve            (company → HF org)   resolve_hf_orgs (hybrid curated + discover-and-flag)
  enumerate + gate   (org → models)       hf_client.list_models_by_org + org_has_models
  enrich + persist   (model → product)    collect_products_for_org + Store.upsert_product

The HF HTTP layer lives in `hf_client`; this module owns orchestration.

Field coverage (verified live): the `full=true` LIST endpoint is lean
(downloads/likes/tags/siblings/pipeline_tag/library_name/sha/timestamps); the
per-model DETAIL endpoint adds cardData/config/spaces/disabled/safetensors/
usedStorage — so collect fetches detail per model to populate those.
downloadsAllTime / per-day velocity are not API-exposed; 30-day `downloads` is
the canonical metric and is always captured.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from x_monitor import hf_client

if TYPE_CHECKING:
    import httpx
    from x_monitor.store import Store

_log = logging.getLogger(__name__)

# How many search candidates to persist as unconfirmed when discovering.
_DISCOVER_CANDIDATES = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _bool_int(v: Any) -> int | None:
    """Coerce a bool/None to 0/1/None (None preserved → column stays NULL)."""
    return None if v is None else int(bool(v))


# --- resolve ------------------------------------------------------------


def resolve_hf_orgs(
    company_id: str,
    display_name: str,
    store: "Store",
    *,
    client: "httpx.Client | None" = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    """Return confirmed HF orgs for a company (hybrid curated + discover-and-flag).

    Reads confirmed orgs from `hf_orgs` first. If none exist and ``persist``
    is True (default), searches HF for candidates and persists them with
    confirmed=0 (flagged for operator review) — they are NOT scraped this
    run. With ``persist=False`` the function is fully read-only (no discovery,
    no writes) — used by ``--dry-run`` so it has no side effects. Returns the
    confirmed orgs only (possibly empty).

    Companies are the corporate-parent axis: an HF namespace belongs to
    exactly one company. The brand→company hop (via `brands_companies`) is
    handled by `collect_all`; this function operates one level higher, on
    companies.
    """
    confirmed = store.read_hf_orgs(company_id, confirmed_only=True)
    if confirmed:
        return confirmed
    if not persist:
        return []

    candidates = hf_client.search_organizations(display_name, client=client)
    kept = candidates[:_DISCOVER_CANDIDATES]
    for cand in kept:
        org = (
            cand.get("name")
            or cand.get("id")
            or cand.get("org")
            or cand.get("user")
        )
        if not org:
            continue
        store.upsert_hf_org(
            org,
            company_id,
            confirmed=0,
            discovered_via=f"search:{display_name}",
        )
    if kept:
        _log.info(
            "hf_products: discovered %d candidate org(s) for company %r — "
            "promote via hf_orgs.confirmed=1 to scrape",
            len(kept),
            company_id,
        )
    return []


# --- enrich + persist ---------------------------------------------------


def _model_to_product_row(
    brand_id: str, hf_org_id: str, m: dict[str, Any]
) -> dict[str, Any]:
    """Map an HF model object onto a `products` row dict.

    Scalar fields → typed columns; nested/list/object fields → JSON columns;
    the full payload is kept verbatim in raw_json. Handles both camelCase
    (REST) and snake_case field names defensively. `hf_org_id` is the HF
    namespace string (e.g. "MiniMaxAI"); it must already exist in the
    `hf_orgs` table (FK enforced at INSERT).
    """
    repo_id = m.get("id") or m.get("modelId") or ""
    display_name = repo_id.split("/", 1)[1] if "/" in repo_id else repo_id
    card = m.get("cardData") or m.get("card_data") or {}
    gated = m.get("gated")
    if gated is False:
        gated_s = "false"
    elif gated is None:
        gated_s = None
    else:
        gated_s = str(gated)
    now = _now_iso()
    return {
        "repo_id": repo_id,
        "brand_id": brand_id,
        "hf_org_id": m.get("author") or hf_org_id,
        "hf_type": "model",
        "display_name": display_name,
        "author": m.get("author"),
        "sha": m.get("sha"),
        "private": _bool_int(m.get("private")),
        "gated": gated_s,
        "disabled": _bool_int(m.get("disabled")),
        "pipeline_tag": m.get("pipeline_tag") or m.get("task"),
        "library_name": m.get("library_name") or card.get("library_name"),
        "downloads": m.get("downloads"),
        "downloads_all_time": m.get("downloadsAllTime") or m.get("downloads_all_time"),
        "download_velocity": m.get("downloads_per_day") or m.get("downloadsPerDay"),
        "likes": m.get("likes"),
        "trending_score": m.get("trendingScore") or m.get("trending_score"),
        "paperswithcode_id": m.get("paperswithcode_id"),
        "created_at": m.get("createdAt") or m.get("created_at"),
        "last_modified": m.get("lastModified") or m.get("last_modified"),
        "tags_json": json.dumps(m.get("tags") or []),
        "siblings_json": json.dumps(m.get("siblings") or []),
        "card_data_json": json.dumps(card),
        "config_json": json.dumps(m.get("config") or {}),
        "spaces_json": json.dumps(m.get("spaces") or []),
        "raw_json": json.dumps(m, default=str),
        "collected_at": now,
        "updated_at": now,
    }


def collect_products_for_org(
    brand_id: str,
    org: str,
    store: "Store",
    *,
    client: "httpx.Client | None" = None,
    max: int | None = None,
    fetch_detail: bool = True,
) -> dict[str, Any]:
    """Sanity-gate ``org``, list its models, enrich each via detail, upsert.

    The LIST endpoint is lean, so each model is enriched via the DETAIL endpoint
    (`GET /api/models/{id}`) to populate cardData/config/spaces. If the detail
    call fails (404/error), the row falls back to the list payload. Per-model
    isolation: a single failing upsert is logged and skipped (counted as
    ``failed``) rather than aborting the rest of the org's models. Returns
    {org, ok, upserted, skipped, failed}. A wrong org fails loudly (ok=False).
    """
    ok, _sample = hf_client.org_has_models(org, client=client)
    if not ok:
        _log.warning("hf_products: sanity gate FAILED for %r — skipped", org)
        return {"org": org, "ok": False, "upserted": 0, "skipped": 0, "failed": 0}

    models = hf_client.list_models_by_org(org, client=client, max=max)
    upserted = 0
    skipped = 0
    failed = 0
    detail_misses = 0
    for m in models:
        author = m.get("author")
        rid = m.get("id", "")
        if author and author != org and not rid.startswith(f"{org}/"):
            skipped += 1
            continue
        if not rid:
            skipped += 1  # empty repo_id would collide on PK '' — skip
            continue
        try:
            source: dict[str, Any] = m
            if fetch_detail:
                detail = hf_client.get_model(rid, client=client)
                if detail:
                    source = detail
                else:
                    detail_misses += 1
            store.upsert_product(_model_to_product_row(brand_id, org, source))
            upserted += 1
        except Exception as e:  # per-model isolation: one bad row skips, not aborts
            failed += 1
            _log.warning("hf_products: failed to upsert %s: %s", rid, e)
    _log.info(
        "hf_products: %s → %d upserted, %d skipped, %d failed, %d detail-miss(es)",
        org, upserted, skipped, failed, detail_misses,
    )
    return {"org": org, "ok": True, "upserted": upserted, "skipped": skipped, "failed": failed}


def collect_all(
    store: "Store",
    *,
    companies: list[str] | None = None,
    client: "httpx.Client | None" = None,
    max: int | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Collect products for every enabled company (or a `companies` subset).

    The outer loop iterates **companies** (the corporate-parent axis); for
    each company we read its HF orgs via `hf_orgs` (1:N) and its brands via
    `brands_companies` (M:N). A company with zero HF coverage is logged and
    skipped; a brand with no `brands_companies` edge (e.g. `_unattributed`)
    is naturally excluded.

    Per-org isolation: one failing org is recorded and skipped; the rest of
    the run completes. `companies` accepts `company_id` or display name;
    unknown values are logged and skipped. `dry_run` resolves orgs only —
    fully read-only (no discovery writes, no product writes).
    """
    company_rows = {c.company_id: c for c in store.read_companies()}

    if companies:
        wanted: set[str] = set()
        for c in companies:
            if c in company_rows:
                wanted.add(c)
                continue
            match = next(
                (
                    cid
                    for cid, cr in company_rows.items()
                    if cr.display_name.lower() == c.lower()
                ),
                None,
            )
            if match:
                wanted.add(match)
            else:
                _log.warning("hf_products: unknown company %r — skipped", c)
        company_rows = {cid: cr for cid, cr in company_rows.items() if cid in wanted}

    results: list[dict[str, Any]] = []
    for cid, c in company_rows.items():
        # dry_run → read-only resolve (no discovery writes)
        orgs = resolve_hf_orgs(cid, c.display_name, store, client=client, persist=not dry_run)
        brand_ids = store.read_brands_companies_for_company(cid)
        if not orgs:
            results.append(
                {
                    "company_id": cid,
                    "brand_ids": brand_ids,
                    "resolved": [],
                    "note": "no confirmed HF org",
                }
            )
            continue
        for org_row in orgs:
            org_id = org_row["id"]
            if dry_run:
                results.append(
                    {
                        "company_id": cid,
                        "brand_ids": brand_ids,
                        "org": org_id,
                        "dry_run": True,
                    }
                )
                continue
            # For each HF org, attribute products to each brand the company owns.
            # (Most companies own a single brand; multi-brand companies like
            # alibaba→qwen will see products spread across brands.)
            for bid in brand_ids:
                try:
                    r = collect_products_for_org(bid, org_id, store, client=client, max=max)
                    results.append({"company_id": cid, "brand_id": bid, **r})
                except Exception as e:  # per-org isolation
                    _log.exception("hf_products: collect failed for %s/%s", bid, org_id)
                    results.append(
                        {
                            "company_id": cid,
                            "brand_id": bid,
                            "org": org_id,
                            "ok": False,
                            "error": f"{type(e).__name__}: {e}",
                        }
                    )
    return results
