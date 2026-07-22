"""
Tests for x_monitor.relevance (v1.2 commit 1).
"""
import tempfile
from pathlib import Path

import pytest

from x_monitor.relevance import (
    REASON_CANONICAL_BYPASS,
    REASON_HARD_DROP_NO_SIGNAL,
    REASON_HARD_DROP_URL_ONLY,
    REASON_KEPT,
    REASON_SOFT_DROP_BANNED,
    REASON_URL_ONLY_KEPT,
    RelevanceConfig,
    casefold_eq,
    filter_posts,
    is_url_only,
    load_filter,
    looks_like_ai_account,
)


# --- is_url_only ---------------------------------------------------------


class TestIsUrlOnly:
    def test_bare_tco_is_url_only(self):
        assert is_url_only("https://t.co/abc123") is True

    def test_text_with_url_is_not_url_only(self):
        assert is_url_only("check this out https://t.co/abc") is False

    def test_empty_string_is_not_url_only(self):
        assert is_url_only("") is False

    def test_none_is_not_url_only(self):
        assert is_url_only(None) is False

    def test_plain_text_is_not_url_only(self):
        assert is_url_only("Kimi is great") is False

    def test_multiple_urls_no_text(self):
        assert is_url_only("https://t.co/aaa https://t.co/bbb") is True


# --- casefold_eq ---------------------------------------------------------


class TestCasefoldEq:
    def test_simple(self):
        assert casefold_eq("Kimi", "kimi") is True
        assert casefold_eq("kimi", "KIMI") is True

    def test_german_sharp_s(self):
        # casefold() maps ß to ss
        assert casefold_eq("Straße", "STRASSE") is True

    def test_different(self):
        assert casefold_eq("kimi", "kimo") is False


# --- Pydantic validation -------------------------------------------------


class TestRelevanceConfigValidation:
    def test_minimal_config(self):
        cfg = RelevanceConfig()
        assert cfg.canonical_handles == []
        assert cfg.must_have_any == []
        assert cfg.must_have_none == []
        assert cfg.cjk_tokens == []
        assert cfg.drop_url_only is False

    def test_blank_strings_stripped(self):
        cfg = RelevanceConfig(canonical_handles=["  kimi  ", "", "  "])
        assert cfg.canonical_handles == ["kimi"]

    def test_short_cjk_rejected(self):
        with pytest.raises(ValueError, match="too short"):
            RelevanceConfig(cjk_tokens=["X"])  # 1 char CJK is too broad

    def test_full_config(self):
        cfg = RelevanceConfig(
            canonical_handles=["Kimi_Moonshot"],
            must_have_any=["kimi"],
            cjk_tokens=["月之暗面"],
            must_have_none=["F1"],
            drop_url_only=False,
        )
        assert cfg.canonical_handles == ["Kimi_Moonshot"]
        assert cfg.cjk_tokens == ["月之暗面"]


# --- filter_posts: token-gate pass/fail -----------------------------------


def _post(text: str, author: str = "alice", **extra) -> dict:
    return {
        "tweet_id": "t",
        "text": text,
        "author_handle": author,
        "brand_id": "test",
        "source_query_id": "Q5",
        **extra,
    }


class TestFilterTokenGate:
    def test_kept_when_text_has_must_token(self):
        cfg = RelevanceConfig(must_have_any=["kimi"])
        kept, stats, soft = filter_posts(
            [_post("Kimi K2 is amazing", author="u")], cfg
        )
        assert len(kept) == 1
        assert stats["n_kept"] == 1
        assert stats["n_dropped"] == 0
        assert stats["reasons"][REASON_KEPT] == 1
        assert soft == []

    def test_hard_dropped_when_no_must_and_no_banned(self):
        cfg = RelevanceConfig(must_have_any=["kimi"])
        kept, stats, soft = filter_posts(
            [_post("a totally unrelated post", author="u")], cfg
        )
        assert kept == []
        assert stats["n_dropped"] == 1
        assert stats["reasons"][REASON_HARD_DROP_NO_SIGNAL] == 1
        assert soft == []

    def test_word_boundary_does_not_partial_match(self):
        # "kimi" should not match "kimiko"
        cfg = RelevanceConfig(must_have_any=["kimi"])
        kept, stats, _ = filter_posts([_post("kimiko is great", author="u")], cfg)
        assert kept == []
        assert stats["reasons"][REASON_HARD_DROP_NO_SIGNAL] == 1

    def test_case_insensitive_must(self):
        cfg = RelevanceConfig(must_have_any=["kimi"])
        kept, stats, _ = filter_posts([_post("KIMI K2 launch", author="u")], cfg)
        assert len(kept) == 1
        assert stats["reasons"][REASON_KEPT] == 1

    def test_cjk_token_uses_in_not_regex(self):
        # "月之暗面" is CJK — must be matched with `in`, not word boundary
        cfg = RelevanceConfig(cjk_tokens=["月之暗面"])
        kept, stats, _ = filter_posts(
            [_post("月之暗面发布了Kimi K2.5", author="u")], cfg
        )
        assert len(kept) == 1
        assert stats["reasons"][REASON_KEPT] == 1


# --- filter_posts: canonical bypass --------------------------------------


class TestFilterCanonicalBypass:
    def test_canonical_author_bypasses_token_gates(self):
        cfg = RelevanceConfig(
            canonical_handles=["Kimi_Moonshot"],
            must_have_any=["kimi"],
        )
        # Author is canonical, text has NO model tokens
        kept, stats, _ = filter_posts(
            [_post("hello world", author="Kimi_Moonshot")], cfg
        )
        assert len(kept) == 1
        assert stats["reasons"][REASON_CANONICAL_BYPASS] == 1

    def test_canonical_author_bypasses_banned_tokens_too(self):
        cfg = RelevanceConfig(
            canonical_handles=["Kimi_Moonshot"],
            must_have_none=["F1"],
        )
        kept, stats, _ = filter_posts(
            [_post("F1 is amazing", author="Kimi_Moonshot")], cfg
        )
        assert len(kept) == 1
        assert stats["reasons"][REASON_CANONICAL_BYPASS] == 1

    def test_canonical_match_is_case_insensitive(self):
        cfg = RelevanceConfig(canonical_handles=["kimi_moonshot"])
        kept, _, _ = filter_posts(
            [_post("anything", author="KIMI_MOONSHOT")], cfg
        )
        assert len(kept) == 1


# --- filter_posts: banned tokens (soft-drop) -----------------------------


class TestFilterBannedTokens:
    def test_banned_without_must_soft_drops(self):
        cfg = RelevanceConfig(must_have_none=["F1"])
        kept, stats, soft = filter_posts(
            [_post("F1 driver Kimi Antonelli is fast", author="u")], cfg
        )
        assert kept == []
        assert stats["reasons"][REASON_SOFT_DROP_BANNED] == 1
        assert stats["n_soft_dropped"] == 1
        assert len(soft) == 1
        assert soft[0]["reason"] == "banned_token"
        assert soft[0]["tweet_id"] == "t"

    def test_banned_with_must_is_kept(self):
        # Critical: a real Kimi post that mentions F1 sponsorship is KEPT
        cfg = RelevanceConfig(
            must_have_any=["kimi"],
            must_have_none=["F1"],
        )
        kept, stats, soft = filter_posts(
            [_post("Kimi K2 is even faster than F1 cars", author="u")], cfg
        )
        assert len(kept) == 1
        assert stats["reasons"][REASON_KEPT] == 1
        assert soft == []

    def test_word_boundary_protects_f12(self):
        # "F1" should not match "F12" (a real F12 Ferrari exists)
        cfg = RelevanceConfig(must_have_none=["F1"])
        kept, stats, _ = filter_posts(
            [_post("the F12 is a beautiful car", author="u")], cfg
        )
        # F12 has no must, so it should hard-drop (not soft-drop on F1)
        assert stats["reasons"][REASON_HARD_DROP_NO_SIGNAL] == 1
        assert stats["reasons"].get(REASON_SOFT_DROP_BANNED, 0) == 0


# --- filter_posts: URL-only handling -------------------------------------


class TestFilterUrlOnly:
    def test_url_only_kept_by_default(self):
        cfg = RelevanceConfig(must_have_any=["kimi"])
        kept, stats, _ = filter_posts(
            [_post("https://t.co/abc123", author="u")], cfg
        )
        assert len(kept) == 1
        assert stats["reasons"][REASON_URL_ONLY_KEPT] == 1

    def test_url_only_dropped_when_configured(self):
        cfg = RelevanceConfig(must_have_any=["kimi"], drop_url_only=True)
        kept, stats, _ = filter_posts(
            [_post("https://t.co/abc123", author="u")], cfg
        )
        assert kept == []
        assert stats["reasons"][REASON_HARD_DROP_URL_ONLY] == 1

    def test_url_only_canonical_bypass_still_works(self):
        # When drop_url_only=True, canonical is still bypassed FIRST
        cfg = RelevanceConfig(
            canonical_handles=["Kimi_Moonshot"],
            drop_url_only=True,
        )
        kept, stats, _ = filter_posts(
            [_post("https://t.co/abc", author="Kimi_Moonshot")], cfg
        )
        assert len(kept) == 1
        assert stats["reasons"][REASON_CANONICAL_BYPASS] == 1


# --- filter_posts: empty config / mixed batch ---------------------------


class TestFilterMixed:
    def test_empty_config_is_pure_noop(self):
        cfg = RelevanceConfig()
        items = [
            _post("anything goes", author="u"),
            _post("F1 racing", author="u"),
            _post("https://t.co/abc", author="u"),
        ]
        kept, stats, _ = filter_posts(items, cfg)
        # No must, no banned, no drop_url_only -> everything kept
        assert len(kept) == 3
        assert stats["n_dropped"] == 0

    def test_mixed_batch_counts_each_reason(self):
        cfg = RelevanceConfig(
            canonical_handles=["OfficialBrand"],
            must_have_any=["kimi"],
            must_have_none=["F1"],
        )
        items = [
            _post("Kimi K2 is great", author="u1"),                  # kept
            _post("hello world", author="OfficialBrand"),            # canonical bypass
            _post("F1 racing", author="u2"),                         # soft-drop banned
            _post("unrelated content", author="u3"),                 # hard-drop no signal
            _post("https://t.co/xyz", author="u4"),                  # url-only kept
            _post("Kimi + F1 = great", author="u5"),                 # kept (must beats banned)
        ]
        kept, stats, soft = filter_posts(items, cfg)
        assert len(kept) == 4   # 1, 2, 5, 6 (urls)
        assert stats["n_soft_dropped"] == 1
        assert len(soft) == 1
        # Reasons must sum (excluding kept) to n_dropped
        drop_reasons = {
            k: v for k, v in stats["reasons"].items()
            if k not in (REASON_KEPT, REASON_CANONICAL_BYPASS, REASON_URL_ONLY_KEPT)
        }
        assert sum(drop_reasons.values()) == stats["n_dropped"]
        assert drop_reasons[REASON_SOFT_DROP_BANNED] == 1
        assert drop_reasons[REASON_HARD_DROP_NO_SIGNAL] == 1


# --- load_filter ---------------------------------------------------------


class TestLoadFilter:
    def test_missing_file_returns_empty_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = load_filter("minimax", Path(d))
            assert isinstance(cfg, RelevanceConfig)
            assert cfg.canonical_handles == []

    def test_loads_real_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "filters").mkdir()
            (root / "filters" / "minimax.yaml").write_text(
                "canonical_handles: [MiniMaxAI]\n"
                "must_have_any: [minimax, m3]\n"
                "cjk_tokens: [海螺]\n"
            )
            cfg = load_filter("minimax", root)
            assert cfg.canonical_handles == ["MiniMaxAI"]
            assert cfg.must_have_any == ["minimax", "m3"]
            assert cfg.cjk_tokens == ["海螺"]

    def test_wrapped_filter_key_supported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "filters").mkdir()
            (root / "filters" / "x.yaml").write_text(
                "filter:\n  canonical_handles: [Foo]\n  notes: hi\n"
            )
            cfg = load_filter("x", root)
            assert cfg.canonical_handles == ["Foo"]
            assert cfg.notes == "hi"

    def test_invalid_yaml_raises(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "filters").mkdir()
            (root / "filters" / "x.yaml").write_text("cjk_tokens: [X]\n")  # 1-char CJK
            with pytest.raises(ValueError, match="too short"):
                load_filter("x", root)


# --- looks_like_ai_account -----------------------------------------------


class TestLooksLikeAiAccount:
    def test_name_match_returns_likely(self):
        info = {"name": "Moonshot AI", "description": "AGI", "followersCount": 100, "verified": False}
        likely, reason = looks_like_ai_account(info, ["moonshot"])
        assert likely is True
        assert "moonshot" in reason

    def test_desc_match_returns_likely(self):
        info = {"name": "Foo", "description": "Building Kimi", "followersCount": 50, "verified": False}
        likely, _ = looks_like_ai_account(info, ["kimi"])
        assert likely is True

    def test_verified_with_followers_returns_likely(self):
        info = {"name": "Foo", "description": "no brand here", "followersCount": 5000, "verified": True}
        likely, _ = looks_like_ai_account(info, ["moonshot"])
        assert likely is True

    def test_low_signal_returns_unlikely(self):
        info = {"name": "John", "description": "trader", "followersCount": 200, "verified": False}
        likely, reason = looks_like_ai_account(info, ["moonshot", "kimi"])
        assert likely is False
        assert "verified" in reason or "name" in reason
