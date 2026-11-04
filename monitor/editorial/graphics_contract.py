"""Graphics v1 boundary; media production remains owned by the separate workflow."""

from datetime import timedelta
from typing import Literal
from uuid import UUID

from django.db import transaction
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from core.models import EditorialPicture, OriginalContentSelection, OriginalContentText
from monitor.original_content import digest, featured_scope, safe_source_url


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Source(Closed):
    source_id: str = Field(min_length=1, max_length=128)
    url: str = Field(max_length=4096)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def safe_url(self):
        safe_source_url(self.url)
        return self


class Asset(Closed):
    reference_id: str = Field(min_length=1, max_length=200)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: Literal["master", "video", "gif", "still", "reference"]
    width: int = Field(gt=0, le=16384)
    height: int = Field(gt=0, le=16384)
    duration_seconds: float | None = Field(default=None, ge=0, le=600)


class GraphicsRequest(Closed):
    contract_version: Literal["graphics/v1"] = "graphics/v1"
    run_id: int = Field(gt=0)
    content_id: int = Field(gt=0)
    story_id: UUID
    revision: int = Field(gt=0)
    text_id: UUID
    locale: Literal["en", "ja", "zh-cn"]
    source_locale: Literal["en", "ja", "zh-CN"]
    editorial_group: Literal["giant", "rest"]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    factual_premise: str = Field(min_length=1, max_length=8000)
    headline: str = Field(min_length=1, max_length=4000)
    byline: str = Field(min_length=1, max_length=8000)
    sources: list[Source] = Field(min_length=1, max_length=200)
    people_ids: list[UUID] = Field(default_factory=list, max_length=50)
    brand_ids: list[str] = Field(default_factory=list, max_length=20)
    references: list[Asset] = Field(default_factory=list, max_length=20)
    visual_inspection_required: bool = False
    slot: Literal["chatter"] = "chatter"
    width: int = 1200
    height: int = 675
    style: str = Field(default="chatter", min_length=1, max_length=200)
    existing_master: Asset | None = None
    max_cost_usd: float = Field(ge=0, le=20)
    caller_workflow: Literal["social-brief"] = "social-brief"
    cycle_started_at: AwareDatetime
    deadline: AwareDatetime

    @model_validator(mode="after")
    def identity(self):
        if (
            digest(self.model_dump(mode="json", exclude={"fingerprint"}))
            != self.fingerprint
        ):
            raise ValueError("graphics request fingerprint mismatch")
        if self.deadline != self.cycle_started_at + timedelta(seconds=300):
            raise ValueError("graphics deadline must inherit the original cycle clock")
        return self


class GraphicsResult(Closed):
    contract_version: Literal["graphics/v1"] = "graphics/v1"
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    story_id: UUID
    revision: int = Field(gt=0)
    text_id: UUID
    locale: Literal["en", "ja", "zh-cn"]
    outcome: Literal["pending", "unavailable", "failed", "complete"]
    source_hashes: list[str] = Field(max_length=200)
    references: list[Asset] = Field(default_factory=list, max_length=20)
    exports: list[Asset] = Field(default_factory=list, max_length=3)
    picture_id: UUID | None = None
    producing_call_ids: list[int] = Field(default_factory=list, max_length=20)
    display_credit: str = Field(default="", max_length=2000)
    watermark: Literal["present", "absent", "unknown"] = "unknown"
    actual_cost_usd: float | None = Field(default=None, ge=0, le=1000)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    gaps: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def package(self):
        if self.outcome == "complete" and (
            not self.picture_id
            or not self.producing_call_ids
            or not {"video"} <= {asset.kind for asset in self.exports}
            or not {"gif", "still"} & {asset.kind for asset in self.exports}
        ):
            raise ValueError(
                "complete graphics requires video, matching still or GIF, and producing lineage"
            )
        return self


def make_request(text, *, max_cost_usd=0):
    parent, run = text.narrative, text.narrative.run
    if parent.consideration_state != "selected" or parent.status != "approved":
        raise ValueError("graphics accepts published winners only")
    start = run.cycle_started_at or run.facts_as_of
    fields = {
        "run_id": run.pk,
        "content_id": parent.pk,
        "story_id": parent.story_id,
        "revision": parent.revision,
        "text_id": text.public_id,
        "locale": text.locale,
        "source_locale": parent.source_locale_id,
        "editorial_group": parent.editorial_group,
        "factual_premise": text.body[:8000],
        "headline": text.headline,
        "byline": text.secondary,
        "sources": [
            Source(
                source_id=row.post_id or f"dossier-source:{row.dossier_source_id}",
                url=row.url_snapshot,
                sha256=row.source_hash,
            )
            for row in text.sources.order_by("position")
        ],
        "max_cost_usd": max_cost_usd,
        "cycle_started_at": start,
        "deadline": start + timedelta(seconds=300),
    }
    # Defaults are included in the fingerprint, making every option reproducible.
    candidate = GraphicsRequest.model_construct(fingerprint="0" * 64, **fields)
    return GraphicsRequest.model_validate(
        {
            **candidate.model_dump(mode="json"),
            "fingerprint": digest(
                candidate.model_dump(mode="json", exclude={"fingerprint"})
            ),
        }
    )


def no_art(request):
    return GraphicsResult(
        request_fingerprint=request.fingerprint,
        story_id=request.story_id,
        revision=request.revision,
        text_id=request.text_id,
        locale=request.locale,
        outcome="unavailable",
        source_hashes=[source.sha256 for source in request.sources],
        actual_cost_usd=0,
        gaps=["Graphics workflow is not activated; factual text is ready."],
    )


@transaction.atomic
def receive_result(request, result):
    request = GraphicsRequest.model_validate(request.model_dump(mode="json"))
    result = GraphicsResult.model_validate(result.model_dump(mode="json"))
    if (
        any(
            getattr(request, key) != getattr(result, key)
            for key in ("story_id", "revision", "text_id", "locale")
        )
        or result.request_fingerprint != request.fingerprint
    ):
        raise ValueError("graphics result identity mismatch")
    if result.source_hashes != [source.sha256 for source in request.sources]:
        raise ValueError("graphics result source lineage mismatch")
    text = (
        OriginalContentText.objects.select_for_update()
        .select_related("narrative__run")
        .get(public_id=request.text_id)
    )
    if make_request(text, max_cost_usd=request.max_cost_usd) != request:
        raise ValueError("graphics request no longer matches immutable text")
    pointer = OriginalContentSelection.objects.filter(
        scope_key=featured_scope(
            "social-brief",
            text.locale,
            source_locale=request.source_locale,
            editorial_group=request.editorial_group,
        )
    ).first()
    if not pointer or pointer.text_id != text.pk:
        return "stale"
    payload = result.model_dump(mode="json")
    existing = text.provenance.get("graphics_result")
    if (
        existing is not None
        and existing != payload
        and existing["outcome"] == "complete"
    ):
        raise ValueError("conflicting graphics completion")
    if result.outcome == "complete":
        picture = EditorialPicture.objects.get(
            pk=result.picture_id,
            content_kind="chatter",
            content_id=str(text.public_id),
            revision_hash=request.fingerprint,
            state="complete",
        )
        if picture.text_id not in (None, text.pk) or picture.run_id not in (
            None,
            request.run_id,
        ):
            raise ValueError("graphics stored ownership mismatch")
        if not picture.source_media_id or picture.source_media_id not in [
            asset.sha256 for asset in result.references
        ]:
            raise ValueError("graphics stored-media lineage mismatch")
        if (
            not picture.generated_storage_name
            or not picture.generated_sha256
            or picture.generated_sha256
            not in [asset.sha256 for asset in result.exports]
        ):
            raise ValueError("graphics stored export mismatch")
    text.provenance = {
        **text.provenance,
        "graphics_request": request.model_dump(mode="json"),
        "graphics_result": payload,
    }
    text.save(update_fields=["provenance"])
    return result.outcome
