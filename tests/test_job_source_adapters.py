from __future__ import annotations

import base64
import json
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from core.job_sources.adapters import (
    decrypt_moka_envelope,
    fetch_deepseek,
    parse_deepseek_bundle,
    parse_feishu_page,
    parse_moka_bootstrap,
    parse_moka_page,
    parse_qwen_page,
)
from core.job_sources.registry import SOURCES


def test_qwen_parser_preserves_stable_identity_and_total():
    jobs, total = parse_qwen_page(
        {
            "content": {
                "totalCount": 1,
                "datas": [
                    {
                        "id": 42,
                        "name": "大模型工程师",
                        "description": "<p>训练模型</p>",
                        "workLocations": [{"name": "杭州"}],
                        "categories": {"name": "研发"},
                        "publishTime": 1780000000000,
                        "modifyTime": 1780000001000,
                    }
                ],
            }
        }
    )
    assert total == 1
    assert jobs[0].source_listing_id == "42"
    assert jobs[0].description_text == "训练模型"
    assert jobs[0].locations == ("杭州",)


def test_feishu_parser_builds_the_official_detail_route():
    jobs, total = parse_feishu_page(
        {
            "code": 0,
            "data": {
                "count": 1,
                "job_post_list": [
                    {
                        "id": "7676",
                        "title": "算法工程师",
                        "description": "职责",
                        "requirement": "要求",
                        "city_list": [{"i18n_name": "上海"}],
                        "job_category": {"i18n_name": "研发"},
                        "recruit_type": {"i18n_name": "正式"},
                        "publish_time": 1780000000000,
                    }
                ],
            },
        },
        SOURCES["minimax"],
    )
    assert total == 1
    assert jobs[0].canonical_url.endswith("/379481/position/7676/detail")
    assert jobs[0].description_text == "职责 要求"


def test_moka_bootstrap_and_encrypted_page_are_decoded():
    iv, key = "0123456789abcdef", "fedcba9876543210"
    data = {
        "code": 0,
        "success": True,
        "data": {
            "jobStats": {"total": 1},
            "jobs": [
                {
                    "id": "uuid-one",
                    "title": "研究员",
                    "status": "open",
                    "jobDescription": "<p>研究</p>",
                    "locations": [{"cityName": "北京"}],
                    "commitment": "全职",
                }
            ],
        },
    }
    padder = PKCS7(128).padder()
    padded = padder.update(json.dumps(data).encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode())).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    bootstrap = parse_moka_bootstrap(
        f'<input value="{{&quot;aesIv&quot;:&quot;{iv}&quot;}}" id="init-data">'
    )
    decoded = decrypt_moka_envelope(
        {"necromancer": key, "data": base64.b64encode(encrypted).decode()},
        bootstrap["aesIv"],
    )
    jobs, total = parse_moka_page(decoded, SOURCES["kimi"])
    assert total == 1
    assert jobs[0].title == "研究员"
    assert jobs[0].application_url.endswith("/apply")


def test_moka_naive_timestamps_are_interpreted_as_china_local_time():
    jobs, _ = parse_moka_page(
        {
            "jobStats": {"total": 1},
            "jobs": [
                {
                    "id": "uuid-time",
                    "title": "研究员",
                    "publishedAt": "2026-09-12T17:45:48",
                    "updatedAt": "2026-09-12T18:45:48",
                }
            ],
        },
        SOURCES["kimi"],
    )
    assert jobs[0].posted_at.utcoffset() == timedelta(hours=8)
    assert jobs[0].posted_at.isoformat() == "2026-09-12T17:45:48+08:00"
    assert jobs[0].updated_at.isoformat() == "2026-09-12T18:45:48+08:00"


def test_deepseek_bundle_parser_keeps_unicode():
    embedded = {"crawledAt": "2026-09-12T00:00:00Z", "total": 1, "jobs": [{"id": "x"}]}
    bundle = (
        f"var jobs=JSON.parse({json.dumps(json.dumps(embedded, ensure_ascii=False))});"
    )
    assert parse_deepseek_bundle(bundle)["jobs"][0]["id"] == "x"


def test_deepseek_malformed_embedded_schema_falls_back_to_official_moka(
    monkeypatch,
):
    sentinel = object()

    class Client:
        def get_text(self, url):
            if url == SOURCES["deepseek"].careers_url:
                return '<script src="/assets/app.js"></script>'
            return "bundle"

    monkeypatch.setattr(
        "core.job_sources.adapters.parse_deepseek_bundle",
        lambda _bundle: {"jobs": None, "total": 1},
    )
    monkeypatch.setattr(
        "core.job_sources.adapters.fetch_moka",
        lambda definition, client: sentinel,
    )

    assert fetch_deepseek(SOURCES["deepseek"], Client()) is sentinel


@pytest.mark.parametrize(
    "parser,payload",
    [
        (parse_qwen_page, {"content": {"totalCount": 1, "datas": []}}),
    ],
)
def test_complete_page_contract_rejects_shape_that_cannot_reconcile(parser, payload):
    jobs, total = parser(payload)
    assert len(jobs) != total
