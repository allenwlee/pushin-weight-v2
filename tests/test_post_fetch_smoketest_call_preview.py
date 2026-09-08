# {{AGENT_ATTRIBUTION}}
"""Tests for the U3 --include-call-preview smoketest flag.

Plan: docs/plans/2026-07-11-002-feat-call-b-revival-via-x-query-specs-plan.md
(Unit U3).
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from pathlib import Path

import pytest

import scripts.post_fetch_smoketest as sm

# ----------------------------------------------------------------------
# 1. --include-call-preview flag exists and is parsed.
# ----------------------------------------------------------------------


def test_include_call_preview_flag_parsed() -> None:
    """`--include-call-preview` parses without error; default off."""
    args = sm._parse_args([])
    assert args.include_call_preview is False

    args = sm._parse_args(["--include-call-preview"])
    assert args.include_call_preview is True


# ----------------------------------------------------------------------
# 2. _print_call_preview prints the current configured call set.
# ----------------------------------------------------------------------


def test_print_call_preview_emits_current_calls() -> None:
    """The helper prints 7 call lines — one per spec in the live
    `x_query_specs:` plus the synthesized Call A. Each line includes
    the call_id, query string, and char count."""
    buf = io.StringIO()
    with redirect_stderr(buf):
        sm._print_call_preview()
    text = buf.getvalue()
    assert "CALL PREVIEW" in text
    # Seven CALL lines (one per spec + Call A). Match "CALL <ID>:"
    # so the header line "CALL PREVIEW ..." isn't counted.
    call_lines = [
        line for line in text.splitlines()
        if line.startswith("CALL ") and line.split()[1].endswith(":")
    ]
    assert len(call_lines) == 7
    # Each expected call_id present.
    for cid in ("A", "B1", "B2", "B3", "C1", "C2", "C3"):
        assert any(line.startswith(f"CALL {cid}:") for line in call_lines), (
            f"missing {cid} in preview"
        )


# ----------------------------------------------------------------------
# 3. Every previewed call's query_length is under 512 chars.
# ----------------------------------------------------------------------


def test_print_call_preview_all_calls_under_cap() -> None:
    """X advanced-search cap is 512 chars; every emitted call must
    fit. The B1/B2/B3 specs use the `is_primary=1` subset (2-4 tokens
    per brand) to stay under cap; this test guards the cap on the
    live config."""
    buf = io.StringIO()
    with redirect_stderr(buf):
        sm._print_call_preview()
    text = buf.getvalue()
    for line in text.splitlines():
        # Match "CALL <ID>:" so the header line isn't counted.
        if not (line.startswith("CALL ") and line.split()[1].endswith(":")):
            continue
        # Format: "CALL <id>: <query> | <N> chars"
        try:
            n = int(line.rsplit("|", 1)[1].strip().split()[0])
        except (IndexError, ValueError):
            pytest.fail(f"could not parse char count from line: {line!r}")
        assert n < 512, (
            f"call {line[:30]!r}... is {n} chars — over the 512-char cap"
        )


# ----------------------------------------------------------------------
# 4. --source=fixture with --include-call-preview prints the preview
#    AND continues into the pipeline (preview is a side
#    channel, not a replacement).
# ----------------------------------------------------------------------


def test_fixture_with_include_call_preview_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The preview prints and fixture dispatch still reaches the pipeline."""
    fixture = tmp_path / "post.jsonl"
    fixture.write_text('{"tweet_id":"1","text":"test"}\n', encoding="utf-8")
    calls: list[object] = []
    monkeypatch.setattr(sm, "_print_call_preview", lambda: calls.append("preview"))
    monkeypatch.setattr(
        sm,
        "_run_pipeline",
        lambda posts, _rows, args: calls.append(
            ("pipeline", args.source, [post["tweet_id"] for post in posts])
        )
        or 0,
    )

    rc = sm.main([
        "--source", "fixture",
        "--fixture", str(fixture),
        "--include-call-preview",
        "--limit", "1",
    ])
    assert rc == 0
    assert calls == ["preview", ("pipeline", "fixture", ["1"])]


# ----------------------------------------------------------------------
# 5. Existing smoketest output is unchanged when --include-call-preview
#    is OMITTED — the preview block does not fire.
# ----------------------------------------------------------------------


def test_no_preview_without_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default fixture dispatch reaches the pipeline without a preview."""
    fixture = tmp_path / "post.jsonl"
    fixture.write_text('{"tweet_id":"1","text":"test"}\n', encoding="utf-8")
    pipeline_calls: list[str] = []
    monkeypatch.setattr(
        sm,
        "_print_call_preview",
        lambda: pytest.fail("preview must remain opt-in"),
    )
    monkeypatch.setattr(
        sm,
        "_run_pipeline",
        lambda _posts, _rows, args: pipeline_calls.append(args.source) or 0,
    )

    rc = sm.main([
        "--source", "fixture",
        "--fixture", str(fixture),
    ])
    assert rc == 0
    assert pipeline_calls == ["fixture"]


# ----------------------------------------------------------------------
# 6. _print_call_preview handles missing DB gracefully — wide-net specs
#    render with empty parens (defensive branch in _build_query).
# ----------------------------------------------------------------------


def test_print_call_preview_handles_missing_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `data/x_monitoring.db` doesn't exist, the helper still
    prints the call set; wide-net specs render with empty brand
    groups (their parens are `(empty)` per the defensive branch)."""
    # Simulate missing DB by monkeypatching the Store class the
    # helper imports. The helper does `from x_monitor.store import
    # Store` lazily — patch on the smoketest module's namespace.
    class _MissingDBStore:
        def __init__(self, *args, **kwargs):
            raise FileNotFoundError("simulated missing DB")

        def read_primary_brand_keywords(self):
            return {}

    # Inject a fake Store into the smoketest module's globals so the
    # helper's lazy `from x_monitor.store import Store` resolves to it.
    monkeypatch.setattr(sm, "Store", _MissingDBStore, raising=False)

    buf = io.StringIO()
    with redirect_stderr(buf):
        sm._print_call_preview()
    text = buf.getvalue()
    # All 7 calls still print (CALL <id>: lines, not the header).
    call_lines = [
        line for line in text.splitlines()
        if line.startswith("CALL ") and line.split()[1].endswith(":")
    ]
    assert len(call_lines) == 7
    # Wide-net specs (B1/B2/B3) show empty brand groups — but each
    # still emits a syntactically valid query with "(empty)" markers
    # for the missing brand groups.
    for cid in ("B1", "B2", "B3"):
        for line in call_lines:
            if line.startswith(f"CALL {cid}:"):
                assert "(empty)" in line or "OR" in line, (
                    f"{cid} should render with at least one brand-paren"
                )


# ----------------------------------------------------------------------
# 7. Live config has exactly 6 x_query_specs entries; the planner
#    synthesizes the seventh (Call A).
# ----------------------------------------------------------------------


def test_live_config_has_current_x_query_specs() -> None:
    """The preview inventory matches the checked-in active policy."""
    from x_monitor.config import load_config
    cfg = load_config(Path("config.yaml"))
    assert len(cfg.x_query_specs) == 6
    call_ids = {s.call_id for s in cfg.x_query_specs}
    assert call_ids == {"C1", "C2", "C3", "B1", "B2", "B3"}

    by_id = {s.call_id: s for s in cfg.x_query_specs}
    assert by_id["B1"].is_wide_net is True
    assert len(by_id["B1"].wide_net_brands) >= 2
    assert by_id["B1"].brands == {}

    # B2/B3 are handle-only discovery specs in the current policy.
    for call_id in ("B2", "B3"):
        assert by_id[call_id].is_wide_net is False
        assert len(by_id[call_id].handles) >= 2
        assert by_id[call_id].brands == {}
