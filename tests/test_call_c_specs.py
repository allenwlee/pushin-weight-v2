"""U5 tests: Call C spec shape and the probe helper.

Plan: docs/plans/2026-07-02-001-feat-configurable-search-limits-and-backlog-plan.md
Unit 5 of 6 (U5 — Review Call C narrow AND-filter).
Plus: C2 spec tests for ERNIE (added 2026-07-09 as the follow-up
to plan 2026-06-25-001 §"Implementation Units" — the dedup of A/B
brands that already existed in C).

Scope:
- Verify `config.yaml` `call_c_specs:` parses cleanly and the C1
  spec is well-formed (5 covered brands, min_faves=0 preserved,
  query string stays under 512 chars).
- Verify the C2 spec for ERNIE is well-formed (single-brand, min_faves=0,
  query string stays under 512 chars, co-occurrence includes the
  Baidu/文心 disambiguators).
- Verify the probe script exits with a clean sentinel when no API
  key is present (so the script is safe to commit + run by anyone).
- Verify the probe script imports parse cleanly when an API key
  is set in env (mark live).

The live "n_results ≥ 1 relevant post" probe is intentionally NOT
covered here — that requires real TwitterAPI.io credentials and
network access. The probe script itself is the operator's path
to capture that data, and the operator commits the probe output
alongside any spec change.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from x_monitor.config import KNOWN_MODELS, load_config


REPO_ROOT = Path(__file__).resolve().parent.parent
CFG_PATH = REPO_ROOT / "config.yaml"
PROBE_SCRIPT = REPO_ROOT / "scripts" / "probe_call_c_spec.py"


# --- spec loads cleanly ---------------------------------------------


def test_call_c_specs_load_from_repo_config():
    """config.yaml's call_c_specs parses cleanly via the existing loader."""
    cfg = load_config(CFG_PATH)
    assert cfg.call_c_specs, (
        "call_c_specs should be non-empty in the repo config; got []"
    )


def test_c1_spec_covers_five_brands():
    """The C1 spec covers mimo, moonshot_kimi, yi, upstage, llama —
    these are the brands whose tokens collide with common nouns and so
    need the AND-filter. Other brands (deepseek, glm, ...) have unique
    enough tokens and rely on Call B alone."""
    cfg = load_config(CFG_PATH)
    c1 = next(
        (s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C1"),
        None,
    )
    assert c1 is not None, (
        "no spec with call_id='C1' in call_c_specs; cannot verify U5 scope"
    )
    covered = set(c1.brands.keys())
    expected = {
        "mimo", "moonshot_kimi", "yi", "upstage", "llama",
    }
    assert covered == expected, (
        f"C1 spec covers {covered}; expected exactly {expected}"
    )


def test_c1_spec_brands_are_known_models():
    """Each brand_id in the C1 spec is a brand KNOWN_MODELS recognizes."""
    cfg = load_config(CFG_PATH)
    c1 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C1"
    )
    for brand_id in c1.brands:
        assert brand_id in KNOWN_MODELS, (
            f"C1 spec brand {brand_id!r} not in KNOWN_MODELS; "
            "the post-fetch attribute_to_brands regex would drop these"
        )


def test_c1_spec_min_faves_locks_at_zero():
    """The plan requires min_faves=0 be preserved across any change.
    Pin the value so any future loosening shape doesn't accidentally
    tighten it."""
    cfg = load_config(CFG_PATH)
    c1 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C1"
    )
    assert c1.min_faves == 0, (
        f"C1 min_faves must remain 0 (per plan: don't accidentally tighten); "
        f"got {c1.min_faves}"
    )


def test_c1_spec_query_under_512_chars():
    """Build the C1 query and verify it's under the X advanced-search
    512-char cap. Any loosening that adds terms must keep us under."""
    cfg = load_config(CFG_PATH)
    c1 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C1"
    )
    from x_monitor.query_plan import _build_call_c_query
    q = _build_call_c_query(c1)
    assert len(q) < 512, (
        f"C1 query {len(q)} chars exceeds the 512-char X cap: "
        f"{q[:200]!r}..."
    )


def test_c1_spec_has_co_occurrence_terms():
    """U5 is about whether the co-occurrence paren is too narrow —
    pin a lower bound (>=5 terms) so an accidental wipe-to-empty
    is caught. The probe script is the operator's path to discover
    whether the spec needs to be loosened further."""
    cfg = load_config(CFG_PATH)
    c1 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C1"
    )
    assert len(c1.co_occurrence) >= 5, (
        f"C1 co_occurrence list has {len(c1.co_occurrence)} terms; "
        "a value below 5 means the AND-filter is exceedingly narrow; "
        "U5's whole purpose is to revisit this — pin here so a wipe "
        "is caught at CI time, not at runtime."
    )


# --- probe script ----------------------------------------------------


def test_probe_script_handles_missing_creds(tmp_path, monkeypatch):
    """Without TWITTER_API_KEY/TWITTERAPI_IO_KEY the probe prints a
    clean sentinel and exits 0 — so it's safe to commit + run from
    any developer's machine."""
    # Ensure no API keys are visible.
    monkeypatch.delenv("TWITTER_API_KEY", raising=False)
    monkeypatch.delenv("TWITTERAPI_IO_KEY", raising=False)

    proc = subprocess.run(
        [sys.executable, str(PROBE_SCRIPT)],
        capture_output=True, text=True, check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"probe script failed without API key: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "TWITTER_API_KEY" in proc.stdout, (
        f"missing creds sentinel not printed; got {proc.stdout!r}"
    )


def test_probe_script_imports_cleanly():
    """The probe imports x_monitor.query_plan and x_monitor.apify on
    live path; even with no creds, those imports must succeed."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, '.'); "
         "from scripts.probe_call_c_spec import _build_query, _have_api_creds; "
         "print(_have_api_creds())"],
        capture_output=True, text=True, check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"probe script imports failed: "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


# --- live probe: SKIPPED without credentials -----------------------


@pytest.mark.skipif(
    not os.environ.get("TWITTER_API_KEY")
    and not os.environ.get("TWITTERAPI_IO_KEY"),
    reason="live probe requires TWITTER_API_KEY or TWITTERAPI_IO_KEY",
)
def test_c1_spec_returns_at_least_one_relevant_post():
    """Live probe: the chosen spec must return ≥1 result and at least
    one of the first 5 results must attribute to a covered brand.

    Skipped unless API credentials are present in the env. When the
    operator runs this locally, they capture the output, attach it
    as a code review artifact, and update config.yaml only when this
    test (run with creds) passes.
    """
    proc = subprocess.run(
        [sys.executable, str(PROBE_SCRIPT), "--call-id", "C1"],
        capture_output=True, text=True, check=False,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"probe failed: stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    assert "n_results: 0" not in proc.stdout, (
        f"live probe returned 0 results: {proc.stdout!r}"
    )


# --- spec regression guard ------------------------------------------


def test_call_c_specs_call_ids_are_unique_and_known():
    """Every spec must have a unique non-empty call_id drawn from {C1, C2, ...}.

    Plan 2026-07-09-001 follow-up added a C2 spec for ERNIE. Future
    additions should follow the C1/C2/... convention. An empty or
    duplicate call_id is a planning bug — the auto-assign path is
    fragile when specs are loaded from yaml in arbitrary order.
    """
    cfg = load_config(CFG_PATH)
    call_ids = [getattr(s, "call_id", "") for s in cfg.call_c_specs]
    assert all(call_ids), (
        f"empty call_id in call_c_specs: {call_ids}"
    )
    assert len(set(call_ids)) == len(call_ids), (
        f"duplicate call_ids in call_c_specs: {call_ids}"
    )
    # Convention: call_ids match C<N> pattern
    import re
    for cid in call_ids:
        assert re.fullmatch(r"C\d+", cid), (
            f"call_id {cid!r} does not match C<N> convention"
        )


# --- C2 spec for ERNIE ----------------------------------------------


def test_c2_spec_exists_and_covers_ernie():
    """The C2 spec for ERNIE was added on 2026-07-09 as the follow-up
    to plan 2026-06-25-001 §"Implementation Units" (the dedup of A/B
    brands that already existed in C). C1 had only 7 chars of headroom
    so a separate spec was needed.
    """
    cfg = load_config(CFG_PATH)
    c2 = next(
        (s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C2"),
        None,
    )
    assert c2 is not None, (
        "no spec with call_id='C2' in call_c_specs; the 2026-07-09 "
        "follow-up to plan 2026-06-25-001 §\"Implementation Units\" "
        "should have added it"
    )
    assert set(c2.brands.keys()) == {"ernie"}, (
        f"C2 spec covers {set(c2.brands.keys())}; expected exactly {{'ernie'}}"
    )


def test_c2_spec_brands_are_known_models():
    """ERNIE must be a brand KNOWN_MODELS recognizes."""
    cfg = load_config(CFG_PATH)
    c2 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C2"
    )
    for brand_id in c2.brands:
        assert brand_id in KNOWN_MODELS, (
            f"C2 spec brand {brand_id!r} not in KNOWN_MODELS"
        )


def test_c2_spec_min_faves_locks_at_zero():
    """C2 follows C1's min_faves=0 contract."""
    cfg = load_config(CFG_PATH)
    c2 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C2"
    )
    assert c2.min_faves == 0, (
        f"C2 min_faves must remain 0 (mirroring C1); got {c2.min_faves}"
    )


def test_c2_spec_query_under_512_chars():
    """C2's emitted query must be under the 512-char X advanced-search cap."""
    cfg = load_config(CFG_PATH)
    c2 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C2"
    )
    from x_monitor.query_plan import _build_call_c_query
    q = _build_call_c_query(c2)
    assert len(q) < 512, (
        f"C2 query {len(q)} chars exceeds the 512-char X cap: "
        f"{q[:200]!r}..."
    )


def test_c2_spec_has_co_occurrence_terms():
    """C2 needs co-occurrence terms to filter Sesame Street + Bert noise."""
    cfg = load_config(CFG_PATH)
    c2 = next(
        s for s in cfg.call_c_specs if getattr(s, "call_id", "") == "C2"
    )
    assert len(c2.co_occurrence) >= 5, (
        f"C2 co_occurrence list has {len(c2.co_occurrence)} terms; "
        "minimum 5 to carry the AI/LLM/dev AND-filter load."
    )
    # The Baidu + 文心 disambiguators must be present (they're what
    # separates Sesame Street ERNIE from Baidu ERNIE).
    assert "baidu" in c2.co_occurrence, (
        "C2 co_occurrence must include 'baidu' to disambiguate from Sesame Street"
    )
    assert "文心" in c2.co_occurrence, (
        "C2 co_occurrence must include '文心' to disambiguate the Chinese token"
    )