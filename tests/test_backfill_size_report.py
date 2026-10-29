"""Offline tests for the OpenAI/Anthropic size report (plan U8, R14-R24).

Plan: docs/plans/2026-10-27-113859-ops-oai-anthropic-size-20261027-plan.md

Every test runs on synthetic rows shaped like the read-only SQL output, so no
database or provider is touched.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import backfill_size_report as report

ROOT = Path(__file__).resolve().parents[1]
XB_SQL = ROOT / "scripts" / "backfill_size_report_xbackfiller.sql"
PROD_SQL = ROOT / "scripts" / "backfill_size_report_production.sql"
FROZEN = ROOT / "docs" / "analysis" / "2026-10-27-215214-oai-anthropic-frozen-queries.json"

PRODUCTION_ROUTES = ("A", "B1", "B2", "B3", "C1", "C2", "C3", "C4")
NEW_ROUTES = ("A_OAI", "OAI_1", "OAI_2", "OAI_3", "B_OAI", "A_ANT", "ANT_1", "ANT_2", "ANT_3", "B_ANT")
START = 1_793_300_400  # an arbitrary 5-minute-aligned epoch
JOB = "0b5e3d1c-6f0e-4d6a-9f51-2f3f6c1b9a10"


def envelope(received, kept, exclusions=(), pages=1, request_id=None, raw_count=None):
    row = {
        "post_ids": list(kept),
        "received_post_ids": list(received),
        "exclusions": [
            {"post_id": pid, "appearance": index, "reason": reason}
            for index, (pid, reason) in enumerate(exclusions)
        ],
        "pages_received": pages,
        "raw_count": len(received) if raw_count is None else raw_count,
    }
    if request_id:
        row["prefetch_request_id"] = request_id
    return row


def scope(route, envelopes, run_id="run-1", slice_index=0, outcome="complete"):
    since = START + slice_index * 300
    return {
        "run_id": run_id,
        "scope_key": f"{route}:{since}:{since + 300}",
        "outcome": outcome,
        "execution_state": "complete",
        "coverage_state": "complete",
        "error_code": None,
        "envelopes": envelopes,
    }


def call(members, *, actual=None, reserved="0.010000", state="completed", stage="classification"):
    return {
        "stage": stage,
        "operation": None,
        "state": state,
        "member_post_ids": list(members),
        "reserved_usd": reserved,
        "actual_usd": actual,
    }


# R14 -----------------------------------------------------------------------


def test_post_fetched_by_two_routes_counts_once_in_total_and_in_both_route_rows():
    scopes = [
        scope("B1", [envelope(["p1", "p2"], ["p1"])]),
        scope("OAI_1", [envelope(["p1", "p3"], ["p1", "p3"])]),
    ]
    sets = report.route_post_sets(scopes)
    summary = report.collection_summary(sets, PRODUCTION_ROUTES, NEW_ROUTES)

    assert summary["totals"]["fetched"] == 3  # p1 once, p2, p3
    assert summary["routes"]["B1"]["fetched"] == 2
    assert summary["routes"]["OAI_1"]["fetched"] == 2
    assert summary["routes"]["B1"]["kept"] == 1
    assert summary["routes"]["OAI_1"]["kept"] == 2
    assert summary["totals"]["kept"] == 2  # p1 once, p3


def test_drops_are_counted_per_route_by_reason():
    scopes = [scope("OAI_3", [envelope(["p1", "p2", "p3"], ["p1"],
                                       exclusions=[("p2", "not_include"), ("p3", "unmatched_attribution")])])]
    summary = report.collection_summary(report.route_post_sets(scopes), PRODUCTION_ROUTES, NEW_ROUTES)

    assert summary["routes"]["OAI_3"]["dropped"] == {"not_include": 1, "unmatched_attribution": 1}


def test_copied_scope_rows_across_three_runs_do_not_inflate_counts():
    first = [envelope(["p1", "p2"], ["p1", "p2"])]
    second = [*first, envelope(["p3"], ["p3"])]
    third = [*second, envelope(["p4"], ["p4"])]
    doc = {
        "job": {"id": JOB, "last_success_id": "run-3"},
        "report_run_id": "run-3",
        "runs": [
            {"id": "run-1", "status": "partial", "completed_at": "2026-10-29T01:00:00+00:00"},
            {"id": "run-2", "status": "partial", "completed_at": "2026-10-29T02:00:00+00:00"},
            {"id": "run-3", "status": "success", "completed_at": "2026-10-29T03:00:00+00:00"},
        ],
        "scopes": [
            scope("B1", first, run_id="run-1"),
            scope("B1", second, run_id="run-2"),
            scope("B1", third, run_id="run-3"),
        ],
    }

    selected = report.report_scopes(doc)
    summary = report.collection_summary(report.route_post_sets(selected), PRODUCTION_ROUTES, NEW_ROUTES)

    assert report.select_report_run(doc) == "run-3"
    assert summary["totals"]["fetched"] == 4
    assert summary["totals"]["kept"] == 4
    assert summary["routes"]["B1"]["pages"] == 3


# R15 -----------------------------------------------------------------------


def test_post_kept_on_b1_only_because_of_openai_tag_is_production_route_new_keyword():
    scopes = [
        scope("B1", [envelope(["p1", "p2"], ["p1", "p2"])]),
        scope("OAI_1", [envelope(["p3"], ["p3"])]),
    ]
    sets = report.route_post_sets(scopes)
    tags = {"p1": {"openai"}, "p2": {"google"}, "p3": {"openai"}}

    growth = report.growth_summary(sets, tags, PRODUCTION_ROUTES, NEW_ROUTES)

    assert growth["baseline_equivalent_kept"] == 1  # p2
    assert growth["incremental_kept"]["by_discovery"]["production_route_new_keyword"] == 1  # p1
    assert growth["incremental_kept"]["by_discovery"]["new_routes_only"] == 1  # p3
    assert growth["incremental_kept"]["by_brand_set"] == {"openai": 2}
    assert growth["net_new_fetched"] == 1  # p3
    assert growth["ratios"]["incremental_kept_to_baseline_kept"] == pytest.approx(2.0)


# R16 -----------------------------------------------------------------------


def test_credits_exact_for_bodies_and_ranges_for_no_body_and_error_bodies():
    requests = [
        {"id": "q1", "scope_key": f"B1:{START}:{START + 300}", "transport_outcome": "received",
         "http_status": 200, "cursor_before": None, "receipt": {"raw_count": 0, "body_lost": False}},
        {"id": "q2", "scope_key": f"B1:{START}:{START + 300}", "transport_outcome": "unknown",
         "http_status": None, "cursor_before": None, "receipt": {"raw_count": None, "body_lost": False}},
        {"id": "q3", "scope_key": f"B1:{START}:{START + 300}", "transport_outcome": "received",
         "http_status": 520, "cursor_before": None, "receipt": {"raw_count": 0, "body_lost": False}},
    ]

    assert report.request_credit_range(requests[0]) == (15, 15, "billed")
    assert report.request_credit_range(requests[1]) == (0, 300, "no_body")
    assert report.request_credit_range(requests[2]) == (0, 15, "error_with_body")

    summary = report.credit_summary(requests)
    assert summary["totals"]["credits_min"] == 15
    assert summary["totals"]["credits_max"] == 15 + 300 + 15
    assert summary["routes"]["B1"]["requests"] == 3
    assert summary["routes"]["B1"]["retries"] == 2  # same page requested three times


def test_lost_body_and_missing_receipt_are_no_body_ranges():
    lost = {"id": "q1", "scope_key": "C1", "http_status": 200, "receipt": {"raw_count": 20, "body_lost": True}}
    missing = {"id": "q2", "scope_key": "C1", "http_status": None, "receipt": None}
    full_page = {"id": "q3", "scope_key": "C1", "http_status": 200, "receipt": {"raw_count": 20, "body_lost": False}}

    assert report.request_credit_range(lost) == (0, 300, "no_body")
    assert report.request_credit_range(missing) == (0, 300, "no_body")
    assert report.request_credit_range(full_page) == (300, 300, "billed")


# R17 -----------------------------------------------------------------------


def test_classification_call_of_four_members_allocates_cost_evenly():
    allocation = report.allocate_call_costs([call(["a", "b", "c", "d"], actual="0.008000")])

    assert {pid: costs["reported"] for pid, costs in allocation.items()} == {
        pid: Decimal("0.002") for pid in "abcd"
    }


def test_settled_cost_uses_reservation_for_unfinished_calls():
    allocation = report.allocate_call_costs([
        call(["a", "b"], actual=None, reserved="0.010000", state="ambiguous"),
    ])

    assert allocation["a"] == {"reported": Decimal(0), "settled": Decimal("0.005")}


# R21-R23 ---------------------------------------------------------------------


def test_per_day_estimate_divides_by_window_share_and_names_it():
    estimate = report.per_day_estimate(4000, 0.25, "production saved posts 2026-10-29")

    assert estimate["per_day"] == pytest.approx(16000)
    assert "0.25" in estimate["label"]
    assert "estimate" in estimate["label"]


def test_engagement_refresh_credits_and_enrichment_limit_factor():
    assert report.engagement_refresh_credits(89_000) == 1_335_000

    limits = {
        "search_max_results": 2000,
        "enrichment_claim_per_cycle": 100,
        "metrics_refresh_per_cycle_cap": 200,
        "run_deadline_seconds": 780,
    }
    rows = {row["limit"]: row for row in report.limit_comparison(89_000, {"OAI_1": 40_680}, limits)}

    enrichment = rows["harvest.enrichment.claim_per_cycle"]
    assert enrichment["per_day_capacity"] == 9600
    assert enrichment["exceeded"] is True
    assert round(enrichment["factor"], 1) == 9.3
    assert rows["metrics_refresh.per_cycle_cap"]["per_day_capacity"] == 19_200
    assert rows["search.max_results"]["exceeded"] is False
    assert "not measured" in rows["harvest.run_deadline_seconds"]["note"]


def test_limits_are_read_from_config_yaml():
    limits = report.load_limits(
        "search:\n  max_results: 2000\nharvest:\n  run_deadline_seconds: 780\n"
        "  enrichment:\n    claim_per_cycle: 100\nmetrics_refresh:\n  per_cycle_cap: 200\n"
    )

    assert limits == {
        "search_max_results": 2000,
        "enrichment_claim_per_cycle": 100,
        "metrics_refresh_per_cycle_cap": 200,
        "run_deadline_seconds": 780,
    }


# R24 -----------------------------------------------------------------------


def test_watch_trigger_holds_at_high_cost_per_classified_post():
    members = [[f"p{n}" for n in range(start, start + 20)] for start in range(0, 2000, 20)]
    calls = [call(group, actual="0.014000") for group in members]  # $1.40 classification
    calls += [call(group, actual="0.010000", stage="translation") for group in members]  # $1.00

    watch = report.watch_summary(calls)

    assert watch["settled_usd"] == Decimal("2.4")
    assert watch["classified_posts"] == 2000
    assert watch["reported_usd_per_classified_post"] == Decimal("0.0012")
    assert watch["trigger"] is True
    assert watch["volume_above_doubling"] is False


def test_watch_flags_volume_without_trigger_at_normal_cost_per_post():
    members = [[f"p{n}" for n in range(start, start + 20)] for start in range(0, 12_000, 20)]
    calls = [call(group, actual="0.010000") for group in members[:200]]
    calls += [call(group, actual="0.005000") for group in members[200:]]

    watch = report.watch_summary(calls)

    assert watch["settled_usd"] == Decimal(4)
    assert watch["classified_posts"] == 12_000
    assert watch["trigger"] is False
    assert watch["volume_above_doubling"] is True


# SQL safety ----------------------------------------------------------------

FORBIDDEN = ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE", "CREATE", "GRANT",
             "REVOKE", "COPY", "MERGE", "CALL", "VACUUM", "LOCK", "COMMIT")


@pytest.mark.parametrize("path", [XB_SQL, PROD_SQL], ids=["xbackfiller", "production"])
def test_sql_files_are_read_only_transactions(path):
    text = path.read_text()
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--")).strip()

    assert body.startswith("BEGIN TRANSACTION READ ONLY;")
    assert body.endswith("ROLLBACK;")
    for word in FORBIDDEN:
        assert not re.search(rf"\b{word}\b", text, re.IGNORECASE), word
    statements = [part.strip() for part in body.split(";") if part.strip()]
    assert statements[0] == "BEGIN TRANSACTION READ ONLY"
    assert statements[-1] == "ROLLBACK"
    assert all(re.match(r"(WITH|SELECT)\b", part) for part in statements[1:-1])
    # The text is passed inside a double-quoted shell argument.
    assert not set(text) & set('"$`\\')


def test_placeholder_substitution_rejects_non_uuid_job_id():
    with pytest.raises(ValueError):
        report.xbackfiller_sql("1; SELECT pg_sleep(10)")
    with pytest.raises(ValueError):
        report.xbackfiller_sql("not-a-uuid")

    sql = report.xbackfiller_sql(JOB.upper())
    assert f"'{JOB}'" in sql
    assert "{{" not in sql


def test_production_sql_takes_integer_epochs_only():
    with pytest.raises(ValueError):
        report.production_sql("1793300400; SELECT 1", 1_793_322_000)
    with pytest.raises(ValueError):
        report.production_sql(True, 1_793_322_000)

    sql = report.production_sql(1_793_300_400, 1_793_322_000)
    assert "1793300400" in sql and "{{" not in sql


# Input parsing and end-to-end report ---------------------------------------


def test_document_is_found_inside_render_json_output():
    inner = {"format": report.XBACKFILLER_FORMAT, "database": "xbackfiller"}
    wrapped = json.dumps([{"size_report_input": json.dumps(inner)}])

    assert report.load_document(wrapped, report.XBACKFILLER_FORMAT) == inner


def _xbackfiller_doc():
    return {
        "format": report.XBACKFILLER_FORMAT,
        "database": "xbackfiller",
        "include_collection": True,
        "job": {"id": JOB, "last_success_id": "run-1", "route_metadata": {}},
        "report_run_id": "run-1",
        "runs": [{"id": "run-1", "status": "success", "completed_at": "2026-10-29T03:00:00+00:00",
                  "staff_relevance": [{"identity": "x", "status": "returned"}],
                  "model_responses": [{"status": "returned", "cost_usd": "0.0001"}]}],
        "scopes": [
            scope("B1", [envelope(["p1", "p2"], ["p1", "p2"], request_id="q1")]),
            scope("OAI_1", [envelope(["p2", "p3", "p4"], ["p3"], exclusions=[("p4", "not_include")],
                                     request_id="q2")]),
        ],
        "requests": [
            {"id": "q1", "scope_key": f"B1:{START}:{START + 300}", "transport_outcome": "received",
             "http_status": 200, "cursor_before": None, "receipt": {"raw_count": 2, "body_lost": False}},
            {"id": "q2", "scope_key": f"OAI_1:{START}:{START + 300}", "transport_outcome": "received",
             "http_status": 200, "cursor_before": None, "receipt": {"raw_count": 3, "body_lost": False}},
        ],
        "calls": [call(["p1", "p2", "p3"], actual="0.000900")],
        "observed_post_ids": ["p1", "p2", "p3"],
        "post_brands": [["p1", "google"], ["p2", "openai"], ["p3", "anthropic"]],
        "brands": [{"nickname": "google", "is_sentinel": False},
                   {"nickname": "openai", "is_sentinel": False},
                   {"nickname": "anthropic", "is_sentinel": False}],
        "table_sizes": {"collection_scope_runs": 3000, "posts": 9000},
    }


def _production_doc():
    return {
        "format": report.PRODUCTION_FORMAT,
        "database": "pushinweight",
        "window_start_epoch": START,
        "window_end_epoch": START + 300,
        "day_start_epoch": START - 43_200,
        "day_end_epoch": START + 43_200,
        "window_posts": [{"source_query_id": "B1", "posts": 2}, {"source_query_id": "SPECIALEVENTS1", "posts": 5}],
        "day_posts": [{"source_query_id": "B1", "posts": 8}, {"source_query_id": "SPECIALEVENTS1", "posts": 9}],
    }


def test_end_to_end_report_writes_markdown_and_json(tmp_path):
    files = {
        "xb.json": json.dumps(_xbackfiller_doc()),
        "prod.json": json.dumps(_production_doc()),
        "share.json": json.dumps({"format": report.PILOT_SHARE_FORMAT, "source": "pilot slices 2-4",
                                  "new_routes_share": 0.5}),
        "config.yaml": "search:\n  max_results: 2000\nharvest:\n  run_deadline_seconds: 780\n"
                       "  enrichment:\n    claim_per_cycle: 100\nmetrics_refresh:\n  per_cycle_cap: 200\n",
        "before.json": json.dumps({"collection_scope_runs": 1000, "posts": 5000}),
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text)

    code = report.main([
        "--xbackfiller", str(tmp_path / "xb.json"), "--production", str(tmp_path / "prod.json"),
        "--frozen-queries", str(FROZEN), "--limits-config", str(tmp_path / "config.yaml"),
        "--pilot-share", str(tmp_path / "share.json"), "--size-before", str(tmp_path / "before.json"),
        "--output-dir", str(tmp_path / "out"), "--timestamp", "2026-10-30-120000",
    ])

    assert code == 0
    data = json.loads((tmp_path / "out" / "2026-10-30-120000-oai-anthropic-size-report.json").read_text())
    markdown = (tmp_path / "out" / "2026-10-30-120000-oai-anthropic-size-report.md").read_text()
    assert data["growth"]["baseline_equivalent_kept"] == 1  # p1 (google) on B1
    assert data["growth"]["incremental_kept"]["by_discovery"]["production_route_new_keyword"] == 1  # p2
    assert data["growth"]["incremental_kept"]["by_discovery"]["new_routes_only"] == 1  # p3
    assert data["shares"]["production_routes"]["share"] == pytest.approx(0.25)  # B1 2 of 8
    assert data["db_growth"]["bookkeeping_bytes"] == 2000
    assert data["db_growth"]["production_equivalent_bytes"] == 4000
    assert data["comparison"]["production_window"]["saved_posts_production_routes"] == 2
    assert report.BASELINE_LABEL in markdown
    assert "not measured" in markdown


def test_production_posts_without_a_source_count_as_the_production_searches(tmp_path):
    # Production's ordinary searches leave posts.source_query_id empty; only the
    # discovery lanes set it (observed in production for 2026-09-19 to 2026-10-29).
    production = {**_production_doc(),
                  "window_posts": [{"source_query_id": None, "posts": 3},
                                   {"source_query_id": "RARE_EXTRA", "posts": 1},
                                   {"source_query_id": "SPECIALEVENTS2", "posts": 4}],
                  "day_posts": [{"source_query_id": None, "posts": 12},
                                {"source_query_id": "RARE_EXTRA", "posts": 6},
                                {"source_query_id": "SPECIALEVENTS2", "posts": 9}]}
    files = {
        "xb.json": json.dumps(_xbackfiller_doc()),
        "prod.json": json.dumps(production),
        "share.json": json.dumps({"format": report.PILOT_SHARE_FORMAT, "source": "pilot slices 2-4",
                                  "new_routes_share": 0.5}),
        "config.yaml": "search:\n  max_results: 2000\nharvest:\n  run_deadline_seconds: 780\n"
                       "  enrichment:\n    claim_per_cycle: 100\nmetrics_refresh:\n  per_cycle_cap: 200\n",
    }
    for name, text in files.items():
        (tmp_path / name).write_text(text)

    code = report.main([
        "--xbackfiller", str(tmp_path / "xb.json"), "--production", str(tmp_path / "prod.json"),
        "--frozen-queries", str(FROZEN), "--limits-config", str(tmp_path / "config.yaml"),
        "--pilot-share", str(tmp_path / "share.json"),
        "--output-dir", str(tmp_path / "out"), "--timestamp", "2026-10-30-120000",
    ])

    assert code == 0
    data = json.loads((tmp_path / "out" / "2026-10-30-120000-oai-anthropic-size-report.json").read_text())
    window = data["comparison"]["production_window"]
    assert data["shares"]["production_routes"]["share"] == pytest.approx(0.25)  # 3 of 12
    assert window["saved_posts_production_routes"] == 3
    assert window["saved_posts_excluded_searches"]["RARE_EXTRA"] == 1
    assert window["saved_posts_excluded_searches"]["SPECIALEVENTS2"] == 4
    assert window["saved_posts_other_sources"] == {}


def test_watch_mode_exit_code_signals_trigger(tmp_path, capsys):
    members = [[f"p{n}" for n in range(start, start + 20)] for start in range(0, 2000, 20)]
    doc = {**_xbackfiller_doc(), "calls": [call(group, actual="0.024000") for group in members]}
    path = tmp_path / "watch.json"
    path.write_text(json.dumps(doc))

    assert report.main(["--watch", str(path)]) == report.WATCH_TRIGGER_EXIT
    assert "R24 trigger: HOLDS" in capsys.readouterr().out


def test_watch_refuses_a_job_id_that_matches_no_job(tmp_path, capsys):
    doc = {**_xbackfiller_doc(), "job": None, "calls": []}
    path = tmp_path / "watch.json"
    path.write_text(json.dumps(doc))

    assert report.main(["--watch", str(path)]) == 1
    assert "matched no CollectionJob" in capsys.readouterr().err


def test_load_document_reads_render_psql_json_wrapper():
    """`render psql -o json` wraps psql's aligned text in {"output": "..."} (observed 2026-10-28)."""
    import json as _json

    from scripts.backfill_size_report import load_document

    doc = {"format": "probe-format/v1", "rows": [{"k": 1, "text": 'a "quoted" value'}]}
    body = _json.dumps(doc)
    aligned = f"BEGIN\n    doc    \n-----------\n {body}\n(1 row)\n\nROLLBACK\n"
    wrapped = _json.dumps({"output": aligned}, indent=2)
    assert load_document(wrapped, "probe-format/v1") == doc
