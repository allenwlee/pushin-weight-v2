from copy import deepcopy

import pytest

from scripts.benchmark_download_collector.collect import contract, load_snapshots
from scripts.benchmark_download_collector.demo import demo
from scripts.benchmark_download_collector.report import render_report
from scripts.benchmark_download_collector.series import build_report


@pytest.fixture
def snapshots(tmp_path):
    demo(tmp_path / "demo")
    return load_snapshots(tmp_path / "demo")


def test_daily_values_units_gaps_and_replay(snapshots):
    result = build_report(snapshots + snapshots, "2026-09-21", "2026-10-04")
    alpha, beta = result["series"]
    assert alpha["points"][0]["posts"] == 30
    assert alpha["points"][0]["hf"]["value"] == 140000
    assert alpha["points"][0]["openrouter"]["value"] == "13000000"
    assert alpha["points"][0]["openrouter"]["other_tokens"] == "43000000"
    assert alpha["points"][0]["openrouter"]["unmapped_models"] == 1
    assert alpha["points"][6]["hf"]["value"] is None
    assert alpha["points"][6]["hf"]["successful"] == 0
    assert all(p["hf"] is None for p in beta["points"])
    assert alpha["points"][0]["arena"]["value"] == 1370
    assert alpha["points"][4]["arena"]["value"] == 1370
    assert alpha["points"][5]["arena"]["value"] == 1395
    assert alpha["points"][5]["arena"]["model"] == "alpha-1-thinking"
    assert result["unresolved"]["openrouter"] == ["unresolved/new-model"]


def test_arena_uses_full_publication_population_and_never_backdates(snapshots):
    for snapshot in snapshots[5:]:
        snapshot["sources"]["arena"]["rows"] = [
            r
            for r in snapshot["sources"]["arena"]["rows"]
            if r["model_name"] != "alpha-1-thinking"
        ]
    points = build_report(snapshots, "2026-09-20", "2026-10-04")["series"][0]["points"]
    assert points[0]["posts"] is None and points[0]["arena"] is None
    assert points[5]["arena"]["value"] == 1370
    assert points[6]["arena"] is None


def test_missing_openrouter_model_is_not_zero_and_variants_only_count_if_mapped(
    snapshots,
):
    snapshot = snapshots[0]
    rows = snapshot["sources"]["openrouter"]["rows"]
    rows[:] = [r for r in rows if r["model_permaslug"] != "example/alpha-1"]
    rows.append(
        {
            "date": "2026-09-21",
            "model_permaslug": "example/alpha-1:free",
            "total_tokens": "9999",
        }
    )
    report = build_report([snapshot], "2026-09-21", "2026-09-21")
    assert report["series"][0]["points"][0]["openrouter"]["value"] is None
    assert "example/alpha-1:free" in report["unresolved"]["openrouter"]
    assert report["series"][1]["points"][0]["openrouter"]["value"] == "17000000"


def test_latest_successful_daily_hf_snapshot_wins_without_summing_retries(snapshots):
    original = snapshots[0]
    changed = deepcopy(original)
    changed["observed_at"] = "2026-09-21T14:00:00+00:00"
    changed["sources"]["hf"]["rows"][0]["raw"]["downloads"] = 170000
    changed["sources"]["hf"]["rows"][0]["observed_at"] = changed["observed_at"]
    failed = deepcopy(changed)
    failed["observed_at"] = "2026-09-21T15:00:00+00:00"
    failed["sources"]["hf"]["status"] = "partial"
    failed["sources"]["hf"]["rows"][0]["status"] = "error"
    report = build_report([failed, changed, original], "2026-09-21", "2026-09-21")
    assert report["series"][0]["points"][0]["hf"]["value"] == 170000
    assert any(s["status"] == "partial" for s in report["statuses"])


@pytest.mark.parametrize("change", ["taxonomy", "mapping", "methodology", "tampering"])
def test_report_refuses_identity_or_methodology_drift(snapshots, change):
    if change == "taxonomy":
        snapshots[-1]["catalog"] = deepcopy(snapshots[-1]["catalog"])
        snapshots[-1]["catalog"]["products"][0]["brand_id"] = "beta"
        snapshots[-1].update(
            contract(snapshots[-1]["catalog"], snapshots[-1]["mapping"])
        )
    elif change == "mapping":
        snapshots[-1]["mapping"] = deepcopy(snapshots[-1]["mapping"])
        snapshots[-1]["mapping"]["mappings"].pop()
        snapshots[-1].update(
            contract(snapshots[-1]["catalog"], snapshots[-1]["mapping"])
        )
    elif change == "methodology":
        snapshots[-1]["sources"]["arena"]["score_contract"] = "new-method"
    else:
        snapshots[-1]["mapping_digest"] = "corrupt"
    with pytest.raises(ValueError):
        build_report(snapshots, "2026-09-21", "2026-10-04")


def test_html_escapes_provider_and_brand_text(snapshots, tmp_path):
    report = build_report(snapshots, "2026-09-21", "2026-10-04")
    report["series"][0]["label"] = '</script><script>alert("bad")</script>'
    output = tmp_path / "report.html"
    render_report(report, output)
    html = output.read_text()
    assert '<script>alert("bad")' not in html
    assert r"\u003c/script\u003e" in html
    assert "__REPORT_DATA__" not in html


def test_exact_large_token_total_survives_report(snapshots):
    snapshots[0]["sources"]["openrouter"]["rows"][0]["total_tokens"] = (
        "9007199254740993"
    )
    point = build_report(snapshots[:1], "2026-09-21", "2026-09-21")["series"][0][
        "points"
    ][0]
    assert point["openrouter"]["value"] == "9007199254740993"


def test_later_collection_cannot_replace_newer_openrouter_revision(snapshots):
    original = snapshots[0]
    stale = deepcopy(original)
    stale["observed_at"] = "2026-09-23T12:00:00+00:00"
    stale["sources"]["openrouter"]["as_of"] = "2026-09-20T12:00:00+00:00"
    stale["sources"]["openrouter"]["rows"][0]["total_tokens"] = "1"
    point = build_report([stale, original], "2026-09-21", "2026-09-21")["series"][0][
        "points"
    ][0]
    assert point["openrouter"]["value"] == "13000000"
    assert point["openrouter"]["as_of"] == original["sources"]["openrouter"]["as_of"]


def test_later_collection_cannot_replace_newer_post_export(snapshots):
    original = snapshots[0]
    stale = deepcopy(original)
    stale["observed_at"] = "2026-10-06T12:00:00+00:00"
    stale["catalog"]["exported_at"] = "2026-09-20T12:00:00+00:00"
    stale["catalog"]["posts"]["counts"] = []
    point = build_report([stale, original], "2026-09-21", "2026-09-21")["series"][0][
        "points"
    ][0]
    assert point["posts"] == 30


def test_newer_post_export_can_correct_counts_within_its_window(snapshots):
    original = snapshots[0]
    correction = deepcopy(original)
    correction["observed_at"] = "2026-10-06T12:00:00+00:00"
    correction["catalog"]["exported_at"] = correction["observed_at"]
    correction["catalog"]["posts"].update(
        start_date="2026-09-21", end_date="2026-09-21", counts=[]
    )
    points = build_report([original, correction], "2026-09-21", "2026-09-22")["series"][
        0
    ]["points"]
    assert points[0]["posts"] == 0
    assert points[1]["posts"] == 50


def test_demo_data_cannot_lose_its_warning_by_mixing_with_live_snapshots(snapshots):
    live = deepcopy(snapshots[0])
    live.pop("synthetic")
    with pytest.raises(ValueError, match="synthetic and live"):
        build_report([snapshots[0], live], "2026-09-21", "2026-09-21")
