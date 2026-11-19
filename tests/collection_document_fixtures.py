"""Represent captured evidence in the schema selected by a collection test."""

from core.collection_capture import archive_legacy, observation_object_documents
from core.models import CollectionObservation


def historical_models():
    """Bind fixture builders/copiers to the selected physical migration state."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from tests.collection_fixtures import historical_fixture_models

    executor = MigrationExecutor(connection)
    apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
    return historical_fixture_models(apps)


def observation_values(*, listing=None, dimensions=None, source_metadata=None):
    documents = {
        "listing": {} if listing is None else listing,
        "dimensions": {} if dimensions is None else dimensions,
        "source_metadata": {} if source_metadata is None else source_metadata,
    }
    if hasattr(CollectionObservation, "listing"):
        return documents
    return {"legacy_archive": archive_legacy(documents)}


def documents(observation):
    return dict(zip(
        ("listing", "dimensions", "source_metadata"),
        observation_object_documents(observation), strict=True,
    ))


def replace_documents(observation, **changes):
    captured = {**documents(observation), **changes}
    if hasattr(type(observation), "listing") and observation.legacy_archive_id is None:
        for field, value in captured.items():
            setattr(observation, field, value)
        observation.save(update_fields=list(captured))
    else:
        observation.legacy_archive = archive_legacy(captured)
        observation.save(update_fields=["legacy_archive"])
