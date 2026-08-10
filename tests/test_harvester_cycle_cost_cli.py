"""CLI tests for scripts.harvest_cost (plan 2026-08-10-003 U4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.harvest_cost import cli  # noqa: E402


def _fixture_cycle(run_id: str, finished: str, b1: int, metrics: int) -> dict:
    return {
        "run_id": run_id,
        "finished_at": finished,
        "calls": [
            {"call_id": "A", "n_results": 1, "status": "completed"},
            {"call_id": "B1", "n_results": b1, "status": "completed"},
        ],
        "metrics_refresh": {"n_due": metrics, "n_refreshed": metrics, "n_missing": 0},
        "totals": {
            "n_results": 1 + b1,
            "n_inserted": 1 + b1,
            "n_calls_run": 2,
        },
    }


def test_cli_ae2_override_tweet_credits(tmp_path: Path, capsys):
    run = tmp_path / "c.json"
    run.write_text(
        json.dumps(_fixture_cycle("r1", "2026-08-10T06:37:01+00:00", 10, 0)),
        encoding="utf-8",
    )
    code = cli.main(
        [
            "--input",
            str(run),
            "--tweet-credits",
            "20",
            "--credits-per-usd",
            "100000",
            "--call-floor-credits",
            "15",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    # A=1 + B1=10 = 11 * 20 = 220
    assert "**220**" in out or "220" in out


def test_cli_ae3_multi_cycle_window(tmp_path: Path, capsys):
    runs = tmp_path / "runs"
    runs.mkdir()
    for rid, fin, b1 in (
        ("c1", "2026-08-10T06:00:00+00:00", 10),
        ("c2", "2026-08-10T06:15:00+00:00", 20),
        ("c3", "2026-08-10T06:30:00+00:00", 30),
    ):
        (runs / f"{rid}.json").write_text(
            json.dumps(_fixture_cycle(rid, fin, b1, 0)),
            encoding="utf-8",
        )
    code = cli.main(
        [
            "--runs-dir",
            str(runs),
            "--since",
            "2026-08-10T05:00:00+00:00",
            "--until",
            "2026-08-10T07:00:00+00:00",
            "--format",
            "json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_cycles"] == 3
    ids = {c["run_id"] for c in payload["cycles"]}
    assert ids == {"c1", "c2", "c3"}


def test_cli_latest(tmp_path: Path, capsys):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "old.json").write_text(
        json.dumps(_fixture_cycle("old", "2026-08-10T05:00:00+00:00", 1, 0)),
        encoding="utf-8",
    )
    (runs / "new.json").write_text(
        json.dumps(_fixture_cycle("new", "2026-08-10T06:00:00+00:00", 2, 0)),
        encoding="utf-8",
    )
    code = cli.main(["--runs-dir", str(runs), "--latest", "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_cycles"] == 1
    assert payload["cycles"][0]["run_id"] == "new"


def test_cli_empty_window_nonzero(tmp_path: Path):
    runs = tmp_path / "runs"
    runs.mkdir()
    code = cli.main(["--runs-dir", str(runs), "--latest"])
    assert code == 2


def test_cli_writes_out_file(tmp_path: Path):
    run = tmp_path / "c.json"
    run.write_text(
        json.dumps(_fixture_cycle("r1", "2026-08-10T06:37:01+00:00", 63, 174)),
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    code = cli.main(["--input", str(run), "--out", str(out)])
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "B1" in text
    assert "metrics_refresh" in text
    assert "945" in text
