"""Source-qualified account classification references and stable public codes."""

from core.source_vocabulary import reference_id

X_FIELDS = {
    "verified_type": "account_verification_types",
    "affiliate_label_url_type": "provider_link_types",
    "affiliate_label_user_label_display_type": "provider_label_display_types",
    "affiliate_label_user_label_type": "provider_label_types",
    "identity_profile_label_url_type": "provider_link_types",
    "identity_profile_label_user_label_display_type": "provider_label_display_types",
    "identity_profile_label_user_label_type": "provider_label_types",
}
SNAPSHOT_FIELDS = {
    "verified_type": "account_verification_types",
    "affiliate_label_type": "provider_label_types",
    "affiliate_display_type": "provider_label_display_types",
}


def code_for(record, field):
    value = getattr(record, field)
    return value.code if value is not None else None


def snapshot_references(values, source_id):
    result = dict(values)
    for field, catalogue in SNAPSHOT_FIELDS.items():
        if field in result:
            result[field + "_id"] = reference_id(
                catalogue, source_id, result.pop(field)
            )
    return result
