import io

import pytest
from django.utils import timezone
from PIL import Image

from core.models import Brand, Person, PersonBrandAffiliation, PersonMedia
from core.staff_assets.media import store_image
from monitor.editorial.config import EditorialConfig, Route
from monitor.editorial.contracts import Event


@pytest.fixture
def editorial_storage(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        **{
            name: {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
                "OPTIONS": {"location": str(tmp_path / name)},
            }
            for name in ("staff_media", "editorial_media")
        },
    }
    settings.STAFF_MEDIA_DURABLE = True
    settings.EDITORIAL_MEDIA_DURABLE = True


def person_photo(
    name,
    kind="employment",
    team="",
    status="current",
    review="confirmed",
    reuse="permitted",
    photo=True,
):
    brand, _ = Brand.objects.get_or_create(nickname="deepseek")
    person = Person.objects.create(display_name=name)
    role = PersonBrandAffiliation.objects.create(
        person=person,
        brand=brand,
        affiliation_type=kind,
        observed_organization_name="DeepSeek",
        status=status,
        review_status=review,
        team=team,
        claim_identity=str(person.pk),
    )
    asset = None
    if photo:
        out = io.BytesIO()
        Image.new("RGB", (320, 480), name if name in ("red", "blue") else "green").save(
            out, format="PNG"
        )
        media = store_image(out.getvalue())
        asset = PersonMedia.objects.create(
            person=person,
            media=media,
            fingerprint=str(person.pk),
            source_url="https://example.org/photo",
            source_kind="official",
            availability="available",
            source_verified=True,
            individual_portrait=True,
            suitability="approved",
            reuse_status=reuse,
            verification_reason="Official attribution",
            observed_at=timezone.now(),
        )
    return person, role, asset


def active_config(**overrides):
    route = Route(
        model="explicit-test",
        endpoint="https://openrouter.ai/api/v1/chat/completions",
        key_env="OPENROUTER_API_KEY",
        input_usd_per_million=1,
        output_usd_per_million=1,
        vision=True,
    )
    values = {
        "enabled": True,
        "daily_usd": 10,
        "assessment_usd": 5,
        "daily_calls": 10,
        "media_daily_calls": 2,
        "media_cost_ceiling_usd": 1,
        "routes": {k: route for k in ("editor", "chatter", "pulse")},
        "pictures": {"chatter": "derive"},
    }
    values.update(overrides)
    return EditorialConfig(**values)


def selection(**kwargs):
    values = {
        "key": "new-agent",
        "summary": "Agent release",
        "post_ids": ["1"],
        "brand_keys": ["deepseek"],
        "occurred_at": timezone.now(),
        "chatter": True,
        "pulse": True,
        "importance": 70,
        "reason": "Release",
        "subject_kind": "agent_release",
    }
    values.update(kwargs)
    return Event(**values)
