"""Offline tests for the OpenAI/Anthropic size-test preflight (plan U7).

Plan: docs/plans/2026-10-27-113859-ops-oai-anthropic-size-20261027-plan.md

Every test runs on a synthetic manifest built from the frozen query file and a
synthetic document shaped like the read-only xbackfiller SQL output. The
keyword and roster tables are the committed CSVs. No database, git object or
provider is touched; HTTP is replaced by a fake.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts import backfill_size_preflight as preflight
from scripts.backfill_size_seed import read_keyword_csv, read_roster_csv

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "scripts" / "backfill_size_preflight_xbackfiller.sql"
FROZEN_PATH = ROOT / "docs" / "analysis" / "2026-10-27-215214-oai-anthropic-frozen-queries.json"
KEYWORDS_PATH = ROOT / "docs" / "analysis" / "2026-10-28-182625-oai-anthropic-keywords.csv"
ROSTER_PATH = ROOT / "docs" / "analysis" / "2026-10-28-182625-oai-anthropic-roster.csv"
POLICY_PATH = ROOT / "config" / "harvest_policy.yaml"

FROZEN = json.loads(FROZEN_PATH.read_text())
FROZEN_SHA = preflight.FROZEN_QUERIES_SHA256
KEYWORDS = read_keyword_csv(KEYWORDS_PATH)
ROSTER = read_roster_csv(ROSTER_PATH)

NOW = datetime(2026, 10, 28, 10, 0, tzinfo=UTC)
LOWER = int(datetime(2026, 10, 27, 19, tzinfo=UTC).timestamp())
SLICES = [(LOWER, LOWER + 300), (LOWER + 300, LOWER + 600)]
MAIN_LIST = preflight.MAIN_LIST
OAI_LIST, ANT_LIST = 2067500935769895374, 2067501173402460553
XB_HOST = "dpg-dbfemu2vcj2c73fsafe0-a"
MAIN_AUTHORS = ("900001", "900002", "900003")
FAKE_TWITTER_KEY = "tw-FAKE-key-0123456789abcdef"
FAKE_DEEPINFRA_KEY = "di-FAKE-key-fedcba9876543210"


# Fixtures --------------------------------------------------------------------


def _context(author_id, official=(), staff=()):
    return {
        "author_id": author_id, "official_brands": list(official), "staff_brands": list(staff),
        "membership_source": "snapshot", "membership_run_id": "", "last_complete_reconciliation_at": None,
    }


def seeded_contexts():
    contexts = {author: _context(author, official=["zhipu"]) for author in MAIN_AUTHORS}
    for row in ROSTER:
        role = "official_brands" if row.role == "official" else "staff_brands"
        contexts.setdefault(row.author_id, _context(row.author_id))[role].append(row.brand)
    return contexts


def make_manifest(*, frozen=FROZEN, contexts=None, degraded=None):
    units, metadata = [], {}
    for row in frozen["baseline"]:
        for lo, hi in SLICES:
            units.append({"scope_key": f"{row['name']}:{lo}:{hi}", "scope_kind": "x_query", "ownership": {
                "call_id": row["name"], "query": row["text"], "since_epoch": lo, "until_epoch": hi}})
    for row in frozen["new"]:
        host = "A" if row["name"].startswith("A_") else "B1"
        for lo, hi in SLICES:
            key = f"{row['name']}:{lo}:{hi}"
            units.append({"scope_key": key, "scope_kind": "x_query", "ownership": {
                "call_id": host, "query": row["text"], "since_epoch": lo, "until_epoch": hi}})
            metadata[key] = {"name": row["name"], "host_call_id": host, "not_include": list(row["not_include"])}
    scope = {
        "credential_purpose": "on-demand",
        "database": {"name": "xbackfiller", "user": "xbackfiller"},
        "response_storage": "database",
        "database_host": XB_HOST,
        "maximum_api_requests": 7000,
        "units": units,
        "route_metadata": metadata,
        "author_scope": {
            "list_id": MAIN_LIST, "list_ids": [MAIN_LIST, OAI_LIST, ANT_LIST],
            "contexts": seeded_contexts() if contexts is None else contexts,
            "degraded": list(degraded or []),
        },
    }
    return {
        "campaign": "oai-anthropic-size",
        "database": {"name": "xbackfiller", "user": "xbackfiller"},
        "credential_purpose": "on-demand",
        "queries": [[row["name"], row["text"]] for row in frozen["baseline"]],
        "windows": [{"index": 1, "maximum_api_requests": 7000, "collection_definition": {"scope": scope}}],
    }


def make_doc(*, seeded=False, **changes):
    memberships = [{"list_id": str(MAIN_LIST), "author_id": author} for author in MAIN_AUTHORS]
    keywords = []
    if seeded:
        memberships += [{"list_id": str(row.list_id), "author_id": row.author_id} for row in ROSTER]
        keywords = [{"brand": row.brand, "pattern": row.pattern, "is_regex": False} for row in KEYWORDS]
    doc = {
        "format": preflight.PREFLIGHT_FORMAT,
        "database": "xbackfiller",
        "session_user": "xbackfiller",
        "current_user": "xbackfiller",
        "transaction_read_only": "on",
        "generated_at": NOW.isoformat(),
        "july": {
            "job": {
                "id": preflight.JULY_JOB_ID, "job_key": "july2026-current-20261026-2026-07-21-w3/3",
                "state": "paused", "mode": "historical", "source_id": "x", "definition_sha256": "a" * 64,
                "active_run_id": None, "last_attempt_id": None, "last_success_id": None,
                "next_due_at": None, "author_contexts": 207,
            },
            "run_count": 5, "runs_by_status": {"failed": 1, "partial": 4}, "scope_rows": 3240,
        },
        "running_historical_runs": [],
        "ready_historical_jobs": [],
        "advisory_locks": [],
        "brands": [{"nickname": "anthropic", "is_sentinel": False}, {"nickname": "openai", "is_sentinel": False}],
        "brand_keywords": keywords,
        "list_memberships": memberships,
        "table_sizes": {"posts": 400_000_000, "collection_scope_runs": 120_000_000},
        "database_bytes": 651_925_183,
    }
    doc.update(changes)
    return doc


BRANCH_POLICY = POLICY_PATH.read_bytes()
DEPLOYED_POLICY = preflight.strip_branch_only_policy(BRANCH_POLICY.decode("utf-8"))[0].encode("utf-8")


def evaluate(stage="pre-seed", *, manifest=None, doc=None, frozen=FROZEN, deployed=DEPLOYED_POLICY, **kwargs):
    return preflight.evaluate(
        stage=stage,
        manifest=make_manifest() if manifest is None else manifest,
        doc=make_doc(seeded=stage == "post-seed") if doc is None else doc,
        frozen=frozen, frozen_sha256=kwargs.pop("frozen_sha256", FROZEN_SHA),
        keywords=KEYWORDS, roster=ROSTER,
        deployed_revision="e5edf737", deployed_policy=deployed, branch_policy=BRANCH_POLICY,
        disk_gb=kwargs.pop("disk_gb", 20), projected_growth_gb=kwargs.pop("projected_growth_gb", 2),
        now=kwargs.pop("now", NOW), **kwargs,
    )


def check(result, number):
    return next(item for item in result["checks"] if item["id"] == number)


# Clean runs ------------------------------------------------------------------


def test_clean_pre_seed_passes_with_keyword_and_roster_checks_pending():
    result = evaluate("pre-seed")

    statuses = {item["id"]: item["status"] for item in result["checks"]}
    assert statuses == {1: "pass", 2: "pass", 3: "pass", 4: "pass", 5: "pending", 6: "pending",
                        7: "not_run", 8: "pass", 9: "pass"}
    assert result["ok"] is True


def test_clean_post_seed_passes_every_check():
    result = evaluate("post-seed")

    statuses = {item["id"]: item["status"] for item in result["checks"]}
    assert statuses == {1: "pass", 2: "pass", 3: "pass", 4: "pass", 5: "pass", 6: "pass",
                        7: "not_run", 8: "pass", 9: "pass"}
    assert result["ok"] is True
    assert check(result, 5)["evidence"]["missing"] == []


# Check 1: identity -----------------------------------------------------------


def test_non_xbackfiller_session_user_fails_check_1():
    result = evaluate(doc=make_doc(session_user="pushinweight"))

    assert check(result, 1)["status"] == "fail"
    assert result["ok"] is False


def test_manifest_window_on_another_database_fails_check_1():
    manifest = make_manifest()
    manifest["windows"][0]["collection_definition"]["scope"]["database"] = {"name": "pushinweight", "user": "xbackfiller"}

    assert check(evaluate(manifest=manifest), 1)["status"] == "fail"


def test_manifest_window_without_database_storage_fails_check_1():
    manifest = make_manifest()
    manifest["windows"][0]["collection_definition"]["scope"]["response_storage"] = "staging"

    assert check(evaluate(manifest=manifest), 1)["status"] == "fail"


def test_manifest_window_on_another_host_fails_check_1():
    manifest = make_manifest()
    manifest["windows"][0]["collection_definition"]["scope"]["database_host"] = "dpg-other-a.oregon-postgres.render.com"

    assert check(evaluate(manifest=manifest), 1)["status"] == "fail"
    manifest["windows"][0]["collection_definition"]["scope"]["database_host"] = XB_HOST + ".oregon-postgres.render.com"
    assert check(evaluate(manifest=manifest), 1)["status"] == "pass"


# Check 2: July held ----------------------------------------------------------


def _running(lease):
    return {"run_id": "e50e3efc-0773-4acf-9642-5240a1ff1a25", "job_id": "3cc51270-71ec-4699-8b0d-2d4e4997cc33",
            "job_key": "july2026-staging-20261023-2026-07-17/4", "job_state": "ready",
            "started_at": "2026-10-24T16:15:10+00:00", "lease_expires_at": lease}


def test_live_lease_fails_check_2():
    live = (NOW + timedelta(minutes=5)).isoformat()
    result = evaluate(doc=make_doc(running_historical_runs=[_running(live)]))

    assert check(result, 2)["status"] == "fail"
    assert "july2026-staging-20261023-2026-07-17/4" in " ".join(check(result, 2)["problems"])


def test_running_run_without_lease_expiry_counts_as_live():
    assert check(evaluate(doc=make_doc(running_historical_runs=[_running(None)])), 2)["status"] == "fail"


def test_expired_lease_is_reported_but_passes_check_2():
    result = evaluate(doc=make_doc(running_historical_runs=[_running("2026-10-24T16:21:10+00:00")]))

    assert check(result, 2)["status"] == "pass"
    assert check(result, 2)["evidence"]["stale_running_runs"][0]["job_key"] == "july2026-staging-20261023-2026-07-17/4"


@pytest.mark.parametrize("state", ["running", "ready"])
def test_july_job_not_held_fails_check_2(state):
    doc = make_doc()
    doc["july"]["job"]["state"] = state

    assert check(evaluate(doc=doc), 2)["status"] == "fail"


def test_missing_july_job_fails_check_2():
    doc = make_doc()
    doc["july"]["job"] = None

    assert check(evaluate(doc=doc), 2)["status"] == "fail"


def test_held_advisory_lock_fails_check_2():
    lock = {"pid": 4242, "classid": 1, "objid": 2, "objsubid": 1, "granted": True, "mode": "ExclusiveLock"}

    assert check(evaluate(doc=make_doc(advisory_locks=[lock])), 2)["status"] == "fail"


def test_stale_snapshot_fails_check_2():
    old = make_doc(generated_at=(NOW - timedelta(hours=2)).isoformat())

    assert check(evaluate(doc=old), 2)["status"] == "fail"


def test_july_snapshot_is_recorded():
    result = evaluate()

    assert result["july_snapshot"] == {
        "job_id": preflight.JULY_JOB_ID, "job_key": "july2026-current-20261026-2026-07-21-w3/3",
        "state": "paused", "definition_sha256": "a" * 64, "active_run_id": None,
        "author_contexts": 207, "run_count": 5, "runs_by_status": {"failed": 1, "partial": 4},
        "scope_rows": 3240,
    }


# Check 3: queries ------------------------------------------------------------


def _replace_route_query(manifest, name, text):
    scope = manifest["windows"][0]["collection_definition"]["scope"]
    for unit in scope["units"]:
        meta = scope["route_metadata"].get(unit["scope_key"])
        if meta and meta["name"] == name:
            unit["ownership"]["query"] = text


def test_one_byte_frozen_query_mismatch_fails_check_3_and_names_the_route():
    original = next(row["text"] for row in FROZEN["new"] if row["name"] == "OAI_2")
    manifest = make_manifest()
    _replace_route_query(manifest, "OAI_2", original[:-1] + ("x" if original[-1] != "x" else "y"))

    item = check(evaluate(manifest=manifest), 3)
    assert item["status"] == "fail"
    assert any(problem.startswith("OAI_2:") for problem in item["problems"])
    assert not any(problem.startswith("OAI_1:") for problem in item["problems"])


def test_production_query_mismatch_fails_check_3_and_names_the_call():
    manifest = make_manifest()
    scope = manifest["windows"][0]["collection_definition"]["scope"]
    for unit in scope["units"]:
        if unit["ownership"]["call_id"] == "C2" and unit["scope_key"] not in scope["route_metadata"]:
            unit["ownership"]["query"] += " "

    item = check(evaluate(manifest=manifest), 3)
    assert item["status"] == "fail"
    assert any(problem.startswith("C2:") for problem in item["problems"])


def test_suffixed_query_of_513_characters_fails_check_3():
    suffix = f" since_time:{SLICES[0][0]} until_time:{SLICES[0][1]}"
    frozen = json.loads(json.dumps(FROZEN))
    for length, expected in ((512, "pass"), (513, "fail")):
        long_text = "(OpenAI OR " + "a" * (length - len(suffix) - len("(OpenAI OR ") - 1) + ")"
        assert len(long_text + suffix) == length
        for row in frozen["new"]:
            if row["name"] == "OAI_1":
                row["text"] = long_text
        item = check(evaluate(manifest=make_manifest(frozen=frozen), frozen=frozen), 3)
        assert item["status"] == expected, item["problems"]
        if expected == "fail":
            assert any(p.startswith("OAI_1:") and "513" in p for p in item["problems"])


def test_missing_frozen_route_fails_check_3():
    frozen = json.loads(json.dumps(FROZEN))
    frozen["new"] = [row for row in frozen["new"] if row["name"] != "B_ANT"]

    item = check(evaluate(manifest=make_manifest(frozen=frozen)), 3)
    assert item["status"] == "fail"
    assert any("B_ANT" in problem for problem in item["problems"])


def test_frozen_file_digest_mismatch_fails_check_3():
    assert check(evaluate(frozen_sha256="0" * 64), 3)["status"] == "fail"


def test_deployed_policy_that_differs_fails_check_3():
    deployed = DEPLOYED_POLICY.replace(b"upstageai", b"upstageAI", 1)
    assert deployed != DEPLOYED_POLICY

    item = check(evaluate(deployed=deployed), 3)
    assert item["status"] == "fail"
    assert any("harvest_policy.yaml" in problem for problem in item["problems"])


def test_unreadable_deployed_policy_fails_check_3():
    assert check(evaluate(deployed=None), 3)["status"] == "fail"


def test_branch_only_block_is_the_only_allowed_policy_difference():
    text = BRANCH_POLICY.decode("utf-8")
    stripped, brands = preflight.strip_branch_only_policy(text)

    assert brands == ["anthropic", "openai"]
    assert "openai:" not in stripped and "co_packs:" in stripped
    assert preflight.strip_branch_only_policy(stripped) == (stripped, [])


def test_branch_only_block_naming_another_brand_is_refused():
    text = BRANCH_POLICY.decode("utf-8").replace("  anthropic:\n", "  mistral:\n", 1)

    with pytest.raises(ValueError):
        preflight.strip_branch_only_policy(text)


# Check 4: route exclusions ---------------------------------------------------


def test_route_not_include_that_differs_fails_check_4():
    manifest = make_manifest()
    scope = manifest["windows"][0]["collection_definition"]["scope"]
    for meta in scope["route_metadata"].values():
        if meta["name"] == "ANT_1":
            meta["not_include"] = meta["not_include"][:-1]

    item = check(evaluate(manifest=manifest), 4)
    assert item["status"] == "fail"
    assert any(problem.startswith("ANT_1:") for problem in item["problems"])


def test_route_not_include_order_matters_for_check_4():
    manifest = make_manifest()
    scope = manifest["windows"][0]["collection_definition"]["scope"]
    for meta in scope["route_metadata"].values():
        if meta["name"] == "OAI_3":
            meta["not_include"] = list(reversed(meta["not_include"]))

    assert check(evaluate(manifest=manifest), 4)["status"] == "fail"


# Check 5: keywords -----------------------------------------------------------


def test_missing_brand_keyword_fails_post_seed_and_is_pending_pre_seed():
    missing = KEYWORDS[5]
    doc = make_doc(seeded=True)
    doc["brand_keywords"] = [row for row in doc["brand_keywords"] if row["pattern"] != missing.pattern]

    post = check(evaluate("post-seed", doc=doc), 5)
    assert post["status"] == "fail"
    assert post["evidence"]["missing"] == [{"brand": missing.brand, "pattern": missing.pattern}]

    pre = check(evaluate("pre-seed", doc=make_doc()), 5)
    assert pre["status"] == "pending"


def test_regex_keyword_row_is_not_literal():
    doc = make_doc(seeded=True)
    doc["brand_keywords"][0]["is_regex"] = True

    assert check(evaluate("post-seed", doc=doc), 5)["status"] == "fail"


def test_keyword_for_the_wrong_brand_does_not_count():
    doc = make_doc(seeded=True)
    target = next(row for row in doc["brand_keywords"] if row["brand"] == "anthropic")
    target["brand"] = "openai"

    assert check(evaluate("post-seed", doc=doc), 5)["status"] == "fail"


# Check 6: lab-list author roles ----------------------------------------------


def test_roster_author_without_a_context_fails_post_seed():
    contexts = seeded_contexts()
    gone = next(row for row in ROSTER if row.brand == "anthropic" and row.role == "staff")
    del contexts[gone.author_id]
    manifest = make_manifest(contexts=contexts, degraded=[f"missing_brand_role:{gone.author_id}"])

    item = check(evaluate("post-seed", manifest=manifest), 6)
    assert item["status"] == "fail"
    assert gone.author_id in " ".join(item["problems"])
    assert item["evidence"]["roster_degraded"] == [f"missing_brand_role:{gone.author_id}"]


def test_roster_author_with_the_wrong_role_fails_post_seed():
    contexts = seeded_contexts()
    official = next(row for row in ROSTER if row.brand == "openai" and row.role == "official")
    contexts[official.author_id] = _context(official.author_id, staff=["openai"])

    assert check(evaluate("post-seed", manifest=make_manifest(contexts=contexts)), 6)["status"] == "fail"


def test_overlap_and_other_brand_roles_are_reported_not_failed():
    contexts = seeded_contexts()
    member = next(row for row in ROSTER if row.brand == "openai" and row.role == "staff")
    contexts[member.author_id]["staff_brands"].append("gpt")
    doc = make_doc(seeded=True)
    doc["list_memberships"].append({"list_id": str(MAIN_LIST), "author_id": member.author_id})

    item = check(evaluate("post-seed", manifest=make_manifest(contexts=contexts), doc=doc), 6)
    assert item["status"] == "pass"
    assert item["evidence"]["main_list_overlap"] == [
        {"author_id": member.author_id, "username": member.username, "brand": "openai"}]
    assert item["evidence"]["other_brand_roles"] == [{
        "author_id": member.author_id, "username": member.username, "brand": "openai",
        "other_official": [], "other_staff": ["gpt"]}]


def test_manifest_without_main_list_contexts_fails_post_seed_and_warns_pre_seed():
    contexts = {k: v for k, v in seeded_contexts().items() if k not in MAIN_AUTHORS}

    post = evaluate("post-seed", manifest=make_manifest(contexts=contexts))
    assert check(post, 6)["status"] == "fail"
    pre = evaluate("pre-seed", manifest=make_manifest(contexts={}))
    assert check(pre, 6)["status"] == "pending"
    assert any("main list" in warning for warning in pre["warnings"])


def test_manifest_without_lab_lists_fails_post_seed():
    manifest = make_manifest()
    manifest["windows"][0]["collection_definition"]["scope"]["author_scope"]["list_ids"] = [MAIN_LIST]

    assert check(evaluate("post-seed", manifest=manifest), 6)["status"] == "fail"


# Check 7: credentials ------------------------------------------------------


class FakeHttp:
    def __init__(self, credits, deepinfra_status=200):
        self.credits = credits
        self.deepinfra_status = deepinfra_status
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        if url == preflight.TWITTERAPI_INFO_URL:
            return 200, {"recharge_credits": self.credits, "user_id": "account-detail-not-reported"}
        if url == preflight.DEEPINFRA_ME_URL:
            return self.deepinfra_status, {"email": "someone@example.com"}
        raise AssertionError(url)


@pytest.fixture
def secrets(tmp_path):
    path = tmp_path / "env.secrets"
    path.write_text(
        "# local secrets\n"
        "TWITTERAPI_IO_API_KEY=legacy-must-not-be-used\n"
        f"export TWITTERAPI_IO_ON_DEMAND_API_KEY='{FAKE_TWITTER_KEY}'\n"
        f"DEEPINFRA_ON_DEMAND={FAKE_DEEPINFRA_KEY}\n"
    )
    return path


@pytest.mark.parametrize(("credits", "status"), [(1_000_000, "fail"), (2_100_000, "pass"), (16_531_104, "pass")])
def test_twitterapi_balance_must_cover_the_search_limit(secrets, credits, status):
    http = FakeHttp(credits)
    item = preflight.check_credentials(secrets_path=secrets, http_get=http)

    assert item["status"] == status
    assert item["evidence"]["twitterapi"]["recharge_credits"] == credits
    assert item["evidence"]["twitterapi"]["required_credits"] == 2_100_000
    assert http.calls[0] == (preflight.TWITTERAPI_INFO_URL, {"X-API-Key": FAKE_TWITTER_KEY,
                                                             "User-Agent": preflight.USER_AGENT})
    assert http.calls[1] == (preflight.DEEPINFRA_ME_URL, {"Authorization": f"Bearer {FAKE_DEEPINFRA_KEY}",
                                                          "User-Agent": preflight.USER_AGENT})


def test_deepinfra_key_that_does_not_respond_fails(secrets):
    assert preflight.check_credentials(secrets_path=secrets, http_get=FakeHttp(16_531_104, 401))["status"] == "fail"


def test_missing_on_demand_key_never_falls_back(tmp_path):
    path = tmp_path / "env.secrets"
    path.write_text("TWITTERAPI_IO_API_KEY=legacy\nTWITTERAPI_IO_SCHEDULED_API_KEY=scheduled\n"
                    "DEEPINFRA_API_KEY=other\nMINIMAX_API_KEY=other\n")
    http = FakeHttp(16_531_104)

    item = preflight.check_credentials(secrets_path=path, http_get=http)
    assert item["status"] == "fail"
    assert http.calls == []


def test_secret_parser_reads_only_the_exact_literal_assignment(tmp_path):
    path = tmp_path / "env.secrets"
    path.write_text(
        "DEEPINFRA_ON_DEMAND_OLD=wrong\n"
        "#DEEPINFRA_ON_DEMAND=commented\n"
        "XDEEPINFRA_ON_DEMAND=wrong\n"
        'export DEEPINFRA_ON_DEMAND="quoted value"\n'
        "TWITTERAPI_IO_ON_DEMAND_API_KEY=plain # trailing comment\n"
        "TWITTERAPI_IO_API_KEY=legacy\n"
    )
    assert preflight.read_secret(path, "DEEPINFRA_ON_DEMAND") == "quoted value"
    assert preflight.read_secret(path, "TWITTERAPI_IO_ON_DEMAND_API_KEY") == "plain"
    with pytest.raises(ValueError):
        preflight.read_secret(path, "TWITTERAPI_IO_API_KEY")

    empty = tmp_path / "empty.secrets"
    empty.write_text("DEEPINFRA_ON_DEMAND=\nexport TWITTERAPI_IO_ON_DEMAND_API_KEY=''\n")
    assert preflight.read_secret(empty, "DEEPINFRA_ON_DEMAND") is None
    assert preflight.read_secret(empty, "TWITTERAPI_IO_ON_DEMAND_API_KEY") is None
    assert preflight.read_secret(tmp_path / "absent.secrets", "DEEPINFRA_ON_DEMAND") is None


def test_credential_output_never_contains_key_values(secrets, tmp_path, monkeypatch, capsys):
    def leaky(url, headers):
        raise OSError(f"connection reset while sending {headers}")

    item = preflight.check_credentials(secrets_path=secrets, http_get=leaky)
    assert item["status"] == "fail"
    assert FAKE_TWITTER_KEY not in json.dumps(item) and FAKE_DEEPINFRA_KEY not in json.dumps(item)

    paths = write_inputs(tmp_path, stage="pre-seed")
    monkeypatch.setattr(preflight, "read_deployed_policy", lambda revision: DEPLOYED_POLICY)
    monkeypatch.setattr(preflight, "http_get_json", FakeHttp(16_531_104))
    code = preflight.main([*paths, "--stage", "pre-seed", "--check-credentials", "--secrets-file", str(secrets)])
    captured = capsys.readouterr()

    assert code == 0, captured.err
    output = captured.out + captured.err
    assert FAKE_TWITTER_KEY not in output and FAKE_DEEPINFRA_KEY not in output
    assert "someone@example.com" not in output and "account-detail-not-reported" not in output
    assert json.loads(captured.out)["checks"][6]["evidence"]["twitterapi"]["recharge_credits"] == 16_531_104


# Check 8 and 9: free space and the before-snapshot ----------------------------


def test_free_space_below_twice_projected_growth_fails_check_8():
    used = 16_000_000_000  # 4 GB free on a 20 GB disk
    passing = check(evaluate(doc=make_doc(database_bytes=used), projected_growth_gb=2), 8)
    failing = check(evaluate(doc=make_doc(database_bytes=used + 1), projected_growth_gb=2), 8)

    assert passing["status"] == "pass"
    assert failing["status"] == "fail"
    assert failing["evidence"]["stop_floor_database_bytes"] == used + 1 + 2_000_000_000


def test_size_snapshot_is_recorded_and_accepted_by_the_report():
    from scripts.backfill_size_report import load_table_sizes

    result = evaluate()
    assert check(result, 9)["status"] == "pass"
    assert result["size_before"]["database_bytes"] == 651_925_183
    assert load_table_sizes(json.dumps(result, indent=2)) == {"posts": 400_000_000, "collection_scope_runs": 120_000_000}


def test_missing_size_snapshot_fails_check_9():
    doc = make_doc()
    del doc["table_sizes"]

    assert check(evaluate(doc=doc), 9)["status"] == "fail"


# SQL and loading -------------------------------------------------------------

FORBIDDEN = ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE", "CREATE", "GRANT",
             "REVOKE", "COPY", "MERGE", "CALL", "VACUUM", "LOCK", "COMMIT")


def test_sql_file_is_a_read_only_transaction():
    text = SQL.read_text()
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--")).strip()

    assert text.startswith("BEGIN TRANSACTION READ ONLY;\n")
    assert text.rstrip().endswith("ROLLBACK;")
    for word in FORBIDDEN:
        assert not re.search(rf"\b{word}\b", text, re.IGNORECASE), word
    statements = [part.strip() for part in body.split(";") if part.strip()]
    assert statements[0] == "BEGIN TRANSACTION READ ONLY"
    assert statements[-1] == "ROLLBACK"
    assert all(re.match(r"(WITH|SELECT)\b", part) for part in statements[1:-1])
    # The text is passed inside a double-quoted shell argument.
    assert not set(text) & set('"$`\\')


def test_rendered_sql_names_the_july_job_and_has_no_placeholders():
    sql = preflight.xbackfiller_sql()

    assert f"'{preflight.JULY_JOB_ID}'::uuid" in sql
    assert "{{" not in sql
    with pytest.raises(ValueError):
        preflight.xbackfiller_sql(template=SQL.read_text().replace("SELECT jsonb_build_object", "DELETE FROM x; SELECT jsonb_build_object", 1))


def test_load_preflight_document_reads_render_psql_json_wrapper():
    doc = make_doc()
    aligned = f"BEGIN\n    preflight_input    \n-----------\n {json.dumps(doc)}\n(1 row)\n\nROLLBACK\n"
    wrapped = json.dumps({"output": aligned}, indent=2)

    assert preflight.load_preflight_document(wrapped) == doc


# Command line ----------------------------------------------------------------


def write_inputs(tmp_path, *, stage, manifest=None, doc=None):
    manifest_path = tmp_path / "manifest.json"
    doc_path = tmp_path / "xbackfiller.json"
    manifest_path.write_text(json.dumps(make_manifest() if manifest is None else manifest))
    body = make_doc(seeded=stage == "post-seed") if doc is None else doc
    body["generated_at"] = datetime.now(UTC).isoformat()
    doc_path.write_text(json.dumps({"output": f"BEGIN\n x \n---\n {json.dumps(body)}\n(1 row)\n\nROLLBACK\n"}))
    return ["--manifest", str(manifest_path), "--xbackfiller", str(doc_path), "--keywords", str(KEYWORDS_PATH),
            "--roster", str(ROSTER_PATH), "--deployed-revision", "e5edf737", "--frozen-queries", str(FROZEN_PATH)]


def test_main_exit_status_follows_the_required_checks(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(preflight, "read_deployed_policy", lambda revision: DEPLOYED_POLICY)

    assert preflight.main([*write_inputs(tmp_path, stage="pre-seed"), "--stage", "pre-seed"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is True
    assert "pending" in captured.err and "PASS" in captured.err

    assert preflight.main([*write_inputs(tmp_path, stage="pre-seed"), "--stage", "post-seed"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is False
    assert "FAIL" in captured.err


def test_main_prints_the_sql_without_other_inputs(capsys):
    assert preflight.main(["--print-xbackfiller-sql"]) == 0
    assert capsys.readouterr().out.strip() == preflight.xbackfiller_sql().strip()


def test_main_requires_inputs_for_a_check(capsys):
    with pytest.raises(SystemExit) as exc:
        preflight.main(["--stage", "pre-seed"])
    assert exc.value.code == 2
