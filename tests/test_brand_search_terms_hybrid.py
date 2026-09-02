"""U8 regression net for live Django BrandKeyword attribution."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.models import Brand, BrandKeyword, PostBrand
from monitor import cycle as cycle_mod
from monitor.cycle import CycleRunner, _build_brand_index
from x_monitor.attribution import detect_brand_mentions
from x_monitor.harvest_policy import load_policy
from x_monitor.query_plan import PlannedCall
from x_monitor.specs_from_policy import active_policy_tokens

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config.yaml"
POLICY_PATH = REPO_ROOT / "config" / "harvest_policy.yaml"


def _enabled_models() -> list[str]:
    from x_monitor.config import load_config

    return list(load_config(CONFIG_PATH).enabled_models)


def _planned() -> PlannedCall:
    return PlannedCall(
        call_id="B1",
        call_kind="brand_wide",
        brand_id="dots",
        bucket=None,
        query_string="dots3-note min_faves:0",
        query_length=23,
    )


def _tweet(tweet_id: str, text: str) -> dict[str, str]:
    return {
        "id": tweet_id,
        "author_id": f"author-{tweet_id}",
        "author_handle": f"user_{tweet_id}",
        "text": text,
        "lang": "en",
        "created_at": "Sat Jul 25 12:00:00 +0000 2026",
    }


class FakeApi:
    def __init__(self, results: list[dict[str, str]]):
        self.results = results
        self.searches: list[tuple[str, dict]] = []

    def run_search(self, query: str, **kwargs):
        self.searches.append((query, kwargs))
        return list(self.results), False


def test_active_policy_tokens_normalize_query_quotes_and_exclude_controls():
    policy = load_policy(POLICY_PATH)
    tokens = active_policy_tokens(policy, brand_nicknames=["glm"])["glm"]
    assert "ox alpha" in tokens
    assert "llm" not in tokens
    assert "zai_org" not in tokens


def test_build_brand_index_uses_all_enabled_db_keywords_and_regex(
    seeded_policy_keywords,
):
    BrandKeyword.objects.create(
        brand_id="glm", pattern=r"GLM-[0-9]+", is_regex=True
    )
    index = _build_brand_index(_enabled_models())
    assert "glm" in detect_brand_mentions("GLM-99", index)
    assert "dots" in detect_brand_mentions("dots3-note Preview", index)
    assert "hunyuan" in detect_brand_mentions("hy4 is genuinely unltd", index)
    assert "glm" in detect_brand_mentions("Ox Alpha is available", index)


def test_disabled_brand_keyword_is_not_compiled(seeded_policy_keywords):
    Brand.objects.get_or_create(
        nickname="disabled_brand",
        defaults={"display_name": "Disabled", "is_sentinel": False},
    )
    BrandKeyword.objects.create(
        brand_id="disabled_brand", pattern="disabled-token"
    )
    index = _build_brand_index(_enabled_models())
    assert detect_brand_mentions("disabled-token", index) == []


def test_real_cycle_persists_db_only_aliases_including_production_kimi_miss(
    seeded_policy_keywords, monkeypatch
):
    api = FakeApi(
        [
            _tweet("u8-dots", "dots3-note Preview is out"),
            _tweet("u8-hy", "hy4 is genuinely unltd"),
            _tweet("u8-ox", "Ox Alpha is no longer available"),
            _tweet(
                "2094999721551225267",
                "Moonshot AI's Kimi K3 climbed to third place",
            ),
        ]
    )
    monkeypatch.setattr(
        cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [_planned()]
    )
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
    )
    monkeypatch.setattr(
        CycleRunner,
        "_run_post_fetch",
        lambda self, items, **kwargs: {},
        raising=False,
    )

    stats = CycleRunner(cycle_kind="scheduled").run()

    assert api.searches
    assert stats["status"] in {"completed", "degraded"}
    assert PostBrand.objects.filter(post_id="u8-dots", brand_id="dots").exists()
    assert PostBrand.objects.filter(post_id="u8-hy", brand_id="hunyuan").exists()
    assert PostBrand.objects.filter(post_id="u8-ox", brand_id="glm").exists()
    assert PostBrand.objects.filter(
        post_id="2094999721551225267",
        brand_id="moonshot_kimi",
    ).exists()


def test_real_cycle_normalizes_quoted_literal_before_compilation(
    seeded_policy_keywords, monkeypatch
):
    BrandKeyword.objects.filter(
        brand_id="moonshot_kimi",
        pattern="kimi",
    ).update(pattern='  "Kimi"  ')
    api = FakeApi(
        [
            _tweet(
                "u8-kimi-normalized",
                "Moonshot AI's Kimi K3 climbed to third place",
            )
        ]
    )
    monkeypatch.setattr(
        cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [_planned()]
    )
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: api),
    )
    monkeypatch.setattr(
        CycleRunner,
        "_run_post_fetch",
        lambda self, items, **kwargs: {},
        raising=False,
    )

    stats = CycleRunner(cycle_kind="scheduled").run()

    assert api.searches
    assert stats["status"] in {"completed", "degraded"}
    assert PostBrand.objects.filter(
        post_id="u8-kimi-normalized",
        brand_id="moonshot_kimi",
    ).exists()


def test_missing_policy_mapping_blocks_provider_construction(
    seeded_policy_keywords, monkeypatch
):
    BrandKeyword.objects.filter(brand_id="glm", pattern="ox alpha").delete()
    constructed: list[object] = []

    def _provider(cls, _purpose):
        constructed.append(True)
        raise AssertionError("provider must not be constructed")

    monkeypatch.setattr(
        cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [_planned()]
    )
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient, "from_env", classmethod(_provider)
    )

    stats = CycleRunner(cycle_kind="scheduled").run()

    assert constructed == []
    assert "glm/ox alpha" in stats["degraded"]["attribution_preflight"]


def test_replay_missing_policy_mapping_blocks_provider_construction(
    seeded_policy_keywords, monkeypatch
):
    BrandKeyword.objects.filter(brand_id="glm", pattern="ox alpha").delete()
    constructed: list[object] = []
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: constructed.append(True)),
    )

    stats = CycleRunner(cycle_kind="backfill").replay_backlog_only()

    assert constructed == []
    assert stats["status"] == "aborted"
    assert any("glm/ox alpha" in error for error in stats["errors"])


def test_unknown_enabled_brand_blocks_provider_construction(
    seeded_policy_keywords, monkeypatch
):
    from x_monitor.config import load_config

    cfg = load_config(CONFIG_PATH)
    cfg.enabled_models.append("not_in_policy")
    constructed: list[object] = []
    monkeypatch.setattr(
        cycle_mod, "plan_calls_for_cycle", lambda cfg=None: [_planned()]
    )
    monkeypatch.setattr(
        cycle_mod.TwitterApiClient,
        "from_env",
        classmethod(lambda cls, _purpose: constructed.append(True)),
    )

    stats = CycleRunner(cfg=cfg, cycle_kind="scheduled").run()

    assert constructed == []
    assert "not_in_policy" in stats["degraded"]["attribution_preflight"]
