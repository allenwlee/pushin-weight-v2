"""Selected-story integration with no provider traffic or billing."""

import base64
import hashlib
import json
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import StaffCollectionWork, StaffProviderRequest
from core.staff_assets import person_research
from monitor.editorial.chatter_trends import DECISION_SCOPE, ROLLING_LANE
from monitor.editorial.graphics_cast import prepare_person_cast
from monitor.editorial.graphics_contracts import WRITER_LED
from monitor.editorial.graphics_packages import materialize_package
from monitor.editorial.graphics_pipeline import advance_step
from monitor.tasks import research_chatter_person
from tests.test_chatter_graphics_publication import personalized
from tests.test_graphics_chatter_adapter import copy_result, prepared
from tests.test_graphics_chatter_adapter import (
    frozen_chatter as frozen_chatter,  # noqa: PLC0414
)
from tests.test_person_intake_identity import arthur as arthur  # noqa: PLC0414
from tests.test_person_portrait import DATA, NAME, PASSAGE, fake_sources

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.mark.parametrize("frozen_chatter", [PASSAGE], indirect=True)
@pytest.mark.parametrize("late", [False, True])
def test_cold_start_to_writer_then_cache(
    frozen_chatter,
    arthur,
    monkeypatch,
    settings,
    tmp_path,
    late,
):
    row, _, _ = frozen_chatter
    personalized(row)
    row.selection.update(subject=PASSAGE, people=[NAME], original_headlines=[PASSAGE])
    row.save(update_fields=["selection"])
    row.run.scope_key = DECISION_SCOPE
    row.run.config_snapshot["editorial"]["chatter"]["discovery_lane"] = ROLLING_LANE
    row.run.save(update_fields=["scope_key", "config_snapshot"])
    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("EXA_API_KEY", "fixture")
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture")
    settings.STORAGES = {
        **settings.STORAGES,
        "staff_media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    research = fake_sources(monkeypatch)
    request = prepared(row)
    keys = {request["writer_route"]["key_env"]: "fixture"}
    run, _ = materialize_package(request)
    first = advance_step(run.pk, keys=keys)
    assert first["state"] == "awaiting_portrait"
    work = StaffCollectionWork.objects.get(policy_version=person_research.POLICY)
    assert work.context["subject"] == NAME
    if late:
        after_deadline = timezone.now() + timedelta(seconds=22)
        monkeypatch.setattr(timezone, "now", lambda: after_deadline)
    assert research_chatter_person.run(work.pk) == "complete"
    assert research_chatter_person.run(work.pk) == "already_claimed_or_finished"
    assert research["search"] == ['"Arthur Mensch" "Mistral"']
    assert len(research["assessment"]) == 1
    before = StaffProviderRequest.objects.count()
    wire = []

    def send(_endpoint, _key, body, **_kwargs):
        wire.append(body)
        proposal = copy_result(used=["F01"])
        proposal.update(
            schema_version=WRITER_LED,
            candidates=[
                {
                    **proposal["candidates"][0],
                    "still_pitch": "A portrait.",
                    "motion_prompt": "The camera pans.",
                }
            ],
        )
        return 200, json.dumps(
            {
                "model": body["model"],
                "usage": {},
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(proposal)},
                    }
                ],
            }
        ).encode()

    next_step = advance_step(run.pk, keys=keys, transport=send)
    assert next_step["stage"] == "C1" and len(wire) == 1
    run.refresh_from_db()
    assets = run.decisions["writer_cast"]["assets"]
    assert [a["sha256"] for a in assets] == (
        [] if late else [hashlib.sha256(DATA).hexdigest()]
    )
    assert (base64.b64encode(DATA).decode() in json.dumps(wire)) == (not late)
    again = prepare_person_cast(request, row.selection, timezone.now())
    assert again["subjects"][0]["work_id"] is None
    assert again["subjects"][0]["asset"]["sha256"] == hashlib.sha256(DATA).hexdigest()
    assert StaffProviderRequest.objects.count() == before


@pytest.mark.parametrize("role", ["author", "quoted_author", "mentioned"])
def test_same_named_reporting_account_is_not_the_subject(arthur, role):
    from core.models import Person
    from core.person_names import record_legacy_display_name
    from monitor.editorial.graphics_cast import story_subjects

    reporter = Person.objects.create()
    record_legacy_display_name(reporter, NAME)
    facts = [{"fact_id": "F01", "source_post_id": "123", "supporting_passage": PASSAGE}]
    saved = {"handoff": {"subject": PASSAGE, "fact_items": facts}}
    selection = {
        "people": [NAME],
        "source_identities": [
            {
                "post_id": "123",
                "person_links": [
                    {
                        "role": role,
                        "resolution_status": "confirmed",
                        "person_id": str(reporter.pk),
                    }
                ],
            }
        ],
    }
    assert list(story_subjects(saved, selection)) == [(NAME, None, facts)]


def test_prerequisite_resume_is_explicit_and_paid_ambiguity_remains_held():
    import uuid

    from core.models import Person
    from core.staff_assets.person_research import (
        POLICY,
        claim_research,
        resume_after_configuration,
    )

    work = StaffCollectionWork.objects.create(
        person=Person.objects.create(),
        fingerprint="d" * 64,
        policy_version=POLICY,
        state="needs_evidence",
        result={"gaps": ["exa_credential_unavailable"]},
    )
    assert claim_research(work.pk) is None
    resume_after_configuration(work.pk)
    claimed = claim_research(work.pk)
    assert claimed.state == "running"
    assert claim_research(work.pk) is None
    StaffProviderRequest.objects.create(
        person=work.person,
        work=work,
        provider="portrait_exa",
        fingerprint="e" * 64,
        run_id=uuid.uuid4(),
    )
    StaffCollectionWork.objects.filter(pk=work.pk).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert claim_research(work.pk) is None
    work.refresh_from_db()
    assert work.state == "needs_review"
    with pytest.raises(ValueError, match="settled prerequisite"):
        resume_after_configuration(work.pk)


def test_same_person_sources_keep_the_official_page_and_skip_search(
    arthur, monkeypatch, tmp_path, settings
):
    from tests.test_person_portrait import PAGE

    _, evidence = arthur
    monkeypatch.setenv("OPENROUTER_API_KEY", "fixture")
    calls = fake_sources(monkeypatch)
    settings.STORAGES = {
        **settings.STORAGES,
        "staff_media": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
    }
    facts = [
        {
            "fact_id": f"F{n}",
            "supporting_passage": PASSAGE,
            "source_id": str(n),
            "observed_at": evidence["observed_at"],
            "source_refs": [url],
        }
        for n, url in ((1, "https://x.com/i/status/123"), (2, PAGE))
    ]
    request = {
        "facts_as_of": evidence["observed_at"],
        "handoff": {"subject": PASSAGE, "fact_items": facts},
    }
    state = prepare_person_cast(request, {"people": [NAME]}, timezone.now())
    work = StaffCollectionWork.objects.get(pk=state["subjects"][0]["work_id"])
    assert PAGE in work.context["evidence"]["source_urls"]
    assert research_chatter_person.run(work.pk) == "complete"
    assert calls["search"] == []


def test_legacy_episode_can_research_a_founder_outside_the_catalog(monkeypatch):
    from unittest.mock import Mock
    from core.staff_assets import person_intake
    from core.models import BrandAccount, CompanyAccount
    from monitor.editorial.graphics_cast import story_subjects

    subject = "Robin Hart"
    passage = "🎤 Heliograph founder Robin Hart talked to the press."
    saved = {
        "facts_as_of": timezone.now().isoformat(),
        "handoff": {
            "subject": "Robin Hart speaks at the summit",
            "fact_items": [{
                "fact_id": "F01",
                "supporting_passage": passage,
                "source_refs": ["https://news.example/interview"],
            }],
        },
    }
    saved["handoff"]["fact_items"][0]["supporting_passage"] = (
        "Robin Hart interviewed Heliograph founder Jane Miller."
    )
    assert list(story_subjects(saved, {})) == []
    saved["handoff"]["fact_items"][0]["supporting_passage"] = passage
    saved["handoff"]["fact_items"].append({
        "fact_id": "F02",
        "supporting_passage": "Heliograph founder Robin Hart answered another question.",
        "source_refs": ["https://news.example/second-report"],
    })
    lookup = Mock(wraps=person_intake.personal_accounts_named)
    monkeypatch.setattr(person_intake, "personal_accounts_named", lookup)
    state = prepare_person_cast(saved, {}, timezone.now())
    lookup.assert_called_once_with(subject)
    entry, = state["subjects"]
    assert entry["name"] == subject and entry["work_id"]
    work = StaffCollectionWork.objects.get(pk=entry["work_id"])
    assert work.context["evidence"]["passage"] == passage
    assert not BrandAccount.objects.exists() and not CompanyAccount.objects.exists()
    repeat = prepare_person_cast(saved, {}, timezone.now())
    assert repeat["subjects"][0]["work_id"] == work.pk
