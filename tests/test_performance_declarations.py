from __future__ import annotations

import copy
import json
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "fixtures/performance_assurance"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _semantic_body(declaration: dict) -> dict:
    body = copy.deepcopy(declaration)
    body.pop("base_origin")
    body.pop("asset_origins")
    for profile in body["profiles"]:
        profile.pop("destination_scope")
    return body


def test_staging_declaration_only_changes_deployment_scope() -> None:
    production = _load("declaration.json")
    staging = _load("declaration.staging.json")

    assert _semantic_body(staging) == _semantic_body(production)

    assert staging["base_origin"] == "https://pushinweight-staging-web.onrender.com"
    assert staging["asset_origins"] == production["asset_origins"]
    assert {profile["destination_scope"] for profile in staging["profiles"]} == {"remote"}
