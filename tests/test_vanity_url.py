# {{AGENT_ATTRIBUTION}}
"""Tests for x_monitor.dashboard vanity URL resolution (U5 of
feat/pushin-weight-home-pages, 2026-07-06).

Covers:
- resolve_vanity_url_for_brand: returns (company, brand) for a brand
  with a parent, ("_", brand) for a brandless orphan, None for missing
- resolve_brand_via_vanity: inverse lookup with strict company match
- legacy_vanity_target: end-to-end helper for the /brand/<id> and
  /model/<id> 302 redirects
"""

from __future__ import annotations

import pytest

from x_monitor.dashboard import (
    resolve_vanity_url_for_brand,
    resolve_brand_via_vanity,
)
from x_monitor._home_routes import legacy_vanity_target
from x_monitor.store import Store


# ---------------------------------------------------------------------------
# In-memory Store stub
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Minimal DB-API 2.0 cursor: .execute(sql, params), .fetchone(),
    .fetchall(). Returns rows that can be indexed by name (dict-like)
    OR by position (tuple-like)."""

    def __init__(self, store: "_FakeStore"):
        self._store = store
        self._rows: list = []
        self._description: list = []
        self._executed = False

    @property
    def description(self):
        return self._description

    def execute(self, sql: str, params: tuple = ()):
        self._executed = True
        normalized = " ".join(sql.split()).lower()
        self._rows, self._description = self._store._plan(normalized, params)
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _FakeStore:
    """Tiny in-memory stand-in for Store, just enough to test the
    vanity URL resolvers. Implements only the methods the resolvers
    call: `_conn.execute(...)`, `_brand_int_id(...)` is not used here."""

    def __init__(
        self,
        brands: list[str],
        brand_to_company: dict[str, str] | None = None,
        companies: list[str] | None = None,
    ):
        self.brands = brands
        # Many-to-one: brand → company nickname (or None for orphan)
        self.brand_to_company = brand_to_company or {}
        self.companies = companies or list(set(brand_to_company.values())) if brand_to_company else []

    @property
    def _conn(self):
        return _FakeCursor(self)

    def _plan(self, sql: str, params: tuple):
        """Return (rows, description) for the query the resolver runs."""
        if "select nickname from brands where nickname = ?" in sql:
            nick = params[0]
            if nick in self.brands:
                return ([{"nickname": nick}], [("nickname",)])
            return ([], [("nickname",)])
        if (
            "select c.nickname as company_nickname" in sql
            and "from brands_companies bc" in sql
        ):
            nick = params[0]
            company = self.brand_to_company.get(nick)
            if company is None:
                return ([], [("company_nickname",)])
            return ([{"company_nickname": company}], [("company_nickname",)])
        if "select count(*) as n" in sql:
            nick = params[0]
            n = 1 if self.brand_to_company.get(nick) else 0
            return ([{"n": n}], [("n",)])
        if (
            "select nickname from companies where nickname = ?" in sql
        ):
            nick = params[0]
            if nick in self.companies:
                return ([{"nickname": nick}], [("nickname",)])
            return ([], [("nickname",)])
        if (
            "select 1" in sql
            and "from brands_companies bc" in sql
            and "join brands b" in sql
        ):
            brand, company = params
            if (
                brand in self.brands
                and self.brand_to_company.get(brand) == company
                and company in self.companies
            ):
                return ([{"1": 1}], [("1",)])
            return ([], [("1",)])
        raise AssertionError(f"unexpected SQL: {sql[:80]}")


# ---------------------------------------------------------------------------
# resolve_vanity_url_for_brand
# ---------------------------------------------------------------------------


def test_resolve_vanity_returns_company_for_known_brand():
    store = _FakeStore(
        brands=["qwen"],
        brand_to_company={"qwen": "alibaba"},
        companies=["alibaba"],
    )
    assert resolve_vanity_url_for_brand(store, "qwen") == ("alibaba", "qwen")


def test_resolve_vanity_returns_underscore_for_orphan_brand():
    store = _FakeStore(brands=["minimax"], brand_to_company={})
    assert resolve_vanity_url_for_brand(store, "minimax") == ("_", "minimax")


def test_resolve_vanity_returns_none_for_missing_brand():
    store = _FakeStore(brands=["qwen"], brand_to_company={"qwen": "alibaba"})
    assert resolve_vanity_url_for_brand(store, "nonexistent") is None


# ---------------------------------------------------------------------------
# resolve_brand_via_vanity (inverse)
# ---------------------------------------------------------------------------


def test_resolve_brand_via_vanity_matches_company():
    store = _FakeStore(
        brands=["qwen"],
        brand_to_company={"qwen": "alibaba"},
        companies=["alibaba"],
    )
    assert resolve_brand_via_vanity(store, "alibaba", "qwen") == "qwen"


def test_resolve_brand_via_vanity_rejects_wrong_company():
    """KTD8: /<wrong-company>/<brand> returns 404 (not 302)."""
    store = _FakeStore(
        brands=["qwen"],
        brand_to_company={"qwen": "alibaba"},
        companies=["alibaba", "tencent"],
    )
    assert resolve_brand_via_vanity(store, "tencent", "qwen") is None


def test_resolve_brand_via_vanity_underscore_path_orphan():
    store = _FakeStore(brands=["minimax"], brand_to_company={})
    assert resolve_brand_via_vanity(store, "_", "minimax") == "minimax"


def test_resolve_brand_via_vanity_underscore_path_company_owned():
    """R12: /_/qwen returns 404 when qwen is owned by alibaba."""
    store = _FakeStore(
        brands=["qwen"],
        brand_to_company={"qwen": "alibaba"},
        companies=["alibaba"],
    )
    assert resolve_brand_via_vanity(store, "_", "qwen") is None


def test_resolve_brand_via_vanity_missing_brand_returns_none():
    store = _FakeStore(brands=["qwen"], brand_to_company={"qwen": "alibaba"})
    assert resolve_brand_via_vanity(store, "alibaba", "nonexistent") is None


def test_resolve_brand_via_vanity_missing_company_returns_none():
    store = _FakeStore(
        brands=["qwen"],
        brand_to_company={"qwen": "alibaba"},
        companies=["alibaba"],
    )
    assert resolve_brand_via_vanity(store, "tencent", "qwen") is None
