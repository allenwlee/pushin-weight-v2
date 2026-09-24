from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
import yaml
from django.core.management import call_command

from core.models import (
    Brand,
    BrandDiscoveryCandidate,
    BrandDiscoveryCandidateToken,
    BrandDiscoveryCandidateTokenEvidence,
    Post,
    RareTypeSearchHit,
    SearchQuery,
)
from core.rare_type_search import (
    mark_search_dispatched,
    persist_hit_batch,
    record_unknown_name_tokens,
    reserve_search_run,
)

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)


def _hit(tweet_id: str, *, kept: bool = True, observed_at: datetime = NOW):
    query = SearchQuery.objects.create(query_id=f"tokens-{tweet_id}")
    reservation = reserve_search_run(
        lane=f"tokens-{tweet_id}",
        slot_start=observed_at,
        source_query=query,
        query_string="test query",
        query_hash=(tweet_id * 64)[:64],
        query_version="test-v1",
        environment="test",
        release_sha="test",
        now=observed_at,
    )
    assert reservation.run is not None
    assert mark_search_dispatched(reservation.run.pk, now=observed_at)
    hit = persist_hit_batch(
        reservation.run.pk,
        [{"id": tweet_id, "text": "source-grounded token", "lang": "en"}],
        now=observed_at,
        raw_count=1,
        normalized_count=1,
    )[0]
    post = Post.objects.create(tweet_id=tweet_id, text="source-grounded token")
    RareTypeSearchHit.objects.filter(pk=hit.pk).update(
        gate_state=(
            RareTypeSearchHit.GateState.KEPT
            if kept
            else RareTypeSearchHit.GateState.JUNK
        ),
        post=post,
    )
    hit.refresh_from_db()
    return hit


MOONSHOT_FORMS = [
    {"form": "Moonshot", "kind": "spelling", "script": "latn"},
    {"form": "月之暗面", "kind": "spelling", "script": "hans"},
    {"form": "@Kimi_Moonshot", "kind": "handle", "script": "latn"},
    {"form": "Kimi", "kind": "nickname", "script": "latn"},
]


def test_exact_forms_survive_replay_and_yaml_round_trip():
    first = _hit("2100299862839603398")
    candidate = record_unknown_name_tokens(
        hit=first,
        candidate_identity="cand_moonshot_kimi",
        observed_name="Moonshot",
        tokens=MOONSHOT_FORMS,
        rare_types=["personnel_changes"],
    )
    record_unknown_name_tokens(
        hit=first,
        candidate_identity="cand_moonshot_kimi",
        observed_name="Moonshot",
        tokens=MOONSHOT_FORMS,
        rare_types=["personnel_changes"],
        observed_at=NOW + timedelta(minutes=5),
    )

    assert list(
        candidate.exact_tokens.order_by("id").values_list("form", flat=True)
    ) == ["Moonshot", "月之暗面", "@Kimi_Moonshot", "Kimi"]
    assert BrandDiscoveryCandidateToken.objects.count() == 4
    assert BrandDiscoveryCandidateTokenEvidence.objects.count() == 4

    stdout = StringIO()
    call_command("export_rare_type_tokens", stdout=stdout)
    document = yaml.safe_load(stdout.getvalue())
    assert document == {
        "version": 1,
        "candidates": [
            {
                "id": "cand_moonshot_kimi",
                "status": "pending",
                "rare_types_seen": ["personnel_changes"],
                "tokens": [
                    {"form": "@Kimi_Moonshot", "kind": "handle", "script": "latn"},
                    {"form": "Kimi", "kind": "nickname", "script": "latn"},
                    {"form": "Moonshot", "kind": "spelling", "script": "latn"},
                    {"form": "月之暗面", "kind": "spelling", "script": "hans"},
                ],
                "first_post_id": "2100299862839603398",
                "last_post_id": "2100299862839603398",
            }
        ],
    }


def test_similar_tokens_stay_under_distinct_candidate_identities():
    first = _hit("101")
    second = _hit("102", observed_at=NOW + timedelta(minutes=15))
    token = [{"form": "Moonshot", "kind": "spelling", "script": "latn"}]
    for hit, identity in ((first, "candidate-a"), (second, "candidate-b")):
        record_unknown_name_tokens(
            hit=hit,
            candidate_identity=identity,
            observed_name="Moonshot",
            tokens=token,
            rare_types=["model_releases"],
        )
    assert BrandDiscoveryCandidate.objects.count() == 2
    assert BrandDiscoveryCandidateToken.objects.count() == 2


def test_hostile_yaml_scalar_is_quoted_safely_and_export_is_deterministic():
    hit = _hit("201")
    hostile = "yes: [no]\n---\n!!python/object/apply:os.system ['false']"
    record_unknown_name_tokens(
        hit=hit,
        candidate_identity="hostile",
        observed_name=hostile,
        tokens=[{"form": hostile, "kind": "nickname", "script": "latn"}],
        rare_types=["events"],
    )
    first = StringIO()
    second = StringIO()
    call_command("export_rare_type_tokens", stdout=first)
    call_command("export_rare_type_tokens", stdout=second)
    assert first.getvalue() == second.getvalue()
    assert (
        yaml.safe_load(first.getvalue())["candidates"][0]["tokens"][0]["form"]
        == hostile
    )


def test_junk_hit_cannot_create_candidate_or_token():
    hit = _hit("301", kept=False)
    with pytest.raises(ValueError, match="kept hit"):
        record_unknown_name_tokens(
            hit=hit,
            candidate_identity="must-not-exist",
            observed_name="JunkCo",
            tokens=[{"form": "JunkCo", "kind": "spelling", "script": "latn"}],
            rare_types=["job_listings"],
        )
    assert not BrandDiscoveryCandidate.objects.exists()


def test_export_does_not_promote_candidates_to_brands():
    hit = _hit("401")
    record_unknown_name_tokens(
        hit=hit,
        candidate_identity="unknown-only",
        observed_name="Unknown AI",
        tokens=[{"form": "Unknown AI", "kind": "spelling", "script": "latn"}],
        rare_types=["opportunities"],
    )
    brand_count = Brand.objects.count()
    call_command("export_rare_type_tokens", stdout=StringIO())
    assert Brand.objects.count() == brand_count
    assert not Brand.objects.filter(nickname="unknown-only").exists()
