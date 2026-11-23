import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from django.core.files.storage import FileSystemStorage
from PIL import Image

from core.models import PersonMedia
from core.staff_assets import person_china as adapter
from core.staff_assets import person_china_runtime as runtime
from tests.person_factory import person_with_name

NAME = "Lin Shu"
ORG = "Qilin Lab"
PASSAGE = "Lin Shu is the chief scientist at Qilin Lab."
SOURCE = {
    "id": "s1",
    "url": "https://example.org/leadership",
    "publisher": ORG,
    "text": PASSAGE,
}
WHEN = "2026-11-21T00:00:00+09:00"
OBS = {
    "passage": PASSAGE,
    "source_url": SOURCE["url"],
    "observed_at": WHEN,
    "industry": True,
    "affiliation": {
        "organization": ORG,
        "title": "chief scientist",
        "status": "current",
    },
}


@pytest.fixture
def pixels(tmp_path):
    image = tmp_path / "selected.png"
    Image.new("RGB", (180, 180), "#426781").save(image)
    return {
        "id": "a1",
        "kind": "image",
        "file": str(image),
        "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "source_id": "s1",
    }


def report(person, seed, pixels, jobs):
    return {
        "person": seed,
        "jobs": jobs,
        "facematch": False,
        "schema": "person-china-research/v1",
        "observed_at": WHEN,
        "gaps": [],
        "counters": runtime.initial_counters(),
        "evidence": [
            {
                **OBS,
                "person_id": str(person.pk),
                "name": NAME,
                "identity_supported": True,
            }
        ]
        if jobs
        else [],
        "assets": [
            {
                "media": {**pixels, "role": "identity-still", "asset_id": "a1"},
                "source": SOURCE,
                "verdict": {
                    "asset_id": "a1",
                    "source_id": "s1",
                    "status": "attributed",
                    "verification_basis": "personal_page",
                    "evidence_quote": PASSAGE,
                },
                "identity_context": PASSAGE,
                "framing_ok": True,
            }
        ],
    }


@pytest.mark.requires_postgres
@pytest.mark.django_db
def test_saved_person_pack_reuses_cast_and_writes_sourced_job(
    tmp_path, monkeypatch, pixels
):
    from core.models import Brand, PersonBrandAffiliation
    from core.staff_assets.person_intake import create_or_update_person

    person = person_with_name(NAME)
    Brand.objects.create(nickname="qilin-lab", display_name=ORG)
    monkeypatch.setattr(
        adapter,
        "storages",
        {"staff_media": FileSystemStorage(location=tmp_path / "media")},
    )
    seed = adapter._seed(person, NAME, [OBS])
    saved = report(person, seed, pixels, True)
    state = tmp_path / "state"
    collector = tmp_path / "collector"
    (collector / "person_collect").mkdir(parents=True)
    (collector / "person_collect/reference_first.py").touch()
    monkeypatch.setenv("PERSON_CHINA_STATE_ROOT", str(state))
    monkeypatch.setenv("PERSON_CHINA_COLLECTOR_ROOT", str(collector))
    calls = []

    def saved_child(req, _collector):
        calls.append(req["person"]["person_id"])
        folder = Path(req["run_dir"])
        folder.mkdir(parents=True)
        media = folder / "portrait.png"
        media.write_bytes(Path(pixels["file"]).read_bytes())
        saved["assets"][0]["media"]["file"] = str(media)
        (folder / "intake-report.json").write_text(json.dumps(saved))
        return saved

    monkeypatch.setattr(adapter, "_run_collector", saved_child)
    result = adapter.research_china_portrait(
        person=person, subject=NAME, evidence=OBS, jobs=True
    )
    assert result["status"] == "complete"
    (collector / "person_collect/reference_first.py").unlink()
    replay = adapter.research_china_portrait(
        person=person, subject=NAME, evidence=OBS, jobs=True
    )
    assert calls == [str(person.pk)] and replay["counters"]["cache_hits"] == 1
    assert replay["asset_ids"] == result["asset_ids"]
    row = PersonMedia.objects.get(pk=result["asset_ids"][0])
    assert (
        row.source_verified
        and row.individual_portrait
        and row.reuse_status == "unknown"
    )
    assert row.media_id == pixels["sha256"]
    assert row.evidence["source_evidence"]["verdict"]["evidence_quote"] == PASSAGE
    assert row.evidence["identity_resolution"]["state"] == "unverified_claim"
    assert not any(
        r.get("event") == "owner_confirmed_media" for r in row.review_history
    )
    assert person.names.filter(evidence__source_reference=SOURCE["url"]).exists()
    for observation in result["evidence"]:
        create_or_update_person(NAME, observation, needs={"jobs"})
    job = PersonBrandAffiliation.objects.get(person=person, brand_id="qilin-lab")
    assert job.title_raw == "chief scientist"
    assert job.status == "current"

    saved["assets"][0]["verdict"]["status"] = "candidate"
    assert not adapter._import_report(person, seed, saved, tmp_path, True)["asset_ids"]
    with pytest.raises(ValueError, match="checkpoint_identity"):
        adapter._import_report(
            person, {**seed, "name": "Another person"}, saved, tmp_path, True
        )


def test_missing_runtime_is_a_gap_and_starts_no_provider(monkeypatch):
    monkeypatch.delenv("PERSON_CHINA_STATE_ROOT", raising=False)
    result = adapter.research_china_portrait(
        person=object(), subject=NAME, evidence=OBS
    )
    assert result["status"] == "partial" and result["counters"]["provider_calls"] == 0
    assert "PERSON_CHINA_STATE_ROOT" in result["gaps"][0]


def test_collector_timeout_terminates_subprocess_group(monkeypatch, tmp_path):
    signals = []

    class Process:
        pid = 42

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

        def communicate(self, *args, **kwargs):
            raise subprocess.TimeoutExpired("person", 1)

    def spawn(*args, **kwargs):
        assert kwargs["start_new_session"]
        return Process()

    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    with pytest.raises(subprocess.TimeoutExpired):
        adapter._run_collector({}, tmp_path, timeout=1)
    assert [s[1] for s in signals] == [adapter.signal.SIGTERM, adapter.signal.SIGKILL]


def test_no_name_only_identity_context():
    person = {"name": NAME, "aliases": [], "name_zh": "", "company": ORG}
    assert not runtime._context(person, SOURCE, "Lin Shu", [])
    assert runtime._context(person, SOURCE, PASSAGE, []) == PASSAGE


def test_named_collector_replay_with_fake_vision_and_no_matching(
    tmp_path, monkeypatch, pixels
):
    # The application does not install the external human-operated checkout. Run this
    # integration wherever its actual named-person modules are available.
    external = Path(
        os.environ.get("PERSON_CHINA_COLLECTOR_ROOT")
        or Path.home() / "development/collect-chinese-workers"
    )
    if not (external / "person_collect/reference_first.py").is_file():
        pytest.skip("Named-person collector checkout is unavailable")
    monkeypatch.syspath_prepend(str(external))
    from company_collect import command
    from person_collect import provider, reference_first, sources
    from person_collect.provider import write_json

    def forbidden(*a, **kw):
        pytest.fail("offline fixture made an unexpected external or matching call")

    for module, name in (
        (sources, "enrich_xhs"),
        (reference_first, "measure"),
        (command, "live_balance"),
        (sources, "live_balance"),
        (provider.DirectModel, "_http"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    for key in ("DEEPINFRA_ON_DEMAND", "SERP_API_KEY"):
        monkeypatch.setenv(key, "test-only")
    monkeypatch.setattr(runtime.shutil, "which", lambda command: command)
    case_dir = tmp_path / "case"
    person = {
        "person_id": "person-123",
        "name": NAME,
        "company": ORG,
        "aliases": [],
        "name_zh": "",
    }
    write_json(
        case_dir / "collection/candidate-case.json",
        {
            "mode": "fresh",
            "id": "collection",
            "person": person,
            "sources": [SOURCE],
            "assets": [pixels],
            "collection_gaps": [],
        },
    )
    calls = []

    def fake_http(self, body, key, timeout):
        calls.append(body["response_format"]["json_schema"]["name"])
        assert "directly" in body["messages"][0]["content"]
        assert body["messages"][1]["content"][-1]["type"] == "image_url"
        answer = (
            {
                "anchor": {
                    "asset_id": "a1",
                    "source_id": "s1",
                    "status": "attributed",
                    "media_description": "Single participant",
                    "evidence_quote": PASSAGE,
                    "reason": "Caption",
                    "verification_basis": "personal_page",
                    "visible_label": None,
                },
                "limitations": [],
            }
            if calls[-1] == "AnchorDecision"
            else {
                "roles": [
                    {
                        "source_id": "s1",
                        "asset_id": "a1",
                        "passage": PASSAGE,
                        "person_name": NAME,
                        "organization": ORG,
                        "title": "chief scientist",
                        "job_function": None,
                        "status": "current",
                        "start_date": None,
                        "end_date": None,
                    }
                ]
            }
        )
        return {
            "model": body["model"],
            "usage": {"prompt_tokens": 5, "completion_tokens": 8},
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(answer)}}
            ],
        }

    monkeypatch.setattr(provider.DirectModel, "_http", fake_http)
    req = {
        "run_dir": str(case_dir / "portrait"),
        "case_dir": str(case_dir),
        "state_root": str(tmp_path),
        "person": person,
        "source_urls": [SOURCE["url"]],
        "profile": {},
        "jobs": False,
        "portrait": True,
        "facematch": False,
    }
    first = runtime.execute(req)
    assert first["gaps"] == []
    assert first["assets"][0]["media"]["sha256"] == pixels["sha256"]
    assert not first["evidence"] and calls == ["AnchorDecision"]
    again = runtime.execute(req)
    assert (
        again["counters"]["cache_hits"] == 1
        and again["counters"]["provider_calls"] == 0
    )
    with_jobs = runtime.execute(
        {**req, "jobs": True, "run_dir": str(case_dir / "with-jobs")}
    )
    assert calls == ["AnchorDecision", "RoleReadings"]
    assert (
        with_jobs["counters"]["cache_hits"] == with_jobs["counters"]["model_calls"] == 1
    )
    assert with_jobs["evidence"][0]["affiliation"] == OBS["affiliation"]
    assert with_jobs["evidence"][0]["passage"] == PASSAGE


def test_matched_video_requires_its_own_attribution_and_framing(tmp_path, monkeypatch):
    import sys
    from types import ModuleType

    source = {**SOURCE, "kind": "youtube"}
    person = {"name": NAME, "name_zh": "", "aliases": [], "company": ORG}
    verdict = {
        "asset_id": "v1",
        "source_id": "s1",
        "status": "attributed",
        "evidence_quote": NAME,
        "verification_basis": "corroborated_named_video",
        "visible_label": None,
    }
    (tmp_path / "source-assessment.json").write_text(json.dumps({"assets": [verdict]}))
    (tmp_path / "face-matches.json").write_text(json.dumps({"frame_measurements": {}}))
    pack = {
        "status": "completed_within_scope",
        "trusted_reference": {
            "source": source,
            "evidence": {"evidence_quote": PASSAGE},
            "sha256": "ab" * 32,
        },
        "render_review": {
            "assets": [
                {
                    "asset_id": "v1",
                    "role": "real-source-clip",
                    "framing_ok": True,
                    "grade": "A",
                }
            ]
        },
        "assets": [
            {
                "asset_id": "v1",
                "role": "real-source-clip",
                "kind": "video",
                "source_start_seconds": 140,
                "source_end_seconds": 148,
                "clip_local_start_seconds": 2,
                "clip_local_end_seconds": 10,
                "parent_sha256": "cd" * 32,
                "sha256": "de" * 32,
            }
        ],
    }
    module = ModuleType("person_collect.pipeline")
    module.run_case = lambda *args: pack
    monkeypatch.setitem(sys.modules, "person_collect.pipeline", module)
    case = {
        "person": person,
        "sources": [source],
        "assets": [{"id": "v1", "source_id": "s1", "original_url": source["url"]}],
    }
    media, gaps = runtime._matched_portraits(case, object(), tmp_path, [])
    assert not gaps and media[0]["reference_sha256"] == "ab" * 32
    assert media[0]["frame_times"]["source_end_seconds"] == 148
    assert media[0]["source"]["url"] == source["url"]
    pack["render_review"]["assets"][0]["framing_ok"] = False
    assert not runtime._matched_portraits(case, object(), tmp_path, [])[0]
    pack["trusted_reference"]["evidence"]["evidence_quote"] = NAME
    assert runtime._matched_portraits(case, object(), tmp_path, [])[1] == [
        "matched_reference_identity_context_unresolved"
    ]


def test_uncertain_model_receipt_stays_unknown_and_uncharged_on_replay(tmp_path):
    from types import SimpleNamespace

    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"status": "unresolved"}))
    used = {"folder": str(tmp_path), "cached": False, "request_sha256": "a" * 64}
    result = {"counters": runtime.initial_counters(), "gaps": []}
    runtime._provider_cost(SimpleNamespace(used_requests=[used]), result)
    assert result["counters"]["estimated_model_usd"] is None
    assert result["counters"]["provider_calls"] == 1
    assert result["gaps"] == ["inspect_model_receipt:" + "a" * 64]
    used["cached"] = True
    resumed = {"counters": runtime.initial_counters(), "gaps": []}
    runtime._provider_cost(SimpleNamespace(used_requests=[used]), resumed)
    assert (
        resumed["counters"]["provider_calls"] == 0
        and resumed["counters"]["cache_hits"] == 0
    )
    assert resumed["gaps"] == result["gaps"]


def test_quota_exhaustion_returns_partial_without_a_second_dispatch(
    tmp_path, monkeypatch
):
    seen = []

    def no_budget(req, report):
        seen.append(req["person"])
        raise RuntimeError("SerpApi quota reserve reached")

    monkeypatch.setattr(runtime, "_collect", no_budget)
    req = {
        "case_dir": str(tmp_path),
        "run_dir": str(tmp_path / "case"),
        "jobs": False,
        "facematch": False,
        "person": {"person_id": "fixture"},
    }
    result = runtime.execute(req)
    assert result["gaps"] == ["china_collector_unavailable:quota_or_budget"]
    assert not result["assets"] and len(seen) == 1


def test_existing_and_named_person_baidu_queries_retain_their_page_sizes(monkeypatch):
    from unittest.mock import MagicMock

    from core.staff_assets import providers

    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.iter_content.return_value = [b'{"organic_results":[]}']
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs["params"])
        return response

    monkeypatch.setattr(providers.requests, "get", get)
    baidu = providers.SerpApiBaidu(api_key="fixture")
    for bounds in ({"rn": 50, "pn": 0}, {"rn": 10}):
        params = {"engine": "baidu", "q": NAME, **bounds}
        assert baidu.search(params) == {"organic_results": []}
        assert calls[-1] == {**params, "api_key": "fixture"}
    with pytest.raises(ValueError, match="first Baidu page"):
        baidu.search({"engine": "baidu", "q": NAME, "rn": 50, "pn": 2})
    assert len(calls) == 2


def test_role_does_not_adopt_a_colleagues_spelling():
    person = {"name": NAME, "name_zh": "", "aliases": []}
    assert not runtime._attested_spelling(
        "Jane Li", person, "Lin Shu and Jane Li work at Qilin Lab."
    )
    assert runtime._attested_spelling(
        "林书", person, "Lin Shu（林书） is chief scientist at Qilin Lab."
    )
