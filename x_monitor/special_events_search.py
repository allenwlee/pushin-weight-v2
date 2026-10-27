"""The two bounded special-events searches; historical rare-search text stays frozen."""

from __future__ import annotations

import json

from x_monitor.apify import TwitterApiClient
from x_monitor.queries import assert_under_length_cap

QUERY_VERSION = "special-events-v1-2026-10-27"
CALL_IDS = ("SPECIALEVENTS1", "SPECIALEVENTS2")
RUN_LANES = dict(
    zip(CALL_IDS, ("special-events/general", "special-events/releases"), strict=True)
)

GENERAL_QUERY = (
    '(("I\'ve joined" OR "I joined" OR "I left" OR "我加入" OR "我离开" OR 出任 OR 换帅 OR に入社 OR を退職) '
    '(AI OR LLM OR OpenAI OR Anthropic) OR ("I\'ve joined @deepseek_ai") OR '
    '("we\'re hiring" OR "currently hiring" OR 招聘 OR 募集中) (engineer OR researcher) OR '
    '("we\'ll be at" OR 登壇) ("AI conference" OR summit) OR '
    '("applications open" OR "apply by" OR 申请) (hackathon OR fellowship) (AI OR LLM)) min_faves:0'
)
RELEASE_QUERY = (
    "((introducing OR announce OR announcing OR announced OR release OR released OR releasing OR "
    'launch OR launched OR launching OR "is here" OR available OR arrived OR "open weights" OR '
    "开源 OR 发布 OR 上线 OR 推出 OR 公開 OR リリース) "
    "(model OR models OR weights OR Preview OR LLM OR VLM OR checkpoint OR agent OR agents OR "
    'harness OR toolkit OR SDK OR "AI tool" OR "AI assistant") OR url:huggingface.co OR url:hf.co) min_faves:0'
)
QUERIES = dict(zip(CALL_IDS, (GENERAL_QUERY, RELEASE_QUERY), strict=True))


def assessment_query_pack() -> str:
    """Hash both exact queries and their dispatch identities in one assessment."""
    return json.dumps(
        QUERIES, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def render_query(call_id: str, *, since_time: int, until_time: int) -> str:
    for value in (since_time, until_time):
        if type(value) is not int or value <= 0 or len(str(value)) > 11:
            raise ValueError(
                "positive integer epochs of at most eleven digits required"
            )
    if since_time >= until_time:
        raise ValueError("search window must have positive duration")
    rendered = TwitterApiClient._effective_search_query(
        QUERIES[call_id],
        since=None,
        since_time=since_time,
        until_time=until_time,
    )
    assert_under_length_cap(rendered)
    return rendered
