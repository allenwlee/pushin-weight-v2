"""Build a deterministic, unseen U18 cohort from a disposable dump restore.

The command reads only the local PostgreSQL database named by ``DATABASE_URL``.
Selection hints shape sampling but never enter the production classifier input
or the blinded reviewer packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import psycopg

LANGUAGES = ("en", "zh", "ja")
LANGUAGE_OUTPUT = {"en": "en", "zh": "zh-cn", "ja": "ja"}
SEED = "u18-2026-09-11-final-v3"
COHORT_ID = "u18-prod-dump-20260910-final-v3"

PATTERNS = {
    "job_listing_terms": {
        "en": r"(we.?re hiring|we are hiring|is hiring|job opening|open roles?|open positions?|apply (here|now|at)|careers page|join our team)",
        "zh": r"(招聘|职位|岗位|投递|申请职位|加入我们)",
        "ja": r"(求人|採用情報|採用中|募集中|応募|採用ページ|採用サイト)",
    },
    "personnel_transition_terms": {
        "en": r"(has joined|have joined|joined (the |@|[A-Z])|is joining|will join|has left|have left|left (the |@|[A-Z])|is leaving|departed|appointed as|named as|welcome .+ (to|as))",
        "zh": r"(已加入|正式加入|宣布加入|入职|离职|离开.{0,20}(公司|团队)|任命为|出任|加盟)",
        "ja": r"(入社しました|入社し|退社|退職|就任|転職しました|に加入|が加入)",
    },
    "product_bug_terms": {
        "en": r"(\mbug\M|broken|crash|error|fails?|not working|regression)",
        "zh": r"(错误|故障|崩溃|失效|不能用|无法使用|问题)",
        "ja": r"(バグ|不具合|エラー|クラッシュ|動かない|使えない|問題)",
    },
    "product_complaint_terms": {
        "en": r"(disappoint|frustrat|terrible|worse|hate|expensive|too slow|annoy)",
        "zh": r"(失望|糟糕|太贵|贵了|不好用|太慢|吐槽|坑人)",
        "ja": r"(残念|ひどい|高すぎ|使いにく|遅い|不満|最悪)",
    },
    "product_testimonial_terms": {
        "en": r"(\mlove\M|amazing|impressive|excellent|awesome|works great|the best)",
        "zh": r"(太强|好用|惊艳|厉害|优秀|最强|喜欢)",
        "ja": r"(すごい|素晴らしい|最高|便利|感動|好き)",
    },
    "product_idea_terms": {
        "en": r"(could you|please add|wish .+ (had|would)|feature request|should add|would be better|needs? a)",
        "zh": r"(希望|建议|应该增加|能否|请加|需要增加)",
        "ja": r"(ほしい|欲しい|追加して|改善して|できれば|要望)",
    },
    "product_misinformation_terms": {
        "en": r"(\mfake\M|scam|misleading|\mfalse\M|not true|hoax|fraud)",
        "zh": r"(假的|骗局|误导|虚假|不实|造假)",
        "ja": r"(偽物|詐欺|誤解|デマ|虚偽|捏造)",
    },
    "event_opportunity_terms": {
        "en": r"(webinar|conference|workshop|hackathon|contest|giveaway|discount|grant|bounty|free credits|limited time|register|deadline)",
        "zh": r"(活动|会议|峰会|研讨会|黑客松|比赛|赠送|折扣|奖金|赏金|限时|报名|截止)",
        "ja": r"(イベント|会議|カンファレンス|ウェビナー|勉強会|ハッカソン|コンテスト|プレゼント|割引|助成金|賞金|期間限定|登録|締切)",
    },
}

ROLE_QUOTAS = {
    ("job_listing_terms", "en"): {"official": 7},
    ("job_listing_terms", "ja"): {"official": 1},
    ("personnel_transition_terms", "en"): {"official": 10, "staff": 3},
    ("event_opportunity_terms", "en"): {"official": 10, "staff": 7},
    ("event_opportunity_terms", "ja"): {"official": 1},
}

_SELECT = """
SELECT DISTINCT ON (p.tweet_id, pb.brand_id)
       p.tweet_id,
       pb.brand_id,
       COALESCE(p.author_handle, ''),
       COALESCE(p.author_name, ''),
       p.lang,
       p.text,
       p.quoted_text,
       parent.text AS parent_text,
       COALESCE(ba.role_id, 'third_party') AS source_role
FROM posts p
JOIN posts_brands pb ON pb.post_id = p.tweet_id
LEFT JOIN posts parent ON parent.tweet_id = p.in_reply_to_id
LEFT JOIN brands_accounts ba
  ON ba.accounts_id = p.author_id AND ba.brand_id = pb.brand_id
WHERE p.lang = %s
  AND p.text IS NOT NULL
  AND p.text <> ''
  AND (%s::text IS NULL OR p.text ~* %s)
ORDER BY p.tweet_id, pb.brand_id
"""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _rank(category: str, row: tuple[Any, ...]) -> str:
    return hashlib.sha256(
        f"{SEED}:{category}:{row[0]}:{row[1]}".encode()
    ).hexdigest()


def _excluded_example_ids(path: Path | None) -> set[str]:
    if path is None:
        return set()
    document = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["example_id"]) for row in document["rows"]}


def _fetch(
    connection: psycopg.Connection[Any], language: str, pattern: str | None
) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(_SELECT, (language, pattern, pattern))
        return list(cursor.fetchall())


def _source_row(
    row: tuple[Any, ...], *, stratum: str, source_hint: str | None
) -> dict[str, Any]:
    (
        tweet_id,
        brand_id,
        author_handle,
        author_name,
        language,
        text,
        quoted_text,
        parent_text,
        source_role,
    ) = row
    context = []
    if quoted_text:
        context.append({"provenance": "stored_quote", "text": quoted_text})
    if parent_text:
        context.append({"provenance": "local_parent", "text": parent_text})
    input_row = {
        "brand_ids": [brand_id],
        "context": context,
        "text": text,
        "tweet_id": tweet_id,
    }
    return {
        "author_handle": author_handle,
        "author_name": author_name,
        "brand_id": brand_id,
        "context_provenance": [entry["provenance"] for entry in context],
        "example_id": tweet_id,
        "input": input_row,
        "input_context_fingerprint": hashlib.sha256(_canonical(input_row)).hexdigest(),
        "source_hint": source_hint,
        "source_language": LANGUAGE_OUTPUT[language],
        "source_role": source_role,
        "stratum": stratum,
    }


def _take(
    candidates: Iterable[tuple[Any, ...]],
    *,
    category: str,
    quota: int,
    chosen: set[str],
    excluded: set[str],
) -> list[tuple[Any, ...]]:
    output = []
    for row in sorted(candidates, key=lambda item: _rank(category, item)):
        example_id = str(row[0])
        if example_id in chosen or example_id in excluded:
            continue
        chosen.add(example_id)
        output.append(row)
        if len(output) == quota:
            return output
    raise RuntimeError(f"{category} supplied {len(output)} rows; required {quota}")


def _take_with_role_support(
    candidates: list[tuple[Any, ...]],
    *,
    category: str,
    language: str,
    quota: int,
    chosen: set[str],
    excluded: set[str],
) -> list[tuple[Any, ...]]:
    output = []
    for role, role_quota in ROLE_QUOTAS.get((category, language), {}).items():
        output.extend(
            _take(
                (row for row in candidates if row[8] == role),
                category=f"{category}:{language}:{role}",
                quota=role_quota,
                chosen=chosen,
                excluded=excluded,
            )
        )
    output.extend(
        _take(
            candidates,
            category=f"{category}:{language}:remainder",
            quota=quota - len(output),
            chosen=chosen,
            excluded=excluded,
        )
    )
    return output


def build(connection: psycopg.Connection[Any], excluded: set[str]) -> dict[str, Any]:
    chosen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for category in ("job_listing_terms", "personnel_transition_terms"):
        for language in LANGUAGES:
            selected = _take_with_role_support(
                _fetch(connection, language, PATTERNS[category][language]),
                category=category,
                language=language,
                quota=25,
                chosen=chosen,
                excluded=excluded,
            )
            rows.extend(
                _source_row(row, stratum="rare_positive", source_hint=category)
                for row in selected
            )
    for category in (
        "product_bug_terms",
        "product_complaint_terms",
        "product_testimonial_terms",
        "product_idea_terms",
        "product_misinformation_terms",
    ):
        for language in LANGUAGES:
            selected = _take(
                _fetch(connection, language, PATTERNS[category][language]),
                category=f"{category}:{language}",
                quota=10,
                chosen=chosen,
                excluded=excluded,
            )
            rows.extend(
                _source_row(row, stratum="rare_positive", source_hint=category)
                for row in selected
            )
    for language in LANGUAGES:
        category = "event_opportunity_terms"
        selected = _take_with_role_support(
            _fetch(connection, language, PATTERNS[category][language]),
            category=category,
            language=language,
            quota=30,
            chosen=chosen,
            excluded=excluded,
        )
        rows.extend(
            _source_row(
                row,
                stratum="event_opportunity_boundary",
                source_hint=category,
            )
            for row in selected
        )
    prevalence_by_language = {"en": 110, "zh": 100, "ja": 100}
    for language, quota in prevalence_by_language.items():
        selected = _take(
            _fetch(connection, language, None),
            category=f"prevalence:{language}",
            quota=quota,
            chosen=chosen,
            excluded=excluded,
        )
        rows.extend(
            _source_row(row, stratum="prevalence", source_hint=None)
            for row in selected
        )
    assert len(rows) == 700
    assert len({row["example_id"] for row in rows}) == len(rows)
    return {
        "cohort_id": COHORT_ID,
        "rows": sorted(rows, key=lambda row: (row["example_id"], row["brand_id"])),
        "schema_version": "stage1c-source-cohort-v1",
        "seed": SEED,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude-cohort", type=Path)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    with psycopg.connect(database_url) as connection:
        document = build(connection, _excluded_example_ids(args.exclude_cohort))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(document["rows"]),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
