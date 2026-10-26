"""Shared publication source artifacts and typed selection without retired fields."""

import httpx
import pytest

from core.collection_capture import observation_object_documents, run_report_document
from core.model_history_collection import execute_model_history
from core.model_history_publications import (
    ROW_CAPTURE,
    WINDOW_CAPTURE,
    _publication_window,
)
from core.models import CollectionObservation, CollectionRun, MetricValue
from scripts.benchmark_download_collector.sources import Budget, SourceError
from tests.test_data_source_history_ingestion import (
    latest_arena_transport,
    publication_scope,
    register,
    transport,
)
from tests.test_hf_catalog_retirement import denied_retirement_columns

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize(
    "source,config", [("openrouter", "text"), ("arena", "text"), ("arena", "agent")]
)
def test_shared_window_and_selected_rows_work_without_retiring_columns(source, config):
    provider, _product, scope = publication_scope(source, config=config)
    job = register(provider, scope)
    with denied_retirement_columns():
        budget, requests = transport(source, config=config)
        run = execute_model_history(job.pk, budget=budget, key="fixture")
        assert run.status == "success", run_report_document(run)
        values = MetricValue.objects.count()
        assert values > 0
        selected = list(
            CollectionObservation.objects.filter(projection_kind=ROW_CAPTURE)
        )
        assert selected
        for observation in selected:
            raw, dimensions, metadata = observation_object_documents(observation)
            edge = observation.inputs.get(input_role="publication_row_origin")
            assert (
                edge.input_observation_id
                == observation.scope_run.resource_observation_id
            )
            assert edge.row_locator.isdecimal()
            assert len(raw["rows"]) == 1 and dimensions["kind"] == "publication_row"
            assert (
                metadata["numeric_snapshot_identity"]["revision"]
                == observation.provider_revision
            )
            assert (
                metadata["numeric_snapshot_identity"]["period"]
                == observation.source_record_date.isoformat()
            )
        window = CollectionObservation.objects.get(projection_kind=WINDOW_CAPTURE)
        assert (
            window.run.payload_archive_id
            and window.scope_run.phase == "typed-publication-v1"
        )
        assert window.run.attempts.get().actual_requests == len(requests)
        assert window.run.attempts.get().accounting_complete is True
        assert window.run.request_count == len(requests)
        assert run.request_count == 0
        previous_at = window.observed_at
        replay = register(provider, scope, key="publication-replay")
        second_budget, second_requests = transport(source, config=config)
        second = execute_model_history(replay.pk, budget=second_budget, key="fixture")
        assert second.status == "success", run_report_document(second)
        assert not second_requests and MetricValue.objects.count() == values
        window.refresh_from_db()
        assert window.observed_at == previous_at


@pytest.mark.parametrize(
    "published,has_values",
    [("2026-09-11", True), ("2026-09-09", False), ("2026-09-12", False)],
)
def test_latest_artifact_keeps_native_publication_day_and_incomplete_coverage(
    published, has_values
):
    provider, _product, scope = publication_scope("arena")
    scope.update(arena_publication_mode="latest-artifact-v1", publication_window_days=1)
    job = register(provider, scope)
    with denied_retirement_columns():
        budget, requests = latest_arena_transport(published=published)
        run = execute_model_history(job.pk, budget=budget)
        assert run.status == "success", run_report_document(run)
        assert len(requests) == 1 and MetricValue.objects.exists() is has_values
        window = CollectionObservation.objects.get(projection_kind=WINDOW_CAPTURE)
        payload, _, _ = observation_object_documents(window)
        assert payload["rows"][0]["leaderboard_publish_date"] == published
        assert (
            window.processing_outcome == "latest_publication_only"
            and window.publication_complete is False
        )
        assert run_report_document(run)["coverage"][0]["outcome"] == "not_published"
        if has_values:
            assert {v.as_of_date.isoformat() for v in MetricValue.objects.all()} == {
                published
            }


@pytest.mark.parametrize("damage", ["position", "dataset"])
def test_publication_row_refuses_changed_evidence_without_legacy_fallback(damage):
    provider, _product, scope = publication_scope()
    job = register(provider, scope)
    with denied_retirement_columns():
        run = execute_model_history(job.pk, budget=transport()[0], key="fixture")
        assert run.status == "success"
        observation = CollectionObservation.objects.filter(
            projection_kind=ROW_CAPTURE
        ).first()
        if damage == "position":
            edge = observation.inputs.get(input_role="publication_row_origin")
            edge.row_locator = "999999"
            edge.save(update_fields=["row_locator"])
        else:
            observation.source_dataset = None
            observation.save(update_fields=["source_dataset"])
        with pytest.raises(ValueError, match="changed"):
            observation_object_documents(observation)


def test_shared_window_retry_preserves_physical_attempts_and_parent_budget():
    provider, _product, scope = publication_scope()
    job = register(provider, scope)
    with denied_retirement_columns():
        failed = Budget(
            httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(503))
            ),
            max_requests=2,
            sleep=lambda _: None,
        )
        with pytest.raises(SourceError, match="http_503"):
            _publication_window(
                job, failed, "2026-09-10", "2026-09-11", key="fixture", config="text"
            )
        child = CollectionRun.objects.get(
            job__job_key__startswith="publication-window:"
        )
        assert child.request_count == 2 and child.attempts.get().actual_requests == 2
        assert child.payload_archive_id is None and failed.remaining == 0
        budget, requests = transport()
        initial = budget.remaining
        window = _publication_window(
            job, budget, "2026-09-10", "2026-09-11", key="fixture", config="text"
        )
        assert window.run_id == child.pk
        child.refresh_from_db()
        assert child.request_count == 2 + len(requests)
        assert budget.remaining == initial - len(requests)
        assert child.attempts.count() == 2
        assert child.attempts.order_by("ordinal").first().accounting_complete is False
        assert child.attempts.order_by("ordinal").last().accounting_complete is True


def test_unknown_transport_keeps_incomplete_accounting_after_successful_retry():
    provider, _product, scope = publication_scope()
    job = register(provider, scope)
    success, _ = transport()
    calls = []

    def respond(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("unknown reply", request=request)
        return success.client._transport.handle_request(request)

    with denied_retirement_columns():
        budget = Budget(
            httpx.Client(transport=httpx.MockTransport(respond)),
            max_requests=5,
            sleep=lambda _: None,
        )
        window = _publication_window(
            job, budget, "2026-09-10", "2026-09-11", key="fixture", config="text"
        )
        attempt = window.run.attempts.get()
        assert len(calls) == attempt.actual_requests == window.run.request_count == 2
        assert (
            attempt.unknown_sent_requests == 1 and attempt.accounting_complete is False
        )
        assert (
            window.inputs.filter(input_role="publication_source_response").count() == 1
        )
        assert budget.remaining == 3


def test_unadopted_cached_window_stops_before_provider_request():
    provider, _product, scope = publication_scope()
    job = register(provider, scope)
    with denied_retirement_columns():
        window = _publication_window(
            job,
            transport()[0],
            "2026-09-10",
            "2026-09-11",
            key="fixture",
            config="text",
        )
        CollectionObservation.objects.filter(pk=window.pk).update(projection_kind=None)
        budget, requests = transport()
        before = budget.remaining
        with pytest.raises(ValueError, match="requires typed adoption"):
            _publication_window(
                job, budget, "2026-09-10", "2026-09-11", key="fixture", config="text"
            )
        assert not requests and budget.remaining == before
