"""Closed, provider-independent contracts. Source IDs are validated against evidence."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(ClosedModel):
    key: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    summary: str = Field(min_length=1, max_length=2000)
    post_ids: list[str] = Field(min_length=1, max_length=50)
    brand_keys: list[str] = Field(default_factory=list, max_length=10)
    occurred_at: AwareDatetime
    chatter: bool
    pulse: bool
    importance: float = Field(ge=0, le=100, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=2000)
    change: Literal["new", "update", "unchanged"] = "new"
    story_id: UUID | None = None
    subject_kind: Literal[
        "company_direction", "model_release", "agent_release", "person", "other"
    ] = "other"
    person_ids: list[int] = Field(default_factory=list, max_length=5)
    visual_essential: bool = False
    source_image_url: str = Field(default="", max_length=4096)
    chart_support: Literal["supported", "unavailable", "not_supported"] = "unavailable"


class Decisions(ClosedModel):
    events: list[Event] = Field(default_factory=list, max_length=20)


class Copy(ClosedModel):
    headline: str = Field(min_length=1, max_length=160)
    byline: str = Field(min_length=1, max_length=500)
    article: str = Field(min_length=1, max_length=12000)
    locale: Literal["en", "zh-cn", "ja"]
    post_ids: list[str] = Field(min_length=1, max_length=50)
    visual_brief: str = Field(default="", max_length=1500)


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def interval_start(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("aware cutoff required")
    value = value.astimezone(UTC)
    return value.replace(minute=value.minute // 15 * 15, second=0, microsecond=0)
