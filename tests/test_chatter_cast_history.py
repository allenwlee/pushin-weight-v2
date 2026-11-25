"""A selected and confirmed portrait can identify the same role in a later article."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from core.models import OriginalContentText
from monitor.editorial.graphics_cast import prepare_person_cast
from tests.editorial_support import editorial_storage, person_photo  # noqa: F401
from tests.person_factory import person_with_name
from tests.test_original_content_consideration import consideration, producer

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.requires_postgres,
    pytest.mark.usefixtures("editorial_storage"),
]

NAME = "Jensen Huang"
EARLIER = "quand Jensen Huang, l'ex-patron de Nvidia, humiliait le Français Arthur Mensch de Mistral sur scène"
LATER = (
    "Nvidia NVDA officially reinstated Jensen Huang as CEO, president and board member"
)


def fact(passage, observed, key):
    return {
        "fact_id": key,
        "source_id": key,
        "source_role": "original",
        "source_usage": "consideration",
        "observed_at": observed.isoformat(),
        "supporting_passage": passage,
    }


def published_cast(name, passage, observed):
    person, _, media = person_photo(name)
    media.observed_at = observed
    media.review_history = [
        {
            "event": "owner_confirmed_media",
            "person_id": str(person.pk),
            "sha256": media.media_id,
            "source_reference": media.source_url,
            "confirmed_at": observed.isoformat(),
        }
    ]
    media.save(update_fields=["observed_at", "review_history"])
    row = consideration(
        consideration_state="selected", published_at=observed + timedelta(minutes=2)
    )
    previous = fact(passage, observed, "F01")
    row.run.workflow_key = "graphics-package"
    row.run.snapshot = {
        "request": {
            "person_ids": [str(person.pk)],
            "handoff": {"fact_items": [previous]},
        }
    }
    row.run.decisions = {
        "writer_cast": {
            "assets": [
                {
                    "asset_ref": f"person:{media.pk}",
                    "role": "identity_reference",
                    "person_id": str(person.pk),
                    "person_name": name,
                    "fact_ids": ["F01"],
                    "sha256": media.media_id,
                }
            ]
        }
    }
    row.run.save(update_fields=["workflow_key", "snapshot", "decisions"])
    call = producer(row, "en")
    call.stage = f"gfx:{row.run_id}:C1"
    call.completed_at = observed + timedelta(minutes=1)
    call.save(update_fields=["stage", "completed_at"])
    text = OriginalContentText.objects.create(
        narrative=row,
        locale="en",
        public_id=uuid4(),
        headline="Earlier article",
        secondary="Earlier angle",
        producing_call=call,
    )
    OriginalContentText.objects.filter(pk=text.pk).update(created_at=row.published_at)
    return media


@pytest.mark.parametrize("review_date,passage", [
    ("confirmed_at", LATER),
    ("recorded_at", "Nvidia Board reinstates Jensen Huang as President, CEO and Board Director."),
])
def test_prior_selected_cast_identifies_current_subject_across_namesakes(review_date, passage):
    started = timezone.now()
    photo = published_cast(NAME, EARLIER, started - timedelta(days=1))
    if review_date != "confirmed_at":
        review = photo.review_history[0]
        review[review_date] = review.pop("confirmed_at")
        photo.save(update_fields=["review_history"])
    person_with_name(NAME)
    saved = {
        "facts_as_of": (started - timedelta(minutes=2)).isoformat(),
        "handoff": {
            "subject": "Jensen Huang’s Nvidia comeback becomes an AI meme",
            "fact_items": [
                fact(passage, started - timedelta(seconds=10), "F05"),
                fact(
                    "Jensen Huang reported on unrelated news.",
                    started - timedelta(seconds=30),
                    "F01",
                ),
            ],
        },
    }
    state = prepare_person_cast(saved, {"people": [NAME]}, started)
    assert [
        (item["person_id"], item["asset"]["asset_ref"], item["fact_ids"])
        for item in state["subjects"]
    ] == [
        (str(photo.person_id), f"person:{photo.pk}", ["F05"]),
    ], state


@pytest.mark.parametrize(
    "control",
    [
        "different_employer",
        "reporter",
        "negated",
        "speculation",
        "question",
        "adjacent_employer",
        "no_role",
        "late_current_fact",
        "unselected_prior",
        "late_prior_edition",
        "late_confirmation",
        "uncited_role",
        "another_qualifying_namesake",
    ],
)
def test_history_rejects_conflicts_and_unavailable_evidence(control):
    started = timezone.now()
    earlier = started - timedelta(days=1)
    photo = published_cast(NAME, EARLIER, earlier)
    row = OriginalContentText.objects.get().narrative
    person_with_name(NAME)
    if control == "another_qualifying_namesake":
        published_cast(NAME, EARLIER, earlier)
    elif control == "unselected_prior":
        row.run.snapshot["request"]["person_ids"] = []
        row.run.save(update_fields=["snapshot"])
    elif control == "late_prior_edition":
        row.published_at = started + timedelta(days=1)
        row.save(update_fields=["published_at"])
    elif control == "late_confirmation":
        photo.review_history[0]["confirmed_at"] = (
            started + timedelta(days=1)
        ).isoformat()
        photo.save(update_fields=["review_history"])
    elif control == "uncited_role":
        row.run.decisions["writer_cast"]["assets"][0]["fact_ids"] = ["F99"]
        row.run.save(update_fields=["decisions"])
    passage = {
        "different_employer": "Example Labs appointed Jensen Huang as CEO. Nvidia reported earnings.",
        "reporter": "Jensen Huang reports that Nvidia appointed Maya Smith as CEO.",
        "negated": "It is false that Nvidia reinstated Jensen Huang as CEO.",
        "question": "Nvidia appointed Jensen Huang as CEO?",
        "speculation": "If Nvidia reinstated Jensen Huang as CEO, shareholders would benefit.",
        "adjacent_employer": "Nvidia rival appointed Jensen Huang as CEO.",
        "no_role": "Jensen Huang posted about Nvidia.",
    }.get(control, LATER)
    when = started + timedelta(seconds=2) if control == "late_current_fact" else earlier
    saved = {
        "facts_as_of": started.isoformat(),
        "handoff": {"subject": NAME, "fact_items": [fact(passage, when, "F05")]},
    }
    state = prepare_person_cast(saved, {"people": [NAME]}, started)
    assert not state["subjects"], state
    assert state["gaps"]


def test_chatter_unique_owner_selected_name_needs_a_current_source_connection():
    from core.staff_assets.person_intake import create_or_update_person

    now = timezone.now()
    media = published_cast(NAME, EARLIER, now - timedelta(days=1))
    media.source_kind = "saved_g2_cast"
    media.evidence = {
        "source_role": "identity-still",
        "identity_resolution": {
            "state": "verified",
            "person_id": str(media.person_id),
            "source_name": NAME,
            "evidence": ["Owner confirmed the saved person and image."],
        },
    }
    media.save(update_fields=["source_kind", "evidence"])
    f = fact("Jensen Huang reports on a new shop.", now, "F01")
    saved = {
        "facts_as_of": now.isoformat(),
        "handoff": {"subject": NAME, "fact_items": [f]},
    }
    ordinary = create_or_update_person(
        NAME,
        {
            "source_id": "F01",
            "passage": f["supporting_passage"],
            "observed_at": now,
        },
        apply=False,
    )
    assert ordinary["person_id"] == str(media.person_id)
    assert not prepare_person_cast(saved, {"people": [NAME]}, now)["subjects"]


def test_second_person_and_dated_source_review_use_the_same_cast_path():
    started = timezone.now()
    name = "Morgan Chen"
    observed = started - timedelta(days=1)
    photo = published_cast(
        name, "Orbit Labs researcher Morgan Chen spoke to the press.", observed
    )
    photo.review_history = [
        {
            "source_verified": True,
            "individual_portrait": True,
            "reviewer": "portrait assessment",
            "reason": "The attributed photograph identifies the sole subject.",
            "at": observed.isoformat(),
        }
    ]
    photo.save(update_fields=["review_history"])
    person_with_name(name)
    saved = {
        "facts_as_of": started.isoformat(),
        "handoff": {
            "subject": name,
            "fact_items": [
                fact(
                    "Morgan Chen, researcher at Orbit Labs, described the experiment.",
                    started,
                    "F04",
                ),
            ],
        },
    }
    state = prepare_person_cast(saved, {"people": [name]}, started)
    assert [entry["asset"]["asset_ref"] for entry in state["subjects"]] == [
        f"person:{photo.pk}"
    ]


def test_current_named_account_for_a_different_person_blocks_an_earlier_cast():
    from core.models import Account
    from tests.test_person_identity import link

    started = timezone.now()
    published_cast(NAME, EARLIER, started - timedelta(days=1))
    other = person_with_name(NAME)
    account = Account.x.create(
        author_id="11349", handle="otherjensen", display_name=NAME
    )
    link(other, account, "confirmed")
    saved = {
        "facts_as_of": started.isoformat(),
        "handoff": {
            "subject": NAME,
            "fact_items": [
                fact(LATER, started, "F05"),
                fact("Jensen Huang (@otherjensen) spoke to reporters.", started, "F02"),
            ],
        },
    }
    state = prepare_person_cast(saved, {"people": [NAME]}, started)
    assert not state["subjects"] and state["gaps"] == [
        f"{NAME}: ambiguous_subject_name"
    ]


def test_published_appearance_lookup_batches_the_entire_namesake_set(
    django_assert_num_queries,
):
    from monitor.editorial.chatter_cast_history import confirmed_appearances

    started = timezone.now()
    photo = published_cast(NAME, EARLIER, started - timedelta(days=1))
    for extras in [0, 225]:
        ids = {str(photo.person_id), *(str(uuid4()) for _ in range(extras))}
        with django_assert_num_queries(2):
            matches = confirmed_appearances(ids, started.isoformat())
        assert set(matches) == {str(photo.person_id)}


@pytest.mark.parametrize(
    "control",
    [
        "matched",
        "competing_link",
        "unverified",
        "wrong_alias",
        "other_primary_author",
        "other_subject",
        "author",
        "changed_post",
        "background",
        "different_provisional_id",
    ],
)
def test_verified_native_mention_corroborates_named_subject_without_promoting_pending_link(
    control,
):
    from core.models import Account, Person, PersonAccount, Post
    from core.person_identity import person_id_for_account
    from core.person_names import record_legacy_display_name
    from tests.test_person_identity import link

    native = "44196397"
    name = "Elon Musk"
    account = Account.x.create(
        author_id=native,
        handle="elonmusk",
        normalized_handle="elonmusk",
        display_name=name,
        verified=control != "unverified",
    )
    provisional = Person.objects.create(
        pk=person_id_for_account(native)
        if control != "different_provisional_id"
        else uuid4()
    )
    record_legacy_display_name(provisional, name)
    link(provisional, account, "pending")
    if control == "competing_link":
        link(person_with_name(name), account, "confirmed")
    _, _, photo = person_photo("Photo Fixture")
    photo.person = provisional
    photo.save(update_fields=["person"])
    native_author = native if control == "author" else "2103516178203238400"
    passage = "@Grimezsz @elonmusk AI is female in the same way a hurricane and Mother Church are"
    post = Post.objects.create(
        tweet_id="2123396364277301277",
        created_at=timezone.now(),
        text=passage,
        author_handle="elonmusk" if control == "author" else "MrSweetbrier",
        entities={
            "user_mentions": [
                {
                    "id_str": native,
                    "screen_name": "elonmusk",
                    "name": name if control != "wrong_alias" else "Other Person",
                }
            ]
        },
    )
    started = timezone.now()
    primary = {
        **fact("GRIMES & ELON MUSK FEUD OVER AI COMPANIONS", started, "F01"),
        "source_post_id": "123",
    }
    if control == "other_primary_author":
        primary["speaker_id"] = native
    cited = {
        **fact(
            passage if control != "changed_post" else passage + " says another post",
            started,
            "F02",
        ),
        "source_kind": "x_post",
        "source_post_id": post.pk,
        "speaker_id": native_author,
        "speaker": post.author_handle,
        "source_usage": "background" if control == "background" else "consideration",
    }
    subject = (
        "Grimes' new song"
        if control == "other_subject"
        else "Posts reporting a Grimes–Elon Musk dispute over AI companions"
    )
    saved = {
        "facts_as_of": started.isoformat(),
        "person_ids": [],
        "handoff": {"subject": subject, "fact_items": [primary, cited]},
    }
    selection = (
        {"original_headlines": [f"{name} comments on an unrelated interview"]}
        if control == "other_subject"
        else {}
    )
    state = prepare_person_cast(saved, selection, started)
    if control == "matched":
        assert [
            (value["person_id"], value["asset"]["asset_ref"], value["fact_ids"])
            for value in state["subjects"]
        ] == [(str(provisional.pk), f"person:{photo.pk}", ["F01", "F02"])], state
    else:
        assert not state["subjects"], state
    assert (
        PersonAccount.objects.get(person=provisional, account=account).resolution_status
        == "pending"
    )
