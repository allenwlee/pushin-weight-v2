"""Resolve exact source codes at ingestion; consumers store typed references."""

from core.models import (
    AccountVerificationType,
    ModelTask,
    ProviderLabelDisplayType,
    ProviderLabelType,
    ProviderLinkType,
    SoftwareLibrary,
    SourceIdentifierNamespace,
)

CATALOGUES = {
    "software_libraries": SoftwareLibrary,
    "model_tasks": ModelTask,
    "account_verification_types": AccountVerificationType,
    "provider_label_types": ProviderLabelType,
    "provider_label_display_types": ProviderLabelDisplayType,
    "provider_link_types": ProviderLinkType,
    "source_identifier_namespaces": SourceIdentifierNamespace,
}


def reference_id(catalogue, source_id, code, *, subject_kind=None, using="default"):
    """Keep code case/wording and NULL distinct from explicit empty identities.

    New provider codes may be registered within their typed catalogue. This does
    not create a business classification or imply equivalence across providers.
    Do not cache IDs across database restores or transaction rollbacks.
    """
    model = CATALOGUES[catalogue]
    namespace = model is SourceIdentifierNamespace
    if namespace and subject_kind not in {"repository", "model", "lab", "account"}:
        raise ValueError("identifier namespace requires a supported subject kind")
    if not namespace and subject_kind is not None:
        raise ValueError("subject kind applies only to identifier namespaces")
    if code is None:
        return None
    if (
        not isinstance(code, str)
        or len(code) > model._meta.get_field("code").max_length
    ):
        raise ValueError("invalid source vocabulary code")
    if code != code.strip() or any(ord(c) < 32 or ord(c) == 127 for c in code):
        raise ValueError("invalid source vocabulary code")
    if not code and model not in {SourceIdentifierNamespace, AccountVerificationType}:
        return None
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source vocabulary requires a source identity")
    identity = {"data_source_id": source_id, "code": code}
    if namespace:
        identity["subject_kind"] = subject_kind
    value, _ = model.objects.using(using).get_or_create(**identity)
    return value.pk
