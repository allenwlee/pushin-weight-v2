"""Guarded sync of production's main-list members and X roles into xbackfiller (plan U7).

Pure tests cover export parsing and refusals, the guard order, the catalog
projection and proof helpers, the command wiring and the read-only export SQL.
Database tests are PostgreSQL-only (``harvest_writer_lock`` requires it) and run
in the backfill workflow's fast CI step.
"""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from monitor import backfill_list_roles as sync_module
from monitor.backfill_list_roles import (
    FORMAT,
    MEMBERSHIP_SOURCE,
    SyncRefused,
    account_delta_proof,
    catalog_digests,
    contexts_proof,
    expected_contexts,
    load_document,
    read_export,
)
from monitor.list_membership import AuthorRoleContext

REPO = Path(__file__).resolve().parents[1]
EXPORT = REPO / "tests/fixtures/backfill_list_roles_export.json"
SQL = REPO / "scripts/backfill_list_roles_production.sql"
MAIN_LIST = 2067062923525275922
LAB, STAFFER, NO_ROLE = "900000000000000001", "900000000000000002", "900000000000000003"
ROLE_ONLY = "999999999999999999"
COMMAND = "sync_backfill_list_roles"


def _document() -> dict:
    return load_document(EXPORT.read_text(encoding="utf-8"), FORMAT)


def _write(tmp_path: Path, document: dict, name: str = "export.json") -> Path:
    """Save a document the way `render psql -o json` wraps psql's aligned output."""
    path = tmp_path / name
    body = json.dumps(document, ensure_ascii=False)
    output = f"BEGIN\n backfill_list_roles_export \n---\n {body}\n(1 row)\n\nROLLBACK\n"
    path.write_text(json.dumps({"output": output}), encoding="utf-8")
    return path


# --- export parsing (pure) ---------------------------------------------------


def test_export_is_read_from_render_psql_json_output():
    export = read_export(EXPORT, list_id=MAIN_LIST)
    assert (export.database, export.list_id) == ("pushinweight_shadow", MAIN_LIST)
    assert [m["author_id"] for m in export.members] == [LAB, STAFFER, NO_ROLE]
    assert export.members[2]["handle"] is None
    assert (ROLE_ONLY, "RoleOnlyStaffer", "qwen", "staff") in {
        (r["author_id"], r["handle"], r["brand_id"], r["role_id"]) for r in export.roles
    }
    assert export.generated_at.tzinfo is not None
    assert export.sha256 == hashlib.sha256(EXPORT.read_bytes()).hexdigest()
    assert export.source_run_id == "production-export-sha256:" + export.sha256
    assert len(export.source_run_id) <= 128  # TwitterListMembership.source_run_id


def test_plain_json_document_is_accepted(tmp_path):
    path = tmp_path / "plain.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")
    assert len(read_export(path, list_id=MAIN_LIST).members) == 3


REFUSALS = {
    "staging database": (lambda d: d.update(database="pushinweight_staging"), "not from production"),
    "another list": (lambda d: d.update(list_id=2067500935769895374), "another list"),
    "list id as text": (lambda d: d.update(list_id=str(MAIN_LIST)), "another list"),
    "empty members": (lambda d: d.update(members=[]), "no members"),
    "non-decimal member": (lambda d: d["members"][0].update(author_id="@MainListLab"), "member author_id"),
    "member without author": (lambda d: d["members"][0].pop("author_id"), "member author_id"),
    "duplicate member": (lambda d: d["members"].append(dict(d["members"][0])), "duplicate member"),
    "role without brand": (lambda d: d["roles"][0].pop("brand_id"), "malformed role"),
    "non-decimal role author": (lambda d: d["roles"][0].update(author_id="abc"), "malformed role"),
    "duplicate role": (lambda d: d["roles"].append(dict(d["roles"][0])), "duplicate role"),
    "roles missing": (lambda d: d.pop("roles"), "roles must be a list"),
    "naive generated_at": (lambda d: d.update(generated_at="2026-10-30T01:00:00"), "generated_at"),
}


@pytest.mark.parametrize("change,message", REFUSALS.values(), ids=REFUSALS.keys())
def test_invalid_export_is_refused(tmp_path, change, message):
    document = _document()
    change(document)
    with pytest.raises(SyncRefused, match=message):
        read_export(_write(tmp_path, document), list_id=MAIN_LIST)


def test_unreadable_or_foreign_export_is_refused(tmp_path):
    with pytest.raises(SyncRefused, match="export unreadable"):
        read_export(tmp_path / "missing.json", list_id=MAIN_LIST)
    foreign = tmp_path / "foreign.json"
    foreign.write_text(EXPORT.read_text().replace(FORMAT, "oai-anthropic-main-list/v1"), encoding="utf-8")
    with pytest.raises(SyncRefused, match="export unreadable"):
        read_export(foreign, list_id=MAIN_LIST)


# --- guard order: every refusal before any write (pure) ----------------------


@pytest.fixture
def no_writes(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("write path reached")

    monkeypatch.setattr(sync_module, "harvest_writer_lock", forbidden)
    monkeypatch.setattr(sync_module, "apply_and_prove", forbidden)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")


def _identity(monkeypatch, name, user, *, host=None, events=None):
    def identity():
        if events is not None:
            events.append("identity")
        return {"name": name, "user": user,
                "host": settings.DATABASES["default"].get("HOST") if host is None else host}

    monkeypatch.setattr("monitor.backfill_database.identity", identity)


def _fake_lock(events, *, acquired=True):
    @contextmanager
    def lock(**kwargs):
        events.append(("lock", kwargs["execution_mode"], kwargs["entrypoint"]))
        try:
            yield SimpleNamespace(acquired=acquired)
        finally:
            events.append("unlock")

    return lock


def test_invalid_export_is_refused_before_the_environment_is_checked(monkeypatch, no_writes, tmp_path):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setattr("monitor.backfill_database.identity", lambda: pytest.fail("identity read"))
    document = _document()
    document["database"] = "pushinweight_staging"
    with pytest.raises(SyncRefused, match="not from production"):
        sync_module.sync(_write(tmp_path, document))


@pytest.mark.parametrize("environment", ["production", "staging", None])
def test_non_backfill_environment_is_refused_before_reading_identity(monkeypatch, no_writes, environment):
    if environment is None:
        monkeypatch.delenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", raising=False)
    else:
        monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", environment)
    monkeypatch.setattr("monitor.backfill_database.identity",
                        lambda: pytest.fail("identity read in a non-backfill environment"))
    with pytest.raises(SyncRefused, match="dedicated backfill environment required"):
        sync_module.sync(EXPORT)


@pytest.mark.parametrize("name,user,host", [
    ("pushinweight", "pushinweight", None),
    ("xbackfiller", "other", None),
    ("other", "xbackfiller", None),
    ("xbackfiller", "xbackfiller", "another-host.internal"),
])
def test_non_xbackfiller_database_is_refused_before_the_lease_check(monkeypatch, no_writes, name, user, host):
    _identity(monkeypatch, name, user, host=host)
    monkeypatch.setattr(sync_module, "live_historical_leases",
                        lambda: pytest.fail("lease check ran after the identity refusal"))
    with pytest.raises(SyncRefused, match="dedicated backfill database required"):
        sync_module.sync(EXPORT)


def test_live_historical_lease_is_refused_before_any_write(monkeypatch, no_writes):
    _identity(monkeypatch, "xbackfiller", "xbackfiller")
    monkeypatch.setattr(sync_module, "live_historical_leases", lambda: ["july2026-w3"])
    with pytest.raises(SyncRefused, match="live lease: july2026-w3"):
        sync_module.sync(EXPORT)


def test_contended_writer_lock_is_refused_before_any_write(monkeypatch, no_writes):
    events = []
    _identity(monkeypatch, "xbackfiller", "xbackfiller")
    monkeypatch.setattr(sync_module, "live_historical_leases", list)
    monkeypatch.setattr(sync_module, "harvest_writer_lock", _fake_lock(events, acquired=False))
    with pytest.raises(SyncRefused, match="harvest writer lock is held"):
        sync_module.sync(EXPORT)
    assert events[-1] == "unlock"


def test_lease_taken_while_acquiring_the_lock_is_refused_before_any_write(monkeypatch, no_writes):
    events = []
    leases = iter([[], ["july2026-w4"]])
    _identity(monkeypatch, "xbackfiller", "xbackfiller")
    monkeypatch.setattr(sync_module, "live_historical_leases", lambda: next(leases))
    monkeypatch.setattr(sync_module, "harvest_writer_lock", _fake_lock(events))
    with pytest.raises(SyncRefused, match="live lease: july2026-w4"):
        sync_module.sync(EXPORT)


@pytest.mark.parametrize("execute", [False, True])
def test_guards_run_in_order_before_the_single_write_transaction(monkeypatch, execute):
    events = []
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")
    _identity(monkeypatch, "xbackfiller", "xbackfiller", events=events)
    monkeypatch.setattr(sync_module, "live_historical_leases", lambda: events.append("lease") or [])
    monkeypatch.setattr(sync_module, "harvest_writer_lock", _fake_lock(events))

    def apply(export, *, execute):
        events.append(("apply", execute, export.source_run_id))
        return {"status": "committed" if execute else "dry_run", "committed": execute}

    monkeypatch.setattr(sync_module, "apply_and_prove", apply)
    report = sync_module.sync(EXPORT, execute=execute)
    export = read_export(EXPORT, list_id=MAIN_LIST)
    assert events == [
        "identity", "lease",
        ("lock", "list_membership", "management.sync_backfill_list_roles"),
        "lease", ("apply", execute, export.source_run_id), "unlock",
    ]
    assert report["database"] == {"name": "xbackfiller", "user": "xbackfiller"}
    assert report["export"]["sha256"] == export.sha256
    assert report["export"]["members"] == 3 and report["export"]["roles"] == 5


# --- command wiring (pure) ----------------------------------------------------


def test_command_reports_a_refusal_as_a_command_error(monkeypatch, no_writes):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    with pytest.raises(CommandError, match="refused: dedicated backfill environment required"):
        call_command(COMMAND, "--export", str(EXPORT), stdout=StringIO())


@pytest.mark.parametrize("flags,execute", [([], False), (["--execute"], True)])
def test_command_writes_only_with_execute_and_prints_one_json_report(monkeypatch, flags, execute):
    seen = []

    def fake_sync(path, *, execute):
        seen.append((Path(path), execute))
        return {"status": "committed" if execute else "dry_run", "committed": execute}

    monkeypatch.setattr("monitor.management.commands.sync_backfill_list_roles.sync", fake_sync)
    out = StringIO()
    call_command(COMMAND, "--export", str(EXPORT), *flags, stdout=out)
    assert seen == [(EXPORT, execute)]
    assert json.loads(out.getvalue()) == {"status": "committed" if execute else "dry_run", "committed": execute}


def test_command_fails_after_printing_a_failed_proof_report(monkeypatch):
    monkeypatch.setattr("monitor.management.commands.sync_backfill_list_roles.sync",
                        lambda path, *, execute: {"status": "proof_failed", "committed": False})
    out = StringIO()
    with pytest.raises(CommandError, match="nothing was changed"):
        call_command(COMMAND, "--export", str(EXPORT), "--execute", stdout=out)
    assert json.loads(out.getvalue())["status"] == "proof_failed"


# --- catalog projection and proofs (pure) ------------------------------------


def _catalog() -> list[dict]:
    return [
        {"brand_id": "deepseek", "aliases": ["deepseek", "DeepSeek"], "handles": ["deepseek_ai"],
         "domains": ["deepseek.com"], "products": ["DeepSeek-V3"], "keywords": ["DeepSeek"],
         "hashtags": ["#DeepSeek"], "accounts": [{"handle": "deepseek_ai", "role": "official"}]},
        {"brand_id": "qwen", "aliases": ["qwen", "Qwen"], "handles": [], "domains": [], "products": [],
         "keywords": ["Qwen"], "hashtags": [], "accounts": []},
    ]


def _add_account(rows, brand, handle, role):
    row = next(row for row in rows if row["brand_id"] == brand)
    row["handles"].append(handle)
    row["accounts"].append({"handle": handle, "role": role})


def test_catalog_revision_is_the_classifier_hash():
    from x_monitor.attribution import _tracked_brand_catalog

    rows = _catalog()
    expected = _tracked_brand_catalog([], [{"tracked_brand_catalog": rows, "brand_ids": []}])
    digests = catalog_digests(rows)
    assert digests["revision"] == expected["revision"] and digests["brands"] == 2


@pytest.mark.parametrize("change", [
    lambda rows: rows[0]["accounts"][0].update(role="staff"),
    lambda rows: _add_account(rows, "qwen", "Alibaba_Qwen", "official"),
    lambda rows: rows[0].update(handles=[], accounts=[]),
], ids=["role corrected", "role added", "account removed"])
def test_projection_digest_ignores_handle_and_role_changes(change):
    before, changed = catalog_digests(_catalog()), _catalog()
    change(changed)
    after = catalog_digests(changed)
    assert after["projection_digest"] == before["projection_digest"]
    assert after["revision"] != before["revision"]


@pytest.mark.parametrize("field,value", [
    ("keywords", "DeepSeek-R2"), ("aliases", "深度求索"), ("domains", "chat.deepseek.com"),
    ("hashtags", "#DeepSeekR2"), ("products", "DeepSeek-R2"),
])
def test_projection_digest_changes_for_every_other_catalog_field(field, value):
    before, changed = catalog_digests(_catalog()), _catalog()
    changed[0][field].append(value)
    after = catalog_digests(changed)
    assert after["projection_digest"] != before["projection_digest"]
    assert after["revision"] != before["revision"]


def test_projection_digest_changes_when_a_brand_appears():
    changed = _catalog()
    changed.append({"brand_id": "glm", "aliases": ["glm"], "handles": [], "domains": [], "products": [],
                    "keywords": [], "hashtags": [], "accounts": []})
    assert catalog_digests(changed)["projection_digest"] != catalog_digests(_catalog())["projection_digest"]


def _written(brand, handle, new, old=None, author="1"):
    return {"author_id": author, "brand_id": brand, "handle": handle, "old_role": old, "new_role": new}


def test_account_delta_accepts_exactly_the_written_roles():
    after = _catalog()
    _add_account(after, "qwen", "NewStaffer", "staff")
    after[0]["accounts"][0]["role"] = "staff"
    written = [_written("qwen", "NewStaffer", "staff"), _written("deepseek", "deepseek_ai", "staff", old="official")]
    proof = account_delta_proof(_catalog(), after, written)
    assert proof["passed"], proof
    assert proof["added_accounts"] == [["deepseek", "deepseek_ai", "staff"], ["qwen", "newstaffer", "staff"]]
    assert proof["removed_accounts"] == [["deepseek", "deepseek_ai", "official"]]
    assert proof["added_handles"] == [["qwen", "NewStaffer"]]


def test_account_delta_rejects_an_entry_no_write_explains():
    after = _catalog()
    _add_account(after, "qwen", "NewStaffer", "staff")
    _add_account(after, "qwen", "Intruder", "official")
    proof = account_delta_proof(_catalog(), after, [_written("qwen", "NewStaffer", "staff")])
    assert not proof["passed"]
    assert proof["unexpected_added_accounts"] == [["qwen", "intruder", "official"]]
    assert proof["unexpected_added_handles"] == [["qwen", "Intruder"]]


def test_account_delta_rejects_a_removal_that_no_correction_explains():
    after = _catalog()
    after[0].update(handles=[], accounts=[])
    proof = account_delta_proof(_catalog(), after, [_written("qwen", "NewStaffer", "staff")])
    assert not proof["passed"]
    assert proof["unexpected_removed_accounts"] == [["deepseek", "deepseek_ai", "official"]]
    assert proof["removed_handles"] == [["deepseek", "deepseek_ai"]]


def test_account_delta_requires_every_written_role_to_appear():
    proof = account_delta_proof(_catalog(), _catalog(), [_written("qwen", "NewStaffer", "staff")])
    assert not proof["passed"] and proof["missing_accounts"] == [["qwen", "newstaffer", "staff"]]


def test_without_role_writes_the_revision_must_stay_byte_identical():
    assert account_delta_proof(_catalog(), _catalog(), [])["passed"]
    after = _catalog()
    after[0]["handles"].append("DeepSeek_AI")  # same casefolded account entry, different handle list
    proof = account_delta_proof(_catalog(), after, [])
    assert not proof["passed"] and proof["revision_unchanged"] is False


def test_roles_outside_the_catalog_expect_no_catalog_entry():
    written = [_written("sentinel_brand", "Someone", "staff"), _written("qwen", None, "staff")]
    assert account_delta_proof(_catalog(), _catalog(), written)["passed"]


def _context(author, official=(), staff=()):
    return AuthorRoleContext(author_id=author, official_brands=tuple(official), staff_brands=tuple(staff),
                             membership_source=MEMBERSHIP_SOURCE, membership_run_id="run",
                             last_complete_reconciliation_at=None)


def test_expected_contexts_apply_export_roles_over_existing_edges():
    before_edges = [(LAB, "deepseek", "staff"), (LAB, "glm", "official"), ("777", "qwen", "official")]
    applied = [(LAB, "deepseek", "official"), (STAFFER, "deepseek", "staff"), (STAFFER, "qwen", "researcher")]
    assert expected_contexts([LAB, STAFFER, NO_ROLE], before_edges, applied) == {
        LAB: {"official": ["deepseek", "glm"], "staff": []},
        STAFFER: {"official": [], "staff": ["deepseek"]},
        NO_ROLE: {"official": [], "staff": []},
    }


def test_contexts_proof_needs_one_matching_context_per_exported_member():
    expected = {LAB: {"official": ["deepseek"], "staff": []}, NO_ROLE: {"official": [], "staff": []}}
    contexts = {LAB: _context(LAB, official=["deepseek"]), NO_ROLE: _context(NO_ROLE)}
    assert contexts_proof(contexts, expected, [LAB, NO_ROLE])["passed"]
    missing = contexts_proof({LAB: contexts[LAB]}, expected, [LAB, NO_ROLE])
    assert not missing["passed"] and missing["missing"] == [NO_ROLE]
    wrong = contexts_proof({**contexts, LAB: _context(LAB, staff=["deepseek"])}, expected, [LAB, NO_ROLE])
    assert not wrong["passed"] and wrong["mismatched"] == [LAB]
    extra_member = contexts_proof(contexts, expected, [LAB, NO_ROLE, STAFFER])
    assert not extra_member["passed"] and extra_member["active_not_exported"] == [STAFFER]


# --- read-only export SQL (pure) ---------------------------------------------


def test_export_sql_is_read_only():
    text = SQL.read_text(encoding="utf-8")
    assert text.startswith("BEGIN TRANSACTION READ ONLY;\n")
    assert text.rstrip().endswith("ROLLBACK;")
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP)\b", text, re.IGNORECASE)
    code = re.sub(r"--[^\n]*", "", text)
    statements = [statement.strip() for statement in code.split(";") if statement.strip()]
    assert [statement.split()[0].upper() for statement in statements] == ["BEGIN", "SELECT", "ROLLBACK"]


def test_export_sql_produces_the_document_the_reader_expects():
    from monitor.cycle import _resolve_x_monitor_list_id
    from x_monitor.config import load_config

    text = SQL.read_text(encoding="utf-8")
    assert f"'{FORMAT}'" in text
    list_id = _resolve_x_monitor_list_id(load_config(REPO / "config.yaml"))
    assert set(re.findall(r"\b\d{19}\b", text)) == {str(list_id)}
    for key in ("database", "generated_at", "list_id", "members", "roles", "author_id", "handle",
                "brand_id", "role_id"):
        assert f"'{key}'" in text


# --- database-backed behaviour (PostgreSQL only) ----------------------------

@pytest.fixture
def xbackfiller(monkeypatch):
    from core.models import Brand, DataSource, Role

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")
    _identity(monkeypatch, "xbackfiller", "xbackfiller")
    DataSource.objects.get_or_create(id="x", defaults={"name": "X", "source_type": "social"})
    for brand in ("deepseek", "qwen"):
        Brand.objects.get_or_create(nickname=brand, defaults={"display_name": brand, "is_sentinel": False})
    for key in ("official", "staff"):
        Role.objects.get_or_create(key=key)


def _run(path: Path, *, execute: bool = True) -> dict:
    out = StringIO()
    call_command(COMMAND, "--export", str(path), *(["--execute"] if execute else []), stdout=out)
    return json.loads(out.getvalue())


def _state() -> dict:
    from core.models import (
        Account,
        Brand,
        BrandAccount,
        BrandHashtag,
        BrandKeyword,
        BrandSearchTerm,
        CollectionJob,
        Product,
        Role,
        TwitterListMembership,
        TwitterListSyncState,
    )

    models = (Account, Brand, BrandAccount, BrandHashtag, BrandKeyword, BrandSearchTerm, CollectionJob,
              Product, Role, TwitterListMembership, TwitterListSyncState)
    return {
        "counts": {model.__name__: model.objects.count() for model in models},
        "memberships": sorted(map(repr, TwitterListMembership.objects.values_list(
            "list_id", "account__author_id", "active", "source", "source_run_id"))),
        "roles": sorted(map(repr, BrandAccount.objects.values_list("brand_id", "account__author_id", "role_id"))),
        "handles": sorted(map(repr, Account.objects.values_list("author_id", "handle"))),
    }


def _plan(monkeypatch) -> dict:
    from monitor.backfill_collection import plan_job_definition
    from x_monitor.config import load_config

    cfg = load_config(REPO / "config.yaml")
    monkeypatch.setattr("monitor.backfill_collection.load_config", lambda path: cfg)
    return plan_job_definition(
        cfg=cfg, since_epoch=1786233600, until_epoch=1786234500, brands=["qwen"],
        requests=3, model_requests=60, seconds=300, maximum_requests=20, maximum_models=100,
    )


def _register(definition: dict, job_key: str):
    from core.collection_jobs import register_job, set_job_state
    from core.models import DataSource

    job = register_job(job_key=job_key, source=DataSource.objects.get(pk="x"), purpose="content",
                       operation="x_backfill", mode="historical", definition=definition)
    return set_job_state(job.pk, "ready")


def _proofs_passed(report: dict) -> bool:
    return bool(report["proofs"]) and all(proof["passed"] for proof in report["proofs"].values())


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_first_execute_creates_members_accounts_and_roles_and_a_rerun_changes_nothing(xbackfiller):
    from core.models import Account, BrandAccount, TwitterListMembership

    first = _run(EXPORT)
    assert (first["status"], first["committed"]) == ("committed", True) and _proofs_passed(first)
    assert first["source_run_id"] == "production-export-sha256:" + hashlib.sha256(EXPORT.read_bytes()).hexdigest()
    counts = first["counts"]
    assert (counts["memberships_created"], counts["accounts_created"], counts["roles_created"],
            counts["roles_skipped"]) == (3, 4, 3, 2)
    assert {(row.account.author_id, row.active, row.source, row.source_run_id)
            for row in TwitterListMembership.objects.filter(list_id=MAIN_LIST).select_related("account")} == {
        (author, True, MEMBERSHIP_SOURCE, first["source_run_id"]) for author in (LAB, STAFFER, NO_ROLE)}
    assert Account.x.get(author_id=ROLE_ONLY).handle == "RoleOnlyStaffer"
    assert Account.x.get(author_id=NO_ROLE).handle is None
    assert not TwitterListMembership.objects.filter(account__author_id=ROLE_ONLY).exists()
    assert set(BrandAccount.objects.values_list("brand_id", "account__author_id", "role_id")) == {
        ("deepseek", LAB, "official"), ("deepseek", STAFFER, "staff"), ("qwen", ROLE_ONLY, "staff")}

    state = _state()
    second = _run(EXPORT)
    assert _state() == state and _proofs_passed(second)
    counts = second["counts"]
    assert (counts["memberships_unchanged"], counts["memberships_created"], counts["memberships_deactivated"],
            counts["accounts_created"], counts["roles_unchanged"], counts["roles_created"],
            counts["roles_corrected"]) == (3, 0, 0, 0, 3, 0, 0)
    assert second["catalog"]["before"]["revision"] == second["catalog"]["after"]["revision"]
    assert second["catalog"]["after"]["revision"] == first["catalog"]["after"]["revision"]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_role_is_corrected_unknown_brand_or_role_is_skipped_and_local_roles_are_kept(xbackfiller, tmp_path):
    from core.models import Account, Brand, BrandAccount, Role

    staffer = Account.objects.create(author_id=STAFFER, handle="MainListStaffer")
    BrandAccount.objects.create(brand_id="deepseek", account=staffer, role_id="staff")
    local = Account.objects.create(author_id="900000000000000777", handle="LocalOnlyLab")
    BrandAccount.objects.create(brand_id="qwen", account=local, role_id="official")
    brands, roles = set(Brand.objects.values_list("nickname", flat=True)), set(Role.objects.values_list("key", flat=True))
    document = _document()
    next(r for r in document["roles"] if (r["author_id"], r["brand_id"]) == (STAFFER, "deepseek"))["role_id"] = "official"

    report = _run(_write(tmp_path, document))

    assert _proofs_passed(report)
    assert BrandAccount.objects.get(brand_id="deepseek", account=staffer).role_id == "official"
    assert report["counts"]["roles_corrected"] == 1
    assert {"author_id": STAFFER, "brand_id": "deepseek", "handle": "MainListStaffer", "old_role": "staff",
            "new_role": "official", "action": "corrected"} in report["roles_written"]
    assert {(s["author_id"], s["brand_id"], s["role_id"], s["reason"]) for s in report["roles_skipped"]} == {
        (LAB, "notabrand", "official", "brand_missing"), (STAFFER, "qwen", "notarole", "role_missing")}
    assert set(Brand.objects.values_list("nickname", flat=True)) == brands
    assert set(Role.objects.values_list("key", flat=True)) == roles
    assert report["extra_roles"] == [{"author_id": "900000000000000777", "brand_id": "qwen", "handle": "LocalOnlyLab",
                                      "role_id": "official"}]
    assert BrandAccount.objects.filter(brand_id="qwen", account=local, role_id="official").exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_catalog_rows_stay_identical_and_only_account_entries_change(xbackfiller):
    from core.models import Brand, BrandHashtag, BrandKeyword, BrandSearchTerm, Product

    BrandKeyword.objects.get_or_create(brand_id="deepseek", pattern="DeepSeek")
    BrandSearchTerm.objects.get_or_create(brand_id="deepseek", term="deepseek.com")
    BrandHashtag.objects.get_or_create(brand_id="qwen", hashtag="Qwen3")

    def rows():
        return {model.__name__: sorted(map(repr, model.objects.values_list()))
                for model in (Brand, BrandKeyword, BrandSearchTerm, BrandHashtag, Product)}

    before = rows()
    report = _run(EXPORT)
    assert rows() == before
    catalog = report["catalog"]
    assert catalog["before"]["projection_digest"] == catalog["after"]["projection_digest"]
    assert catalog["before"]["revision"] != catalog["after"]["revision"]
    delta = report["proofs"]["account_delta_matches_written_roles"]
    assert delta["passed"] and delta["removed_accounts"] == [] and delta["removed_handles"] == []
    assert delta["added_accounts"] == [["deepseek", "mainlistlab", "official"],
                                       ["deepseek", "mainliststaffer", "staff"],
                                       ["qwen", "roleonlystaffer", "staff"]]
    assert report["proofs"]["protected_rows_unchanged"]["passed"]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_memberships_only_export_keeps_the_catalog_revision_byte_identical(xbackfiller, tmp_path):
    from core.models import Account, BrandAccount

    lab = Account.objects.create(author_id=LAB, handle="MainListLab")
    BrandAccount.objects.create(brand_id="deepseek", account=lab, role_id="official")
    document = _document()
    document["roles"] = []

    report = _run(_write(tmp_path, document))

    assert _proofs_passed(report) and report["counts"]["memberships_created"] == 3
    assert report["catalog"]["before"]["revision"] == report["catalog"]["after"]["revision"]
    assert report["roles_written"] == [] and BrandAccount.objects.count() == 1
    assert report["extra_roles"] == [{"author_id": LAB, "brand_id": "deepseek", "handle": "MainListLab",
                                      "role_id": "official"}]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_member_dropped_from_the_export_is_the_only_row_deactivated(xbackfiller, tmp_path):
    from core.models import Account, TwitterListMembership, TwitterListSyncState

    other = Account.objects.create(author_id="900000000000000888", handle="OtherListMember")
    TwitterListMembership.objects.create(list_id=42, account=other, active=True, source="snapshot")
    first = _run(EXPORT)
    document = _document()
    document["members"] = [m for m in document["members"] if m["author_id"] != NO_ROLE]

    second = _run(_write(tmp_path, document))

    rows = {row.account.author_id: row for row in TwitterListMembership.objects.select_related("account")}
    assert second["memberships_deactivated"] == [NO_ROLE] and _proofs_passed(second)
    assert (rows[NO_ROLE].active, rows[NO_ROLE].source, rows[NO_ROLE].source_run_id) == (
        False, MEMBERSHIP_SOURCE, second["source_run_id"])
    assert rows[LAB].active and rows[STAFFER].active
    assert rows[LAB].source_run_id == first["source_run_id"]  # already-active rows are left unchanged
    assert (rows[other.author_id].active, rows[other.author_id].source) == (True, "snapshot")
    assert (second["counts"]["memberships_deactivated"], second["counts"]["memberships_unchanged"]) == (1, 2)
    assert not TwitterListSyncState.objects.exists()


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_existing_account_handle_is_never_edited_and_is_reported(xbackfiller):
    from core.models import Account

    lab = Account.objects.create(author_id=LAB, handle="OldLabHandle")
    report = _run(EXPORT)
    lab.refresh_from_db()
    assert lab.handle == "OldLabHandle" and _proofs_passed(report)
    assert report["handle_differs"] == [{"author_id": LAB, "production": "MainListLab", "xbackfiller": "OldLabHandle"}]
    assert ["deepseek", "oldlabhandle", "official"] in report["proofs"]["account_delta_matches_written_roles"][
        "added_accounts"]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_planning_after_sync_freezes_one_context_per_member_and_saved_jobs_keep_their_checksum(
    xbackfiller, seeded_policy_keywords, monkeypatch,
):
    before = _plan(monkeypatch)
    assert before["scope"]["author_scope"]["contexts"] == {}
    job = _register(before, "u7-saved-window")
    job.refresh_from_db()
    saved = (job.definition_sha256, job.definition)

    report = _run(EXPORT)

    job.refresh_from_db()
    assert (job.definition_sha256, job.definition) == saved
    jobs_proof = report["proofs"]["historical_jobs_unchanged"]
    assert jobs_proof["passed"] and jobs_proof["jobs"] == 1
    contexts = _plan(monkeypatch)["scope"]["author_scope"]["contexts"]
    assert set(contexts) == {LAB, STAFFER, NO_ROLE}
    assert (contexts[LAB]["official_brands"], contexts[LAB]["staff_brands"]) == (["deepseek"], [])
    assert (contexts[STAFFER]["official_brands"], contexts[STAFFER]["staff_brands"]) == ([], ["deepseek"])
    assert (contexts[NO_ROLE]["official_brands"], contexts[NO_ROLE]["staff_brands"]) == ([], [])
    assert {context["membership_source"] for context in contexts.values()} == {MEMBERSHIP_SOURCE}


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_dry_run_changes_no_rows_and_reports_the_would_be_revision(xbackfiller):
    from core.models import Account, BrandAccount, TwitterListMembership

    staffer = Account.objects.create(author_id=STAFFER, handle="MainListStaffer")
    BrandAccount.objects.create(brand_id="deepseek", account=staffer, role_id="official")
    gone = Account.objects.create(author_id="900000000000000999", handle="LeftTheList")
    TwitterListMembership.objects.create(list_id=MAIN_LIST, account=gone, active=True, source="snapshot")
    state = _state()

    preview = _run(EXPORT, execute=False)

    assert _state() == state
    assert (preview["status"], preview["committed"]) == ("dry_run", False) and _proofs_passed(preview)
    assert (preview["counts"]["roles_corrected"], preview["counts"]["memberships_deactivated"]) == (1, 1)
    assert preview["catalog"]["after"]["revision"] != preview["catalog"]["before"]["revision"]
    applied = _run(EXPORT)
    assert applied["catalog"]["after"]["revision"] == preview["catalog"]["after"]["revision"]


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_live_historical_lease_refuses_with_no_writes(xbackfiller, seeded_policy_keywords, monkeypatch):
    from django.utils import timezone

    from core.models import CollectionRun

    job = _register(_plan(monkeypatch), "u7-running-window")
    CollectionRun.objects.create(job=job, ingestion_key=uuid4().hex * 2, lease_token=uuid4(),
                                 lease_expires_at=timezone.now() + timedelta(minutes=5))
    state = _state()
    with pytest.raises(CommandError, match="live lease: u7-running-window"):
        _run(EXPORT)
    assert _state() == state


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_failed_proof_rolls_back_every_write_even_with_execute(xbackfiller, monkeypatch):
    monkeypatch.setattr(sync_module, "contexts_proof", lambda *args, **kwargs: {"passed": False, "forced": True})
    state = _state()
    out = StringIO()
    with pytest.raises(CommandError, match="nothing was changed"):
        call_command(COMMAND, "--export", str(EXPORT), "--execute", stdout=out)
    assert _state() == state
    report = json.loads(out.getvalue())
    assert (report["status"], report["committed"]) == ("proof_failed", False)
    assert report["proofs"]["contexts_match_export"] == {"passed": False, "forced": True}
