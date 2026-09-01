"""Regression pin for the owner-approved, partial V24 Bridgewright target."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
V24_MOCKUP = "docs/ideation/mockups/v24.html"
V24_CONTRACT = "docs/reference/2026-08-19-132714-v24-bridgewright-target.md"
PRODUCTION_CONTRACT = "docs/reference/2026-08-19-174833-production-filter-feed-bridgewright-target.md"
CHART_CONTRACT = "docs/reference/2026-08-24-162449-home-chart-time-axes-bridgewright-target.md"
PREFERENCES_UI_CONTRACT = "docs/reference/2026-08-26-141113-home-preferences-ui-regressions-bridgewright-target.md"
PULSE_FEED_TIMEZONE_CONTRACT = "docs/reference/2026-08-26-202742-pulse-feed-timezone-polish-bridgewright-target.md"
CYBER_QUAN_CONTRACT = "docs/reference/2026-08-28-134649-cyber-quan-icons-bridgewright-target.md"
FEED_HEADLINE_CONTRACT = "docs/reference/2026-08-28-164425-feed-headline-usability-bridgewright-target.md"
HOVER_FREEZE_CONTRACT = "docs/reference/2026-08-28-181416-chart-hover-freeze-bridgewright-target.md"
GEOGRAPHY_CONTRACT = "docs/reference/2026-08-31-221955-feed-country-geography-bridgewright-target.md"
FEED_INSPECTION_CONTRACT = "docs/reference/2026-09-01-114311-feed-inspection-pagination-bridgewright-target.md"


def test_bridgewright_uses_v24_and_its_partial_target_contract() -> None:
    manifest = yaml.safe_load((REPO_ROOT / "bridgewright.yaml").read_text())
    adapter = yaml.safe_load((REPO_ROOT / ".bridgewright/adapter.yaml").read_text())
    authorities = manifest["configuration"]["authorities"]

    assert authorities["approved_mockup"] == V24_MOCKUP
    assert authorities["last_approved_contract"] == FEED_INSPECTION_CONTRACT
    assert FEED_INSPECTION_CONTRACT in authorities["approved_product_intent"]
    assert GEOGRAPHY_CONTRACT in authorities["approved_product_intent"]
    assert HOVER_FREEZE_CONTRACT in authorities["approved_product_intent"]
    assert FEED_HEADLINE_CONTRACT in authorities["approved_product_intent"]
    assert CYBER_QUAN_CONTRACT in authorities["approved_product_intent"]
    assert PULSE_FEED_TIMEZONE_CONTRACT in authorities["approved_product_intent"]
    assert PREFERENCES_UI_CONTRACT in authorities["approved_product_intent"]
    assert CHART_CONTRACT in authorities["approved_product_intent"]
    assert PRODUCTION_CONTRACT in authorities["approved_product_intent"]
    assert V24_CONTRACT in authorities["approved_product_intent"]
    assert adapter["surface"] == "v24-home"
    assert adapter["mockup"] == V24_MOCKUP
    assert manifest["configuration"]["semantic_anchors"] == [
        {
            "key": "v24.home",
            "description": "Owner-approved partial V24 dashboard target.",
        },
        {
            "key": "production.home.filter-feed",
            "description": "Owner-approved production filter and feed interaction delta.",
        },
        {
            "key": "production.home.chart-time-performance",
            "description": "Owner-approved home-chart time-axis and performance delta.",
        },
        {
            "key": "production.home.preferences-ui",
            "description": "Owner-approved browser preferences and homepage UI regression delta.",
        },
        {
            "key": "production.home.pulse-feed-timezone-polish",
            "description": "Owner-approved pulse navigation, timezone chart, and feed identity delta.",
        },
        {
            "key": "production.home.cyber-quan-icons",
            "description": "Owner-approved icon-only Cyber-Quan replacement and compact masthead mark.",
        },
        {
            "key": "production.home.feed-headline-usability",
            "description": "Owner-approved bounded feed text, headline disclosure, semantic option icons, account roles, and one-line identity delta.",
        },
        {
            "key": "production.home.chart-hover-freeze",
            "description": "Owner-approved one-day point freeze, local and Beijing datetime tooltip, brand-only bucket feed, and exact transient-state restoration delta.",
        },
        {
            "key": "production.home.feed-country-geography",
            "description": "Owner-approved normalized account geography, guiding-country hierarchy, Taiwan-neutral signal, and one-button headline disclosure delta.",
        },
        {
            "key": "production.home.feed-inspection-pagination",
            "description": "Owner-approved feed inspection, X-only navigation, language and region projection, flag-tree hierarchy, one-day chart sizing, and window-complete pagination delta.",
        },
        {
            "key": "trend.headline",
            "description": "Shared analytical trend narrative surface.",
        },
    ]

    contract = (REPO_ROOT / V24_CONTRACT).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in contract
    assert "V24 replaces V22" in contract
    assert "Production line graph" in contract
    assert "Production feed" in contract
    assert "not targets" in contract
    assert "Do not replace" in contract

    production_contract = (REPO_ROOT / PRODUCTION_CONTRACT).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in production_contract
    assert "d821c4b7188c7df8100efec7d21195d9e1277d58" in production_contract
    assert "The production Chart.js component is not" in production_contract
    assert "substantial Chart.js batch" in production_contract
    assert "`posts.commentary_zh_cn` and `posts.commentary_en`" in production_contract
    assert "Do not populate `commentary_en` yet" in production_contract
    assert "commentary -> literal Chinese -> English" in production_contract

    chart_contract = (REPO_ROOT / CHART_CONTRACT).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in chart_contract
    assert "e290ba67ef0cd382a34fc774cd3cc173e5a00b1f" in chart_contract
    assert "30d and 365d" in chart_contract
    assert "top local-time x-axis" in chart_contract
    assert "bottom California-time x-axis" in chart_contract
    assert "exactly 24 fixed hourly positions" in chart_contract
    assert "#fbbf24" in chart_contract
    assert "same order as the visible pulse chips" in chart_contract
    assert "Do not replace the production Chart.js component" in chart_contract
    assert "does not approve staging or production release" in chart_contract

    preferences_contract = (REPO_ROOT / PREFERENCES_UI_CONTRACT).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in preferences_contract
    assert "2184d58fa718cdc7bde2eb30861dd1f388aa3523" in preferences_contract
    assert "versioned, user-namespaced browser payload" in preferences_contract
    assert "all 20 canonical enabled-model chips" in preferences_contract
    assert "both hourly axes below" in preferences_contract
    assert "follower-count circles" in preferences_contract
    assert "`gemini`, `gpt`, `claude`, and `grok`" in preferences_contract
    assert "current hosted staging\nappearance is not an approved baseline" in preferences_contract.lower()
    assert "does\nnot approve promotion to production" in preferences_contract

    pulse_feed_timezone_contract = (
        REPO_ROOT / PULSE_FEED_TIMEZONE_CONTRACT
    ).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in pulse_feed_timezone_contract
    assert "c2c713d07f6fb7c9659ae70f4d4d03dcf414ac7b" in pulse_feed_timezone_contract
    assert "visible native horizontal scrollbar" in pulse_feed_timezone_contract
    assert "model-colored left edge" in pulse_feed_timezone_contract
    assert "only the local row draws a baseline" in pulse_feed_timezone_contract
    assert "retain odd-hour hashes only for local time" in pulse_feed_timezone_contract
    assert "DeepSeek, Qwen, MiniMax" in pulse_feed_timezone_contract
    assert "America/Los_Angeles" in pulse_feed_timezone_contract
    assert "Asia/Shanghai" in pulse_feed_timezone_contract
    assert "fixed-width follower lead column" in pulse_feed_timezone_contract
    assert "account display name" in pulse_feed_timezone_contract
    assert "current hosted staging appearance" in pulse_feed_timezone_contract.lower()
    assert "exact staged candidate SHA" in pulse_feed_timezone_contract

    cyber_quan_contract = (REPO_ROOT / CYBER_QUAN_CONTRACT).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in cyber_quan_contract
    assert "icon-only delta" in cyber_quan_contract
    assert "9a5fd90add8e5d60baf87796054b0211fbb94d9ad92e952fc5133465eb9da658" in cyber_quan_contract
    assert "exactly these 32 symbols" in cyber_quan_contract
    assert "mark A (`mark-quiet`)" in cyber_quan_contract
    assert "physical iPhone" in cyber_quan_contract

    feed_headline_contract = (
        REPO_ROOT / FEED_HEADLINE_CONTRACT
    ).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in feed_headline_contract
    assert "at most nine lines on mobile" in feed_headline_contract
    assert "schema-3 secondary starts hidden" in feed_headline_contract
    assert "rough credential-badge symbol" in feed_headline_contract

    hover_freeze_contract = (
        REPO_ROOT / HOVER_FREEZE_CONTRACT
    ).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in hover_freeze_contract
    assert "e2d48a2c642ccbf03407a7a1ecfd36161ab0f018" in hover_freeze_contract
    assert "exact half-open five-minute bucket" in hover_freeze_contract
    assert "browser-local datetime" in hover_freeze_contract
    assert "preserves the active brand selection" in hover_freeze_contract
    assert "7-, 30-, and 365-day charts" in hover_freeze_contract

    feed_inspection_contract = (
        REPO_ROOT / FEED_INSPECTION_CONTRACT
    ).read_text(encoding="utf-8")
    assert "Approval status: APPROVED" in feed_inspection_contract
    assert "staging delivery only" in feed_inspection_contract
    assert "only control that opens the exact original post" in feed_inspection_contract
    assert "no cumulative 500-row ceiling" in feed_inspection_contract
    assert "stroke `4 / 3`" in feed_inspection_contract
