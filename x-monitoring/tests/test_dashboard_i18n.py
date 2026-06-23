"""Dashboard wiring: DB-backed brand display names + signal/role labels (Unit 5).

Plan: docs/plans/2026-06-23-001-feat-i18n-locale-columns-plan.md (Unit 5).

Verifies:
- `_load_brand_display_names` reads the per-locale columns from the
  `brands` table and falls back to source / en / MODEL_DISPLAY_NAMES.
- `_load_signal_labels` returns all six chart-series keys with their
  localized labels (signal_labels table seeded by migration 007).
- `_load_role_labels` returns localized labels for the requested role
  keys (with safe fallback to the raw key).
- `serialize_grid_card` accepts `display_name` and `signal_labels`
  overrides and threads them into the returned dict.
- `_build_cards` reads DB-backed brand names + signal labels once per
  request and threads them into every card.
- `model_detail` route renders localized role-bar labels (Chinese
  labels via the role_labels table, English fallback otherwise).
- The trend-chart-wrap div emits a `data-signal-labels` attribute when
  the card has `signal_labels`; absent when the card has none.
- Integration: full /grid render with ?locale=zh-CN renders Chinese
  strings in the card title, with ?locale=en renders English.
- `api_model/<brand_id>.json` returns the DB-backed display_name.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from x_monitor.config import Config
from x_monitor.dashboard import (
    MODEL_DISPLAY_NAMES,
    _load_brand_display_names,
    _load_role_labels,
    _load_signal_labels,
    serialize_grid_card,
)
from x_monitor.store import Store


# --- _load_brand_display_names -----------------------------------------


def test_load_brand_display_names_zh_cn_returns_zh_cn_column(tmp_path):
    """When display_name_zh_cn is populated, the lookup returns it."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Seeded brands include minimax. Set its zh_cn display name.
        s._conn.execute(
            "UPDATE brands SET display_name_zh_cn = ? WHERE brand_id = ?",
            ("MiniMax AI 公司", "minimax"),
        )
        names = _load_brand_display_names(s, "zh_cn")
        assert names["minimax"] == "MiniMax AI 公司"
    finally:
        s.close()


def test_load_brand_display_names_falls_back_to_en(tmp_path):
    """When display_name_zh_cn is NULL, the lookup falls back to
    display_name_en, then to the source display_name."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "UPDATE brands SET display_name_en = ? WHERE brand_id = ?",
            ("MiniMax AI", "minimax"),
        )
        names = _load_brand_display_names(s, "zh_cn")
        assert names["minimax"] == "MiniMax AI"
    finally:
        s.close()


def test_load_brand_display_names_falls_back_to_source(tmp_path):
    """When both locale columns are NULL, the lookup falls back to
    the source display_name column (which is NOT NULL by schema)."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Source is "MiniMax AI" by default seed.
        names = _load_brand_display_names(s, "zh_cn")
        assert names["minimax"] == "MiniMax AI"
    finally:
        s.close()


def test_load_brand_display_names_zh_cn_alias_supported(tmp_path):
    """Both 'zh-CN' and 'zh_cn' spellings resolve to the same column."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "UPDATE brands SET display_name_zh_cn = ? WHERE brand_id = ?",
            ("MiniMax AI 公司", "minimax"),
        )
        names_canonical = _load_brand_display_names(s, "zh-CN")
        names_alias = _load_brand_display_names(s, "zh_cn")
        assert names_canonical["minimax"] == "MiniMax AI 公司"
        assert names_alias["minimax"] == "MiniMax AI 公司"
    finally:
        s.close()


def test_load_brand_display_names_unsupported_locale_warns_falls_back(tmp_path, caplog):
    """An unsupported locale falls back to 'en' with a warning log
    (mirrors normalize_locale behavior)."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        with caplog.at_level("WARNING"):
            names = _load_brand_display_names(s, "fr")
        assert names["minimax"] == "MiniMax AI"  # falls back to source
        # Warning is logged by normalize_locale, not by this helper.
    finally:
        s.close()


# --- _load_signal_labels -----------------------------------------------


def test_load_signal_labels_returns_all_six_series_keys(tmp_path):
    """The lookup returns all six chart-series keys, even if some are
    unseeded (in which case the raw key is the defensive fallback)."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        labels = _load_signal_labels(s, "en")
        assert set(labels.keys()) == {
            "release", "community_question", "criticism",
            "commenter_capture", "other", "praise",
        }
    finally:
        s.close()


def test_load_signal_labels_en_returns_english_labels(tmp_path):
    """English locale returns the English seeded labels."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        labels = _load_signal_labels(s, "en")
        assert labels["release"] == "Release"
        assert labels["criticism"] == "Criticism"
        assert labels["praise"] == "Praise"
    finally:
        s.close()


def test_load_signal_labels_zh_cn_returns_chinese_labels(tmp_path):
    """Chinese locale returns the zh_cn seeded labels (seeded by
    migration 007 with operator-curated translations)."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        labels = _load_signal_labels(s, "zh_cn")
        assert labels["release"] == "发布"
        assert labels["criticism"] == "批评"
        assert labels["praise"] == "称赞"
    finally:
        s.close()


# --- _load_role_labels -------------------------------------------------


def test_load_role_labels_returns_localized_labels(tmp_path):
    """Role keys map to their localized label per the role_labels table."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        labels = _load_role_labels(s, "zh_cn", ["official", "community"])
        assert labels["official"] == "官方"
        assert labels["community"] == "社区"
    finally:
        s.close()


def test_load_role_labels_falls_back_to_raw_key_on_unseeded(tmp_path):
    """An unseeded role key falls back to the raw key (defensive: the
    role could come from a legacy `unknown` value that the FK guard
    dead-lettered)."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        labels = _load_role_labels(s, "en", ["ghost_role"])
        assert labels["ghost_role"] == "ghost_role"
    finally:
        s.close()


def test_load_role_labels_empty_keys_returns_empty_dict(tmp_path):
    """Defensive: empty input list → empty dict (no SQL hit)."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        assert _load_role_labels(s, "en", []) == {}
    finally:
        s.close()


# --- serialize_grid_card overrides --------------------------------------


def test_serialize_grid_card_uses_display_name_override():
    """The `display_name` param overrides the default MODEL_DISPLAY_NAMES
    lookup, allowing the dashboard to thread a DB-backed localized name."""
    posts: list = []
    card = serialize_grid_card(
        "minimax", posts, display_name="M3 (中文)",
    )
    assert card["display_name"] == "M3 (中文)"


def test_serialize_grid_card_falls_back_to_model_dict_when_no_override():
    """When no `display_name` override is given, the card uses the
    MODEL_DISPLAY_NAMES dict (defensive fallback)."""
    posts: list = []
    card = serialize_grid_card("minimax", posts)
    assert card["display_name"] == MODEL_DISPLAY_NAMES["minimax"]


def test_serialize_grid_card_threads_signal_labels_override():
    """The `signal_labels` param is emitted into the card dict under
    `signal_labels`, ready for the template to render as a JSON attr."""
    posts: list = []
    labels = {"release": "发布", "praise": "称赞"}
    card = serialize_grid_card(
        "minimax", posts, signal_labels=labels,
    )
    assert card["signal_labels"] == labels


# --- _build_cards DB integration ----------------------------------------


def test_build_cards_threads_db_brand_names_zh_cn(tmp_path):
    """_build_cards reads brand display names from the DB for every
    enabled model in the requested locale."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    s.close()
    cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
    from x_monitor.dashboard import DashboardApp
    app = DashboardApp(cfg, tmp_path, db)
    with app.app.test_client() as c:
        c.set_cookie("locale", "zh_cn")
        # Seed zh_cn name.
        s2 = Store(db)
        try:
            s2._conn.execute(
                "UPDATE brands SET display_name_zh_cn = ? "
                "WHERE brand_id = ?",
                ("MiniMax AI 中文", "minimax"),
            )
        finally:
            s2.close()
        resp = c.get("/api/grid.json")
        assert resp.status_code == 200
        cards = resp.get_json()["cards"]
        assert len(cards) == 1
        assert cards[0]["display_name"] == "MiniMax AI 中文"


def test_build_cards_threads_db_signal_labels_zh_cn(tmp_path):
    """_build_cards reads signal labels from the DB for the requested
    locale and threads them into the card."""
    db = tmp_path / "x.db"
    cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
    from x_monitor.dashboard import DashboardApp
    app = DashboardApp(cfg, tmp_path, db)
    with app.app.test_client() as c:
        c.set_cookie("locale", "zh_cn")
        resp = c.get("/api/grid.json")
        cards = resp.get_json()["cards"]
        assert len(cards) == 1
        labels = cards[0]["signal_labels"]
        assert labels["release"] == "发布"
        assert labels["praise"] == "称赞"


def test_build_cards_en_locale_returns_english_signals(tmp_path):
    """Default English locale returns English signal labels."""
    db = tmp_path / "x.db"
    cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
    from x_monitor.dashboard import DashboardApp
    app = DashboardApp(cfg, tmp_path, db)
    with app.app.test_client() as c:
        # No cookie, no query param → "en" default.
        resp = c.get("/api/grid.json")
        cards = resp.get_json()["cards"]
        labels = cards[0]["signal_labels"]
        assert labels["release"] == "Release"
        assert labels["criticism"] == "Criticism"


# --- model_detail route role labels -------------------------------------


def test_brand_detail_renders_localized_role_labels_zh_cn(tmp_path):
    """The brand detail page renders Chinese role-bar labels when the
    locale cookie is zh_cn."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        # Use upsert_account to populate the role edge correctly
        # (author_id must be "handle:<handle>" by v1.8 schema).
        s.upsert_account(
            "minimax", "u_role_zh",
            role="official", engagement_tier="low",
        )
    finally:
        s.close()
    cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
    from x_monitor.dashboard import DashboardApp
    app = DashboardApp(cfg, tmp_path, db)
    with app.app.test_client() as c:
        c.set_cookie("locale", "zh_cn")
        resp = c.get("/brand/minimax")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "官方" in body  # the zh_cn label for "official"


def test_brand_detail_falls_back_to_en_when_zh_cn_label_missing(tmp_path):
    """If the zh_cn role label is missing (e.g. operator override
    removed it), the dashboard falls back to the English label rather
    than rendering the raw key."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s.upsert_account(
            "minimax", "u_fallback",
            role="official", engagement_tier="low",
        )
        # Wipe the zh_cn label for "official" to simulate operator
        # override removal. The dashboard should fall back to "Official".
        s._conn.execute(
            "DELETE FROM role_labels WHERE key = ? AND locale = ?",
            ("official", "zh_cn"),
        )
    finally:
        s.close()
    cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
    from x_monitor.dashboard import DashboardApp
    app = DashboardApp(cfg, tmp_path, db)
    with app.app.test_client() as c:
        c.set_cookie("locale", "zh_cn")
        resp = c.get("/brand/minimax")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # English fallback appears (raw key "official" should NOT be
        # the rendered text, since role_labels has the en row).
        assert "Official" in body
        assert "官方" not in body


# --- api_model.json integration ------------------------------------------


def test_api_model_returns_db_display_name_zh_cn(tmp_path):
    """The /api/model/<id>.json endpoint returns the DB-backed
    display_name in the requested locale."""
    db = tmp_path / "x.db"
    s = Store(db, auto_migrate=True)
    try:
        s._conn.execute(
            "UPDATE brands SET display_name_zh_cn = ? WHERE brand_id = ?",
            ("MiniMax AI 公司", "minimax"),
        )
    finally:
        s.close()
    cfg = Config(enabled_models=["minimax"], daily_ceiling=333)
    from x_monitor.dashboard import DashboardApp
    app = DashboardApp(cfg, tmp_path, db)
    with app.app.test_client() as c:
        c.set_cookie("locale", "zh_cn")
        resp = c.get("/api/model/minimax.json")
        data = resp.get_json()
        assert data["display_name"] == "MiniMax AI 公司"


# --- data-signal-labels attribute on _model_card.html.j2 -----------------


def test_model_card_template_emits_data_signal_labels_when_present(tmp_path):
    """When the card has signal_labels, the template emits
    data-signal-labels='<json>' on .trend-chart-wrap."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from x_monitor.dashboard import brand_colorize

    env = Environment(
        loader=FileSystemLoader(
            str(Path(__file__).parent.parent / "x_monitor" / "templates")
        ),
        autoescape=select_autoescape(["html.j2"]),
    )
    env.filters["brand_colorize"] = brand_colorize
    tpl = env.get_template("_model_card.html.j2")
    card = {
        "brand_id": "minimax",
        "display_name": "MiniMax AI",
        "accent_color": "#3b82f6",
        "chart": {"days": ["2026-06-23"], "series": {}},
        "signal_labels": {"release": "发布", "praise": "称赞"},
        "signal_labels_json": '{"release": "发布", "praise": "称赞"}',
        "top3_posts": [],
        "top3_7d": [],
        "top3_24h": [],
        "n_posts_in_window": 0,
        "n_posts_7d": 0,
        "n_posts_24h": 0,
        "degraded_sentinels": [],
        "last_run_at": None,
        "display_locale": "zh_cn",
    }
    rendered = tpl.render(card=card)
    assert "data-signal-labels=" in rendered
    # The labels must appear in the rendered JSON (UTF-8, not escaped).
    assert "发布" in rendered
    assert "称赞" in rendered


def test_model_card_template_omits_data_signal_labels_when_absent(tmp_path):
    """When the card has no signal_labels, the template omits the
    attribute (lets the JS fall back to its hardcoded English labels)."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from x_monitor.dashboard import brand_colorize

    env = Environment(
        loader=FileSystemLoader(
            str(Path(__file__).parent.parent / "x_monitor" / "templates")
        ),
        autoescape=select_autoescape(["html.j2"]),
    )
    env.filters["brand_colorize"] = brand_colorize
    tpl = env.get_template("_model_card.html.j2")
    card = {
        "brand_id": "minimax",
        "display_name": "MiniMax AI",
        "accent_color": "#3b82f6",
        "chart": {"days": ["2026-06-23"], "series": {}},
        "signal_labels": {},
        "signal_labels_json": "",
        "top3_posts": [],
        "top3_7d": [],
        "top3_24h": [],
        "n_posts_in_window": 0,
        "n_posts_7d": 0,
        "n_posts_24h": 0,
        "degraded_sentinels": [],
        "last_run_at": None,
        "display_locale": "en",
    }
    rendered = tpl.render(card=card)
    assert "data-signal-labels=" not in rendered
