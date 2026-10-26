"""Replay native release assets through their captured replies and typed parents."""

from core.collection_capture import observation_object_documents, read_document
from core.measurement_taxonomy import digest, require


def _native_id(value):
    require(
        isinstance(value, str) and value.isascii() and value.isdecimal()
        and value.lstrip("0") == value,
        "GitHub asset identity is not a positive native ID",
    )
    return int(value)


def asset_documents(observation, *, legacy_documents=None):
    """Select one original asset object; do not infer its parent from JSON keys.

    Numbers are still parsed by the shared metric-purpose writer. The catalog
    observation supplies the exact captured object and its frozen identity.
    """
    require(
        observation.run.job.source_id == "github"
        and observation.run.job.purpose == "catalog"
        and observation.source_subject_kind == "repository",
        "GitHub asset requires catalog repository evidence",
    )
    snapshot = getattr(observation, "resource_snapshot", None)
    require(
        snapshot is not None and snapshot.resource_kind == "release_asset"
        and snapshot.native_identifier == observation.source_identifier,
        "GitHub asset snapshot is not retained",
    )
    asset_id = _native_id(snapshot.native_stable_id)
    repository_id = _native_id(observation.source_identifier)
    publisher = snapshot.publisher_account
    require(publisher is not None and publisher.data_source_id == "github",
            "GitHub asset publisher is not retained")
    owner_id = _native_id(publisher.normalized_identifier)
    parents = list(observation.inputs.filter(input_role="release_asset_parent").select_related(
        "input_observation__run__job", "input_observation__resource_snapshot",
    ))
    require(len(parents) == 1, "GitHub asset requires one captured release parent")
    edge = parents[0]
    release = edge.input_observation
    parent = getattr(release, "resource_snapshot", None)
    require(
        release is not None and release.status == "ok"
        and release.run.job.source_id == "github" and release.run.job.purpose == "catalog"
        and release.source_subject_kind == "repository"
        and release.source_identifier == observation.source_identifier
        and parent is not None and parent.resource_kind == "releases"
        and parent.native_identifier == observation.source_identifier
        and parent.publisher_account_id in (None, publisher.pk)
        and edge.input_sha256 == release.observation_key
        and edge.row_locator == parent.native_stable_id,
        "GitHub release parent identity mismatch",
    )
    release_id = _native_id(parent.native_stable_id)
    coordinates = {"release_id": release_id, "asset_id": asset_id}
    replies = list(observation.inputs.filter(input_request__isnull=False).select_related(
        "input_request__archive", "input_request__attempt",
    ))
    if not replies:
        # Historical selected-object evidence may predate request capture. Keep
        # that compatibility, but require the same typed identity/parent proof.
        raw, _, metadata = legacy_documents or observation_object_documents(observation)
        require(type(raw.get("id")) is int and raw["id"] == asset_id,
                "GitHub asset payload identity mismatch")
        for key, expected in (("owner_id", owner_id), ("repository_id", repository_id)):
            require(key not in metadata or str(metadata[key]) == str(expected),
                    "GitHub asset captured ownership mismatch")
        metadata = {**metadata, "owner_id": owner_id, "repository_id": repository_id}
    else:
        require(observation.payload_sha256 is not None, "GitHub asset payload hash is not retained")
        selected = []
        for reply in replies:
            request = reply.input_request
            require(
                request.attempt.run_id == observation.run_id
                and request.scope_run_id == observation.scope_run_id
                and request.transport_outcome == "received" and request.http_status == 200
                and request.archive_id is not None
                and reply.input_sha256 == request.archive.content_sha256,
                "GitHub asset response identity mismatch",
            )
            body = read_document(request.archive)
            require(isinstance(body, list), "GitHub assets require a captured list reply")
            selected.extend(
                row for row in body if isinstance(row, dict)
                and type(row.get("id")) is int and row["id"] == asset_id
                and digest(row) == observation.payload_sha256
            )
        require(selected and all(row == selected[0] for row in selected),
                "GitHub asset object is absent or conflicting in captured replies")
        raw = selected[0]
        metadata = {
            "clocks": {"asset_created_at": raw.get("created_at"),
                       "asset_updated_at": raw.get("updated_at")},
            "reused_from": None, "owner_id": owner_id, "repository_id": repository_id,
        }
    dimensions = {"kind": "release_asset", "coordinate": coordinates, **coordinates}
    return raw, dimensions, metadata
