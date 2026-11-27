"""Product classification fixtures honor the actual historical model registry."""


def product_type_fields(model, code):
    if "product_type" not in {field.name for field in model._meta.fields}:
        # Bridge schemas before RG5 stored this vocabulary as constrained text.
        historical = {"model-llm": "llm-model", "model-other": "other-ai-model", "harness": "agent-harness"}
        return {"type": historical.get(code, code)}
    catalogue = model._meta.apps.get_model("core", "ProductType")
    value = None if code is None else catalogue.objects.get(code=code).pk
    return {"product_type_id": value}
