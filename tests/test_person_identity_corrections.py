import pytest
from django.db import IntegrityError, transaction

from core.models import Person, StaffCollectionWork, StaffIntake, StaffProviderRequest
from core.person_names import record_name, review_name, select_names
from core.staff_assets.intake import ingest_record
from core.staff_assets.queue import claim, reserve_request
from tests.test_person_identity import link
from tests.test_staff_library import record

pytestmark = [pytest.mark.requires_postgres, pytest.mark.django_db(transaction=True)]


def named(person, spelling="测试人", source="https://example.com/name"):
    name = record_name(
        person,
        full_name=spelling,
        language="zh-Hans",
        source_kind="website",
        source_reference=source,
        source_text=spelling,
        collection_method="manual",
    )
    review_name(name, "confirmed", "fixture", "Official bio")
    select_names(person, primary=name)
    return name


def correct(kind, source, target, key="correction-1", **kwargs):
    from core.person_identity_corrections import correct_identity

    return correct_identity(
        kind=kind,
        source_id=source.pk,
        target_id=target.pk,
        reviewer="Allen",
        reason="Compared original profiles",
        request_key=key,
        **kwargs,
    )


def test_merge_preserves_sources_and_redirects_existing_id():
    from core.person_identity import canonical_person

    intake, _ = ingest_record(record())
    source = intake.person
    original = source.names.get(language="zh-Hans")
    target = Person.objects.create(display_name="Survivor")
    result = correct("merge", source, target)
    original.refresh_from_db()
    intake.refresh_from_db()
    assert original.person_id == source.pk  # immutable source representation retained
    assert intake.person_id == target.pk
    assert target.brand_affiliations.count() == 1
    assert target.names.get(full_name="测试人").evidence.count() == 1
    assert canonical_person(source.pk).pk == target.pk
    assert correct("merge", source, target).pk == result.pk


def test_new_observation_after_merge_does_not_duplicate_the_moved_job():
    intake, _ = ingest_record(record())
    target = Person.objects.create(display_name="Survivor")
    correct("merge", intake.person, target)
    updated, _ = ingest_record(record(observed_at="2026-10-02T00:00:00Z"))
    assert updated.person_id == target.pk
    assert target.brand_affiliations.count() == 1


def test_profile_write_finishes_before_a_concurrent_merge(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections

    import core.profile_snapshots as snapshots
    from core.models import Account
    from tests.test_person_identity import profile

    record()  # known brand
    account = Account.objects.create(author_id="concurrent-correction", handle="worker")
    source = Person.objects.create(display_name="Source")
    target = Person.objects.create(display_name="Target")
    link(source, account, "confirmed")
    resolved, merged = Event(), Event()
    original = snapshots.account_person

    def pause_after_resolution(*args, **kwargs):
        person = original(*args, **kwargs)
        resolved.set()
        merged.wait(0.3)
        return person

    def capture():
        close_old_connections()
        try:
            profile(account)
        finally:
            close_old_connections()

    def merge():
        close_old_connections()
        try:
            assert resolved.wait(5)
            correct("merge", source, target)
            merged.set()
        finally:
            close_old_connections()

    monkeypatch.setattr(snapshots, "account_person", pause_after_resolution)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(capture), pool.submit(merge)
        first.result(timeout=10)
        second.result(timeout=10)
    assert not source.brand_affiliations.exists()
    assert target.brand_affiliations.count() == 1


def test_duplicate_name_retains_both_evidence_observations():
    source = Person.objects.create(display_name="First")
    target = Person.objects.create(display_name="Second")
    named(source, source="https://example.com/one")
    named(target, source="https://example.com/two")
    correct("merge", source, target)
    assert target.names.filter(full_name="测试人").count() == 1
    assert target.names.get(full_name="测试人").evidence.count() == 2
    assert source.names.get().evidence.count() == 1


def test_reimport_after_split_does_not_attach_evidence_to_the_other_person():
    intake, _ = ingest_record(record())
    source = intake.person
    target = Person.objects.create(display_name="Separated person")
    affiliation = source.brand_affiliations.get()
    evidence_before = affiliation.evidence.count()
    names_before = source.names.count()
    correct(
        "split",
        source,
        target,
        key="split-affiliation-only",
        selection={"affiliations": [affiliation.pk]},
    )
    affiliation.refresh_from_db()
    assert affiliation.person_id == target.pk
    replay = record()
    replay["affiliations"][0]["evidence_text"] = "另一条任职摘录"
    held, _ = ingest_record(replay)
    assert held.eligibility == "needs_review" and held.person_id is None
    assert affiliation.evidence.count() == evidence_before
    assert affiliation.evidence.filter(evidence_text="另一条任职摘录").count() == 0
    assert StaffIntake.objects.get(pk=intake.pk).person_id == source.pk
    assert source.names.count() == names_before
    assert not source.brand_affiliations.exists()


def test_split_moves_only_selected_claim_and_copies_name_with_audit():
    intake, _ = ingest_record(record())
    source = intake.person
    target = Person.objects.create(display_name="Separated person")
    original = source.names.get(language="zh-Hans")
    affiliation = source.brand_affiliations.get()
    correct(
        "split",
        source,
        target,
        selection={
            "affiliations": [affiliation.pk],
            "intakes": [intake.pk],
            "names": [original.pk],
        },
    )
    original.refresh_from_db()
    assert original.person_id == source.pk and original.review_status == "rejected"
    assert target.names.get(full_name="测试人").review_status == "confirmed"
    affiliation.refresh_from_db()
    assert affiliation.person_id == target.pk
    source.refresh_from_db()
    assert source.primary_name_id is None and source.merged_into_id is None


def test_correction_rejects_foreign_rows_without_partial_updates():
    source = Person.objects.create(display_name="Source")
    target = Person.objects.create(display_name="Target")
    other = Person.objects.create(display_name="Other")
    foreign_name = named(other)
    with pytest.raises(ValueError, match="belong"):
        correct("split", source, target, selection={"names": [foreign_name.pk]})
    assert not target.names.exists()
    source.refresh_from_db()
    assert source.merged_into_id is None


def test_correction_refuses_running_work_and_keeps_all_rows():
    intake, _ = ingest_record(record())
    source = intake.person
    target = Person.objects.create(display_name="Target")
    work = claim()
    assert work.person_id == source.pk
    with pytest.raises(ValueError, match="running"):
        correct("merge", source, target)
    assert not target.names.exists()
    assert source.brand_affiliations.count() == 1


def test_merge_keeps_paid_request_cache_and_budget_history():
    import uuid

    source = Person.objects.create(display_name="Source")
    target = Person.objects.create(display_name="Target")
    parameters = {"engine": "baidu", "q": "测试人 DeepSeek"}
    from core.person_names import digest

    old = StaffProviderRequest.objects.create(
        person=source,
        provider="serpapi",
        fingerprint=digest(parameters),
        run_id=uuid.uuid4(),
        parameters=parameters,
        state="complete",
        response={"ok": 1},
    )
    correct("merge", source, target)
    StaffCollectionWork.objects.create(person=target, fingerprint="new", context={})
    work = claim()
    cached, created = reserve_request(
        work,
        run_id=uuid.uuid4(),
        provider="serpapi",
        parameters=parameters,
        per_person=1,
        per_run=1,
        per_day=1,
    )
    assert not created and cached.pk == old.pk
    assert StaffProviderRequest.objects.count() == 1


def test_confirm_account_records_review_and_refuses_another_confirmed_person():
    from core.models import Account

    source = Person.objects.create(display_name="Source")
    target = Person.objects.create(display_name="Target")
    account = Account.objects.create(author_id="reviewed-account", handle="researcher")
    link(source, account, "confirmed")
    with pytest.raises(ValueError, match="confirmed"):
        correct("confirm_account", target, target, account_id=account.pk)
    assert not target.account_links.exists()


def test_correction_journal_cannot_be_rewritten_with_sql():
    from core.models import PersonIdentityCorrection

    source = Person.objects.create(display_name="Source")
    target = Person.objects.create(display_name="Target")
    audit = correct("merge", source, target)
    with pytest.raises(IntegrityError), transaction.atomic():
        PersonIdentityCorrection.objects.filter(pk=audit.pk).update(reason="erased")
    assert (
        PersonIdentityCorrection.objects.get(pk=audit.pk).reason
        == "Compared original profiles"
    )


def test_preview_command_is_read_only_then_apply_is_repeatable():
    import io
    import json

    from django.core.management import call_command

    from core.models import PersonIdentityCorrection

    source = Person.objects.create(display_name="Source")
    target = Person.objects.create(display_name="Target")
    output = io.StringIO()
    args = [
        "merge",
        "--source",
        str(source.pk),
        "--target",
        str(target.pk),
        "--reviewer",
        "Allen",
        "--reason",
        "Same profile",
        "--request-key",
        "cli-1",
    ]
    call_command("correct_person_identity", *args, stdout=output)
    assert json.loads(output.getvalue())["applied"] is False
    assert not PersonIdentityCorrection.objects.exists()
    source.refresh_from_db()
    assert source.merged_into_id is None
    call_command("correct_person_identity", *args, "--apply", stdout=io.StringIO())
    call_command("correct_person_identity", *args, "--apply", stdout=io.StringIO())
    assert PersonIdentityCorrection.objects.count() == 1


def test_merge_transfers_account_media_text_and_derived_name_without_changing_bytes():
    from core.intelligence_readers import person_intelligence
    from core.models import Account
    from core.person_text import record_text
    from core.staff_assets.media import record_media

    intake, _ = ingest_record(record())
    source = intake.person
    target = Person.objects.create(display_name="Target")
    original = source.names.get(language="zh-Hans")
    derived = record_name(
        source,
        full_name="Ceshi Ren",
        language="en-Latn",
        origin="generated",
        derived_from=original,
        source_kind="transliteration",
        source_reference="manual:pinyin",
        source_text="测试人",
        collection_method="manual",
    )
    account = Account.objects.create(author_id="owned", handle="owned")
    link(source, account, "confirmed")
    prose = record_text(
        source,
        kind="biography",
        language="zh-Hans",
        text="研究工作",
        source_reference="https://example.com/bio",
    )
    media = record_media(
        source,
        {
            "source_url": "https://example.com/bio",
            "original_url": "https://example.com/photo.jpg",
            "source_kind": "official_bio",
            "kind": "photo",
        },
    )
    correct("merge", source, target)
    assert target.account_links.get().resolution_status == "confirmed"
    assert (
        target.names.get(full_name=derived.full_name).derived_from.person_id
        == target.pk
    )
    prose.refresh_from_db()
    media.refresh_from_db()
    assert prose.person_id == media.person_id == target.pk
    assert (
        prose.text == "研究工作"
        and media.original_url == "https://example.com/photo.jpg"
    )
    assert person_intelligence(source.pk)["person"]["id"] == str(target.pk)
    assert source.collection_work.filter(state="queued").count() == 0
