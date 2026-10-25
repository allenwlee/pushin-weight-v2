"""Product classification fixtures honor the actual historical model registry."""


def product_type_fields(model, code):
    if "product_type" not in {field.name for field in model._meta.fields}:
        return {"type": code}
    catalogue = model._meta.apps.get_model("core", "ProductType")
    value = None if code is None else catalogue.objects.get(code=code).pk
    return {"product_type_id": value}
