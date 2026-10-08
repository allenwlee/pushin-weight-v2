from copy import deepcopy

import pytest

from scripts.benchmark_download_collector.identity import validate_inputs


def inputs():
    catalog = {
        "schema_version": 1,
        "exported_at": "2026-10-04T12:00:00+00:00",
        "brands": [{"id": "alpha", "label": "Alpha", "company_ids": ["maker"]}],
        "companies": [{"id": "maker", "label": "Maker"}],
        "products": [
            {
                "product_key": "00000000-0000-4000-8000-000000000001",
                "brand_id": "alpha",
                "label": "Alpha 1",
                "repo_id": "maker/Alpha-1",
                "hf_namespace": "maker",
                "hf_confirmed": True,
                "hf_company_id": "maker",
            }
        ],
        "posts": {
            "start_date": "2026-10-01",
            "end_date": "2026-10-04",
            "scope": "collected_postbrand",
            "counts": [],
        },
    }
    mapping = {
        "schema_version": 1,
        "hf_product_keys": [catalog["products"][0]["product_key"]],
        "mappings": [
            {
                "source": "arena",
                "source_id": "alpha-1-thinking",
                "product_key": catalog["products"][0]["product_key"],
                "evidence": "https://example.com/alpha-1",
            }
        ],
    }
    return catalog, mapping


def test_closed_weight_product_keeps_identity_without_hf_repo():
    catalog, mapping = inputs()
    catalog["products"][0].update(
        repo_id=None, hf_namespace=None, hf_confirmed=False, hf_company_id=None
    )
    mapping["hf_product_keys"] = []
    validate_inputs(catalog, mapping)


@pytest.mark.parametrize(
    "problem", ["unknown_product", "duplicate_source", "unconfirmed", "wrong_company"]
)
def test_rejects_mapping_and_official_repo_mistakes(problem):
    catalog, mapping = inputs()
    if problem == "unknown_product":
        mapping["mappings"][0]["product_key"] = "00000000-0000-4000-8000-000000000999"
    elif problem == "duplicate_source":
        mapping["mappings"].append(deepcopy(mapping["mappings"][0]))
    elif problem == "unconfirmed":
        catalog["products"][0]["hf_confirmed"] = False
    else:
        catalog["products"][0]["hf_company_id"] = "unrelated"
    with pytest.raises(ValueError):
        validate_inputs(catalog, mapping)
