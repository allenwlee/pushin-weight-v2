import pytest

from core.product_release_github_identity import source_names_repository


@pytest.mark.parametrize("text,author,owner,expected", [
    ("We released DeepSeek Harness today.", "deepseek_ai", "DeepSeek_AI", "deepseek-harness"),
    ("I just released deepseek-harness!", "deepseek_ai", "deepseek_ai", "deepseek-harness"),
    ("We released DeepSeek Harness 2.", "another", "deepseek_ai", None),
    ("They released DeepSeek Harness.", "deepseek_ai", "deepseek_ai", None),
    ("We have not released DeepSeek Harness.", "deepseek_ai", "deepseek_ai", None),
    ("We will release DeepSeek Harness tomorrow.", "deepseek_ai", "deepseek_ai", None),
    ("We released DeepSeek Harness Pro.", "deepseek_ai", "deepseek_ai", None),
    ("We released DeepSeek Harness-2.", "deepseek_ai", "deepseek_ai", None),
    ("We released DeepSeek Harness.", "deepseek_ai", "", None),
])
def test_self_release_identity_signal(text, author, owner, expected):
    assert source_names_repository(text=text, author_handle=author, owner_handle=owner,
                                   repository="deepseek-ai/deepseek-harness") == expected
