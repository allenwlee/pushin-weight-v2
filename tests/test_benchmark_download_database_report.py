import json
import re
from io import StringIO

import pytest
from django.core.management import call_command

from core.benchmark_metric_series import build_comparison
from tests.test_benchmark_pulse_views import comparison

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def test_database_report_keeps_shared_points_missingness_and_contract(tmp_path):
    contract = comparison()
    output = tmp_path / "comparison.html"
    call_command(
        "render_benchmark_report",
        contract=str(contract.pk),
        preset="fixture",
        end_date="2026-09-12",
        output=str(output),
        stdout=StringIO(),
    )
    html = output.read_text()
    match = re.search(
        r'<script[^>]*id="report-data"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    assert match is not None
    report = json.loads(match.group(1))
    shared = build_comparison(contract, "fixture", end_date="2026-09-12")
    assert report["database_comparison"]["lines"] == shared["lines"]
    assert report["database_comparison"]["contract_id"] == str(contract.pk)
    assert [p["hf"]["value"] for p in report["series"][0]["points"]] == [None] * 3
    assert all(p["posts"] is None for p in report["series"][0]["points"])
    assert report["synthetic"] is False
    assert "unknown" in report["statuses"][0]["status"]


def test_report_preserves_large_counts_and_rejects_ambiguous_panels():
    from copy import deepcopy

    from core.benchmark_metric_report import report_from_comparison

    data = build_comparison(comparison(), "fixture", end_date="2026-09-12")
    line = data["lines"][0]
    line["source"] = "openrouter"
    line["metric_key"] = "total_tokens"
    line["points"][0].update(raw_value="9007199254740993000000", coverage="observed")
    report = report_from_comparison(data)
    assert (
        report["series"][0]["points"][0]["openrouter"]["value"]
        == "9007199254740993000000"
    )
    assert report["series"][0]["points"][1]["openrouter"]["value"] is None
    assert report["database_comparison"] == data
    data["lines"].append(deepcopy(line))
    with pytest.raises(ValueError, match="one openrouter line"):
        report_from_comparison(data)
