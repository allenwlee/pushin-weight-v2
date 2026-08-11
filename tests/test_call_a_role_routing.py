from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest

from core.models import (
    Account,
    Brand,
    BrandAccount,
    Post,
    PostBrand,
    PostBrandMention,
    Role,
    TwitterListMembership,
)
from monitor.cycle import CycleRunner
from x_monitor.attribution import compile_keyword_index
from x_monitor.config import Config
from x_monitor.query_plan import PlannedCall

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db]


def _call(call_id="A"):
    return PlannedCall(
        call_id=call_id,
        call_kind="list" if call_id == "A" else "brand_wide",
        brand_id="*" if call_id == "A" else "deepseek",
        bucket=None,
        query_string=call_id,
        query_length=len(call_id),
    )


def _seed_author(*, author_id="author-1", active=True, edges=()):
    account = Account.objects.create(author_id=author_id, handle=author_id)
    TwitterListMembership.objects.create(
        list_id=42,
        account=account,
        active=active,
        source="snapshot",
        source_run_id="snapshot-1",
    )
    for brand_id, role_id in edges:
        Brand.objects.get_or_create(nickname=brand_id)
        Role.objects.get_or_create(key=role_id)
        BrandAccount.objects.create(
            brand_id=brand_id,
            account=account,
            role_id=role_id,
        )
    return account


def _tweet(tweet_id, *, author_id="author-1", text="off topic lunch"):
    return {
        "id": tweet_id,
        "author_id": author_id,
        "author_handle": author_id,
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "_api_received_monotonic": time.monotonic(),
    }


def _route(runner, item, *, call_id="A"):
    role_degraded = runner._prepare_call_a_roles([item], list_id=42)
    index = compile_keyword_index([("deepseek", "DeepSeek", False)])
    runner._attribute_items([item], index, {})
    kept = [
        item
        for item in [item]
        if not item.get("_unattributed") or item.get("_call_a_staff_candidate")
    ]
    routed = runner._route_and_persist(_call(call_id), kept)
    return role_degraded, routed


def _runner(llm_call=None):
    return CycleRunner(
        cfg=Config(
            enabled_models=["minimax", "deepseek"], daily_ceiling=100
        ),
        cycle_kind="scheduled",
        _relevancy_llm_call=llm_call,
    )


def test_official_seeds_own_brand_without_text_and_never_calls_relevance():
    _seed_author(edges=[("minimax", "official")])

    def forbidden(system, user):
        raise AssertionError("official author must bypass relevance")

    _, routed = _route(_runner(forbidden), _tweet("official"))
    assert routed[4] == 0
    assert Post.objects.filter(tweet_id="official").exists()
    assert set(PostBrand.objects.filter(post_id="official").values_list(
        "brand_id", flat=True
    )) == {"minimax"}
    mention = PostBrandMention.objects.get(
        post_id="official", brand_id="minimax", source="author_account"
    )
    assert "role=official" in mention.raw_token
    assert "run=snapshot-1" in mention.raw_token


def test_official_body_mention_adds_second_brand_with_distinct_provenance():
    _seed_author(edges=[("minimax", "official")])
    Brand.objects.get_or_create(nickname="deepseek")
    _route(_runner(), _tweet("both", text="DeepSeek launched a model"))

    assert set(PostBrand.objects.filter(post_id="both").values_list(
        "brand_id", flat=True
    )) == {"minimax", "deepseek"}
    assert PostBrandMention.objects.filter(
        post_id="both", brand_id="minimax", source="author_account"
    ).exists()
    assert PostBrandMention.objects.filter(
        post_id="both", brand_id="deepseek", source="body_keyword"
    ).exists()


def test_staff_only_is_gated_then_seeded_on_keep():
    _seed_author(edges=[("minimax", "staff")])
    calls = []

    def keep(system, user):
        calls.append((system, user))
        return "KEEP"

    _, routed = _route(_runner(keep), _tweet("staff-keep"))
    assert len(calls) == 1
    assert routed[4] == 0
    assert PostBrand.objects.filter(
        post_id="staff-keep", brand_id="minimax"
    ).exists()


def test_staff_drop_is_not_persisted_and_fail_open_is_persisted():
    _seed_author(edges=[("minimax", "staff")])
    _, dropped = _route(_runner(lambda s, u: "DROP"), _tweet("staff-drop"))
    assert dropped[4] == 1
    assert not Post.objects.filter(tweet_id="staff-drop").exists()

    def fail(system, user):
        raise TimeoutError("30 second bound")

    _, opened = _route(_runner(fail), _tweet("staff-open"))
    assert opened[5]
    assert PostBrand.objects.filter(
        post_id="staff-open", brand_id="minimax"
    ).exists()


def test_official_precedence_does_not_seed_staff_brand_or_call_relevance():
    _seed_author(edges=[("minimax", "official"), ("deepseek", "staff")])

    def forbidden(system, user):
        raise AssertionError("official precedence must bypass")

    _route(_runner(forbidden), _tweet("mixed-role"))
    assert set(PostBrand.objects.filter(post_id="mixed-role").values_list(
        "brand_id", flat=True
    )) == {"minimax"}


def test_stale_membership_cannot_seed_and_non_a_calls_never_use_relevance():
    _seed_author(active=False, edges=[("minimax", "official")])
    degraded, routed = _route(_runner(), _tweet("stale"))
    assert degraded == ["inactive_or_unknown_member:author-1"]
    assert routed[0] == []
    assert not Post.objects.filter(tweet_id="stale").exists()

    Brand.objects.get_or_create(nickname="deepseek")
    calls = []

    def forbidden(system, user):
        calls.append(1)
        return "DROP"

    item = _tweet("c-call", text="DeepSeek model", author_id="other")
    runner = _runner(forbidden)
    runner._attribute_items(
        [item], compile_keyword_index([("deepseek", "DeepSeek", False)]), {}
    )
    runner._route_and_persist(_call("C1"), [item])
    assert calls == []
    assert Post.objects.filter(tweet_id="c-call").exists()


def test_staff_candidate_near_receipt_deadline_fails_open_without_llm():
    _seed_author(edges=[("minimax", "staff")])
    calls = []
    item = _tweet("receipt-old")
    item["_api_received_monotonic"] = time.monotonic() - 106
    _, routed = _route(
        _runner(lambda s, u: calls.append(1) or "DROP"), item
    )
    assert calls == []
    assert any("receipt_age_fail_open" in value for value in routed[5])
    assert Post.objects.filter(tweet_id="receipt-old").exists()


def test_official_commits_before_first_staff_relevance_request():
    _seed_author(author_id="official", edges=[("minimax", "official")])
    _seed_author(author_id="staff", edges=[("minimax", "staff")])
    events = []

    def keep(system, user):
        events.append("relevance")
        assert Post.objects.filter(tweet_id="official-first").exists()
        return "KEEP"

    runner = _runner(keep)
    items = [
        _tweet("official-first", author_id="official"),
        _tweet("staff-second", author_id="staff"),
    ]
    runner._prepare_call_a_roles(items, list_id=42)
    runner._attribute_items(items, compile_keyword_index([]), {})
    kept = [
        item
        for item in items
        if not item.get("_unattributed") or item.get("_call_a_staff_candidate")
    ]
    runner._route_and_persist(_call(), kept)
    assert events == ["relevance"]
    assert Post.objects.filter(tweet_id="staff-second").exists()
