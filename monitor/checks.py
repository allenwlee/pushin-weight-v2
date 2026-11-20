"""Validate the classifier's promotion matcher without startup data writes."""

from django.core.checks import Error, Tags, register

from monitor.promotion_subject_matcher import load_matching_config


@register(Tags.models)
def check_promotion_subject_matching_config(app_configs=None, **kwargs):
    try:
        # Schema-independent by default; selected runtime supplies its complete
        # registry separately before admitting provider work.
        load_matching_config(kwargs.get("config_path"), known_brand_ids=kwargs.get("known_brand_ids"))
    except (OSError, ValueError) as exc:
        return [Error(str(exc), id="monitor.E051")]
    return []
