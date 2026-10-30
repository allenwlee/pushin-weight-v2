"""OpenAI/Anthropic size-test seed data, guards and switch-off (plan U1/U10).

The keyword/roster CSVs and the branch-only policy entries exist only for the
dedicated xbackfiller database. Pure tests run the production matcher
(``compile_keyword_index`` / ``attribute_to_brands``) over the committed CSV
and policy; database tests are PostgreSQL-only and skipped elsewhere.
"""

from __future__ import annotations

import csv
import io
import json
import random
from pathlib import Path

import pytest

from scripts import backfill_size_seed as seed_module
from scripts.backfill_size_seed import (
    BRANDS,
    OFFICIAL_HANDLES,
    SeedRefused,
    build_keyword_rows,
    build_roster_rows,
    check_policy_alignment,
    keyword_csv_bytes,
    onboard_rows,
    read_keyword_csv,
    read_roster_csv,
    roster_csv_bytes,
    route_terms,
)
from x_monitor.attribution import attribute_to_brands, compile_keyword_index
from x_monitor.harvest_policy import load_policy, normalize_policy_token

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / "docs/analysis/2026-10-27-215214-oai-anthropic-frozen-queries.json"
POLICY = REPO / "config/harvest_policy.yaml"
CONFIG = REPO / "config.yaml"


def _one(pattern: str) -> Path:
    matches = sorted((REPO / "docs/analysis").glob(pattern))
    assert len(matches) == 1, f"expected one {pattern}, got {matches}"
    return matches[0]


KEYWORDS = _one("*-oai-anthropic-keywords.csv")
ROSTER = _one("*-oai-anthropic-roster.csv")


def _frozen() -> dict:
    return json.loads(FROZEN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def size_index():
    """Literal rows normalized exactly as monitor.cycle._build_brand_index does."""
    rows = read_keyword_csv(KEYWORDS)
    triples = [(row.brand, normalize_policy_token(row.pattern), False) for row in rows]
    return compile_keyword_index(triples, policy=load_policy(POLICY))


def _brands(text: str, index) -> set[str]:
    post = {"tweet_id": "1", "created_at": "2026-10-28T00:00:00Z", "text": text}
    mentions = attribute_to_brands(
        post, brands_accounts={}, brand_hashtags={}, compiled_keyword_index=index,
        search_query=[], brand_search_terms={},
    )
    return {mention.brand_id for mention in mentions}


# --- matcher behaviour through the production attribution path ------------


def test_sol_needs_its_context_word(size_index):
    assert "openai" not in _brands("Sol is out", size_index)
    assert "openai" in _brands("Sol AI model", size_index)


def test_sama_handle_string_needs_its_context_word(size_index):
    assert _brands("sama", size_index) == set()
    assert "openai" in _brands("sama said the model…", size_index)


def test_chatgpt_followed_by_japanese_stays_unmatched(size_index):
    # Deliberate pin of the unchanged matcher: \b does not split Latin from
    # kana, so production would drop this post. The size answer must match.
    assert _brands("ChatGPTの新機能", size_index) == set()
    assert _brands("ChatGPT の新機能", size_index) == {"openai"}


def test_standalone_names_stay_unconditional(size_index):
    for text, brand in (("OpenAI", "openai"), ("GPT", "openai"), ("Codex", "openai"),
                        ("Sora 2 is out", "openai"), ("Claude", "anthropic"),
                        ("Anthropic", "anthropic"), ("Opus 5 is out", "anthropic"),
                        ("haiku-5.5", "anthropic"), ("@claude_code", "anthropic")):
        assert _brands(text, size_index) == {brand}, text
    for text in ("Sora is a name", "Opus is out", "Dario said hi", "o3 tonight"):
        assert _brands(text, size_index) == set(), text


# --- keyword table ----------------------------------------------------------


def test_keyword_table_holds_every_frozen_term_and_handle():
    table = {normalize_policy_token(row.pattern): row for row in read_keyword_csv(KEYWORDS)}
    for route in _frozen()["new"]:
        kind, terms, context = route_terms(route["text"])
        for term in terms:
            row = table[normalize_policy_token(term)]
            if kind == "gated" and row.source == f"frozen:{route['name']}":
                # Only the gated pack uses it, so it carries the pack's context.
                assert row.context_gated and row.context_words == context, term
    for brand, handles in OFFICIAL_HANDLES.items():
        for handle in handles:
            assert table[normalize_policy_token(handle)].brand == brand
    assert table["sama"].context_gated and table["sol"].context_gated and table["opus"].context_gated
    for name in ("openai", "chatgpt", "gpt", "codex", "claude", "anthropic", "opus 5"):
        assert not table[name].context_gated, name


def test_gated_rows_match_the_branch_policy():
    policy = load_policy(POLICY)
    check_policy_alignment(read_keyword_csv(KEYWORDS), policy)
    assert {policy.brands[b].paths for b in BRANDS} == {frozenset({"none"})}


def test_policy_alignment_rejects_a_drifted_gate():
    rows = read_keyword_csv(KEYWORDS)
    drifted = [row if row.pattern != "Sol" else row.__class__(row.brand, row.pattern, False, (), row.source)
               for row in rows]
    with pytest.raises(SeedRefused, match="alias_context"):
        check_policy_alignment(drifted, load_policy(POLICY))


def test_route_parser_reads_gated_pack_and_rejects_malformed_text():
    oai_3 = next(r["text"] for r in _frozen()["new"] if r["name"] == "OAI_3")
    kind, terms, context = route_terms(oai_3)
    assert kind == "gated" and terms[:2] == ("Sora", "Sol") and "Deep Research" in terms
    assert context == ("AI", "model", "models", "llm", "api", "agent", "coding", "模型", "モデル")
    assert route_terms('(@OpenAI OR @sama) min_faves:0')[1] == ("OpenAI", "sama")
    for bad in ("((a OR b) min_faves:0", "(a OR) min_faves:0", "(a OR b)"):
        with pytest.raises(SeedRefused):
            route_terms(bad)


# --- roster -----------------------------------------------------------------


def test_roster_roles_follow_the_owner_decision():
    rows = read_roster_csv(ROSTER)
    for brand, handles in OFFICIAL_HANDLES.items():
        own = [row for row in rows if row.brand == brand]
        assert {r.username for r in own if r.role == "official"} == set(handles)
        assert all(r.role == "staff" for r in own if r.username not in handles)
    counts = {(r.brand, r.role): 0 for r in rows}
    for row in rows:
        counts[(row.brand, row.role)] += 1
    assert counts == {("openai", "official"): 3, ("openai", "staff"): 26,
                      ("anthropic", "official"): 4, ("anthropic", "staff"): 15}
    by_handle = {row.username: row for row in rows}
    assert (by_handle["karpathy"].brand, by_handle["karpathy"].role) == ("anthropic", "staff")
    assert (by_handle["addyosmani"].brand, by_handle["addyosmani"].role) == ("anthropic", "staff")
    assert {row.list_id for row in rows} == {2067500935769895374, 2067501173402460553}


def _members_from_roster_csv(shuffle_seed: int) -> dict:
    members = {"OpenAI": [], "Anthropic": []}
    for row in read_roster_csv(ROSTER):
        key = "OpenAI" if row.brand == "openai" else "Anthropic"
        members[key].append({"id": row.author_id, "username": row.username, "name": row.username})
    rng = random.Random(shuffle_seed)
    for values in members.values():
        rng.shuffle(values)
    return members


def test_csv_builders_are_deterministic_and_reproduce_the_committed_files():
    frozen = _frozen()
    first = keyword_csv_bytes(build_keyword_rows(frozen))
    assert first == keyword_csv_bytes(build_keyword_rows(json.loads(json.dumps(frozen))))
    assert first == KEYWORDS.read_bytes()
    roster = [roster_csv_bytes(build_roster_rows(_members_from_roster_csv(seed))) for seed in (1, 2)]
    assert roster[0] == roster[1] == ROSTER.read_bytes()


def test_roster_builder_rejects_a_changed_list():
    members = _members_from_roster_csv(3)
    members["Anthropic"] = [m for m in members["Anthropic"] if m["username"] != "claude_code"]
    with pytest.raises(SeedRefused, match="official"):
        build_roster_rows(members)


def test_onboard_rows_pass_the_onboard_brand_parser():
    from monitor.management.commands.onboard_brand import CSV_FIELDS, _parse_row

    keywords, roster = read_keyword_csv(KEYWORDS), read_roster_csv(ROSTER)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(onboard_rows(keywords, roster))
    parsed = [_parse_row(raw, n) for n, raw in enumerate(csv.DictReader(io.StringIO(stream.getvalue())), start=2)]
    for brand, row in zip(BRANDS, parsed, strict=True):
        assert row.nickname == brand and row.harvest_paths == ["none"]
        assert [p for p, _primary in row.keywords] == [k.pattern for k in keywords if k.brand == brand]
        roles = {(h, a, r) for h, a, r in row.account_roles}
        assert roles == {(m.username, m.author_id, m.role) for m in roster if m.brand == brand}


# --- guards: refuse before any write ---------------------------------------


@pytest.fixture
def no_writes(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("write path reached")

    for name in ("_write_seed", "_write_switch_off", "catalog_report"):
        monkeypatch.setattr(seed_module, name, forbidden)
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")


def _identity(monkeypatch, name, user):
    monkeypatch.setattr("monitor.backfill_database.identity",
                        lambda: {"name": name, "user": user, "host": "db.internal"})


UNDO = "/nonexistent/size-test-undo-receipt.json"
MAIN_LIST = REPO / "tests/fixtures/size_test_main_list_export.json"
SEED_ARGS = ["seed", "--keywords", str(KEYWORDS), "--roster", str(ROSTER), "--config", str(CONFIG),
             "--policy", str(POLICY), "--main-list", str(MAIN_LIST), "--undo-receipt", UNDO]
SWITCH_OFF_ARGS = ["switch-off", "--undo-receipt", UNDO]


@pytest.mark.parametrize("command", [SEED_ARGS, SWITCH_OFF_ARGS])
@pytest.mark.parametrize("name,user", [("pushinweight", "pushinweight"), ("xbackfiller", "other"),
                                       ("other", "xbackfiller")])
def test_non_xbackfiller_database_is_refused_before_any_write(monkeypatch, no_writes, capsys, command, name, user):
    _identity(monkeypatch, name, user)
    monkeypatch.setattr(seed_module, "live_historical_leases",
                        lambda: pytest.fail("lease check ran after the identity refusal"))
    assert seed_module.main(command) == 2
    assert "dedicated backfill database required" in capsys.readouterr().err


@pytest.mark.parametrize("command", [SEED_ARGS, SWITCH_OFF_ARGS])
def test_non_backfill_environment_is_refused_before_reading_identity(monkeypatch, no_writes, capsys, command):
    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "production")
    monkeypatch.setattr("monitor.backfill_database.identity",
                        lambda: pytest.fail("identity read in a non-backfill environment"))
    assert seed_module.main(command) == 2
    assert "dedicated backfill environment required" in capsys.readouterr().err


@pytest.mark.parametrize("command", [SEED_ARGS, SWITCH_OFF_ARGS])
def test_live_historical_lease_is_refused_before_any_write(monkeypatch, no_writes, capsys, command):
    _identity(monkeypatch, "xbackfiller", "xbackfiller")
    monkeypatch.setattr(seed_module, "live_historical_leases", lambda: ["july-2026/07"])
    assert seed_module.main(command) == 2
    assert "live lease: july-2026/07" in capsys.readouterr().err


# --- undo plan (pure) --------------------------------------------------------


def _state(*, keywords=(), accounts=(), accent=None, memberships=None, companies=()):
    brands = {brand: {"display_name": brand.title(), "display_name_en": None, "display_name_zh_cn": None,
                      "accent_color": accent, "is_sentinel": False} for brand in BRANDS}
    rows = {name: [] for name in seed_module.BRAND_SCOPED}
    rows["BrandKeyword"], rows["BrandAccount"] = [list(k) for k in keywords], [list(a) for a in accounts]
    return {"brands": brands, "rows": rows, "memberships": memberships or {}, "companies": list(companies)}


def test_undo_plan_names_only_what_the_seed_created_or_changed():
    # Brand link tables use composite keys such as (brand_id, pattern).
    before = _state(accounts=[("openai", "a1")], memberships={"m1": {"active": False, "source": "call_a"}},
                    companies=["c1"])
    after = _state(keywords=[("openai", "k1"), ("openai", "k2")], accounts=[("openai", "a1"), ("openai", "a2")],
                   accent="#10a37f",
                   memberships={"m1": {"active": True, "source": "size-test-roster"},
                                "m2": {"active": True, "source": "size-test-roster"}},
                   companies=["c1", "c2"])
    plan = seed_module.undo_plan(before, after)
    assert plan["created_rows"]["BrandKeyword"] == [["openai", "k1"], ["openai", "k2"]]
    assert plan["created_rows"]["BrandAccount"] == [["openai", "a2"]]
    json.dumps(plan)  # the receipt is plain JSON
    assert plan["brand_fields"]["openai"]["accent_color"] is None
    assert plan["created_memberships"] == ["m2"]
    assert plan["changed_memberships"] == {"m1": {"active": False, "source": "call_a"}}
    assert plan["created_companies"] == ["c2"]


def test_undo_plan_requires_the_brands_to_exist_before_the_seed():
    before = _state()
    del before["brands"]["openai"]
    with pytest.raises(SeedRefused, match="must exist before the seed"):
        seed_module.undo_plan(before, _state())


def test_undo_plan_reverses_copied_main_list_roles():
    before = _state()
    before["roles"] = {"deepseek|acc-1": "staff"}
    after = _state()
    after["roles"] = {"deepseek|acc-1": "official", "qwen|acc-2": "staff"}
    plan = seed_module.undo_plan(before, after)
    assert plan["created_roles"] == ["qwen|acc-2"]
    assert plan["changed_roles"] == {"deepseek|acc-1": "staff"}


def test_main_list_export_is_read_from_render_output_and_validated(tmp_path):
    export = seed_module.read_main_list_export(MAIN_LIST)
    assert [m["author_id"] for m in export["members"]] == ["900000000000000001", "900000000000000002"]
    roster = read_roster_csv(ROSTER)
    authors = seed_module.scope_author_ids(roster, export)
    assert "900000000000000001" in authors and len(authors) == 48 + 2
    staging = tmp_path / "staging.json"
    staging.write_text(MAIN_LIST.read_text().replace("pushinweight_shadow", "pushinweight_staging"))
    with pytest.raises(SeedRefused, match="not from production"):
        seed_module.read_main_list_export(staging)
    other = tmp_path / "other.json"
    other.write_text(MAIN_LIST.read_text().replace("2067062923525275922", "2067500935769895374"))
    with pytest.raises(SeedRefused, match="another list"):
        seed_module.read_main_list_export(other)


def test_switch_off_refuses_an_unreadable_or_foreign_receipt(tmp_path):
    with pytest.raises(SeedRefused, match="unreadable"):
        seed_module.read_undo_receipt(tmp_path / "missing.json")
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"format": "oai-anthropic-size-seed-undo/v1", "database": "pushinweight_shadow"}')
    with pytest.raises(SeedRefused, match="another database"):
        seed_module.read_undo_receipt(foreign)


# --- database-backed behaviour (PostgreSQL only) ----------------------------


def _row_counts() -> dict[str, int]:
    from core.models import (
        Account,
        Brand,
        BrandAccount,
        BrandKeyword,
        TwitterListMembership,
    )

    return {
        "brands": Brand.objects.filter(nickname__in=BRANDS).count(),
        "keywords": BrandKeyword.objects.filter(brand_id__in=BRANDS).count(),
        "accounts": Account.x.filter(author_id__in=[r.author_id for r in read_roster_csv(ROSTER)]).count(),
        "brand_accounts": BrandAccount.objects.filter(brand_id__in=BRANDS).count(),
        "memberships": TwitterListMembership.objects.filter(
            list_id__in=[2067500935769895374, 2067501173402460553]).count(),
    }


@pytest.fixture
def xbackfiller(monkeypatch, seeded_policy_keywords, tmp_path):
    from core.models import Brand

    monkeypatch.setenv("X_MONITOR_DEPLOYMENT_ENVIRONMENT", "backfill")
    _identity(monkeypatch, "xbackfiller", "xbackfiller")
    # Production and xbackfiller already hold both brands as alias-only rows.
    for brand, display in (("openai", "OpenAI"), ("anthropic", "Anthropic")):
        Brand.objects.get_or_create(nickname=brand, defaults={"display_name": display})
    return tmp_path


def _seed(receipt):
    return seed_module.seed(KEYWORDS, ROSTER, config_path=CONFIG, policy_path=POLICY, undo_receipt=receipt,
                            main_list_path=MAIN_LIST)


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_second_seed_is_refused_and_creates_no_duplicates(xbackfiller):
    from core.models import BrandAccount

    _seed(xbackfiller / "undo-1.json")
    counts = _row_counts()
    with pytest.raises(SeedRefused, match="already carry keywords"):
        _seed(xbackfiller / "undo-2.json")
    assert _row_counts() == counts
    keyword_rows = len(read_keyword_csv(KEYWORDS))
    assert counts == {"brands": 2, "keywords": keyword_rows, "accounts": 48, "brand_accounts": 48, "memberships": 48}
    from core.models import TwitterListMembership

    assert TwitterListMembership.objects.filter(list_id=seed_module.MAIN_LIST, active=True).count() == 2
    roles = {(e.brand_id, e.account.handle): e.role_id for e in BrandAccount.objects.filter(brand_id__in=BRANDS)}
    assert roles[("anthropic", "karpathy")] == "staff" and roles[("openai", "OpenAINewsroom")] == "official"


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_seeded_index_gates_context_through_build_brand_index(xbackfiller):
    from monitor.cycle import _build_brand_index
    from x_monitor.attribution import detect_brand_mentions
    from x_monitor.config import load_config

    _seed(xbackfiller / "undo.json")
    index = _build_brand_index(list(load_config(CONFIG).enabled_models))
    assert "openai" not in detect_brand_mentions("Sol is out", index)
    assert "openai" in detect_brand_mentions("Sol AI model", index)
    assert detect_brand_mentions("ChatGPTの新機能", index) == []


@pytest.mark.requires_postgres
@pytest.mark.django_db(transaction=True)
def test_switch_off_restores_the_pre_seed_catalog_and_keeps_post_brands(xbackfiller):
    from core.models import Brand, BrandAccount, BrandKeyword, Post, PostBrand

    receipt = xbackfiller / "undo.json"
    pre_seed = seed_module.catalog_report()
    _seed(receipt)
    assert seed_module.catalog_report()["revision"] != pre_seed["revision"]
    post = Post.objects.create(tweet_id="size-test-1", text="OpenAI and Anthropic")
    for brand in BRANDS:
        PostBrand.objects.create(post=post, brand_id=brand)
    report = seed_module.switch_off(undo_receipt=receipt)
    assert report["catalog_after"]["revision"] == pre_seed["revision"]
    assert report["post_brands"] == {"openai": 1, "anthropic": 1}
    assert PostBrand.objects.filter(post=post).count() == 2
    assert not BrandKeyword.objects.filter(brand_id__in=BRANDS).exists()
    assert not BrandAccount.objects.filter(brand_id__in=BRANDS).exists()
    assert set(Brand.objects.filter(nickname__in=BRANDS).values_list("is_sentinel", flat=True)) == {False}
    assert set(Brand.objects.filter(nickname__in=BRANDS).values_list("accent_color", flat=True)) == {None}
    from core.models import TwitterListMembership

    assert not TwitterListMembership.objects.filter(list_id=seed_module.MAIN_LIST).exists()
    assert not BrandAccount.objects.filter(account__author_id__startswith="9000000000000000").exists()
    # A repeated switch-off finds nothing left to undo and still matches.
    assert seed_module.switch_off(undo_receipt=receipt)["catalog_after"]["revision"] == pre_seed["revision"]
