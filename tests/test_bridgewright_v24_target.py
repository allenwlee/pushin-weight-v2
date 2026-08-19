"""Regression pin for the owner-approved, partial V24 Bridgewright target."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
V24_MOCKUP = "docs/ideation/mockups/v24.html"
V24_CONTRACT = "docs/reference/2026-08-19-132714-v24-bridgewright-target.md"
PRODUCTION_CONTRACT = "docs/reference/2026-08-19-174833-production-filter-feed-bridgewright-target.md"


def test_bridgewright_uses_v24_and_its_partial_target_contract() -> None:
    manifest = yaml.safe_load((REPO_ROOT / "bridgewright.yaml").read_text())
    adapter = yaml.safe_load((REPO_ROOT / ".bridgewright/adapter.yaml").read_text())
    authorities = manifest["configuration"]["authorities"]

    assert authorities["approved_mockup"] == V24_MOCKUP
    assert authorities["last_approved_contract"] == PRODUCTION_CONTRACT
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
