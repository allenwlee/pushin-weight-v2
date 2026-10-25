"""Product classification boundaries; raw provider payloads remain with their capture."""

from core.models import ModelGatingState, ProductRelationshipType, ProductType
from core.source_vocabulary import reference_id


def product_type_id(code):
    if code is None:
        return None
    try:
        return ProductType.objects.only("id").get(code=code).pk
    except ProductType.DoesNotExist as exc:
        raise ValueError("invalid_product_type") from exc


def relationship_type_id(code):
    try:
        return ProductRelationshipType.objects.only("id").get(code=code).pk
    except ProductRelationshipType.DoesNotExist as exc:
        raise ValueError("invalid_product_relationship_type") from exc


def product_type_choices():
    labels = {
        "llm-model": "LLM model",
        "other-ai-model": "Other AI model",
        "agent-harness": "Agent harness",
    }
    return [
        (code, labels.get(code, code))
        for code in ProductType.objects.order_by("code").values_list("code", flat=True)
    ]


def gating_state_id(value):
    if value is None:
        return None
    if type(value) is bool:
        code = "gated" if value else "public"
    elif isinstance(value, str):
        code = {"False": "public", "True": "gated"}.get(value, value)
    else:
        raise ValueError("invalid model gating value")
    try:
        return ModelGatingState.objects.only("id").get(code=code).pk
    except ModelGatingState.DoesNotExist as exc:
        raise ValueError("unregistered model gating state") from exc


def metadata_references(values, *, source_id):
    """Convert just fields present in this update; absence never clears prior data."""
    result = dict(values)
    for field, catalogue in (
        ("library_name", "software_libraries"),
        ("pipeline_tag", "model_tasks"),
    ):
        if field in result:
            result[field + "_id"] = reference_id(
                catalogue, source_id, result.pop(field)
            )
    for field in ("gated", "gated_status"):
        if field in result:
            result["gating_state_id"] = gating_state_id(result.pop(field))
    return result


def category_ancestry(category):
    """Capture current ancestry explicitly when creating a new taxonomy version."""
    result, seen = [], set()
    while category is not None:
        if category.pk in seen:
            raise ValueError("cyclic product category ancestry")
        seen.add(category.pk)
        result.append(category.code)
        category = category.parent
    return result
