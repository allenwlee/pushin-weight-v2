"""Source-qualified feed identities; publisher/host evidence stays separate."""

from core.measurement_taxonomy import require
from core.models import SourceDataset


def dataset_code(metadata):
    """Read existing adapter coordinates without changing source policy meaning."""
    publication = metadata.get("publication_provenance")
    require(publication is None or type(publication) is dict, "invalid publication provenance")
    values = [
        value for value in (
            metadata.get("dataset_id"), (publication or {}).get("dataset_id"),
        ) if value is not None
    ]
    require(
        all(type(value) is str and 0 < len(value) <= 256 for value in values),
        "invalid source dataset code",
    )
    require(len(set(values)) <= 1, "conflicting source dataset coordinates")
    return values[0] if values else None


def resolve_dataset(source_id, metadata, *, cache=None):
    code = dataset_code(metadata)
    if code is None:
        return None
    key = (source_id, code)
    if cache is not None and key in cache:
        return cache[key]
    dataset, _ = SourceDataset.objects.get_or_create(source_id=source_id, code=code)
    if cache is not None:
        cache[key] = dataset
    return dataset


def observation_dataset_code(observation):
    return observation.source_dataset.code if observation.source_dataset_id is not None else None
