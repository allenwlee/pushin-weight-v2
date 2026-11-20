from datetime import UTC, datetime
from types import SimpleNamespace

from monitor.enrichment_queue import stage_is_due


def test_translation_is_due_only_after_explicit_request():
    now = datetime.now(UTC)
    state = SimpleNamespace(
        translation_status='pending', translation_next_attempt_at=None,
        translation_requested=False, source_collection_job_id=None,
    )
    assert not stage_is_due(state, 'translation', now)
    state.translation_requested = True
    assert stage_is_due(state, 'translation', now)


def test_classification_does_not_require_translation_request():
    now = datetime.now(UTC)
    state = SimpleNamespace(
        classification_status='pending', classification_next_attempt_at=None,
        translation_requested=False, source_collection_job_id=None,
    )
    assert stage_is_due(state, 'classification', now)
