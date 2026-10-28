"""Named, sliced size-test routes (U2) and lab-list author contexts (U3).

These tests run the real campaign manifest, the real ``plan_job_definition``
and the real query planner from ``config.yaml``. Only the database lookups are
replaced: the database identity and the TwitterListMembership/BrandAccount
rows read by the author-context resolver. No provider, network or database
call is made. Database-backed call chains live in
``tests/test_backfill_collection.py``, ``tests/test_run_backfill_command.py``
and ``tests/test_call_a_role_routing.py``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

PRODUCTION = ["A", "B1", "B2", "B3", "C1", "C2", "C3", "C4"]
# 12:00-18:00 US Pacific (UTC-7) on 2026-10-26.
SINCE, UNTIL = "2026-10-26T19:00:00+00:00", "2026-10-27T01:00:00+00:00"
LOWER = int(datetime(2026, 10, 26, 19, tzinfo=UTC).timestamp())
UPPER = LOWER + 6 * 3600
OAI_LIST, ANT_LIST = 2067500935769895374, 2067501173402460553
FROZEN = Path("docs/analysis/2026-10-27-215214-oai-anthropic-frozen-queries.json")
ROUTE_NAMES = ["A_OAI", "OAI_1", "OAI_2", "OAI_3", "B_OAI", "A_ANT", "ANT_1", "ANT_2", "ANT_3", "B_ANT"]


class _Query(list):
    """Just enough of a queryset for the author-context resolver."""

    def filter(self, **conditions):
        def keep(row):
            for key, value in conditions.items():
                if key == "account__author_id__in":
                    if row.account.author_id not in value:
                        return False
                elif key == "account__data_source_id":
                    continue
                elif getattr(row, key) != value:
                    return False
            return True

        return _Query(row for row in self if keep(row))

    def select_related(self, *fields):
        return self

    def values_list(self, field, flat=False):
        assert field == "account__author_id" and flat
        return [row.account.author_id for row in self]


def _membership(list_id, author_id, *, active=True):
    return SimpleNamespace(
        list_id=list_id, active=active, account=SimpleNamespace(author_id=author_id),
        source="snapshot", source_run_id=f"snapshot-{list_id}", last_complete_reconciliation_at=None,
    )


def _edge(author_id, brand_id, role_id):
    return SimpleNamespace(account=SimpleNamespace(author_id=author_id), brand_id=brand_id, role_id=role_id)


@pytest.fixture
def roster(monkeypatch):
    """Replace only the membership and role rows; everything else is real."""
    import core.models
    from monitor import list_membership

    def seed(memberships=(), edges=()):
        members = SimpleNamespace(objects=_Query(memberships))
        monkeypatch.setattr(core.models, "TwitterListMembership", members)
        monkeypatch.setattr(list_membership, "TwitterListMembership", members)
        monkeypatch.setattr(list_membership, "BrandAccount", SimpleNamespace(objects=_Query(edges)))

    seed()
    return seed


@pytest.fixture
def cfg(monkeypatch, roster):
    from scripts import backfill_campaign as campaign
    from x_monitor.config import load_config

    monkeypatch.setattr(campaign, "database_identity", lambda: {"name": "xbackfiller", "user": "xbackfiller"})
    return load_config(Path("config.yaml"))


@pytest.fixture
def main_list(cfg):
    from monitor.cycle import _resolve_x_monitor_list_id

    value = _resolve_x_monitor_list_id(cfg)
    assert value is not None
    return value


def _routes():
    queries = {
        "A_OAI": f"(list:{OAI_LIST}) min_faves:0 -from:xxyweb3",
        "A_ANT": f"(list:{ANT_LIST}) min_faves:0 -from:xxyweb3",
    }
    exclusions = {"OAI_2": ["Warhammer", "40k"], "OAI_3": ["Solana", "$SOL"], "ANT_1": ["Monet", "Debussy"]}
    return [
        {
            "name": name,
            "host_call_id": "A" if name.startswith("A_") else "B1",
            "query": queries.get(name, f"({name.replace('_', ' ')} OR route{index}) min_faves:0 -from:xxyweb3"),
            "not_include": exclusions.get(name, []),
        }
        for index, name in enumerate(ROUTE_NAMES)
    ]


def _window(**changes):
    return {
        "since": SINCE, "until": UNTIL, "call_ids": list(PRODUCTION), "slice_seconds": 300,
        "routes": _routes(), "author_list_ids": [OAI_LIST, ANT_LIST],
        "ceilings": {"maximum_api_requests": 7000, "max_usd": "30", "maximum_model_requests": 100000},
        "spend_basis": "settled",
    } | changes


def _manifest(cfg, window, **kwargs):
    from scripts import backfill_campaign as campaign

    return campaign.manifest(
        cfg, windows=[window], campaign_name="oai-anthropic-size",
        deadline=kwargs.pop("deadline", datetime(2026, 10, 30, tzinfo=UTC)),
        expected_revision="r" * 40, **kwargs,
    )


def test_size_window_plans_1296_unique_sliced_units_without_rare_extra(cfg, main_list):
    frozen = _manifest(cfg, _window())
    window = frozen["windows"][0]
    scope = window["collection_definition"]["scope"]
    units = scope["units"]
    keys = [unit["scope_key"] for unit in units]
    assert len(units) == 1296 == 18 * 72
    assert len(set(keys)) == len(keys)
    assert {unit["ownership"]["call_id"] for unit in units} == set(PRODUCTION)
    assert all(set(unit["ownership"]) == {"call_id", "query", "since_epoch", "until_epoch"} for unit in units)
    assert scope["selected_call_ids"] == scope["required_call_ids"]
    assert sorted(scope["required_call_ids"]) == sorted(PRODUCTION)

    by_route = {}
    for unit in units:
        route, lower, upper = unit["scope_key"].rsplit(":", 2)
        assert (int(lower), int(upper)) == (unit["ownership"]["since_epoch"], unit["ownership"]["until_epoch"])
        by_route.setdefault(route, []).append((int(lower), int(upper)))
    assert set(by_route) == set(PRODUCTION) | set(ROUTE_NAMES)
    expected_slices = [(at, at + 300) for at in range(LOWER, UPPER, 300)]
    assert all(slices == expected_slices for slices in by_route.values())

    metadata = scope["route_metadata"]
    route_units = [unit for unit in units if unit["scope_key"].split(":")[0] in ROUTE_NAMES]
    assert len(route_units) == len(metadata) == 720
    assert set(metadata) == {unit["scope_key"] for unit in route_units}
    routes = {route["name"]: route for route in _routes()}
    for unit in route_units:
        name = unit["scope_key"].split(":")[0]
        assert metadata[unit["scope_key"]] == {
            "name": name, "host_call_id": routes[name]["host_call_id"], "not_include": routes[name]["not_include"],
        }
        assert unit["ownership"]["call_id"] == routes[name]["host_call_id"]
        assert unit["ownership"]["query"] == routes[name]["query"]
    production_queries = {call: query for call, query in frozen["queries"] if call in PRODUCTION}
    for unit in units:
        if unit["scope_key"] not in metadata:
            assert unit["ownership"]["query"] == production_queries[unit["ownership"]["call_id"]]

    assert (window["maximum_api_requests"], window["max_usd"], window["maximum_model_requests"]) == (
        7000, "30", 100000,
    )
    assert scope["maximum_api_requests"] == 7000 and scope["maximum_model_requests"] == 100000
    assert window["spend_basis"] == "settled"
    assert frozen["model_reservation_ceiling_usd"] == "30"
    assert scope["author_scope"]["list_id"] == main_list
    assert scope["author_scope"]["list_ids"] == [main_list, OAI_LIST, ANT_LIST]


def test_command_dry_run_prints_the_same_sliced_manifest(cfg, tmp_path):
    path = tmp_path / "window.json"
    path.write_text(json.dumps({"name": "oai-anthropic-size", "windows": [_window()]}))
    output = StringIO()
    call_command("run_backfill", windows=path, stdout=output)
    frozen = json.loads(output.getvalue())
    scope = frozen["windows"][0]["collection_definition"]["scope"]
    assert frozen["campaign"] == "oai-anthropic-size"
    assert len(scope["units"]) == 1296 and len(scope["route_metadata"]) == 720
    assert frozen["windows"][0]["maximum_api_requests"] == 7000
    assert frozen["windows"][0]["spend_basis"] == "settled"


def test_legacy_rows_reach_the_manifest_as_plain_bounds(monkeypatch, tmp_path):
    """Regression net: rows with only since/until keep today's input shape."""
    import monitor.management.commands.run_backfill as command

    seen = []
    monkeypatch.setattr(command, "manifest", lambda cfg, **kw: seen.append(kw) or {"deadline": "unused"})
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"windows": [{"since": "2026-07-01", "until": "2026-07-02"}],
                                "supplemental_queries": [{"call_id": "B1", "query": "alias"}]}))
    call_command("run_backfill", windows=path, stdout=StringIO())
    assert seen[0]["windows"] == [("2026-07-01", "2026-07-02")]
    assert seen[0]["supplemental_queries"] == [("B1", "alias")]
    assert seen[0]["campaign_name"].startswith("x-backfill-")


@pytest.mark.parametrize("field", ["name", "slices", "not_include"])
def test_unknown_window_fields_are_rejected(cfg, tmp_path, field):
    path = tmp_path / "window.json"
    path.write_text(json.dumps({"windows": [_window(**{field: 1})]}))
    with pytest.raises(CommandError, match="window_field"):
        call_command("run_backfill", windows=path, stdout=StringIO())


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda routes: routes[1].update(name="B1"), "route_name"),
        (lambda routes: routes[1].update(name="RARE_EXTRA"), "route_name"),
        (lambda routes: routes[2].update(name=routes[1]["name"]), "route_name"),
        (lambda routes: routes[1].update(name="oai_1"), "route_name"),
        (lambda routes: routes[0].update(query="(OpenAI OR GPT) min_faves:0"), "route_list_search"),
        (lambda routes: routes[0].update(query="(list:999) min_faves:0"), "route_author_list"),
        (lambda routes: routes[1].update(host_call_id="C9"), "route_host"),
        (lambda routes: routes[1].update(not_include=["Solana", ""]), "invalid_route"),
        (lambda routes: routes[1].update(not_include="Solana"), "invalid_route"),
        (lambda routes: routes[1].update(extra=True), "invalid_route"),
        (lambda routes: routes[1].update(query="OpenAI since_time:1"), "invalid_route_query"),
    ],
)
def test_invalid_routes_are_rejected_before_any_job(cfg, mutate, code):
    routes = _routes()
    mutate(routes)
    with pytest.raises(ValueError, match=code):
        _manifest(cfg, _window(routes=routes))


def test_route_host_must_be_a_selected_call(cfg):
    with pytest.raises(ValueError, match="route_host"):
        _manifest(cfg, _window(call_ids=["A", "B2"]))


def test_route_suffixed_query_over_512_characters_is_rejected_at_manifest_time(cfg):
    suffix = len(f" since_time:{LOWER} until_time:{UPPER}")
    routes = _routes()
    routes[1]["query"] = "x" * (512 - suffix)
    frozen = _manifest(cfg, _window(routes=routes))
    longest = max(len(unit["ownership"]["query"]) for unit in frozen["windows"][0]["collection_definition"]["scope"]["units"])
    assert longest + suffix == 512
    routes[1]["query"] = "x" * (513 - suffix)
    with pytest.raises(ValueError, match="invalid_route_query"):
        _manifest(cfg, _window(routes=routes))


def test_request_ceiling_must_exceed_the_unit_count(cfg):
    with pytest.raises(ValueError, match="units_exceed_request_allowance"):
        _manifest(cfg, _window(ceilings={"maximum_api_requests": 1000}))
    with pytest.raises(ValueError, match="units_exceed_request_allowance"):
        _manifest(cfg, _window(ceilings={"maximum_api_requests": 1296}))
    assert _manifest(cfg, _window(ceilings={"maximum_api_requests": 1297}))["windows"][0]["maximum_api_requests"] == 1297


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"slice_seconds": 0}, "slice_seconds"),
        ({"slice_seconds": True}, "slice_seconds"),
        ({"slice_seconds": 7}, "slice_seconds"),
        ({"slice_seconds": "300"}, "slice_seconds"),
        ({"ceilings": {"max_usd": 30}}, "ceilings"),
        ({"ceilings": {"max_usd": "0"}}, "ceilings"),
        ({"ceilings": {"max_usd": "NaN"}}, "ceilings"),
        ({"ceilings": {"maximum_api_requests": 0}}, "ceilings"),
        ({"ceilings": {"maximum_model_requests": True}}, "ceilings"),
        ({"ceilings": {"budget": 1}}, "ceilings"),
        ({"ceilings": {}}, "ceilings"),
        ({"spend_basis": "actual"}, "spend_basis"),
        ({"author_list_ids": ["2067500935769895374"]}, "author_list_ids"),
        ({"author_list_ids": [OAI_LIST, OAI_LIST]}, "author_list_ids"),
        ({"call_ids": ["A", "A"]}, "call_ids"),
        ({"call_ids": []}, "call_ids"),
        ({"call_ids": ["A", "B1", "UNKNOWN"]}, "call_ids"),
    ],
)
def test_invalid_window_options_are_rejected(cfg, changes, code):
    with pytest.raises(ValueError, match=code):
        _manifest(cfg, _window(**changes))


def test_partial_ceilings_override_only_their_own_limit(cfg):
    window = _window(ceilings={"max_usd": "12.50"})
    del window["slice_seconds"]
    window = _manifest(cfg, window)["windows"][0]
    assert window["max_usd"] == "12.50"
    assert window["maximum_api_requests"] == 1250 and window["maximum_model_requests"] == 12500


def test_routes_without_slicing_use_one_whole_window_unit_each(cfg):
    window = _window()
    del window["slice_seconds"]
    scope = _manifest(cfg, window)["windows"][0]["collection_definition"]["scope"]
    keys = [unit["scope_key"] for unit in scope["units"]]
    assert sorted(scope["required_call_ids"]) == sorted(PRODUCTION)
    assert keys == scope["required_call_ids"] + [f"{name}:{LOWER}:{UPPER}" for name in ROUTE_NAMES]
    assert set(scope["route_metadata"]) == set(keys[8:])


def test_spend_basis_and_routes_are_omitted_when_not_requested(cfg):
    window = _manifest(cfg, {"since": SINCE, "until": UNTIL, "call_ids": list(PRODUCTION)})["windows"][0]
    scope = window["collection_definition"]["scope"]
    assert "spend_basis" not in window and "route_metadata" not in scope
    assert "list_ids" not in scope["author_scope"]
    assert [unit["scope_key"] for unit in scope["units"]] == scope["required_call_ids"]
    assert sorted(scope["required_call_ids"]) == sorted(PRODUCTION)


def _differences(left, right, path=()):
    if isinstance(left, dict) and isinstance(right, dict):
        found = set()
        for key in set(left) | set(right):
            found |= _differences(left.get(key), right.get(key), (*path, key))
        return found
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        found = set()
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            found |= _differences(a, b, (*path, index))
        return found
    return set() if left == right else {path}


def test_rebuilding_from_the_same_input_changes_only_time_dependent_fields(cfg):
    from scripts import backfill_campaign as campaign

    first = campaign.manifest(cfg, windows=[_window()], campaign_name="size", expected_revision="r" * 40)
    second = campaign.manifest(cfg, windows=[_window()], campaign_name="size", expected_revision="r" * 40)
    allowed = {
        ("deadline",),
        ("windows", 0, "collection_definition", "scope", "deadline"),
        ("windows", 0, "collection_definition", "scope", "author_scope", "observed_at"),
    }
    assert _differences(first, second) <= allowed
    for frozen in (first, second):
        frozen.pop("deadline")
        scope = frozen["windows"][0]["collection_definition"]["scope"]
        scope.pop("deadline")
        scope["author_scope"].pop("observed_at")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.skipif(not FROZEN.exists(), reason="size-test frozen query file absent")
def test_frozen_size_routes_are_carried_byte_identically(cfg):
    rows = json.loads(FROZEN.read_text())["new"]
    routes = [{"name": row["name"], "host_call_id": "A" if row["name"].startswith("A_") else "B1",
               "query": row["text"], "not_include": row["not_include"]} for row in rows]
    assert [route["name"] for route in routes] == ROUTE_NAMES
    scope = _manifest(cfg, _window(routes=routes))["windows"][0]["collection_definition"]["scope"]
    assert len(scope["units"]) == 1296
    texts = {row["name"]: row["text"] for row in rows}
    exclusions = {row["name"]: row["not_include"] for row in rows}
    for unit in scope["units"]:
        metadata = scope["route_metadata"].get(unit["scope_key"])
        if metadata is not None:
            assert unit["ownership"]["query"] == texts[metadata["name"]]
            assert metadata["not_include"] == exclusions[metadata["name"]]


# ---------------------------------------------------------------------------
# Route exclusions reach the shared runner (U2 step 5)
# ---------------------------------------------------------------------------

def _planned_runner(cfg, call_id, *, query, route_not_include):
    from monitor.backfill_resources import BackfillBudget, BackfillContext
    from monitor.cycle import CycleRunner

    context = BackfillContext(
        budget=BackfillBudget(max_api_requests=1, max_llm_calls=0, run_seconds=60),
        query_override=query, match_scheduled_policy=True, route_not_include=route_not_include,
    )
    runner = CycleRunner(cfg=cfg, cycle_kind="backfill", _backfill_call_ids=[call_id], _backfill_context=context)
    return next(call for call in runner._plan_calls() if call.call_id == call_id)


def test_route_exclusions_replace_the_host_list_while_production_keeps_its_own(cfg, settings):
    from monitor.cycle import _matches_any_term, plan_calls_for_cycle

    settings.X_MONITOR_CYCLE_BRAND_FILTER = ",".join(cfg.enabled_models)
    production = {call.call_id: call for call in plan_calls_for_cycle(cfg, scheduled_exclusions=True)}
    assert production["C1"].not_include, "C1 must carry its own F1 exclusions for this pin"

    oai_3 = _planned_runner(cfg, "B1", query="(Sora OR Sol) min_faves:0", route_not_include=("Solana", "$SOL"))
    c1 = _planned_runner(cfg, "C1", query=production["C1"].query_string, route_not_include=None)
    hosted_production = _planned_runner(cfg, "B1", query=production["B1"].query_string, route_not_include=None)
    assert oai_3.query_string == "(Sora OR Sol) min_faves:0"
    assert oai_3.not_include == ["Solana", "$SOL"]
    assert c1.not_include == production["C1"].not_include
    assert hosted_production.not_include == production["B1"].not_include

    def dropped(call, text):
        return _matches_any_term(text, "", [term.lower() for term in call.not_include if term])

    assert dropped(oai_3, "Sol is pumping on Solana today")
    assert not dropped(oai_3, "Sora ships a new model")
    f1_term = production["C1"].not_include[0]
    assert dropped(c1, f"Kimi wins the {f1_term} race")
    assert not dropped(c1, "Solana and Kimi")


def test_empty_route_exclusions_clear_the_host_list(cfg, settings):
    from monitor.cycle import plan_calls_for_cycle

    settings.X_MONITOR_CYCLE_BRAND_FILTER = ",".join(cfg.enabled_models)
    production = {call.call_id: call for call in plan_calls_for_cycle(cfg, scheduled_exclusions=True)}
    hosted = _planned_runner(cfg, "C1", query="(OpenAI) min_faves:0", route_not_include=())
    assert production["C1"].not_include and hosted.not_include == []


def test_scope_route_exclusions_are_read_per_unit():
    from monitor.backfill_collection import route_not_include

    scope = {"route_metadata": {"OAI_3:1:2": {"name": "OAI_3", "host_call_id": "B1", "not_include": ["Solana"]},
                                "B_OAI:1:2": {"name": "B_OAI", "host_call_id": "B1", "not_include": []}}}
    assert route_not_include(scope, "OAI_3:1:2") == ("Solana",)
    assert route_not_include(scope, "B_OAI:1:2") == ()
    assert route_not_include(scope, "B1:1:2") is None
    assert route_not_include({}, "B1") is None


@pytest.mark.parametrize(
    "metadata,code",
    [
        ({"missing:1:2": {"name": "OAI_3", "host_call_id": "B1", "not_include": []}}, "unknown scope"),
        ({"OAI_3:1:2": {"name": "OAI_3", "host_call_id": "A", "not_include": []}}, "host"),
        ({"OAI_3:1:2": {"name": "OAI_3", "host_call_id": "B1", "not_include": "Solana"}}, "exclusions"),
        ({"OAI_3:1:2": {"name": "OAI_3", "host_call_id": "B1", "not_include": [1]}}, "exclusions"),
        ({"OAI_3:1:2": {"name": "OAI_3", "host_call_id": "B1"}}, "fields"),
        ({"OAI_3:1:2": {"name": None, "host_call_id": "B1", "not_include": []}}, "name"),
        ([], "object"),
    ],
)
def test_saved_route_metadata_is_validated(metadata, code):
    from monitor.backfill_collection import validate_route_metadata

    units = [{"scope_key": "OAI_3:1:2", "ownership": {"call_id": "B1"}},
             {"scope_key": "B1:1:2", "ownership": {"call_id": "B1"}}]
    with pytest.raises(ValueError, match=code):
        validate_route_metadata(metadata, units)
    validate_route_metadata({"OAI_3:1:2": {"name": "OAI_3", "host_call_id": "B1", "not_include": ["Solana"]}}, units)


# ---------------------------------------------------------------------------
# U3: frozen author contexts across the main list and the lab lists
# ---------------------------------------------------------------------------

def _plan(cfg, **kwargs):
    from monitor.backfill_collection import plan_job_definition

    return plan_job_definition(
        cfg=cfg, since_epoch=LOWER, until_epoch=UPPER, brands=["qwen"], requests=200, model_requests=500,
        seconds=300, maximum_requests=7000, maximum_models=100000, call_ids=["A"], **kwargs,
    )


def test_author_contexts_union_three_lists_with_official_precedence(cfg, roster, main_list):
    roster(
        memberships=[
            _membership(main_list, "both"), _membership(OAI_LIST, "both"),
            _membership(OAI_LIST, "openai-official"), _membership(ANT_LIST, "anthropic-staff"),
            _membership(OAI_LIST, "roleless"), _membership(ANT_LIST, "inactive", active=False),
        ],
        edges=[
            _edge("both", "openai", "official"), _edge("both", "deepseek", "staff"),
            _edge("openai-official", "openai", "official"), _edge("anthropic-staff", "anthropic", "staff"),
            _edge("inactive", "anthropic", "official"),
        ],
    )
    author_scope = _plan(cfg, author_list_ids=[OAI_LIST, ANT_LIST])["scope"]["author_scope"]
    assert author_scope["list_id"] == main_list
    assert author_scope["list_ids"] == [main_list, OAI_LIST, ANT_LIST]
    contexts = author_scope["contexts"]
    assert set(contexts) == {"both", "openai-official", "anthropic-staff", "roleless"}
    assert (contexts["both"]["official_brands"], contexts["both"]["staff_brands"]) == (["openai"], ["deepseek"])
    # The first list that names an author supplies its membership evidence.
    assert contexts["both"]["membership_run_id"] == f"snapshot-{main_list}"
    assert contexts["openai-official"]["official_brands"] == ["openai"]
    assert contexts["anthropic-staff"]["staff_brands"] == ["anthropic"]
    assert contexts["roleless"]["official_brands"] == contexts["roleless"]["staff_brands"] == []
    assert author_scope["degraded"] == ["missing_brand_role:roleless"]

    from monitor.backfill_resources import BackfillBudget, BackfillContext
    from monitor.cycle import CycleRunner

    runner = CycleRunner(cfg=cfg, cycle_kind="backfill", _backfill_context=BackfillContext(
        budget=BackfillBudget(max_api_requests=1, max_llm_calls=0, run_seconds=60),
        author_contexts=json.loads(json.dumps(contexts)),
    ))
    items = [{"id": author, "author_id": author, "text": "no tracked words"}
             for author in ("both", "openai-official", "anthropic-staff", "roleless", "outsider")]
    runner._prepare_call_a_roles(items, list_id=main_list)
    seeded = {item["id"]: (item.get("_author_seed_brands"), item.get("_author_staff_brands"),
                           item.get("_call_a_staff_candidate")) for item in items}
    assert seeded == {
        "both": (["openai"], [], False),
        "openai-official": (["openai"], [], False),
        "anthropic-staff": ([], ["anthropic"], True),
        "roleless": (None, None, None),
        "outsider": (None, None, None),
    }


def test_single_list_author_scope_keeps_its_frozen_shape(cfg, roster, main_list):
    """Regression net: without lab lists the frozen author scope is unchanged."""
    roster(memberships=[_membership(main_list, "member"), _membership(OAI_LIST, "lab-only")],
           edges=[_edge("member", "qwen", "official"), _edge("lab-only", "openai", "official")])
    author_scope = _plan(cfg)["scope"]["author_scope"]
    assert set(author_scope) == {"observed_at", "list_id", "historical_membership_reconstructed",
                                 "contexts", "degraded"}
    assert author_scope["list_id"] == main_list and set(author_scope["contexts"]) == {"member"}
    assert author_scope["contexts"]["member"] == {
        "author_id": "member", "official_brands": ["qwen"], "staff_brands": [],
        "membership_source": "snapshot", "membership_run_id": f"snapshot-{main_list}",
        "last_complete_reconciliation_at": None,
    }


@pytest.mark.parametrize("value", [[], ["1"], [True], [0], [OAI_LIST, OAI_LIST], "1", "main"])
def test_invalid_author_list_selection_is_rejected(cfg, main_list, value):
    with pytest.raises(ValueError, match="author list"):
        _plan(cfg, author_list_ids=[main_list] if value == "main" else value)


def test_union_helper_keeps_first_membership_evidence_and_unique_degradation():
    from monitor.backfill_collection import union_author_contexts
    from monitor.list_membership import AuthorRoleContext

    def context(author, official=(), staff=(), run="main"):
        return AuthorRoleContext(author_id=author, official_brands=official, staff_brands=staff,
                                 membership_source="snapshot", membership_run_id=run,
                                 last_complete_reconciliation_at=datetime(2026, 10, 1, tzinfo=UTC) + timedelta())

    merged, degraded = union_author_contexts([
        ({"a": context("a", official=("qwen",))}, ["missing_brand_role:x"]),
        ({"a": context("a", official=("openai",), staff=("deepseek",), run="lab"),
          "x": context("x", run="lab")}, ["missing_brand_role:x"]),
    ])
    assert merged["a"].official_brands == ("openai", "qwen")
    assert merged["a"].staff_brands == ("deepseek",)
    assert merged["a"].membership_run_id == "main"
    assert merged["x"].membership_run_id == "lab"
    assert degraded == ["missing_brand_role:x"]
