from __future__ import annotations

import ast
import base64
import html
import json
import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from dateutil.parser import isoparse
from django.utils.html import strip_tags

from .http import SourceHttpClient, SourceHttpError
from .types import SourceDefinition, SourceJob, SourceSnapshot


def _text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(html.unescape(strip_tags(value)).split())
    return cleaned or None


_CHINA_TIME = ZoneInfo("Asia/Shanghai")


def _aware(value: str | float | None, *, naive_timezone=UTC) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=UTC)
    parsed = isoparse(value)
    return parsed.replace(tzinfo=naive_timezone) if parsed.tzinfo is None else parsed


class _InitDataParser(HTMLParser):
    value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "input" and values.get("id") == "init-data":
            self.value = values.get("value")


def parse_moka_bootstrap(document: str) -> dict[str, Any]:
    parser = _InitDataParser()
    parser.feed(document)
    if not parser.value:
        raise ValueError("Moka bootstrap did not contain #init-data")
    value = json.loads(html.unescape(parser.value))
    if not isinstance(value, dict) or not isinstance(value.get("aesIv"), str):
        raise TypeError("Moka bootstrap is missing the AES IV")
    return value


def decrypt_moka_envelope(envelope: dict[str, Any], iv: str) -> dict[str, Any]:
    key = envelope.get("necromancer")
    ciphertext = envelope.get("data")
    if not isinstance(key, str) or len(key.encode()) not in {16, 24, 32}:
        raise ValueError("Moka envelope has an invalid AES key")
    if not isinstance(ciphertext, str) or len(iv.encode()) != 16:
        raise ValueError("Moka envelope has invalid ciphertext or IV")
    decryptor = Cipher(algorithms.AES(key.encode()), modes.CBC(iv.encode())).decryptor()
    padded = (
        decryptor.update(base64.b64decode(ciphertext, validate=True))
        + decryptor.finalize()
    )
    unpadder = PKCS7(128).unpadder()
    raw = unpadder.update(padded) + unpadder.finalize()
    value = json.loads(raw.decode("utf-8"))
    if (
        not isinstance(value, dict)
        or not value.get("success")
        or not isinstance(value.get("data"), dict)
    ):
        raise ValueError("Moka decrypted response is not a successful jobs payload")
    return value["data"]


def parse_moka_page(
    data: dict[str, Any], definition: SourceDefinition
) -> tuple[list[SourceJob], int]:
    rows = data.get("jobs")
    stats = data.get("jobStats") or {}
    total = stats.get("total")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise TypeError("Moka jobs payload omitted jobs or total")
    base = definition.adapter_options.get("moka_url", definition.careers_url).split(
        "#/", 1
    )[0]
    jobs: list[SourceJob] = []
    for row in rows:
        source_id = str(row.get("id") or "")
        title = str(row.get("title") or "").strip()
        if not source_id or not title:
            raise ValueError("Moka job omitted stable id or title")
        detail = f"{base}#/job/{source_id}"
        locations = tuple(
            dict.fromkeys(
                str(
                    location.get("cityName") or location.get("provinceName") or ""
                ).strip()
                for location in (row.get("locations") or [])
                if str(
                    location.get("cityName") or location.get("provinceName") or ""
                ).strip()
            )
        )
        department = row.get("department") or {}
        jobs.append(
            SourceJob(
                source_listing_id=source_id,
                title=title,
                canonical_url=detail,
                application_url=f"{detail}/apply",
                description_html=row.get("jobDescription"),
                description_text=_text(row.get("jobDescription")),
                department=department.get("name")
                if isinstance(department, dict)
                else None,
                job_function=row.get("zhineng"),
                employment_type=row.get("commitment"),
                locations=locations,
                posted_at=_aware(
                    row.get("publishedAt")
                    or row.get("openedAt")
                    or row.get("createdAt"),
                    naive_timezone=_CHINA_TIME,
                ),
                updated_at=_aware(row.get("updatedAt"), naive_timezone=_CHINA_TIME),
                raw_payload=row,
            )
        )
    return jobs, total


def fetch_moka(
    definition: SourceDefinition, client: SourceHttpClient
) -> SourceSnapshot:
    careers_url = definition.adapter_options.get("moka_url", definition.careers_url)
    document = client.get_text(careers_url)
    bootstrap = parse_moka_bootstrap(document)
    options = definition.adapter_options
    api_url = "https://app.mokahr.com/api/outer/ats-apply/website/jobs/v2"
    jobs: list[SourceJob] = []
    total: int | None = None
    limit = 50
    for offset in range(0, 10000, limit):
        envelope = client.post_json(
            api_url,
            {
                "orgId": options["moka_org"],
                "siteId": int(options["moka_site"]),
                "limit": limit,
                "offset": offset,
                "needStat": True,
                "jobIdTopList": [],
                "customFields": {},
                "site": "social",
                "locale": "zh-CN",
            },
            headers={"Referer": careers_url, "use-http-status": "0"},
        )
        page_jobs, page_total = parse_moka_page(
            decrypt_moka_envelope(envelope, bootstrap["aesIv"]), definition
        )
        if total is not None and page_total != total:
            raise ValueError("Moka total changed during pagination")
        total = page_total
        jobs.extend(page_jobs)
        if len(jobs) >= total or not page_jobs:
            break
    complete = total is not None and len(jobs) == total
    return SourceSnapshot(
        definition.key, tuple(jobs), total, complete, datetime.now(UTC)
    )


def parse_qwen_page(payload: dict[str, Any]) -> tuple[list[SourceJob], int]:
    content = payload.get("content") or {}
    rows = content.get("datas")
    total = content.get("totalCount")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise TypeError("Qwen payload omitted jobs or total")
    jobs: list[SourceJob] = []
    for row in rows:
        source_id = str(row.get("id") or "")
        title = str(row.get("name") or "").strip()
        if not source_id or not title:
            raise ValueError("Qwen job omitted stable id or title")
        url = f"https://talent.quark.cn/off-campus/position-detail?positionId={source_id}&lang=zh"
        work_locations = row.get("workLocations") or []
        locations = tuple(
            value
            for value in (
                str(item.get("name") if isinstance(item, dict) else item).strip()
                for item in work_locations
            )
            if value
        )
        category = row.get("categories") or {}
        jobs.append(
            SourceJob(
                source_listing_id=source_id,
                title=title,
                canonical_url=url,
                application_url=url,
                description_html=row.get("description"),
                description_text=_text(row.get("description")),
                department=row.get("departmentName"),
                job_function=category.get("name")
                if isinstance(category, dict)
                else None,
                employment_type=row.get("workTypeName"),
                locations=locations,
                posted_at=_aware(row.get("publishTime")),
                updated_at=_aware(row.get("modifyTime")),
                raw_payload=row,
            )
        )
    return jobs, total


def fetch_qwen(
    definition: SourceDefinition, client: SourceHttpClient
) -> SourceSnapshot:
    client.get_text(definition.careers_url)
    token = client.session.cookies.get("XSRF-TOKEN")
    if not token:
        raise ValueError("Qwen careers page did not set an XSRF token")
    jobs: list[SourceJob] = []
    total: int | None = None
    page_size = 50
    for page_index in range(1, 201):
        payload = client.post_json(
            f"https://talent.quark.cn/position/search?_csrf={token}",
            {
                "channel": "group_official_site",
                "language": "zh",
                "batchId": "",
                "categories": "",
                "deptCodes": [],
                "key": "",
                "pageIndex": page_index,
                "pageSize": page_size,
                "regions": "",
                "subCategories": "",
                "shareType": "",
                "shareId": "",
                "myReferralShareCode": "",
            },
            headers={"Referer": definition.careers_url},
        )
        page_jobs, page_total = parse_qwen_page(payload)
        if total is not None and page_total != total:
            raise ValueError("Qwen total changed during pagination")
        total = page_total
        jobs.extend(page_jobs)
        if len(jobs) >= total or not page_jobs:
            break
    return SourceSnapshot(
        definition.key,
        tuple(jobs),
        total,
        total is not None and len(jobs) == total,
        datetime.now(UTC),
    )


def parse_feishu_page(
    payload: dict[str, Any], definition: SourceDefinition
) -> tuple[list[SourceJob], int]:
    if payload.get("code") != 0:
        raise ValueError(f"Feishu returned code {payload.get('code')}")
    data = payload.get("data") or {}
    rows, total = data.get("job_post_list"), data.get("count")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise TypeError("Feishu payload omitted jobs or total")
    portal = definition.careers_url.rstrip("/")
    jobs: list[SourceJob] = []
    for row in rows:
        source_id = str(row.get("id") or "")
        title = str(row.get("title") or "").strip()
        if not source_id or not title:
            raise ValueError("Feishu job omitted stable id or title")
        category = row.get("job_category") or {}
        recruit_type = row.get("recruit_type") or {}
        locations = tuple(
            str(item.get("i18n_name") or item.get("name") or "").strip()
            for item in (row.get("city_list") or [])
            if str(item.get("i18n_name") or item.get("name") or "").strip()
        )
        detail = f"{portal}/position/{source_id}/detail"
        description = "\n\n".join(
            value for value in [row.get("description"), row.get("requirement")] if value
        )
        jobs.append(
            SourceJob(
                source_listing_id=source_id,
                title=title,
                canonical_url=detail,
                application_url=detail,
                description_text=_text(description),
                department=category.get("i18n_name") or category.get("name")
                if isinstance(category, dict)
                else None,
                job_function=(row.get("job_function") or {}).get("i18n_name")
                if isinstance(row.get("job_function"), dict)
                else None,
                employment_type=recruit_type.get("i18n_name")
                or recruit_type.get("name")
                if isinstance(recruit_type, dict)
                else None,
                locations=locations,
                posted_at=_aware(row.get("publish_time")),
                raw_payload=row,
            )
        )
    return jobs, total


def fetch_feishu(
    definition: SourceDefinition, client: SourceHttpClient
) -> SourceSnapshot:
    client.session.headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Portal-Channel": "saas-career",
            "Portal-Platform": "pc",
            "Referer": definition.careers_url,
            "accept-language": "zh-CN",
            "env": "undefined",
            "website-path": definition.adapter_options["website_path"],
            "x-csrf-token": "undefined",
            "sec-ch-ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        }
    )
    client.get_text(definition.careers_url)
    api_url = urljoin(definition.careers_url, "/api/v1/search/job/posts")
    params = {
        "website_path": definition.adapter_options["website_path"],
        "portal_channel": "saas-career",
        "portal_platform": "pc",
        "portal_type": 6,
    }
    jobs: list[SourceJob] = []
    total: int | None = None
    limit = 50
    for offset in range(0, 10000, limit):
        payload = client.post_json(
            api_url,
            {
                "keyword": "",
                "limit": limit,
                "offset": offset,
                "job_category_id_list": [],
                "tag_id_list": [],
                "location_code_list": [],
                "subject_id_list": [],
                "recruitment_id_list": [],
                "portal_type": 6,
                "job_function_id_list": [],
                "storefront_id_list": [],
                "portal_entrance": 1,
            },
            params=params,
        )
        page_jobs, page_total = parse_feishu_page(payload, definition)
        if total is not None and page_total != total:
            raise ValueError("Feishu total changed during pagination")
        total = page_total
        jobs.extend(page_jobs)
        if len(jobs) >= total or not page_jobs:
            break
    return SourceSnapshot(
        definition.key,
        tuple(jobs),
        total,
        total is not None and len(jobs) == total,
        datetime.now(UTC),
    )


def parse_deepseek_bundle(bundle: str) -> dict[str, Any]:
    pattern = re.compile(
        r"JSON\.parse\(((?P<quote>['\"])(?:\\.|(?!\2).)*\2)\)", re.DOTALL
    )
    for match in pattern.finditer(bundle):
        try:
            value = json.loads(ast.literal_eval(match.group(1)))
        except (ValueError, SyntaxError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and {"crawledAt", "jobs", "total"} <= value.keys():
            return value
    raise ValueError("DeepSeek bundle did not contain its jobs snapshot")


def _deepseek_snapshot(
    value: dict[str, Any], definition: SourceDefinition
) -> SourceSnapshot:
    rows, total = value.get("jobs"), value.get("total")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise TypeError("DeepSeek snapshot omitted jobs or total")
    jobs = []
    for row in rows:
        source_id, title = str(row.get("id") or ""), str(row.get("title") or "").strip()
        if not source_id or not title:
            raise ValueError("DeepSeek job omitted stable id or title")
        jobs.append(
            SourceJob(
                source_listing_id=source_id,
                title=title,
                canonical_url=row["detailUrl"],
                application_url=row.get("submitUrl") or row["detailUrl"],
                description_html=row.get("descriptionHtml"),
                description_text=_text(row.get("descriptionHtml")),
                job_function=row.get("functionName"),
                locations=tuple(row.get("locations") or ()),
                raw_payload=row,
            )
        )
    crawled_at = _aware(value.get("crawledAt")) or datetime.now(UTC)
    return SourceSnapshot(
        definition.key,
        tuple(jobs),
        total,
        len(jobs) == total,
        datetime.now(UTC),
        {
            "embedded_crawled_at": crawled_at.isoformat(),
            "embedded_source_url": value.get("sourceUrl"),
        },
    )


def fetch_deepseek(
    definition: SourceDefinition, client: SourceHttpClient
) -> SourceSnapshot:
    document = client.get_text(definition.careers_url)
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+\.js)["\']', document)
    if not scripts:
        raise ValueError("DeepSeek careers page did not link an application bundle")
    try:
        value = parse_deepseek_bundle(
            client.get_text(urljoin(definition.careers_url, scripts[-1]))
        )
        snapshot = _deepseek_snapshot(value, definition)
        crawled = _aware(value.get("crawledAt"))
        if crawled is not None and datetime.now(UTC) - crawled <= timedelta(days=14):
            return snapshot
    except (KeyError, TypeError, ValueError, SourceHttpError):
        pass
    return fetch_moka(definition, client)


def fetch_source(
    definition: SourceDefinition, *, client: SourceHttpClient | None = None
) -> SourceSnapshot:
    client = client or SourceHttpClient(allowed_hosts=definition.allowed_hosts)
    if definition.adapter == "qwen":
        return fetch_qwen(definition, client)
    if definition.adapter == "moka":
        return fetch_moka(definition, client)
    if definition.adapter == "feishu":
        return fetch_feishu(definition, client)
    if definition.adapter == "deepseek":
        return fetch_deepseek(definition, client)
    raise ValueError(f"unsupported adapter: {definition.adapter}")
