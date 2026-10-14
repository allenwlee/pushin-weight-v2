import copy as copying
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone

from core.models import (
    EditorialAssessment,
    EditorialCall,
    EditorialEdition,
    OriginalContentCall,
    OriginalContentText,
    Post,
)
from monitor.editorial.contracts import Copy
from monitor.editorial.persistence import claim_assessment
from monitor.editorial.service import publish_edition
from monitor.editorial.voices import load_voice
from tests.editorial_support import (
    active_config,
    grounded_reply,
    selection,
    senior_approval,
)


def review_inputs():
    now = timezone.now()
    copy = Copy(
        headline="A release",
        byline="A new model.",
        article="A company announced a model.",
        locale="en",
        post_ids=["1"],
    )
    packet = {
        "cutoff": now.isoformat(),
        "posts": [
            {
                "id": "1",
                "original_text": "A company announced a model.",
                "images": [],
                "url": "https://x.com/i/status/1",
            }
        ],
        "context": [],
    }
    return copy, packet, load_voice("chatter-en-v1")


def test_production_review_preserves_the_complete_accepted_writer_requests():
    from monitor.editorial.config import load_editorial_config
    from monitor.editorial.contracts import Event
    from monitor.editorial.providers import request_payload
    from monitor.editorial.writing import writer_request

    cfg = load_editorial_config(Path("config/editorial-english-launch.yaml"))
    assert cfg.reviewer.model == "gpt-6.1-sol" and cfg.reviewer.reasoning == "high"
    assert cfg.daily_usd == 5 and cfg.assessment_usd == 2
    for data in json.loads(
        Path("tests/fixtures/editorial_repaired_writer_inputs.json").read_text()
    ).values():
        request = writer_request(
            Event.model_validate(data["event"]),
            data["packet"],
            load_voice(cfg.voices["chatter:en"]),
            cfg,
        )
        wire = request_payload(cfg.writer_route("chatter", "en"), request)
        assert (
            hashlib.sha256(json.dumps(wire, ensure_ascii=False).encode()).hexdigest()
            == data["request_hash"]
        )


def test_review_request_contains_literal_skill_untouched_copy_and_closed_packet():
    from monitor.editorial.providers import request_payload
    from monitor.editorial.reviewing import review_request, skill_text, validate_review

    copy, packet, voice = review_inputs()
    request, identity = review_request(
        copy, packet, voice, "writer-model", {"images": []}, active_config()
    )
    payload = json.loads(request["user"])
    assert payload["draft"] == copy.model_dump(mode="json")
    assert payload["evidence"] == packet
    assert skill_text()[0] in request["system"]
    assert identity["skill_sha256"] == skill_text()[1]
    wire = request_payload(active_config().reviewer, request)
    assert not {"tools", "tool_choice", "source_ids", "source_bindings"} & wire.keys()
    assert len(validate_review(senior_approval(), copy, packet).sections.__dict__) == 9


@pytest.mark.parametrize(
    "change", ["packet", "writer_model", "review_route", "saved_record"]
)
def test_approval_cannot_cross_identity_or_saved_record_boundary(change):
    from types import SimpleNamespace

    from monitor.editorial.reviewing import (
        require_approval,
        review_record,
        review_request,
    )

    copy, packet, voice = review_inputs()
    cfg = active_config()
    _, identity = review_request(copy, packet, voice, "writer-model", {}, cfg)
    record = review_record(
        {"data": senior_approval(), "model": cfg.reviewer.model},
        copy,
        packet,
        identity,
        "review-stage",
        "writer-stage",
    )
    row = SimpleNamespace(
        outcome={"senior_reviews": {"review-stage": copying.deepcopy(record)}}
    )
    writer_model = "writer-model"
    if change == "packet":
        packet["posts"][0]["original_text"] = "A different source claim."
    elif change == "writer_model":
        writer_model = "another-model"
    elif change == "review_route":
        cfg = cfg.model_copy(
            update={"reviewer": cfg.reviewer.model_copy(update={"reasoning": "high"})}
        )
    else:
        row.outcome["senior_reviews"] = {}
    with pytest.raises(ValueError, match="senior review"):
        require_approval(row, copy, packet, voice, writer_model, cfg, record)


@pytest.mark.parametrize(
    "defect",
    [
        "grade",
        "reason",
        "three_sentences",
        "section",
        "required",
        "material",
        "excerpt",
        "source",
        "source_field",
    ],
)
def test_malformed_or_contradictory_review_cannot_approve(defect):
    from monitor.editorial.reviewing import validate_review

    copy, packet, _ = review_inputs()
    data = senior_approval()
    section = data["sections"]["facts"]
    if defect == "grade":
        section["grade"] = "A++"
    elif defect == "reason":
        section["reason"] = ""
    elif defect == "three_sentences":
        section["reason"] = "This is supported. This is clear. This is readable."
    elif defect == "section":
        del data["sections"]["body"]
    elif defect == "required":
        data["required_changes"] = ["Fix the unsupported claim."]
    else:
        section["findings"] = [
            {
                "grade": "C",
                "reason": "This assertion is not supported by the supplied source.",
                "excerpt": "A release",
                "source_post_id": "1",
                "source_field": "original_text",
                "verification": "unsupported",
                "severity": "optional",
                "correction": "Remove the unsupported claim.",
            }
        ]
        finding = section["findings"][0]
        if defect == "material":
            finding["severity"] = "material"
        elif defect == "excerpt":
            finding["excerpt"] = "An invented sentence"
        elif defect == "source":
            finding["source_post_id"] = "outside-packet"
        else:
            finding["source_field"] = "stored_quote"
    with pytest.raises(ValueError):
        validate_review(data, copy, packet)


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
@pytest.mark.parametrize(
    "locale,verdict",
    [
        ("en", "publish"),
        ("ja", "publish"),
        ("zh-cn", "publish"),
        ("en", "revise"),
        ("ja", "hold"),
        ("zh-cn", "http_failure"),
        ("en", "malformed"),
        ("en", "budget"),
    ],
)
def test_real_transport_review_gate_and_durable_accounting(
    monkeypatch, locale, verdict
):
    from monitor.editorial import providers, service

    monkeypatch.setenv("ORIGINAL_CONTENT_STORAGE", "shared")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only")
    now = timezone.now()
    Post.objects.create(
        tweet_id="100",
        text="A company announced a model.",
        created_at=now - timedelta(minutes=1),
    )
    now = timezone.now()
    profiles = {
        "en": "chatter-en-v3",
        "ja": "chatter-ja-tospo-v2",
        "zh-cn": "chatter-zh-cn-wemedia-v2",
    }
    cfg = active_config(
        pictures={},
        voices={
            "chatter:en": profiles["en"],
            "pulse:en": "pulse-en-v1",
            f"chatter:{locale}": profiles[locale],
        },
        assessment_calls=2 if verdict == "budget" else 6,
    )
    expected_editions = 1 if locale == "en" else 2
    sends = []

    def transport(endpoint, key, body, **kwargs):
        sends.append(body)
        content = body["messages"][1]["content"]
        if isinstance(content, list):
            content = content[0]["text"]
        payload = json.loads(content)
        if "review_identity" in payload:
            assert payload["evidence"]["posts"][0]["id"] == "100"
            assert payload["draft"]["headline"] == "A release"
            assert EditorialCall.objects.filter(
                state="sent", stage__startswith="senior-review:"
            ).exists()
            if verdict == "http_failure":
                return 503, b"unavailable"
            data = senior_approval()
            if verdict == "malformed":
                data["sections"]["facts"]["grade"] = "invented"
            elif verdict in {"revise", "hold"}:
                data["verdict"] = verdict
                data["required_changes"] = [
                    "Clarify source ownership before publication."
                ]
        elif "editor-in-chief" in body["messages"][0]["content"]:
            data = grounded_reply(
                body,
                {
                    "events": [
                        {
                            "key": "new-model",
                            "summary": "A company announced a model.",
                            "post_ids": ["100"],
                            "occurred_at": (now - timedelta(minutes=1)).isoformat(),
                            "chatter": True,
                            "pulse": False,
                            "importance": 90,
                            "reason": "A substantive announcement.",
                        }
                    ]
                },
            )
        else:
            import re

            writer_locale = re.search(
                r"Write in (en|ja|zh-cn) directly", body["messages"][0]["content"]
            ).group(1)
            data = grounded_reply(
                body,
                {
                    "headline": "A release",
                    "byline": "A new model.",
                    "article": "A company announced a model.",
                    "locale": writer_locale,
                    "post_ids": ["100"],
                },
            )
        return 200, json.dumps(
            {
                "model": body["model"],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100},
                "choices": [
                    {"finish_reason": "stop", "message": {"content": json.dumps(data)}}
                ],
            }
        ).encode()

    monkeypatch.setattr(providers, "https_request", transport)
    envelope = {
        "schema_version": 1,
        "completed_at": now.isoformat(),
        "source_cycle_id": f"sr-{locale}-{verdict}",
        "outcome": "completed",
        "dry_run": False,
    }
    result = service.run_editorial(envelope, cfg=cfg)
    assert result["published"] == (expected_editions if verdict == "publish" else 0), (
        result
    )
    expected_sends = 2 if verdict == "budget" else 1 + 2 * expected_editions
    assert len(sends) == expected_sends
    assert EditorialCall.objects.count() == len(sends)
    assert OriginalContentCall.objects.count() == len(sends)
    row = EditorialAssessment.objects.get()
    if verdict in {"publish", "revise", "hold"}:
        record = next(
            r for r in row.outcome["senior_reviews"].values() if r["locale"] == locale
        )
        assert record["result"]["verdict"] == verdict
        assert record["result"]["overall_reason"]
        assert len(record["result"]["sections"]) == 9
        if verdict == "publish":
            edition = EditorialEdition.objects.get(locale=locale)
            assert edition.evidence["senior_review"] == record
            assert (
                OriginalContentText.objects.get(locale=locale).narrative.provenance[
                    "evidence"
                ]["senior_review"]
                == record
            )
            # Exact identity, not an old approval for changed copy or changed evidence.
            from monitor.editorial.reviewing import require_approval

            voice = load_voice(profiles[locale])
            writer_copy = Copy.model_validate(
                json.loads(sends[-1]["messages"][1]["content"])["draft"]
            )
            require_approval(
                row,
                writer_copy,
                json.loads(sends[-1]["messages"][1]["content"])["evidence"],
                voice,
                "explicit-test",
                cfg,
                record,
            )
            altered = copying.deepcopy(writer_copy)
            altered.headline = "Changed after approval"
            with pytest.raises(ValueError, match="identity mismatch"):
                require_approval(
                    row,
                    altered,
                    json.loads(sends[-1]["messages"][1]["content"])["evidence"],
                    voice,
                    "explicit-test",
                    cfg,
                    record,
                )
    assert service.run_editorial(envelope, cfg=cfg)["status"] == "already_claimed"
    assert len(sends) == expected_sends


@pytest.mark.django_db(transaction=True)
@pytest.mark.requires_postgres
def test_publication_without_senior_review_is_rejected():
    now = timezone.now()
    row = claim_assessment(now, "senior-review-missing")
    event = selection(occurred_at=now - timedelta(minutes=1))
    packet = {
        "cutoff": now.isoformat(),
        "posts": [{"id": "1", "url": "https://x.com/i/status/1"}],
        "context": [],
    }
    copy = Copy(
        headline="A release",
        byline="A new model.",
        article="A company announced a model.",
        locale="en",
        post_ids=["1"],
    )
    with pytest.raises(ValueError, match="senior review"):
        publish_edition(
            row,
            event,
            packet,
            "chatter",
            load_voice("chatter-en-v1"),
            copy,
            "explicit-test",
            active_config(pictures={}),
        )
    assert not EditorialEdition.objects.exists()
