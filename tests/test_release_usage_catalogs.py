import json

import pytest

from core.release_usage_catalogs import opencode_candidates, openrouter_candidates
from scripts.benchmark_download_collector.sources import AmbiguousCatalogMatch


def fetcher(pages):
    def fetch(url, params=None):
        assert url in pages, url
        value = pages[url]
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    return fetch


OR = "https://openrouter.ai/api/v1/models"
OC = "https://opencode.ai/data"
MODEL = "deepseek/deepseek-v4.1-flash"
SLUG = "deepseek-v4-1-flash"
PAGE = f"{OC}/deepseek/{SLUG}"
OR_ROW = {
    "name": "DeepSeek: DeepSeek V4.1 Flash",
    "id": MODEL,
    "canonical_slug": MODEL + "-20261017",
}


def matches(value):
    return value.lower().replace(" ", "-") == "deepseek-v4.1-flash"


def owns(value):
    return value.casefold() == "deepseek"


def test_router_catalog_does_not_generate_rankings_id():
    fetch = fetcher({OR: {"data": [OR_ROW], "total_count": 1}})
    result = openrouter_candidates(fetch, matches, owns)
    assert [(i, scope, url) for i, scope, url, _ in result] == [
        (MODEL, "catalog_id", "https://openrouter.ai/" + MODEL),
    ]
    assert result[0][3]["canonical_slug"] == OR_ROW["canonical_slug"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "Stranger: DeepSeek V4.1 Flash"},
        {"name": "DeepSeek: DeepSeek V4.1 Flash Instruct"},
        {"id": "community/deepseek-v4.1-flash"},
        {"id": MODEL + "-preview"},
        {"id": MODEL + ":free"},
        {"id": "deepseek/latest"},
        {"canonical_slug": "another-lab/deepseek-v4.1-flash"},
        {"canonical_slug": "deepseek/deepseek-v4.1-flash-latest"},
        {"id": "deepseek/../somewhere"},
    ],
)
def test_router_excludes_namesakes_variants_and_aliases(overrides):
    row = {**OR_ROW, **overrides}
    assert openrouter_candidates(fetcher({OR: {"data": [row]}}), matches, owns) == []


def test_router_does_not_pick_first_of_several_compatible_ids():
    other = {**OR_ROW, "id": MODEL.replace(".", "-")}
    with pytest.raises(AmbiguousCatalogMatch):
        openrouter_candidates(fetcher({OR: {"data": [OR_ROW, other]}}), matches, owns)


def test_router_never_treats_an_unread_page_as_a_complete_catalog():
    seen = []

    def fetch(url, params=None):
        seen.append(url)
        if len(seen) == 1:
            return json.dumps({"data": [OR_ROW], "total_count": 2}).encode()
        raise ValueError("provider unavailable")

    with pytest.raises(ValueError):
        openrouter_candidates(fetch, matches, owns)
    assert seen == [OR, OR]


def pages(model=MODEL):
    return {
        OC
        + "/llms.txt": b"## Top models: past 7 days\n\n## Labs\n\n- [DeepSeek](https://opencode.ai/data/deepseek.md): 1 model\n\n## Data\n",
        OC + "/deepseek.json": {
            "page": OC + "/deepseek",
            "lab": {"id": "deepseek", "name": "DeepSeek"},
            "models": [{"id": model, "name": "DeepSeek V4.1 Flash", "page": PAGE}],
        },
        PAGE + ".json": {
            "page": PAGE,
            "model": {
                "id": model,
                "name": "DeepSeek V4.1 Flash",
                "lab": "deepseek",
                "labName": "DeepSeek",
            },
        },
    }


def test_opencode_uses_native_model_id_and_verified_page_path():
    result = opencode_candidates(fetcher(pages()), matches, owns)
    assert result == [
        (
            MODEL,
            "model_id",
            PAGE,
            {"endpoint_path": "/data/deepseek/" + SLUG + ".json"},
        ),
    ]


@pytest.mark.parametrize(
    "model", ["deepseek/deepseek-v4.1-flash-1017", "other/deepseek-v4.1-flash"]
)
def test_opencode_rejects_near_variant_and_wrong_native_owner(model):
    assert opencode_candidates(fetcher(pages(model)), matches, owns) == []


def test_opencode_uses_publisher_index_even_outside_top_models():
    docs = pages()
    label = "Zhipu"
    src = OC + "/zhipuai"
    page = src + "/glm-5-4"
    docs[OC + "/llms.txt"] = (
        f"## Labs\n- [{label}]({src}.md): 1 model\n## Data\n".encode()
    )
    model = {"id": "zhipuai/glm-5.4", "name": "GLM-5.4"}
    docs[src + ".json"] = {
        "page": src,
        "lab": {"id": "zhipuai", "name": label},
        "models": [{**model, "page": page}],
    }
    docs[page + ".json"] = {
        "page": page,
        "model": {**model, "lab": "zhipuai", "labName": label},
    }
    found = opencode_candidates(
        fetcher(docs),
        lambda name: name.lower() == "glm-5.4",
        lambda issuer: issuer == label,
    )
    assert found[0][0] == model["id"]


def test_opencode_rejects_changed_detail_or_offsite_endpoint():
    docs = pages()
    docs[PAGE + ".json"]["model"]["id"] += "-preview"
    with pytest.raises(ValueError):
        opencode_candidates(fetcher(docs), matches, owns)
    docs = pages()
    docs[OC + "/deepseek.json"]["models"][0]["page"] = (
        "https://unrelated.example/deepseek-v4.1-flash"
    )
    with pytest.raises(ValueError):
        opencode_candidates(fetcher(docs), matches, owns)


def test_opencode_damaged_index_is_not_an_absence():
    with pytest.raises(ValueError):
        opencode_candidates(
            fetcher({OC + "/llms.txt": b"gateway error"}), matches, owns
        )
