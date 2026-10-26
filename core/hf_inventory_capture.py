"""Selected HF inventory objects backed by exact captured provider responses."""

import json

from core.collection_capture import archive_document, link_request, read_document
from core.collection_numeric_selection import record_numeric_selection
from core.collection_resources import project_observation_facts
from core.hf_catalog import _accepted_request
from core.measurement_taxonomy import digest, require

EVIDENCE_KIND = "hf_inventory_evidence"
KINDS = {"creation_inventory": "namespace", "hf_metadata": "hf_metadata", "hf_profile": "hf_profile"}


def capture_object(observation, result, *, raw, position=None, fields=None, metadata=None):
    """Caller holds the run fence; retain evidence before publishing the checkpoint."""
    request = _accepted_request(result)
    require(request is not None and request.scope_run_id == observation.scope_run_id
            and request.attempt.run_id == observation.run_id,
            "HF inventory capture belongs to another scope or run")
    # These derived diagnostics have no operational reader. Preserve the exact
    # original result without making it a replacement execution settings bag.
    document = {"hf_inventory_evidence": 1, "observation_key": observation.observation_key,
                "metadata": metadata or {}}
    observation.legacy_archive = archive_document(
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
        encoding="selected-json-canonical-v1", capture_kind=EVIDENCE_KIND,
    )
    observation.payload_sha256 = digest(raw)
    observation.save(update_fields=["legacy_archive", "payload_sha256"])
    edge = link_request(observation, request, role="hf_inventory_capture",
                        row_locator="object" if position is None else str(position))
    if edge.row_locator != ("object" if position is None else str(position)):
        raise ValueError("HF inventory selected position changed")
    record_numeric_selection(observation, fields)
    snapshot = project_observation_facts(observation)
    change = (metadata or {}).get("file_changes")
    if change is not None:
        snapshot.file_change_kind = change["kind"]
        snapshot.file_comparison_basis = change["comparison_basis"]
        snapshot.save(update_fields=["file_change_kind", "file_comparison_basis"])


def inventory_documents(observation):
    """No legacy-column or derived-archive fallback for an adopted capture."""
    kind = observation.observation_kind
    scope = observation.scope_run
    require(observation.run.job.source_id == "hf" and observation.run.job.purpose == "catalog"
            and kind in KINDS and scope is not None and scope.run_id == observation.run_id
            and scope.scope_kind == KINDS[kind], "HF inventory capture owner changed")
    group = None
    namespace = observation.source_identifier if kind == "hf_profile" else observation.source_identifier.split("/", 1)[0]
    frozen = observation.run.job.scope["hf_scope"]["namespaces"]
    require(sum(entry["namespace"].casefold() == namespace.casefold() for entry in frozen) == 1,
            "HF inventory namespace differs from frozen instructions")
    if kind in {"creation_inventory", "hf_profile"}:
        require(scope.scope_key.casefold() == namespace.casefold(), "HF inventory namespace owner changed")
    require(observation.source_subject_kind == ("account" if kind == "hf_profile" else "repository"),
            "HF inventory subject kind changed")
    if kind == "hf_metadata":
        parent = scope.resource_observation
        group = scope.phase
        require(group in {"detail", "expanded"} and parent is not None
                and parent.run_id == observation.run_id
                and parent.source_identifier == observation.source_identifier
                and parent.scope_run.scope_kind == "namespace"
                and parent.scope_run.scope_key.casefold() == namespace.casefold()
                and scope.scope_key == observation.source_identifier + ":" + group,
                "HF metadata parent or group changed")
    links = list(observation.inputs.filter(input_role="hf_inventory_capture").select_related(
        "input_request__archive", "input_request__attempt",
    ))
    require(links, "HF inventory capture has no request input")
    matches = []
    for link in links:
        request = link.input_request
        require(request is not None and request.scope_run_id == scope.pk
                and request.attempt.run_id == observation.run_id
                and request.transport_outcome == "received" and request.http_status == 200
                and request.request_group == (group or ("profile" if kind == "hf_profile" else "listing"))
                and request.archive_id is not None
                and link.input_sha256 == request.archive.content_sha256,
                "HF inventory request ownership or checksum changed")
        body = read_document(request.archive)
        if kind == "creation_inventory":
            locator = link.row_locator
            require(isinstance(locator, str) and locator.isascii() and locator.isdecimal()
                    and str(int(locator)) == locator and isinstance(body, list)
                    and int(locator) < len(body), "HF inventory list position is invalid")
            raw = body[int(locator)]
        else:
            require(link.row_locator == "object", "HF inventory object position is invalid")
            raw = body
        require(isinstance(raw, dict), "HF inventory response is not an object")
        native_id = (raw.get("name") or raw.get("user") or raw.get("organization") or raw.get("id")) \
            if kind == "hf_profile" else (raw.get("id") or raw.get("modelId"))
        require(isinstance(native_id, str)
                and native_id.casefold() == observation.source_identifier.casefold(),
                "HF inventory native identity changed")
        if digest(raw) == observation.payload_sha256:
            matches.append(raw)
    require(matches and all(row == matches[0] for row in matches),
            "HF inventory selected object is absent or conflicting")
    dimensions = {} if kind == "hf_profile" else {"kind": kind}
    if group:
        dimensions["group"] = group
    metadata = {}
    if observation.historical_visibility_proven is not None:
        metadata["historical_public_visibility_proven"] = observation.historical_visibility_proven
    snapshot = getattr(observation, "resource_snapshot", None)
    if snapshot is not None and (snapshot.file_change_kind is not None or snapshot.file_comparison_basis is not None):
        metadata["file_changes"] = {"kind": snapshot.file_change_kind,
                                    "comparison_basis": snapshot.file_comparison_basis}
    return matches[0], dimensions, metadata
