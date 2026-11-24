"""Import named-person reference research from the existing Chinese staff collector."""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from billiard.exceptions import SoftTimeLimitExceeded
from django.core.files.storage import storages
from django.db import transaction

from core.person_affiliations import active_claims
from core.person_names import digest, record_name
from core.staff_assets.g2_cast_ingest import ingest_image, ingest_video
from core.staff_assets.media import review_media


def _seed(person, subject, observations):
    name = subject if isinstance(subject, str) else subject.get("name", "")
    aliases = list(
        person.names.exclude(review_status="rejected")
        .order_by("id")
        .values_list("full_name", flat=True)
    )
    company = next(
        (
            o["affiliation"]["organization"]
            for o in observations
            if isinstance(o.get("affiliation"), dict)
            and o["affiliation"].get("organization")
        ),
        "",
    )
    if not company:
        known = set(
            active_claims(person.brand_affiliations.all())
            .filter(
                status="current",
                affiliation_type_reference__code__in=("employment", "founder"),
            )
            .exclude(observed_organization_name="")
            .values_list("observed_organization_name", flat=True)
        )
        if len(known) == 1:
            company = known.pop()
    return {
        "person_id": str(person.pk),
        "name": name.strip(),
        "aliases": sorted(set(aliases) - {name}),
        "name_zh": next(
            (n for n in [name, *aliases] if any("\u3400" <= c <= "\u9fff" for c in n)),
            "",
        ),
        "company": company,
    }


def _import_report(person, seed, report, root, jobs):
    if report["person"] != seed or report["schema"] != "person-china-research/v1":
        raise ValueError("china_checkpoint_identity_mismatch")
    if type(report["jobs"]) is not bool or report["jobs"] != jobs:
        raise ValueError("china_checkpoint_needs_mismatch")
    asset_ids, evidence = [], []
    gaps = list(report["gaps"])
    for observation in report["evidence"]:
        if observation.get("person_id") == str(person.pk) and (
            jobs or "affiliation" not in observation
        ):
            evidence.append(observation)
    with transaction.atomic():
        for obs in evidence:
            name = obs.get("name")
            if name and name in obs["passage"]:
                record_name(
                    person,
                    full_name=name,
                    language="und",
                    source_kind="named_third_party",
                    source_reference=obs["source_url"],
                    source_text=obs["passage"],
                    collection_method="chinese_person_collector",
                    observed_at=datetime.fromisoformat(obs["observed_at"]),
                )
        for asset in report["assets"]:
            source, verdict = asset["source"], asset["verdict"]
            quote, label = verdict["evidence_quote"], verdict.get("visible_label") or ""
            if (
                verdict["status"] != "attributed"
                or verdict["source_id"] != source["id"]
                or not (
                    quote
                    and quote in source["text"]
                    or label
                    and verdict.get("verification_basis") == "visible_name_label"
                )
                or not asset.get("identity_context")
                or not asset.get("framing_ok")
            ):
                gaps.append("portrait_attribution_unresolved")
                continue
            # The collector distinguishes a visible spelling from inferred identity.
            # Preserve exact, already-linked names when this source also attests them.
            for spelling in dict.fromkeys([seed["name"], *seed["aliases"]]):
                if spelling and spelling in (quote + " " + label):
                    language = (
                        person.names.filter(full_name=spelling)
                        .exclude(review_status="rejected")
                        .values_list("locale__code", flat=True)
                        .first()
                        or "und"
                    )
                    record_name(
                        person,
                        full_name=spelling,
                        language=language,
                        source_kind="named_third_party",
                        source_reference=source["url"],
                        source_text=quote or label,
                        collection_method="chinese_person_collector",
                        observed_at=datetime.fromisoformat(report["observed_at"]),
                    )
            original = asset["media"]
            kind = original["kind"]
            if kind not in ("image", "video"):
                gaps.append("unsupported_collector_asset")
                continue
            entry = {
                "candidate_person_id": str(person.pk),
                "person_key": str(person.pk),
                "role": original["role"],
                "file": original["file"],
                "expected_sha256": original["sha256"],
                "source_url": source["url"],
                "original_url": asset.get("original_url") or "",
                "source_evidence": {
                    "source": source,
                    "verdict": verdict,
                    "identity_context": asset["identity_context"],
                    "observed_at": report["observed_at"],
                    "reference_sha256": asset.get("reference_sha256"),
                    "measurements": asset.get("measurements"),
                    "frame_times": asset.get("frame_times"),
                    "collector_asset_id": original["asset_id"],
                },
                "source_verified": True,
                "source_verification": verdict.get("verification_basis"),
                "identity_resolution": {
                    "state": "verified",
                    "person_id": str(person.pk),
                    "method": "collector_source_attribution",
                    "evidence": [asset["identity_context"], quote or label],
                },
                "credit": original.get("credit") or source.get("publisher") or "",
                "credit_origin": "source_publisher",
                "recorded_accreditation": original.get("accreditation"),
                "parent_sha256": original.get("parent_sha256"),
                "crop_pixels_xyxy": original.get("crop_pixels_xyxy"),
                "source_seconds": original.get("source_start_seconds"),
                "local_seconds": original.get("local_seconds"),
                "transformation": original.get("transformation"),
                "reuse_status": original.get("reuse_status", "unknown"),
                "grade": asset.get("grade"),
            }
            ingest = ingest_image if kind == "image" else ingest_video
            try:
                row, created = ingest(
                    person=person,
                    entry=entry,
                    source_roots=[root],
                    storage=storages["staff_media"],
                    observed_at=datetime.fromisoformat(report["observed_at"]),
                )
            except (ValueError, OSError) as exc:
                gaps.append(f"collector_media_import:{type(exc).__name__}")
                continue
            # Only a new attributed observation receives the automated assessment.
            # Independent decisions recorded on a pre-existing row take precedence.
            if created:
                review_media(
                    row,
                    reviewer="collect-chinese-workers",
                    reason=quote or label,
                    source_verified=True,
                    individual_portrait=kind == "image",
                    reuse_status=entry["reuse_status"],
                )
            if row.suitability != "rejected":
                asset_ids.append(row.pk)
    status = "complete" if (asset_ids or jobs and evidence) and not gaps else "partial"
    if any(
        isinstance(gap, str) and ("inspect_" in gap or "interrupted" in gap)
        for gap in gaps
    ):
        status = "needs_review"
    return {
        "status": status,
        "asset_ids": asset_ids,
        "evidence": evidence,
        "gaps": gaps,
        "counters": report["counters"],
    }


def _run_collector(request, collector, timeout=400):
    with subprocess.Popen(
        [sys.executable, "-m", "core.staff_assets.person_china_runtime"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "PYTHONPATH": str(collector.resolve())},
        start_new_session=True,
    ) as proc:
        try:
            stdout, _ = proc.communicate(json.dumps(request), timeout=timeout)
            if proc.returncode:
                raise RuntimeError(f"collector_process_exit_{proc.returncode}")
            return json.loads(stdout.splitlines()[-1])
        finally:
            # The child can own yt-dlp, ffmpeg and matcher processes. On a worker soft
            # timeout, stop the whole isolated group before Celery kills the task.
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()


def research_china_portrait(
    *, person, subject, evidence, facematch=False, jobs=False, work=None
):
    """Run or resume one person's bounded direct-API lookup in the collector's own runtime."""
    from core.staff_assets.person_china_runtime import initial_counters

    started = time.monotonic()
    counters = initial_counters()
    result = {
        "status": "partial",
        "asset_ids": [],
        "evidence": [],
        "gaps": [],
        "counters": counters,
    }
    state = os.environ.get("PERSON_CHINA_STATE_ROOT", "")
    if not state or not Path(state).is_absolute():
        result["gaps"].append(
            "china_runtime_missing:PERSON_CHINA_STATE_ROOT (shared persistent directory for source files and paid-call ledgers)"
        )
        return result
    observations = [evidence] if isinstance(evidence, dict) else list(evidence or [])
    seed = _seed(person, subject, observations)
    if (
        not seed["name"]
        or person.merged_into_id
        or work is not None
        and work.person_id != person.pk
    ):
        result["gaps"].append("china_subject_unresolved")
        return result
    urls = {o["source_url"] for o in observations if o.get("source_url")}
    for o in observations:
        urls.update(url for url in o.get("source_urls", []) if isinstance(url, str))
    state_root = Path(state).resolve()
    case_dir = (
        state_root
        / "people"
        / digest([seed[k] for k in ("person_id", "name", "company")])
    )
    frozen_seed = case_dir / "identity.json"
    if frozen_seed.is_file():
        try:
            prior = json.loads(frozen_seed.read_text())
            if any(prior[k] != seed[k] for k in ("person_id", "name", "company")):
                raise ValueError
            seed = prior
        except (OSError, ValueError, KeyError):
            result["gaps"].append("china_saved_identity_unresolved")
            return result
    request = {
        "person": seed,
        "profile": next(
            (
                o["personal_account"]
                for o in observations
                if isinstance(o.get("personal_account"), dict)
            ),
            {},
        ),
        "portrait": work is None
        or work.context.get("options", {}).get("portrait", True),
        "facematch": facematch,
        "jobs": jobs,
        "source_urls": sorted(urls),
    }
    # Keep raw discovery person-specific, and separate the results of different requested needs.
    request["profile"] = {
        key: str(request["profile"].get(key) or "")
        for key in ("bio", "location", "handle")
    }
    run_dir = case_dir / digest(request)
    checkpoint = run_dir / "intake-report.json"
    try:
        if checkpoint.is_file():
            report = json.loads(checkpoint.read_text())
            report["counters"] = {**counters, "cache_hits": 1}
        else:
            collector = Path(
                os.environ.get("PERSON_CHINA_COLLECTOR_ROOT")
                or Path.home() / "development/collect-chinese-workers"
            )
            if not (collector / "person_collect/reference_first.py").is_file():
                result["gaps"].append(
                    "china_runtime_missing:named-person collect-chinese-workers checkout (PERSON_CHINA_COLLECTOR_ROOT)"
                )
                return result
            # Isolate the external collector and its process-scoped HTTP transports from Django.
            try:
                report = _run_collector(
                    {
                        **request,
                        "state_root": str(state_root),
                        "case_dir": str(case_dir),
                        "run_dir": str(run_dir),
                    },
                    collector,
                )
            except (
                subprocess.TimeoutExpired,
                SoftTimeLimitExceeded,
                RuntimeError,
            ) as exc:
                interrupted = (
                    "china_interrupted_check_provider_receipts:" + type(exc).__name__
                )
                partial = run_dir / "partial-report.json"
                unknown = {key: None for key in counters}
                if not partial.is_file():
                    result["gaps"].append(interrupted)
                    result["status"] = "needs_review"
                    result["counters"].update(unknown)
                    result["counters"]["duration_seconds"] = round(
                        time.monotonic() - started, 3
                    )
                    return result
                report = json.loads(partial.read_text())
                report["gaps"].append(interrupted)
                report["counters"].update(unknown)
        if report.get("facematch") != facematch:
            raise ValueError("china_checkpoint_facematch_mismatch")
        result = _import_report(person, seed, report, case_dir, jobs)
    except (OSError, ValueError, IndexError, KeyError) as exc:
        result["gaps"].append(f"china_report_unavailable:{type(exc).__name__}")
    result["counters"]["duration_seconds"] = round(time.monotonic() - started, 3)
    return result
