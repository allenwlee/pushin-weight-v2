"""Source/resource namespace resolution at explicit persistence boundaries."""

from core.models import CollectionObservation, SourceSubjectMapping
from core.source_vocabulary import reference_id


def namespace_id(source, kind, code):
    return reference_id("source_identifier_namespaces", source, code, subject_kind=kind)


def target_namespace_id(values):
    code = values.get("identifier_scope")
    if code is None:
        return None
    mapping = None
    observation = None
    if values.get("mapping_id") is not None:
        mapping = SourceSubjectMapping.objects.get(pk=values["mapping_id"])
    if values.get("evidence_observation_id") is not None:
        observation = CollectionObservation.objects.select_related("run__job").get(
            pk=values["evidence_observation_id"]
        )
    if mapping is not None:
        source, kind = mapping.source_id, mapping.source_subject_kind
        if observation is not None and observation.run.job.source_id != source:
            raise ValueError("target mapping and evidence sources disagree")
    elif observation is not None:
        source = observation.run.job.source_id
        kind = observation.source_subject_kind
        if values.get("target_kind") == "match_candidate":
            if source not in {"github", "hf", "arena", "openrouter"}:
                raise ValueError("unsupported matching evidence source")
            kind = "repository" if source == "github" else "model"
    else:
        raise ValueError("identifier namespace requires pinned mapping or evidence")
    return namespace_id(source, kind, code)
