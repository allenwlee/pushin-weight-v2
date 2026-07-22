# {{AGENT_ATTRIBUTION}}
"""Tests for the `hf-products` CLI subcommand (arg wiring + dispatch)."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest

from x_monitor import hf_products
from x_monitor.__main__ import build_parser, cmd_hf_products


def test_hf_products_subcommand_registered():
    """The hf-products subparser parses flags and wires func=cmd_hf_products."""
    args = build_parser().parse_args(
        ["hf-products", "--companies", "deepseek,glm", "--max", "5", "--dry-run"]
    )
    assert args.func is cmd_hf_products
    assert args.companies == "deepseek,glm"
    assert args.max == 5
    assert args.dry_run is True


def test_hf_products_subcommand_defaults():
    args = build_parser().parse_args(["hf-products"])
    assert args.func is cmd_hf_products
    assert args.companies is None
    assert args.brand is None
    assert args.max is None
    assert args.dry_run is False


def _stub_collect_all(captured):
    def _fake(store, *, companies=None, client=None, max=None, dry_run=False):
        captured["companies"] = companies
        captured["dry_run"] = dry_run
        captured["max"] = max
        captured["client_is_none"] = client is None
        return [{"brand_id": "deepseek", "ok": True, "upserted": 3}]

    return _fake


def test_cmd_hf_products_parses_companies(monkeypatch, tmp_path, capsys):
    captured: dict = {}
    monkeypatch.setattr(hf_products, "collect_all", _stub_collect_all(captured))

    args = Namespace(companies="deepseek,glm", brand=None, max=None, dry_run=True)
    rc = cmd_hf_products(args, {"db": tmp_path / "x.db"})

    assert rc == 0
    assert captured["companies"] == ["deepseek", "glm"]
    assert captured["dry_run"] is True
    out = json.loads(capsys.readouterr().out)
    assert out == [{"brand_id": "deepseek", "ok": True, "upserted": 3}]


def test_cmd_hf_products_brand_flag(monkeypatch, tmp_path):
    captured: dict = {}
    monkeypatch.setattr(hf_products, "collect_all", _stub_collect_all(captured))

    args = Namespace(companies=None, brand="qwen", max=None, dry_run=False)
    rc = cmd_hf_products(args, {"db": tmp_path / "x.db"})

    assert rc == 0
    assert captured["companies"] == ["qwen"]
    assert captured["dry_run"] is False


def test_cmd_hf_products_no_filter_defaults_all(monkeypatch, tmp_path):
    captured: dict = {}
    monkeypatch.setattr(hf_products, "collect_all", _stub_collect_all(captured))

    args = Namespace(companies=None, brand=None, max=2, dry_run=False)
    rc = cmd_hf_products(args, {"db": tmp_path / "x.db"})

    assert rc == 0
    assert captured["companies"] is None  # all enabled brands
    assert captured["max"] == 2
