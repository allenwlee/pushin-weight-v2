"""Frozen expansion and real command routing, without a database or providers."""

import copy
import json
from datetime import UTC, datetime
from itertools import pairwise
from types import SimpleNamespace

import pytest

from scripts import backfill_month as month


def recipe():
    units = [
        {
            "scope_key": r,
            "scope_kind": "x_query",
            "ownership": {
                "call_id": r,
                "query": "frozen:" + r,
                "since_epoch": 1,
                "until_epoch": 2,
            },
        }
        for r in sorted(month.ROUTES)
    ]
    return {
        "format": "x-month-recipe/v1",
        "spec": {
            "since": "2026-07-01T00:00:00+09:00",
            "until": "2026-08-01T00:00:00+09:00",
            "calendar_timezone": "Asia/Tokyo",
            "campaign": "test-month",
            "deadline": "2026-11-05T00:00:00+00:00",
            "runtime_revision": "a" * 40,
            "source_sha256": {"scripts/backfill_campaign.py": "a" * 64},
            "database": {"name": "test", "user": "test"},
        },
        "template": {
            "campaign": "seed",
            "deadline": "2026-11-05T00:00:00+00:00",
            "direct_concurrency": 32,
            "database": {"name": "test", "user": "test"},
            "windows": [
                {
                    "index": 1,
                    "max_usd": "6.25",
                    "maximum_api_requests": 1250,
                    "maximum_model_requests": 12500,
                    "collection_definition": {
                        "scope": {
                            "units": units,
                            "author_scope": {
                                "contexts": {"123": {"staff_brands": ["qwen"]}}
                            },
                        }
                    },
                }
            ],
        },
    }


def test_frozen_july_expansion_matches_original_private_fixtures():
    r = recipe()
    before = copy.deepcopy(r)
    # Frozen hashes generated from the original private operator's test recipe.
    assert [
        month.digest(month.daily_manifest(r, n)) for n in range(31)
    ] == ORIGINAL_DAILY_HASHES
    windows = [w for f in month.iter_manifests(r) for w in f["windows"]]
    assert len(windows) == 124
    assert (
        sum(len(w["collection_definition"]["scope"]["units"]) for w in windows) == 71424
    )
    assert windows[0]["since_epoch"] == 1782831600
    assert windows[-1]["until_epoch"] == 1785510000
    assert all(a["until_epoch"] == b["since_epoch"] for a, b in pairwise(windows))
    assert r == before


@pytest.mark.parametrize("evaluate_at_end", [False, True])
def test_all_collects_two_whole_days_before_first_enrichment(evaluate_at_end):
    r = recipe()
    r["spec"]["until"] = "2026-07-03T00:00:00+09:00"
    seen = []

    def collect(w, **kw):
        seen.append(("collect", kw["frozen"]["campaign"], w["index"]))
        assert kw["collection_options"] == {"concurrency": 20, "starts_per_second": 10}
        return {"status": "verified", "phase_usage_scope": "job_cumulative",
                "phase_usage": {"twitterapi_requests": 7, "collection_gate": {"requests_started": 2}}}

    def verify(w, **kw):
        seen.append(("verify", kw["frozen"]["campaign"], w["index"]))

    def enrich(w, **kw):
        seen.append(("enrich", kw["frozen"]["campaign"], w["index"]))
        assert kw["enrichment_concurrency"] == 8
        return {"status": "verified", "phase": "enrichment",
                "phase_usage_scope": "job_cumulative",
                "phase_usage": {"post_enrichment": {"requests_sent": 3,
                                 "requests_without_reported_cost": 1}}}

    def assess(frozen, cfg, rows):
        return {"windows": [{"status": "failed", "attempt": row} for row in rows]}

    results = month.phase_sequence(
        lambda: month.iter_manifests(r),
        phase="all",
        cfg=object(),
        collect=collect,
        enrich=enrich,
        verify=verify,
        collection_options={"concurrency": 20, "starts_per_second": 10},
        enrichment_concurrency=8,
        evaluate_at_end=evaluate_at_end,
        assess=assess,
    )
    assert [x[0] for x in seen] == ["collect"] * 8 + ["verify"] * 8 + ["enrich"] * 8
    assert all(row["phase_usage_scope"] == "job_cumulative" for row in results[:8])
    assert all(row["phase_usage"]["collection_gate"]["requests_started"] == 2 for row in results[:8])
    assert all(row["phase_usage"]["post_enrichment"]["requests_without_reported_cost"] == 1
               for row in results[8:])
    assert all(row["status"] == ("failed" if evaluate_at_end else "verified")
               for row in results[8:])


def test_enrich_rejects_any_incomplete_window_before_first_model_call():
    frozen = {"windows": [{"index": 1}, {"index": 2}]}
    seen = []

    def verify(w, **kw):
        if w["index"] == 2:
            raise ValueError("collection_not_verified")

    with pytest.raises(ValueError, match="collection_not_verified"):
        month.phase_sequence(
            lambda: iter([frozen]),
            phase="enrich",
            cfg=None,
            collect=lambda *a, **kw: pytest.fail("enrich recollected"),
            enrich=lambda *a, **kw: seen.append("enriched"),
            verify=verify,
        )
    assert seen == []


def test_collection_failure_stops_range_without_enrichment():
    def fail(*a, **kw):
        raise RuntimeError("rare_gate_pending")

    with pytest.raises(RuntimeError, match="rare_gate_pending"):
        month.phase_sequence(
            lambda: iter([{"windows": [{"index": 1}, {"index": 2}]}]),
            phase="all",
            cfg=None,
            collect=fail,
            enrich=lambda *a, **kw: pytest.fail("enriched after failed collection"),
            verify=lambda *a, **kw: None,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "bad"},
        {"enrichment_concurrency": 33},
        {"enrichment_concurrency": True},
        {"collection_concurrency": 21},
        {"collection_concurrency": 0},
        {"collection_starts_per_second": 0},
        {"collection_starts_per_second": float("nan")},
    ],
)
def test_invalid_preferences_fail_purely(changes):
    with pytest.raises(ValueError):
        month.execution_options(recipe(), **({"phase": "all"} | changes))


def test_preferences_respect_saved_ceiling_and_do_not_change_hashes():
    r = recipe()
    r["template"]["direct_concurrency"] = 4
    before = month.digest(r)
    assert month.execution_options(r, phase="all")["enrichment_concurrency"] == 4
    with pytest.raises(ValueError, match="enrichment_concurrency"):
        month.execution_options(r, phase="all", enrichment_concurrency=5)
    assert month.digest(r) == before


def test_runtime_attestation_may_extend_original_sources_but_not_omit_them():
    r = recipe()
    original = month.digest(r)
    sources = {
        p: "b" * 64 for p in month.RUNTIME_MODULES | set(r["spec"]["source_sha256"])
    }
    runtime = {"runtime_revision": "b" * 40, "source_sha256": sources}
    assert month.selected_runtime(r, runtime)["source_sha256"] == sources
    assert month.digest(r) == original
    for change in [
        runtime | {"deadline": "later"},
        runtime | {"source_sha256": {}},
        runtime | {"runtime_revision": "main"},
    ]:
        with pytest.raises(ValueError):
            month.selected_runtime(r, change)


def test_live_lease_rejected_expired_owned_lease_left_for_fenced_reclaim():
    now = datetime(2026, 10, 22, tzinfo=UTC)
    job = SimpleNamespace(
        active_run=SimpleNamespace(status="running", lease_expires_at=now),
        active_run_id="saved",
    )
    month.check_active_lease(job, now=now)
    assert job.active_run_id == "saved"
    job.active_run.lease_expires_at = now.replace(year=2027)
    with pytest.raises(RuntimeError, match="active"):
        month.check_active_lease(job, now=now)


# Populated below from the pre-existing private implementation before implementation.
ORIGINAL_DAILY_HASHES = [
    "0808eb43c6797fb2c78ff86cbffa2fef9b4cb34112f3ac6a6c63e83b4a246ba0",
    "7230f42e9e6f2bceb71bab7d2650b8525fdf24afbd85f0f602bbeadfd2e0b9e8",
    "7e100196f3fa278ee7cde7f81ab1d7838d3d1850f0c78b936c94968a8f0d9a4e",
    "31d427c0f3f0aa2a55952f90e1c6b6e6dea05322e8e17e908ee4a4470c72921d",
    "a763d5c7629a1fc4c18c5036842594457f2319d69592eaa7361b1d9cabeb3a05",
    "ca0eeff3869764b39593bb3b32e7c8281c45e892faa889441fcd6712f9715a29",
    "fcf9459613e074a985cb8beefdfe57b6bfacb1febbdd91bbe3c10ca002d31fe0",
    "be6f127f9cdcaa5d9f4bb2b76e82b4bf1fbd558faec916e218cb015e19fa7414",
    "f091c670734eb2500975477823dc798412c53b8c0e22bbe8a7d0dcbb27467e42",
    "926e76564e53a626430eaeed0cd2161a41aad4df13554665602f4f3831fb3816",
    "37df19b161bcf93d478c745139cadc8d4fad2672f1de28ed2adfcf2aeb90222c",
    "fac899d0c1495eb1f24bffe8632d6ec5cdbbb3138c2a396e340a6d452b253e3d",
    "3a6fb3d74694ce7b9bbf254710574c3e567705110d097ce9080b62ad3d99ff0b",
    "3b49a298ae0223dd6629fc5b2dae18f84f0a1a45f699a5578f6a39997e1e3f2e",
    "3fbef0e4d3fd9b30fac7155a577577dfb1e9b980de9930b8af189a8ee5dd3cbf",
    "d5d85251ce7b33839ee3fdd85fa3f77d4a0702887b3d99866e0fc2925bdd2979",
    "01cbe62da19ba43decb3c516eb8d768b0d804dea6757d4e996efd610bd267c6a",
    "5fae7f526dd9920d2877d92f1f379171c0c5e5cdcfc756972159bb7c6c1db3ca",
    "fd8622b2f4cc2955d75804b9ee8c78a044c84c9d5a509db653e8a7654fc8eb62",
    "1123ea388d7d304731453d9331d94ad759b4b0ca980fc5e1b426bec5979d370c",
    "d57a2799280deb574067fb41ba1743f9b7e13c3e19e421edf71504d795107988",
    "d90675f3df0cdd9e1ac695882d07e2919bb6abdf83cd72ff08c5331b00dffde5",
    "5cc555bf2733765caa62481aaa49a18508fa73607eddad29baeef8e00a007828",
    "a7886b9829aea21487c80c8ec02f8794d7a6c47fa2c06cea6f560371d76aa1ac",
    "e72e1012607a5f4d261849354eb61da0d940810ddc8266fde9dac7f83e8446ee",
    "bdd75b318cfd8bbadc7e8796eb136771219bda38ce64f13a0ee966bfe97a62e8",
    "e633f7a2c559cd84f995928b8b88019411d1d1d5b89c0fba48407252ad18ff59",
    "487d40a3309a8b51c5a4620d32daedae07c9681cda7d9b0c89c9e1b389417cfb",
    "61986d0a203593f22fad0411512916fc3be264b46fe560410ba9cff2f091d0bc",
    "cfa0e11f69f3d090378932b5690f44ba1c6d2be50f26044c5a787d0000e00e85",
    "ae5a8a25f5b569e3432df85f1afe2c283ba1d441bd849842ae2b6de6eb5e4798",
]


def command_input(tmp_path, instructions):
    path = tmp_path / "instructions.json"
    path.write_text(json.dumps(instructions))
    return path


def test_command_routes_new_month_phases_without_changing_recipe(tmp_path, monkeypatch):
    from django.core.management import call_command

    import monitor.management.commands.run_backfill as command

    r = recipe()
    path = command_input(tmp_path, r)
    seen = []
    monkeypatch.setattr(command, "run_phases", lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr(command, "load_config", lambda *a: "config")
    call_command(
        "run_backfill",
        month_recipe=path,
        phase="all",
        execute=True,
        collection_concurrency=20,
        enrichment_concurrency=8,
    )
    assert seen == [
        (
            (r, "config"),
            {
                "phase": "all",
                "enrichment_concurrency": 8,
                "collection_concurrency": 20,
                "collection_starts_per_second": 10,
                "evaluate_at_end": False,
            },
        )
    ]
    assert json.loads(path.read_text()) == r


def test_command_month_dry_run_has_no_execution(tmp_path, monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    import monitor.management.commands.run_backfill as command

    r = recipe()
    path = command_input(tmp_path, r)
    monkeypatch.setattr(
        command, "run_phases", lambda *a, **kw: pytest.fail("executed dry run")
    )
    monkeypatch.setattr(command, "load_config", lambda *a: "config")
    out = StringIO()
    call_command(
        "run_backfill", month_recipe=path, phase="enrich", dry_run=True, stdout=out
    )
    assert json.loads(out.getvalue()) == r


@pytest.mark.parametrize(
    "kw,match",
    [
        ({"phase": "bad"}, "phase"),
        ({"phase": "all", "collection_concurrency": 21}, "collection_concurrency"),
        ({"phase": "all", "enrichment_concurrency": 33}, "enrichment_concurrency"),
        ({"collection_concurrency": 2}, "phase"),
    ],
)
def test_command_rejects_preferences_before_manifest_planning(monkeypatch, kw, match):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    import monitor.management.commands.run_backfill as command

    monkeypatch.setattr(
        command, "manifest", lambda *a, **kw: pytest.fail("planned invalid options")
    )
    with pytest.raises(CommandError, match=match):
        call_command("run_backfill", since="2026-07-01", until="2026-07-02", **kw)


def test_command_month_requires_phase_and_attests_runtime_before_execution(
    tmp_path, monkeypatch
):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    import monitor.management.commands.run_backfill as command

    path = command_input(tmp_path, recipe())
    monkeypatch.setattr(
        command, "run_phases", lambda *a, **kw: pytest.fail("invalid execution")
    )
    with pytest.raises(CommandError, match="phase"):
        call_command("run_backfill", month_recipe=path)
    with pytest.raises(CommandError, match="attestation"):
        call_command(
            "run_backfill",
            month_recipe=path,
            phase="all",
            runtime_revision="b" * 40,
            execute=True,
        )


def test_phase_runtime_holds_original_month_and_campaign_locks_and_cursor_guard(
    monkeypatch,
):
    from contextlib import contextmanager

    import psycopg
    from django.db import connection

    from scripts import backfill_campaign as campaign

    frozen = {
        "campaign": "test-campaign",
        "direct_concurrency": 32,
        "database": {"name": "test", "user": "test"},
        "deadline": "2026-11-05T00:00:00+00:00",
        "windows": [{"index": 1}, {"index": 2}],
    }
    events, locks = [], []

    class Guard:
        def execute(self, sql, params=None):
            if params:
                locks.append(params[0])
            return self

        def fetchone(self):
            return (True,)

        def close(self):
            events.append("closed")

    @contextmanager
    def wrapper(value):
        assert value is campaign.block_live_cursor_writes
        events.append("cursor_guard")
        yield

    monkeypatch.setenv("DATABASE_URL", "postgres://fixture")
    monkeypatch.setattr(psycopg, "connect", lambda *a, **kw: Guard())
    monkeypatch.setattr(
        month, "_validate_campaign_runtime", lambda *a: events.append("runtime_checked")
    )
    monkeypatch.setattr(
        month, "_check_saved_jobs", lambda *a: events.append("saved_checked")
    )
    monkeypatch.setattr(
        campaign, "validate_storage_schema", lambda: events.append("schema_checked")
    )
    monkeypatch.setattr(connection, "execute_wrapper", wrapper)
    monkeypatch.setattr(
        campaign,
        "collect_window",
        lambda w, **kw: (
            events.append("collect")
            or {
                "status": "verified",
                "source_collection_job": str(w["index"]),
                "window": {"huge": list(range(1000))},
            }
        ),
    )
    monkeypatch.setattr(
        month, "_verify_saved_collection", lambda *a, **kw: events.append("verify")
    )
    monkeypatch.setattr(
        campaign,
        "enrich_window",
        lambda w, **kw: events.append("enrich") or {"status": "verified"},
    )
    out = month.run_phases(frozen, object(), phase="all")
    assert events == [
        "runtime_checked",
        "schema_checked",
        "saved_checked",
        "cursor_guard",
        "collect",
        "collect",
        "verify",
        "verify",
        "enrich",
        "enrich",
        "closed",
    ]
    assert locks == [
        int(
            __import__("hashlib")
            .sha256(("x-manual-month-controller:" + str(frozen["database"])).encode())
            .hexdigest()[:15],
            16,
        ),
        int(
            __import__("hashlib")
            .sha256((frozen["campaign"] + str(frozen["database"])).encode())
            .hexdigest()[:15],
            16,
        ),
    ]
    assert all("window" not in row for row in out)


def test_legacy_command_without_phase_still_uses_existing_runner(tmp_path, monkeypatch):
    from django.core.management import call_command

    import monitor.management.commands.run_backfill as command

    frozen = {"campaign": "legacy", "revision": "a" * 40}
    path = command_input(tmp_path, frozen)
    seen = []
    monkeypatch.setattr(command, "load_config", lambda *a: "config")
    monkeypatch.setattr(command, "run", lambda *a, **kw: seen.append((a, kw)))
    monkeypatch.setattr(
        command, "run_phases", lambda *a, **kw: pytest.fail("changed legacy path")
    )
    call_command("run_backfill", manifest=path, execute=True, runtime_revision="b" * 40)
    assert seen == [
        ((frozen, "config"), {"evaluate_at_end": False, "runtime_revision": "b" * 40})
    ]


def test_expired_deadline_fails_dry_run_before_work(tmp_path, monkeypatch):
    from django.core.management import call_command
    from django.core.management.base import CommandError

    import monitor.management.commands.run_backfill as command

    r = recipe()
    r["spec"]["deadline"] = r["template"]["deadline"] = "2020-01-01T00:00:00+00:00"
    path = command_input(tmp_path, r)
    monkeypatch.setattr(command, "load_config", lambda *a: "config")
    monkeypatch.setattr(
        command, "run_phases", lambda *a, **kw: pytest.fail("expired execution")
    )
    with pytest.raises(CommandError, match="deadline"):
        call_command("run_backfill", month_recipe=path, phase="all", dry_run=True)
