"""Offline history plans do not call a provider."""

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from core.staff_assets.job_history_collection import build_history_plan
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose


class MemoryJournal:
    def __init__(self):
        self.entries = []

    def load(self, identity):
        return deepcopy(
            [entry for entry in self.entries if entry["identity"] == identity]
        )

    def reserve(self, identity, cursor):
        self.entries.append(
            {"identity": identity, "cursor_before": cursor, "state": "pending"}
        )
        return len(self.entries) - 1

    def finish(self, token, page):
        self.entries[token].update(state="received", page=deepcopy(page))


class FakeHistoryClient:
    api_key = "fake-key"

    def __init__(self, pages):
        self.pages = dict(pages)
        self.calls = []

    def run_search_pages(self, query, *, cursor, **kwargs):
        self.calls.append((query, cursor, kwargs))
        value = self.pages[cursor]
        if isinstance(value, Exception):
            raise value
        return iter([value])


def history_page(items, *, next_cursor=None, more=False, clipped=False, invalid=False):
    return SimpleNamespace(
        items=items,
        has_more=more,
        next_cursor=next_cursor,
        clipped=clipped,
        continuation_invalid=invalid,
        raw_post_ids=tuple(x.get("id") for x in items),
        received_at=datetime(2026, 11, 9, tzinfo=ZoneInfo("Asia/Tokyo")),
    )


def run_history(client, journal, **changes):
    from core.staff_assets.job_history_collection import collect_history_pages

    plan = build_history_plan(
        people=[{"native_id": "123", "handle": "example"}],
        cutoff=datetime(2026, 11, 9, tzinfo=ZoneInfo("Asia/Tokyo")),
    )
    args = {
        "request": plan["queries"][0],
        "since_time": plan["since_time"],
        "until_time": plan["until_time"],
        "client": client,
        "journal": journal,
        "authorized": True,
        "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND,
        "max_requests": 5,
        "max_pages": 5,
        "max_posts": 100,
        "deadline": datetime(2030, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")),
    }
    args.update(changes)
    return collect_history_pages(**args)


def history_item(
    post_id, *, author="123", created="2026-08-01T00:00:00+00:00", text="Joined"
):
    return {"id": post_id, "author_id": author, "created_at": created, "text": text}


def test_fake_collection_reuses_saved_pages_and_counts_duplicate_appearances():
    journal = MemoryJournal()
    client = FakeHistoryClient(
        {
            None: history_page([history_item("1")], next_cursor="next", more=True),
            "next": history_page([history_item("1"), history_item("2")]),
        }
    )
    first = run_history(client, journal)
    assert first["status"] == "complete"
    assert [x["id"] for x in first["records"]] == ["1", "2"]
    assert len(first["appearances"]) == 3
    assert first["requests_made"] == 2
    replay = run_history(client, journal)
    assert replay["status"] == "complete" and replay["requests_made"] == 0
    assert len(client.calls) == 2


def test_fake_collection_refuses_unknown_request_replay():
    journal = MemoryJournal()
    client = FakeHistoryClient({None: TimeoutError()})
    result = run_history(client, journal)
    assert result["reason"] == "request_failed_or_unknown"
    assert run_history(client, journal)["reason"] == "unknown_request_outcome"
    assert len(client.calls) == 1


def test_fake_collection_holds_wrong_author_and_window():
    client = FakeHistoryClient(
        {
            None: history_page(
                [
                    history_item("1", author="999"),
                    history_item("2", created="2025-01-01T00:00:00Z"),
                ]
            )
        }
    )
    result = run_history(client, MemoryJournal())
    assert result["status"] == "partial"
    assert {row["reason"] for row in result["rejected"]} == {
        "wrong_author",
        "outside_window",
    }
    assert result["records"] == []


def test_fake_collection_holds_conflicting_source_text_and_empty_text():
    client = FakeHistoryClient(
        {
            None: history_page(
                [
                    history_item("1", text="First"),
                    history_item("1", text="Other"),
                    history_item("2", text=""),
                ]
            )
        }
    )
    result = run_history(client, MemoryJournal())
    assert result["status"] == "partial"
    assert {row["reason"] for row in result["rejected"]} == {
        "conflicting_post_content",
        "missing_source_text",
    }
    assert result["records"] == []


def test_fake_collection_stops_repeated_cursor_and_bounds():
    journal = MemoryJournal()
    client = FakeHistoryClient(
        {
            None: history_page([history_item("1")], next_cursor="x", more=True),
            "x": history_page([history_item("2")], next_cursor="x", more=True),
        }
    )
    assert run_history(client, journal)["reason"] == "repeated_or_missing_cursor"
    journal = MemoryJournal()
    client = FakeHistoryClient(
        {
            None: history_page([history_item("1")], next_cursor="x", more=True),
            "x": history_page([history_item("2")]),
        }
    )
    assert run_history(client, journal, max_requests=1)["reason"] == "bound_reached"
    assert run_history(client, journal, max_requests=1)["status"] == "complete"
    assert len(client.calls) == 2


def test_fake_collection_cannot_run_without_authorization_or_on_demand_purpose():
    client = FakeHistoryClient({})
    with pytest.raises(ValueError, match="authorization"):
        run_history(client, MemoryJournal(), authorized=False)
    with pytest.raises(ValueError, match="authorization"):
        run_history(
            client,
            MemoryJournal(),
            credential_purpose=TwitterApiCredentialPurpose.SCHEDULED,
        )
    assert not client.calls


def test_fake_lookup_batches_missing_and_replays_without_refetch():
    from core.staff_assets.job_history_collection import lookup_history_posts

    class FakeLookup:
        api_key = "fake-key"

        def __init__(self):
            self.calls = []

        def get_posts_by_ids(self, ids):
            self.calls.append(ids)
            return {value: history_item(value) for value in ids if value != "51"}

    client, journal = FakeLookup(), MemoryJournal()
    ids = [str(i) for i in range(1, 52)] + ["1"]
    kwargs = {
        "post_ids": ids,
        "expected_authors": {value: "123" for value in ids},
        "client": client,
        "journal": journal,
        "authorized": True,
        "credential_purpose": TwitterApiCredentialPurpose.ON_DEMAND,
        "max_requests": 2,
        "deadline": datetime(2030, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")),
    }
    first = lookup_history_posts(**kwargs)
    assert first["reason"] == "unresolved_posts"
    assert len(first["records"]) == 50
    assert first["unresolved"][0]["reason"] == "missing_or_unavailable"
    assert first["duplicate_id_count"] == 1
    assert [len(batch) for batch in client.calls] == [50, 1]
    replay = lookup_history_posts(**kwargs)
    assert replay["requests_made"] == 0 and len(client.calls) == 2


def test_fake_lookup_does_not_claim_wrong_author_or_unknown_sender():
    from core.staff_assets.job_history_collection import lookup_history_posts

    class FakeLookup:
        api_key = "fake-key"

        def get_posts_by_ids(self, ids):
            return {"1": history_item("1", author="999"), "2": history_item("2")}

    result = lookup_history_posts(
        post_ids=["1", "2"],
        expected_authors={"1": "123"},
        client=FakeLookup(),
        journal=MemoryJournal(),
        authorized=True,
        credential_purpose=TwitterApiCredentialPurpose.ON_DEMAND,
        max_requests=1,
        deadline=datetime(2030, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")),
    )
    assert {row["reason"] for row in result["unresolved"]} == {
        "wrong_author",
        "author_not_established",
    }
    assert not result["records"]


def test_history_plan_uses_jst_bounds_and_keeps_ungated_move_phrases():
    result = build_history_plan(
        people=[{"native_id": "123", "handle": "example"}],
        cutoff=datetime(2026, 11, 9, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        post_ids=[str(i) for i in range(1, 52)],
    )
    assert result["since_time"] == int(
        datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()
    )
    assert len(result["lookup_batches"]) == 2
    assert all(len(batch) <= 50 for batch in result["lookup_batches"])
    assert any(
        '"I joined"' in q["query"]
        and "from:example" in q["query"]
        and "OpenAI" not in q["query"]
        for q in result["queries"]
    )
    job_queries = [
        q["query"] for q in result["queries"] if q["family"] == "job_history"
    ]
    for phrase in ('"my last day"', '"starting at"', '"after three years at"'):
        assert any(phrase in query for query in job_queries)
    assert result["dispatch_available"] is False
    assert all(len(q["query"].encode()) <= 512 for q in result["queries"])


def test_history_split_preserves_every_baseline_clause_with_maximum_handle():
    import hashlib

    from x_monitor.special_events_search import GENERAL_QUERY, GENERAL_QUERY_CLAUSES

    # The recurring special-events query is an existing frozen contract.
    assert hashlib.sha256(GENERAL_QUERY.encode()).hexdigest() == (
        "3667a79e2ea74def2ac32f5a72666990ffa3bd71344e06286058a0ba863fad8f"
    )
    result = build_history_plan(
        people=[{"native_id": "123", "handle": "maxhandle_12345"}],
        cutoff=datetime(2030, 1, 1, tzinfo=ZoneInfo("Asia/Tokyo")),
    )
    baseline = [q["query"] for q in result["queries"] if q["family"] == "special_events_1_baseline"]
    assert len(baseline) == 2
    for clause in GENERAL_QUERY_CLAUSES:
        assert sum(clause in query for query in baseline) == 1
    for query in result["queries"]:
        assert query["query"].startswith("from:maxhandle_12345 (")
        assert query["query"].endswith(
            f" since_time:{result['since_time']} until_time:{result['until_time']}"
        )
        assert len(query["query"].encode("utf-8")) <= 512


def test_history_plan_keeps_missing_id_as_hold_and_reports_duplicate_ids():
    result = build_history_plan(
        people=[
            {"native_id": "123", "handle": "known"},
            {"native_id": None, "handle": "missing"},
        ],
        cutoff=datetime(2026, 11, 9, tzinfo=ZoneInfo("Asia/Tokyo")),
        post_ids=["123", "123", "456"],
    )
    assert result["held_people"][0]["handle"] == "missing"
    assert result["requested_post_ids"] == ["123", "123", "456"]
    assert result["lookup_batches"] == [["123", "456"]]
    assert result["duplicate_post_id_count"] == 1


def test_real_command_can_write_offline_history_plan(tmp_path, django_db_blocker):
    import json

    from django.core.management import call_command

    from tests.test_record_job_history import inventory, person

    manifest = tmp_path / "manifest.json"
    target = tmp_path / "inventory.json"
    plan = tmp_path / "history-plan.json"
    saved_person = person()
    saved_person["sources"][0]["observations"][0]["post_id"] = "123456789"
    manifest.write_text(
        json.dumps({"schema": "record-job-history/v1", "people": [saved_person]})
    )
    target.write_text(json.dumps(inventory()))
    with django_db_blocker.block():
        call_command(
            "save_person_job",
            str(manifest),
            inventory=str(target),
            output=str(tmp_path / "preview.html"),
            history_plan=str(plan),
            history_cutoff="2026-11-09T00:00:00+09:00",
        )
    result = json.loads(plan.read_text())
    assert result["dispatch_available"] is False
    assert result["credential_purpose"] == "on_demand"
    assert result["queries"]
    assert result["lookup_batches"] == [["123456789"]]


def test_preview_output_cannot_overwrite_input_manifest(tmp_path, django_db_blocker):
    import json

    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from tests.test_record_job_history import inventory, person

    manifest = tmp_path / "preview.json"
    target = tmp_path / "inventory.json"
    source = json.dumps({"schema": "record-job-history/v1", "people": [person()]})
    manifest.write_text(source)
    target.write_text(json.dumps(inventory()))
    with django_db_blocker.block(), pytest.raises(CommandError, match="overwrite"):
        call_command(
            "save_person_job",
            str(manifest),
            inventory=str(target),
            output=str(tmp_path / "preview.html"),
        )
    assert manifest.read_text() == source


def test_real_command_writes_a_source_bound_coverage_comparison(
    tmp_path, django_db_blocker
):
    import json

    from django.core.management import call_command

    from core.staff_assets.job_history import prepare_job_history
    from tests.test_record_job_history import inventory, person

    manifest, target = tmp_path / "manifest.json", tmp_path / "inventory.json"
    baseline, output = tmp_path / "baseline.json", tmp_path / "preview.html"
    manifest.write_text(
        json.dumps({"schema": "record-job-history/v1", "people": [person()]})
    )
    target.write_text(json.dumps(inventory()))
    baseline.write_text(json.dumps(prepare_job_history([person()], inventory())))
    with django_db_blocker.block():
        call_command(
            "save_person_job",
            str(manifest),
            inventory=str(target),
            coverage_baseline=str(baseline),
            output=str(output),
        )
    comparison = json.loads((tmp_path / "preview.coverage.json").read_text())
    assert comparison["before"]["people"] == comparison["after"]["people"] == 1
    assert "Coverage comparison:" in output.read_text()
    assert 'href="preview.coverage.json"' in output.read_text()


def test_coverage_baseline_digest_failure_is_rejected(tmp_path, django_db_blocker):
    import json

    import pytest
    from django.core.management import call_command
    from django.core.management.base import CommandError

    from tests.test_record_job_history import inventory, person

    manifest, target, baseline = (
        tmp_path / "manifest.json",
        tmp_path / "inventory.json",
        tmp_path / "baseline.json",
    )
    manifest.write_text(
        json.dumps({"schema": "record-job-history/v1", "people": [person()]})
    )
    target.write_text(json.dumps(inventory()))
    baseline.write_text(
        json.dumps(
            {
                "schema": "record-job-history-preview/v1",
                "payload_digest": "bad",
                "people": [],
            }
        )
    )
    with (
        django_db_blocker.block(),
        pytest.raises(CommandError, match="baseline digest"),
    ):
        call_command(
            "save_person_job",
            str(manifest),
            inventory=str(target),
            coverage_baseline=str(baseline),
            output=str(tmp_path / "preview.html"),
        )
    assert not (tmp_path / "preview.html").exists()
