from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceJob:
    source_listing_id: str
    title: str
    canonical_url: str
    application_url: str | None = None
    description_html: str | None = None
    description_text: str | None = None
    department: str | None = None
    team: str | None = None
    job_function: str | None = None
    seniority: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    locations: tuple[str, ...] = ()
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    source_key: str
    jobs: tuple[SourceJob, ...]
    declared_total: int | None
    complete: bool
    observed_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    key: str
    brand_nickname: str
    display_name: str
    careers_url: str
    allowed_hosts: frozenset[str]
    adapter: str
    adapter_options: dict[str, Any] = field(default_factory=dict)
