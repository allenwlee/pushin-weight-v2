"""Catch accidental use of external geography metadata as a relationship key."""

from django.apps import apps
from django.core.checks import Error, Tags, register


@register(Tags.models)
def check_geolocation_reference_targets(app_configs=None, **kwargs):
    model_list = (
        apps.get_models() if app_configs is None
        else [model for config in app_configs for model in config.get_models()]
    )
    errors = []
    for model in model_list:
        for field in model._meta.local_fields:
            target = getattr(getattr(field, "remote_field", None), "model", None)
            if not hasattr(target, "_meta") or target._meta.db_table != "geolocations":
                continue
            if not field.target_field.primary_key:
                errors.append(Error(
                    f"{model._meta.label}.{field.name} must reference geolocations.id",
                    hint="Country codes and GeoNames IDs are import/export metadata.",
                    obj=field, id="core.E041",
                ))
    return errors
