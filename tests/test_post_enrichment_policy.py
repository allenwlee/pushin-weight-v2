from __future__ import annotations

from uuid import uuid4

import pytest

from monitor.post_enrichment import (
    persisted_output_complete,
    persisted_output_complete_q,
)

_VALID = {
    "source_text": "DeepSeek launched a model",
    "lang_detected": "en",
    "text_en": "DeepSeek launched a model",
    "text_zh_cn": "深度求索发布了一个模型",
    "commentary_en": "The launch intensifies model competition.",
    "commentary_zh_cn": "这次发布加剧了模型竞争。",
}

_CASES = [
    pytest.param({}, True, id="valid"),
    pytest.param({"text_zh_cn": None}, False, id="null"),
    pytest.param({"commentary_en": ""}, False, id="blank"),
    pytest.param({"commentary_zh_cn": "   "}, False, id="whitespace"),
    pytest.param({"commentary_en": "N/A"}, False, id="n-a"),
    pytest.param({"commentary_zh_cn": " na "}, False, id="na"),
    pytest.param({"lang_detected": "english"}, False, id="invalid-lang"),
    pytest.param(
        {"commentary_en": "  deepseek LAUNCHED a model  "},
        False,
        id="copied-source-normalized",
    ),
    pytest.param(
        {"commentary_zh_cn": " 深度求索发布了一个模型 "},
        False,
        id="copied-translation-normalized",
    ),
    pytest.param(
        {
            "commentary_en": "The same commentary in both fields.",
            "commentary_zh_cn": " the SAME commentary in BOTH fields. ",
        },
        False,
        id="commentaries-copied-from-each-other",
    ),
    pytest.param({"lang_detected": " zh-Hans "}, True, id="trimmed-canonical-lang"),
]


@pytest.mark.parametrize(("overrides", "expected"), _CASES)
def test_persisted_output_scalar_policy(overrides, expected):
    fields = {**_VALID, **overrides}

    assert persisted_output_complete(**fields) is expected


@pytest.mark.requires_postgres
@pytest.mark.django_db
@pytest.mark.parametrize(("overrides", "expected"), _CASES)
def test_persisted_output_orm_policy_matches_scalar(overrides, expected):
    from core.models import Post

    fields = {**_VALID, **overrides}
    post = Post.objects.create(
        tweet_id=f"policy-{uuid4().hex}",
        text=fields.pop("source_text"),
        **fields,
    )

    matched = Post.objects.filter(
        pk=post.pk,
    ).filter(persisted_output_complete_q()).exists()

    assert matched is expected
