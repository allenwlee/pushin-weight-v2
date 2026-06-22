# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.hf_products: resolver + collector + Store product methods."""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from x_monitor import hf_client, hf_products
from x_monitor.store import Store


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _model(repo: str, author: str, **kw):
    m = {"id": repo, "author": author, "downloads": 0, "likes": 0}
    m.update(kw)
    return m


def _org_client(models):
    """Mock client serving LIST at /api/models and DETAIL at /api/models/{id}.

    The detail response is the list model enriched with cardData/config (what
    the real HF detail endpoint adds over the lean list payload).
    """
    by_id = {m["id"]: m for m in models}

    def handler(req):
        path = req.url.path
        if path == "/api/models":
            return httpx.Response(200, json=list(by_id.values()))
        if path.startswith("/api/models/"):
            rid = path[len("/api/models/"):]
            base = by_id.get(rid, {"id": rid, "author": rid.split("/")[0]})
            detail = dict(base)
            detail.setdefault("cardData", {"license": "mit", "library_name": "transformers"})
            detail.setdefault("config", {"model_type": "test"})
            detail.setdefault("disabled", False)
            return httpx.Response(200, json=detail)
        return httpx.Response(404)

    return _mock_client(handler)


# --- Store.read_brand_hf_orgs / upsert_brand_hf_org --------------------


def test_read_brand_hf_orgs_curated(tmp_path):
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        rows = s.read_brand_hf_orgs("deepseek")
        assert [r["hf_org"] for r in rows] == ["deepseek-ai"]
        assert all(r["confirmed"] == 1 for r in rows)
    finally:
        s.close()


def test_read_brand_hf_orgs_confirmed_only_filter(tmp_path):
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s.upsert_brand_hf_org(
            "deepseek", "deepseek-labs", confirmed=0, discovered_via="search:x"
        )
        confirmed = s.read_brand_hf_orgs("deepseek", confirmed_only=True)
        assert {r["hf_org"] for r in confirmed} == {"deepseek-ai"}
        all_rows = s.read_brand_hf_orgs("deepseek", confirmed_only=False)
        assert {r["hf_org"] for r in all_rows} == {"deepseek-ai", "deepseek-labs"}
    finally:
        s.close()


def test_upsert_brand_hf_org_does_not_demote_confirmed(tmp_path):
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s.upsert_brand_hf_org(
            "deepseek", "deepseek-ai", confirmed=0, discovered_via="search:x"
        )
        rows = s.read_brand_hf_orgs("deepseek", confirmed_only=True)
        assert any(r["hf_org"] == "deepseek-ai" and r["confirmed"] == 1 for r in rows)
    finally:
        s.close()


def test_upsert_brand_hf_org_idempotent(tmp_path):
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s.upsert_brand_hf_org("deepseek", "deepseek-labs", confirmed=0, discovered_via="search:x")
        s.upsert_brand_hf_org("deepseek", "deepseek-labs", confirmed=0, discovered_via="search:x")
        n = s._conn.execute(
            "SELECT COUNT(*) FROM brand_hf_orgs "
            "WHERE brand_id='deepseek' AND hf_org='deepseek-labs'"
        ).fetchone()[0]
        assert n == 1
    finally:
        s.close()


# --- resolve_hf_orgs ----------------------------------------------------


def test_resolve_hf_orgs_curated_skips_search(monkeypatch, tmp_path):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        calls = {"n": 0}

        def handler(req):
            calls["n"] += 1
            return httpx.Response(200, json=[])

        result = hf_products.resolve_hf_orgs(
            "deepseek", "DeepSeek", s, client=_mock_client(handler)
        )
        assert [r["hf_org"] for r in result] == ["deepseek-ai"]
        assert calls["n"] == 0
    finally:
        s.close()


def test_resolve_hf_orgs_discovers_and_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s._conn.execute("DELETE FROM brand_hf_orgs WHERE brand_id='qwen'")
        calls = {"n": 0}

        def handler(req):
            calls["n"] += 1
            assert req.url.path == "/api/organizations"
            return httpx.Response(200, json=[{"name": "Qwen"}, {"name": "Qwen-org"}])

        result = hf_products.resolve_hf_orgs("qwen", "Qwen", s, client=_mock_client(handler))
        assert result == []
        assert calls["n"] == 1
        cand = {r["hf_org"]: r for r in s.read_brand_hf_orgs("qwen", confirmed_only=False)}
        assert cand["Qwen"]["confirmed"] == 0
        assert cand["Qwen"]["discovered_via"] == "search:Qwen"
    finally:
        s.close()


def test_resolve_hf_orgs_read_only_skips_discovery(monkeypatch, tmp_path):
    """persist=False is read-only: no search, no candidate writes."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s._conn.execute("DELETE FROM brand_hf_orgs WHERE brand_id='qwen'")
        calls = {"n": 0}
        client = _mock_client(
            lambda req: (calls.__setitem__("n", calls["n"] + 1), httpx.Response(200, json=[{"name": "Qwen"}]))[1]
        )
        result = hf_products.resolve_hf_orgs("qwen", "Qwen", s, client=client, persist=False)
        assert result == []
        assert calls["n"] == 0  # no search performed
        n = s._conn.execute(
            "SELECT COUNT(*) FROM brand_hf_orgs WHERE brand_id='qwen'"
        ).fetchone()[0]
        assert n == 0  # no candidate persisted
    finally:
        s.close()


def test_resolve_hf_orgs_discovery_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s._conn.execute("DELETE FROM brand_hf_orgs WHERE brand_id='qwen'")
        client = _mock_client(lambda req: httpx.Response(200, json=[{"name": "Qwen"}]))
        hf_products.resolve_hf_orgs("qwen", "Qwen", s, client=client)
        hf_products.resolve_hf_orgs("qwen", "Qwen", s, client=client)
        n = s._conn.execute(
            "SELECT COUNT(*) FROM brand_hf_orgs WHERE brand_id='qwen' AND hf_org='Qwen'"
        ).fetchone()[0]
        assert n == 1
    finally:
        s.close()


# --- _model_to_product_row mapping -------------------------------------


def test_model_to_product_row_maps_fields():
    m = {
        "id": "org/Name", "author": "org", "downloads": 42, "downloadsAllTime": 420,
        "likes": 7, "pipeline_tag": "text-generation", "gated": "auto",
        "private": False, "tags": ["a", "b"],
        "siblings": [{"rfilename": "config.json"}],
        "cardData": {"license": "mit", "library_name": "transformers"},
        "config": {"model_type": "llama"},
        "createdAt": "2026-01-01T00:00:00", "lastModified": "2026-06-01T00:00:00",
    }
    row = hf_products._model_to_product_row("deepseek", "org", m)
    assert row["repo_id"] == "org/Name"
    assert row["display_name"] == "Name"
    assert row["hf_org"] == "org"
    assert row["hf_type"] == "model"
    assert row["brand_id"] == "deepseek"
    assert row["downloads"] == 42 and row["downloads_all_time"] == 420
    assert row["gated"] == "auto"
    assert row["private"] == 0
    assert row["library_name"] == "transformers"  # from cardData
    assert json.loads(row["tags_json"]) == ["a", "b"]
    assert json.loads(row["raw_json"])["id"] == "org/Name"


def test_model_to_product_row_gated_false_to_string():
    row = hf_products._model_to_product_row(
        "b", "org", {"id": "org/x", "author": "org", "gated": False}
    )
    assert row["gated"] == "false"


# --- Store.upsert_product / read_products ------------------------------


def test_upsert_product_insert_then_update_idempotent(tmp_path):
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s.upsert_product(hf_products._model_to_product_row(
            "deepseek", "deepseek-ai", _model("deepseek-ai/X", "deepseek-ai", downloads=10)
        ))
        prods = s.read_products()
        assert len(prods) == 1 and prods[0]["downloads"] == 10
        first_collected = prods[0]["collected_at"]

        s.upsert_product(hf_products._model_to_product_row(
            "deepseek", "deepseek-ai", _model("deepseek-ai/X", "deepseek-ai", downloads=99)
        ))
        prods = s.read_products()
        assert len(prods) == 1           # no duplicate
        assert prods[0]["downloads"] == 99
        assert prods[0]["collected_at"] == first_collected  # stable on update
    finally:
        s.close()


def test_upsert_product_refreshes_mutable_keeps_stable(tmp_path):
    """On conflict: mutable stats refresh; brand_id/display_name stay stable."""
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s.upsert_product(hf_products._model_to_product_row(
            "deepseek", "deepseek-ai", _model("deepseek-ai/A", "deepseek-ai", downloads=10, likes=1)
        ))
        # Re-scrape same repo with new stats + a different (wrong) brand_id: brand must NOT flip.
        s.upsert_product(hf_products._model_to_product_row(
            "qwen", "deepseek-ai", _model("deepseek-ai/A", "deepseek-ai", downloads=90, likes=7)
        ))
        prods = s.read_products()
        assert len(prods) == 1
        assert prods[0]["downloads"] == 90  # mutable refreshed
        assert prods[0]["likes"] == 7       # mutable refreshed
        assert prods[0]["brand_id"] == "deepseek"  # stable, not flipped to qwen
    finally:
        s.close()


def test_read_products_filter_and_order(tmp_path):
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s.upsert_product(hf_products._model_to_product_row(
            "deepseek", "deepseek-ai", _model("deepseek-ai/A", "deepseek-ai", downloads=5)
        ))
        s.upsert_product(hf_products._model_to_product_row(
            "qwen", "Qwen", _model("Qwen/B", "Qwen", downloads=50)
        ))
        deepseek = s.read_products("deepseek")
        assert [p["repo_id"] for p in deepseek] == ["deepseek-ai/A"]
        ordered = [p["downloads"] for p in s.read_products()]
        assert ordered == [50, 5]
    finally:
        s.close()


# --- collect_products_for_org (list + detail enrichment) ---------------


def test_collect_products_for_org_upserts_with_carddata(monkeypatch, tmp_path):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        models = [
            _model("deepseek-ai/V3", "deepseek-ai", downloads=100, likes=10),
            _model("deepseek-ai/R1", "deepseek-ai", downloads=50),
            _model("deepseek-ai/DSM", "deepseek-ai", downloads=5),
        ]
        r = hf_products.collect_products_for_org(
            "deepseek", "deepseek-ai", s, client=_org_client(models)
        )
        assert r == {"org": "deepseek-ai", "ok": True, "upserted": 3, "skipped": 0, "failed": 0}
        prods = s.read_products("deepseek")
        assert len(prods) == 3
        assert all(p["hf_type"] == "model" for p in prods)
        # cardData/config populated from the DETAIL endpoint
        assert json.loads(prods[0]["card_data_json"])["license"] == "mit"
        assert json.loads(prods[0]["config_json"])["model_type"] == "test"
        assert json.loads(prods[0]["raw_json"])["id"].startswith("deepseek-ai/")
    finally:
        s.close()


def test_collect_products_for_org_skips_author_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        models = [
            _model("deepseek-ai/A", "deepseek-ai"),
            _model("other/B", "other"),  # wrong namespace → skipped
        ]
        r = hf_products.collect_products_for_org(
            "deepseek", "deepseek-ai", s, client=_org_client(models)
        )
        assert r == {"org": "deepseek-ai", "ok": True, "upserted": 1, "skipped": 1, "failed": 0}
        assert len(s.read_products("deepseek")) == 1
    finally:
        s.close()


def test_collect_products_for_org_invalid_org(monkeypatch, tmp_path):
    """Sanity gate fails (no models) → ok=False, nothing scraped."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        client = _mock_client(lambda req: httpx.Response(200, json=[]))
        r = hf_products.collect_products_for_org(
            "deepseek", "deepseek-ai", s, client=client
        )
        assert r == {"org": "deepseek-ai", "ok": False, "upserted": 0, "skipped": 0, "failed": 0}
        assert s.read_products() == []
    finally:
        s.close()


def test_collect_skips_failing_model(monkeypatch, tmp_path):
    """One model's upsert raising is skipped (failed), the rest still collected."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        models = [
            _model("deepseek-ai/A", "deepseek-ai", downloads=10),
            _model("deepseek-ai/BAD", "deepseek-ai", downloads=5),
            _model("deepseek-ai/C", "deepseek-ai", downloads=1),
        ]
        client = _org_client(models)
        orig = s.upsert_product

        def wrapped(row):
            if row["repo_id"] == "deepseek-ai/BAD":
                raise sqlite3.IntegrityError("simulated")
            return orig(row)

        s.upsert_product = wrapped
        r = hf_products.collect_products_for_org("deepseek", "deepseek-ai", s, client=client)
        assert r["upserted"] == 2
        assert r["failed"] == 1
        ids = {p["repo_id"] for p in s.read_products("deepseek")}
        assert ids == {"deepseek-ai/A", "deepseek-ai/C"}
    finally:
        s.close()


def test_collect_falls_back_to_list_when_detail_404(monkeypatch, tmp_path):
    """A detail 404 falls back to the lean list payload (cardData empty)."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        def handler(req):
            if req.url.path == "/api/models":
                return httpx.Response(200, json=[_model("deepseek-ai/A", "deepseek-ai", downloads=10)])
            return httpx.Response(404)  # detail missing

        r = hf_products.collect_products_for_org(
            "deepseek", "deepseek-ai", s, client=_mock_client(handler)
        )
        assert r["upserted"] == 1
        prods = s.read_products("deepseek")
        assert prods[0]["downloads"] == 10           # from list payload
        assert json.loads(prods[0]["card_data_json"]) == {}  # no detail → no cardData
    finally:
        s.close()


# --- collect_all --------------------------------------------------------


def _collect_all_handler():
    """Dual-path handler: list returns one {org}/m model; detail enriches it."""
    def handler(req):
        path = req.url.path
        if path == "/api/models":
            org = req.url.params.get("author")
            return httpx.Response(200, json=[{"id": f"{org}/m", "author": org}])
        if path.startswith("/api/models/"):
            rid = path[len("/api/models/"):]
            return httpx.Response(
                200, json={"id": rid, "author": rid.split("/")[0], "cardData": {"license": "mit"}}
            )
        return httpx.Response(404)
    return handler


def test_collect_all_scopes_to_companies(monkeypatch, tmp_path):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        hf_products.collect_all(s, companies=["deepseek"], client=_mock_client(_collect_all_handler()))
        brands = {p["brand_id"] for p in s.read_products()}
        assert brands == {"deepseek"}
    finally:
        s.close()


def test_collect_all_dry_run_no_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        res = hf_products.collect_all(
            s, companies=["deepseek"], client=_mock_client(_collect_all_handler()), dry_run=True
        )
        assert any(r.get("dry_run") for r in res)
        assert s.read_products() == []
    finally:
        s.close()


def test_collect_all_dry_run_read_only_on_unconfirmed(monkeypatch, tmp_path):
    """dry_run on a brand with NO confirmed org writes nothing (no discovery)."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        s._conn.execute("DELETE FROM brand_hf_orgs WHERE brand_id='deepseek'")
        calls = {"n": 0}

        def handler(req):
            calls["n"] += 1
            return httpx.Response(200, json=[{"name": "deepseek-ai"}])  # would-be candidates

        hf_products.collect_all(
            s, companies=["deepseek"], client=_mock_client(handler), dry_run=True
        )
        # No discovery search, no candidate persisted, no products.
        assert calls["n"] == 0
        n = s._conn.execute(
            "SELECT COUNT(*) FROM brand_hf_orgs WHERE brand_id='deepseek'"
        ).fetchone()[0]
        assert n == 0
        assert s.read_products() == []
    finally:
        s.close()


def test_collect_all_org_isolation(monkeypatch, tmp_path):
    """One org raising does not abort the run; the other still completes."""
    monkeypatch.setattr(hf_client, "_sleep", lambda s: None)
    s = Store(tmp_path / "x.db", auto_migrate=True)
    try:
        base = _collect_all_handler()

        def handler(req):
            if req.url.path == "/api/models" and req.url.params.get("author") == "Qwen":
                raise RuntimeError("boom")
            return base(req)

        res = hf_products.collect_all(
            s, companies=["deepseek", "qwen"], client=_mock_client(handler)
        )
        by_brand = {r["brand_id"]: r for r in res}
        assert by_brand["deepseek"].get("ok") is True
        assert by_brand["qwen"].get("ok") is False
        assert "error" in by_brand["qwen"]
    finally:
        s.close()
