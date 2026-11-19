"""Runtime cleanup must respect retained rows behind nullable foreign keys."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

from core.models import (
    CollectionCorrection,
    CollectionRun,
    EditorialStory,
    OriginalContentCall,
    OriginalContentRun,
    ProviderBatch,
)
from monitor.editorial.chatter_sources import SourceSession
from monitor.original_content import digest
from scripts.staging_refresh.database import RefreshError, scrub_candidate_data
from scripts.staging_refresh.policy import load_policy
from tests.test_chatter_chain import chain_config
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose
from x_monitor.x_client import XClient

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.requires_postgres]


def policy():
    return load_policy(Path(__file__).resolve().parents[1] / "config/staging_refresh.yaml")


def correction():
    from core.collection_corrections import correct_attribution
    from core.models import Actor
    from tests.test_source_metric_projection import configured, evidence, project

    contract, raw, _, _ = configured(mapped=True, product_type="llm-model")
    observation = project(contract, "hf", [evidence("hf", raw)]).observations.get()
    actor = Actor.objects.create(actor_kind="human", actor_key="retained-operator")
    row = correct_attribution(
        observation, product=None, mapping=None, actor_identity=actor,
        reason="incorrect_product",
    )
    return row, observation


def runtime_run():
    return OriginalContentRun.objects.create(
        source_cycle_id=str(uuid4()), scope_key="chatter:v1",
        workflow_key="chatter-discovery", facts_as_of=timezone.now(),
        packet_schema_version=1, snapshot={}, execution_state="running",
        lease_until=timezone.now() + timedelta(minutes=10),
    )


def test_scrub_keeps_null_owner_measurements_and_removes_linked_runtime():
    saved, observation = correction()
    expected = CollectionCorrection.objects.values().get(pk=saved.pk)
    get_user_model().objects.create_user(username="disposable-login")
    run = runtime_run()
    call = OriginalContentCall.objects.create(
        run=run, stage="discovery", workflow_key="chatter-discovery",
        request_identity=str(uuid4()), state="completed", reserved_at=timezone.now(),
        sent_at=timezone.now(), completed_at=timezone.now(),
        request_hash=digest({}), response_hash=digest({}),
    )
    session = SourceSession(
        run, chain_config(), purpose=TwitterApiCredentialPurpose.ON_DEMAND,
        client=XClient(api_key="fixture-only", max_retries=0),
    )
    scope = session.scope("disposable-source", "fixture cleanup")
    source_run = CollectionRun.objects.get(pk=session.claim.run_id)
    batch = ProviderBatch.objects.create(
        source_collection_job=source_run.job, group_key="disposable",
        transport="direct", source_definition_hash="1" * 64,
        cohort_hash="2" * 64, manifest_hash="3" * 64,
        provider="fixture", model="fixture", endpoint="https://example.invalid",
        request_profile="fixture", deadline_at=timezone.now() + timedelta(hours=1),
    )
    story = EditorialStory.objects.create(development_key="disposable:" + str(uuid4()))
    assert observation.run.content_run_id is None
    assert source_run.content_run_id == run.pk
    assert scope.content_call_id == call.pk

    with transaction.atomic(), connection.cursor() as cursor:
        scrub_candidate_data(cursor, policy())

    assert CollectionCorrection.objects.values().get(pk=saved.pk) == expected
    observation.refresh_from_db()
    assert not get_user_model().objects.exists()
    assert not CollectionRun.objects.filter(pk=source_run.pk).exists()
    assert not OriginalContentRun.objects.filter(pk=run.pk).exists()
    assert not OriginalContentCall.objects.filter(pk=call.pk).exists()
    assert not ProviderBatch.objects.filter(pk=batch.pk).exists()
    assert not EditorialStory.objects.filter(pk=story.pk).exists()


def test_scrub_refuses_to_delete_a_retained_measurements_content_owner():
    saved, observation = correction()
    expected = CollectionCorrection.objects.values().get(pk=saved.pk)
    user = get_user_model().objects.create_user(username="must-survive-refusal")
    run = runtime_run()
    CollectionRun.objects.filter(pk=observation.run_id).update(content_run=run)

    with (
        pytest.raises(RefreshError, match="retained_runtime_reference"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        scrub_candidate_data(cursor, policy())

    assert get_user_model().objects.filter(pk=user.pk).exists()
    assert OriginalContentRun.objects.filter(pk=run.pk).exists()
    assert CollectionCorrection.objects.values().get(pk=saved.pk) == expected


def test_scrub_preserves_a_retained_querys_required_story_on_refusal():
    from core.models import SearchQuery
    from monitor.editorial.chatter_history import save_query

    user = get_user_model().objects.create_user(username="query-owner-refusal")
    story = EditorialStory.objects.create(development_key="retained:" + str(uuid4()))
    query = save_query("retained source query", development=story)
    with (
        pytest.raises(RefreshError, match="retained_runtime_reference:public.search_queries"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        scrub_candidate_data(cursor, policy())
    assert get_user_model().objects.filter(pk=user.pk).exists()
    assert EditorialStory.objects.filter(pk=story.pk).exists()
    assert SearchQuery.objects.get(pk=query.pk).development_id == story.pk
