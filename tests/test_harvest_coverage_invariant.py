"""Tests for harvest_preview + coverage invariant (U4).

Plan: docs/plans/2026-08-05-001-refactor-harvest-policy-3of5-plan.md
Unit U4 (R10, R11, R21).
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
import yaml

from x_monitor.harvest_policy import BrandPolicy, CoPack, HarvestPolicy
from x_monitor.harvest_preview import (
    CallPreview,
    CoveragePreview,
    HarvestPreviewReport,
    build_preview,
    coverage_invariant_holds,
    render_preview,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


# -------------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------------

def _write_yaml(path: Path, doc: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f)


def _make_policy(brands: dict[str, BrandPolicy], packs: list[CoPack] = ()) -> HarvestPolicy:
    return HarvestPolicy(brands=brands, co_packs=tuple(packs))


# -------------------------------------------------------------------------
# R10: preview produces call + coverage data
# -------------------------------------------------------------------------

def test_build_preview_returns_structured_report(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {
        "enabled_models": ["minimax", "moonshot_kimi", "exaone"],
        "x_monitor_list_id": "1234567890",
    })
    policy = _make_policy(
        brands={
            "minimax": BrandPolicy(
                nickname="minimax", paths=frozenset({"bare", "handle"}),
                tokens=("MiniMax", "MiniMaxAI"),
                handles=("MiniMax_AI",),
            ),
            "moonshot_kimi": BrandPolicy(
                nickname="moonshot_kimi", paths=frozenset({"co", "handle"}),
                tokens=("Kimi",), co=("llm", "model"),
                handles=("Kimi_Moonshot",),
                not_include=("f1",),
            ),
            "exaone": BrandPolicy(
                nickname="exaone", paths=frozenset({"none"}),
                notes="Temporarily opted out for legal review.",
            ),
        },
        packs=[CoPack(brand_nicknames=("moonshot_kimi",))],
    )
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        yaml.safe_dump({
            "brands": {
                "minimax": {"paths": ["bare", "handle"],
                            "tokens": ["MiniMax", "MiniMaxAI"],
                            "handles": ["MiniMax_AI"]},
                "moonshot_kimi": {"paths": ["co", "handle"],
                                  "tokens": ["Kimi"],
                                  "co": ["llm", "model"],
                                  "handles": ["Kimi_Moonshot"],
                                  "not_include": ["f1"]},
                "exaone": {"paths": ["none"],
                           "notes": "Temporarily opted out for legal review."},
            },
            "co_packs": [["moonshot_kimi"]],
        }, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    assert isinstance(report, HarvestPreviewReport)
    # A + B1 + C1 + B2 = 4 calls
    assert {c.call_id for c in report.calls} == {"A", "B1", "C1", "B2"}
    # All under cap
    for c in report.calls:
        assert c.length <= 512
        assert c.headroom == 512 - c.length


def test_render_preview_writes_table(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {
        "enabled_models": ["minimax"], "x_monitor_list_id": "1234567890",
    })
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        yaml.safe_dump({
            "brands": {"minimax": {"paths": ["bare"],
                                   "tokens": ["MiniMax"]}},
        }, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    buf = io.StringIO()
    render_preview(report, buf)
    out = buf.getvalue()
    assert "# harvest_preview" in out
    assert "## Calls" in out
    assert "## Coverage" in out
    assert "minimax" in out


# -------------------------------------------------------------------------
# R11 invariant: enabled brand must have ≥1 path or explicit none
# -------------------------------------------------------------------------

def test_invariant_passes_when_all_brands_covered(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"enabled_models": ["minimax"], "x_monitor_list_id": "1"})
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        yaml.safe_dump({"brands": {"minimax": {"paths": ["bare"],
                                               "tokens": ["MiniMax"]}}}, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    assert coverage_invariant_holds(report)


def test_invariant_fails_when_enabled_brand_lacks_paths(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"enabled_models": ["minimax", "ghost"], "x_monitor_list_id": "1"})
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        # ghost is enabled but not in policy -> invariant violation
        yaml.safe_dump({"brands": {"minimax": {"paths": ["bare"],
                                               "tokens": ["MiniMax"]}}}, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    assert not coverage_invariant_holds(report)
    assert "ghost" in report.unmapped_enabled
    assert any("ghost" in w for w in report.warnings)


def test_invariant_passes_when_brand_opted_out_with_reason(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"enabled_models": ["minimax", "exaone"], "x_monitor_list_id": "1"})
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        yaml.safe_dump({
            "brands": {
                "minimax": {"paths": ["bare"], "tokens": ["MiniMax"]},
                "exaone": {"paths": ["none"], "notes": "Legal review pending"},
            },
        }, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    assert coverage_invariant_holds(report)
    # No warning about exaone being silent (notes present)
    exaone_warns = [w for w in report.warnings if "exaone" in w]
    assert not exaone_warns


def test_invariant_warns_when_none_has_no_reason(tmp_path):
    """AE1 doc rule: explicit none must carry a reason in `notes:`."""
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"enabled_models": ["minimax", "exaone"], "x_monitor_list_id": "1"})
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        yaml.safe_dump({
            "brands": {
                "minimax": {"paths": ["bare"], "tokens": ["MiniMax"]},
                "exaone": {"paths": ["none"]},  # no notes
            },
        }, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    # Invariant still passes (explicit none is OK)
    assert coverage_invariant_holds(report)
    # But a warning is emitted
    assert any("exaone" in w and "notes" in w for w in report.warnings)


# -------------------------------------------------------------------------
# M8 / R21: preview must NOT make network calls
# -------------------------------------------------------------------------

def test_preview_has_no_network_imports():
    """Static guard: harvest_preview does not import requests / httpx / aiohttp.

    Even if a future maintainer adds a network call by accident, this
    test breaks the build. (M8 / R21 — preview is OFFLINE.)
    """
    import x_monitor.harvest_preview as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    forbidden = ["import requests", "import httpx", "import aiohttp",
                "from requests", "from httpx", "from aiohttp",
                "urllib.request", "urlopen"]
    for needle in forbidden:
        assert needle not in src, (
            f"harvest_preview must be OFFLINE (R21 / M8). "
            f"Found {needle!r} in source."
        )


def test_specs_from_policy_has_no_network_imports():
    """Same guard for specs_from_policy — also offline by construction."""
    import x_monitor.specs_from_policy as mod
    src = Path(mod.__file__).read_text(encoding="utf-8")
    forbidden = ["import requests", "import httpx", "import aiohttp",
                "from requests", "from httpx", "from aiohttp"]
    for needle in forbidden:
        assert needle not in src, (
            f"specs_from_policy must be OFFLINE. Found {needle!r} in source."
        )


# -------------------------------------------------------------------------
# R10: each planned call renders with headroom
# -------------------------------------------------------------------------

def test_each_call_reports_length_and_headroom(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"enabled_models": ["minimax", "moonshot_kimi"],
                      "x_monitor_list_id": "1"})
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        yaml.safe_dump({
            "brands": {
                "minimax": {"paths": ["bare", "handle"],
                            "tokens": ["MiniMax"], "handles": ["MiniMax_AI"]},
                "moonshot_kimi": {"paths": ["co"],
                                  "tokens": ["Kimi"], "co": ["llm", "model"]},
            },
            "co_packs": [["moonshot_kimi"]],
        }, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    for c in report.calls:
        assert isinstance(c, CallPreview)
        assert c.headroom == 512 - c.length
        assert 0 < c.length <= 512
        assert c.query  # non-empty


# -------------------------------------------------------------------------
# Coverage map captures multi-path brand on multiple call_ids
# -------------------------------------------------------------------------

def test_coverage_captures_multi_path_brand(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"enabled_models": ["minimax"], "x_monitor_list_id": "1"})
    pol_path = tmp_path / "harvest_policy.yaml"
    with pol_path.open("w") as f:
        yaml.safe_dump({
            "brands": {"minimax": {"paths": ["bare", "handle"],
                                   "tokens": ["MiniMax"],
                                   "handles": ["MiniMax_AI"]}},
        }, f)
    report = build_preview(config_path=cfg, policy_path=pol_path)
    by_nick = {c.nickname: c for c in report.coverage}
    m = by_nick["minimax"]
    # Multi-path: appears on B1 (bare) and B2 (handle)
    assert "B1" in m.call_ids and "B2" in m.call_ids
    assert not m.is_explicit_none


# -------------------------------------------------------------------------
# Fallback to x_query_specs when policy file is missing (pre-U5 mode)
# -------------------------------------------------------------------------

def test_falls_back_to_x_query_specs_when_policy_missing(tmp_path, monkeypatch):
    """Before U5 ships the policy file, preview still works against the
    live config.x_query_specs. After U5 cutover, this branch is removed."""
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {
        "enabled_models": ["minimax"],
        "x_monitor_list_id": "1",
        "x_query_specs": [
            {"call_id": "B1", "is_wide_net": True,
             "wide_net_brands": ["minimax"], "brands": {},
             "co_occurrence": [], "min_faves": 0,
             "handles": [], "not_include": []},
        ],
    })
    pol_path = tmp_path / "harvest_policy.yaml"  # does NOT exist
    report = build_preview(config_path=cfg, policy_path=pol_path)
    assert any("falling back" in w for w in report.warnings)
    # Coverage stays empty (no policy to map from)
    assert report.coverage == ()
    # But calls still render
    assert {c.call_id for c in report.calls} == {"A", "B1"}