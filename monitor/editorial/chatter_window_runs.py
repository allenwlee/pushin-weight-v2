"""Durable rolling selection over the official receipts archived by capture runs."""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from core.models import OriginalContent, OriginalContentCall, OriginalContentRun
from monitor.original_content import advisory_lock, digest, shared_storage

from .chatter_accounting import call_once
from .chatter_history import locked_run
from .chatter_trends import (
    CAPTURE_SCOPE,
    DECISION_SCOPE,
    WINDOW_RANK_STAGE,
    _headlines,
    _save,
    _saved_observation,
    checkpoint,
    workflow_version,
)
from .chatter_windows import (
    GRACE,
    HORIZON,
    QUARTER,
    apply_selection,
    decision_packet,
    selection_request,
    wording,
)
from .config import EditorialConfig
from .providers import json_call, request_fingerprint, request_payload


def _manifest(run, now):
    """Wait only for this slot's terminal response and never move its freeze past grace."""
    deadline = run.interval + GRACE
    captures = OriginalContentRun.objects.filter(
        scope_key=CAPTURE_SCOPE,
        interval__gt=run.interval - 4 * QUARTER,
        interval__lte=run.interval,
    ).order_by("interval")
    by_slot = {capture.interval: (capture, checkpoint(capture)) for capture in captures}
    at_boundary = by_slot.get(run.interval)
    terminal = None
    if at_boundary:
        state = at_boundary[1]
        terminal = (
            state.observation.observed_at if state.observation else state.terminal_at
        )
    if not terminal and now < deadline:
        return None
    freeze = min(deadline, terminal) if terminal else deadline
    manifest, missing = [], []
    for index in reversed(range(4)):
        slot = run.interval - index * QUARTER
        entry = by_slot.get(slot)
        receipt = entry[1].observation if entry else None
        if receipt and receipt.http_status == 200 and receipt.observed_at <= freeze:
            try:
                _headlines(_saved_observation(*entry)[1])
            except (TypeError, ValueError):
                missing.append(slot.isoformat())
                continue
            manifest.append(
                {
                    "run_id": entry[0].pk,
                    "request_id": str(receipt.request_id),
                    "archive_sha256": receipt.archive_sha256,
                }
            )
        else:
            missing.append(slot.isoformat())
    return freeze, manifest, missing


def _selected_developments(cutoff):
    # Snapshot the already-selected story metadata as it stood at freeze. A later
    # headline revision or pointer change cannot rewrite a past model request.
    rows = (
        OriginalContent.objects.filter(
            run__workflow_key="chatter-discovery",
            consideration_state="selected",
            decision_call__completed_at__lte=cutoff,
            decision_call__completed_at__gt=cutoff - HORIZON,
            development_id__isnull=False,
        )
        .order_by("-decision_call__completed_at", "-pk")
        .values("pk", "development_id", "decision_call__completed_at", "selection")[
            :200
        ]
    )
    developments = {}
    for row in rows:
        pitch = row["selection"] or {}
        title = pitch.get("subject")
        if not title or row["development_id"] in developments:
            continue
        developments[row["development_id"]] = {
            "consideration_id": row["pk"],
            "development_id": str(row["development_id"]),
            "episode_id": pitch.get("episode_id")
            or "development:" + str(row["development_id"]),
            "title": title,
            "selected_at": row["decision_call__completed_at"].isoformat(),
            "wordings": [
                wording(h)
                for h in pitch.get("original_headlines", [])
                if isinstance(h, str)
            ],
        }
    return list(developments.values())


def _compact(result):
    # The provider owns the complete ranking and the collection ledger owns
    # the raw feed. Keep only future queue state, admissions, and expiry IDs.
    return {
        "history": result["history"],
        "expired": result["expired"],
        "admissions": [
            {k: e[k] for k in ("episode_id", "rank", "rank_call_id", "headline_ids")}
            for e in result["leads"]
        ],
    }


def _packet(run, state):
    observations = []
    for pointer in state.manifest:
        capture = OriginalContentRun.objects.get(
            pk=pointer.run_id, scope_key=CAPTURE_SCOPE
        )
        capture_state = checkpoint(capture)
        receipt = capture_state.observation
        if (
            not receipt
            or receipt.request_id != pointer.request_id
            or receipt.archive_sha256 != pointer.archive_sha256
            or receipt.http_status != 200
            or receipt.observed_at > state.freeze_at
        ):
            raise ValueError("window_observation_changed")
        _, document = _saved_observation(capture, capture_state)
        observations.append(
            {
                "request_id": str(receipt.request_id),
                "slot": capture.interval.isoformat(),
                "observed_at": receipt.observed_at.isoformat(),
                "headlines": _headlines(document),
            }
        )
    history = {}
    if state.previous_id:
        prior = OriginalContentRun.objects.get(
            pk=state.previous_id, scope_key=DECISION_SCOPE, interval__lt=run.interval
        )
        prior_state = checkpoint(prior)
        saved = prior.outcome["window_result"]
        if not prior_state.committed_at or not (
            digest(saved) == prior_state.ranking_sha256 == state.previous_sha256
        ):
            raise ValueError("previous_decision_changed")
        history = saved["history"]
    admitted = {e["episode_id"]: e for e in history.get("admitted", [])}
    for selected in state.selected_developments:
        admitted.setdefault(
            selected.episode_id,
            {
                "episode_id": selected.episode_id,
                "title": selected.title,
                "last_seen": selected.selected_at.isoformat(),
                "wordings": selected.wordings,
            },
        )
    history = {**history, "admitted": list(admitted.values())}
    packet = decision_packet(observations, run.interval, history)
    if packet["missing_slots"] != [slot.isoformat() for slot in state.missing_slots]:
        raise ValueError("window_manifest_changed")
    return packet


def _result(packet, reply, call_id):
    result = apply_selection(packet, reply)
    # A drained item keeps the call that actually ranked it, including across windows.
    for episode in [*result["leads"], *result["history"]["pending"]]:
        if "rank_call_id" not in episode:
            if not call_id:
                raise ValueError("missing_originating_rank_call")
            episode["rank_call_id"] = call_id
    return result


def _reply(run, packet, cfg, *, send, transport=None):
    if not packet["needs_ranking"]:
        return None, None
    request = selection_request(packet)
    expected = request_payload(cfg.chatter.ranking, request)
    _, fingerprint = request_fingerprint(expected)
    call = OriginalContentCall.objects.filter(run=run, stage=WINDOW_RANK_STAGE).first()
    if not call and send:
        json_call(
            run,
            WINDOW_RANK_STAGE,
            cfg.chatter.ranking,
            request,
            cfg,
            transport=transport,
            reservation=call_once,
        )
        call = OriginalContentCall.objects.get(run=run, stage=WINDOW_RANK_STAGE)
    if not call or (
        call.state != "completed"
        or call.request_hash != fingerprint
        or call.request_packet != expected
        or call.response_hash != digest(call.response_payload)
        or call.response_payload.get("diagnostics", {}).get("request_sha256")
        != fingerprint
    ):
        raise ValueError("ranking_send_requires_reconciliation")
    return call.response_payload["data"], call.pk


def read_window_batch(run, state):
    if not state.committed_at:
        raise ValueError("decision_not_committed")
    packet = _packet(run, state)
    cfg = EditorialConfig.model_validate(run.config_snapshot["editorial"])
    reply, call_id = _reply(run, packet, cfg, send=False)
    result = _result(packet, reply, call_id)
    if call_id != state.rank_call_id or not (
        digest(_compact(result))
        == state.ranking_sha256
        == digest(run.outcome["window_result"])
    ):
        raise ValueError("committed_decision_changed")
    leads = result["leads"]
    return {
        "schema_version": 2,
        "run_id": run.pk,
        "batch_sha256": state.ranking_sha256,
        "rank_call_id": call_id or (leads[0]["rank_call_id"] if leads else None),
        "observed_at": state.committed_at.isoformat(),
        "cutoff": run.interval.isoformat(),
        "headlines": packet["headlines"],
        "ranked_stories": result["ranked_stories"],
        "leads": leads,
    }


def decide_window(run_id, *, transport=None, resume=False):
    """Serialize reservations and freeze ancestry before making a paid call outside the lock."""
    if not shared_storage():
        raise ValueError("Chatter workflow requires shared content storage")
    with transaction.atomic():
        advisory_lock(DECISION_SCOPE)
        run = OriginalContentRun.objects.select_for_update().get(
            pk=run_id, scope_key=DECISION_SCOPE
        )
        state = checkpoint(run)
        if run.workflow_version != workflow_version(state.lane):
            raise ValueError("window_prompt_changed")
        if state.committed_at:
            read_window_batch(run, state)
            return {"status": state.phase, "run_id": run.pk}
        now = timezone.now()
        can_resume = (
            resume
            and state.phase == "held"
            and state.freeze_at
            and OriginalContentCall.objects.filter(
                run=run, stage=WINDOW_RANK_STAGE, state="completed"
            ).exists()
        )
        if (state.phase == "held" and not can_resume) or (
            run.claim_owner and run.lease_until and run.lease_until > now
        ):
            return {
                "status": "held" if state.phase == "held" else "already_dispatched",
                "run_id": run.pk,
            }
        decisions = OriginalContentRun.objects.filter(scope_key=DECISION_SCOPE)
        if (
            decisions.filter(
                interval__gt=run.interval, outcome__trends__freeze_at__isnull=False
            )
            .exclude(outcome__trends__freeze_at=None)
            .exists()
        ):
            run.fence += 1
            run.lease_until = now + timedelta(minutes=10)
            run.execution_state = "running"
            run.save(update_fields=["fence", "lease_until", "execution_state"])
            _save(run, state, phase="held", error_code="newer_window_frozen")
            return {"status": "held", "run_id": run.pk}
        if decisions.filter(
            interval__lt=run.interval, outcome__trends__phase__in=["ranking", "queued"]
        ).exists():
            return {"status": "waiting_previous", "run_id": run.pk}
        frozen = None if state.freeze_at else _manifest(run, now)
        if not state.freeze_at and frozen is None:
            return {"status": "waiting_capture", "run_id": run.pk}
        run.fence += 1
        run.claim_owner = str(uuid4())
        run.lease_until = now + timedelta(minutes=10)
        run.execution_state = "running"
        run.save(
            update_fields=["fence", "claim_owner", "lease_until", "execution_state"]
        )
        if can_resume:
            state = _save(run, state, phase="ranking", error_code="")
        if frozen:
            freeze, manifest, missing = frozen
            previous = (
                decisions.filter(
                    interval__lt=run.interval,
                    outcome__trends__committed_at__isnull=False,
                )
                .exclude(outcome__trends__committed_at=None)
                .order_by("-interval")
                .first()
            )
            state = _save(
                run,
                state,
                phase="ranking",
                freeze_at=freeze.isoformat(),
                manifest=manifest,
                missing_slots=missing,
                selected_developments=_selected_developments(freeze),
                previous_id=previous.pk if previous else None,
                previous_sha256=checkpoint(previous).ranking_sha256
                if previous
                else None,
            )
    try:
        packet = _packet(run, state)
        cfg = EditorialConfig.model_validate(run.config_snapshot["editorial"])
        reply, call_id = _reply(
            run, packet, cfg, send=not can_resume, transport=transport
        )
        result = _result(packet, reply, call_id)
        with transaction.atomic():
            advisory_lock(DECISION_SCOPE)
            current = locked_run(run.pk, run.fence)
            current.outcome = {**current.outcome, "window_result": _compact(result)}
            current.save(update_fields=["outcome", "updated_at"])
            phase = "ranked" if result["leads"] else "empty"
            _save(
                run,
                state,
                phase=phase,
                ranking_sha256=digest(_compact(result)),
                rank_call_id=call_id,
                committed_at=timezone.now().isoformat(),
            )
        return {"status": phase, "run_id": run.pk}
    except Exception as exc:  # noqa: BLE001 - persist failure at the queued boundary
        from .chatter_chain import _failure

        _save(run, state, phase="held", error_code="window_decision_failed")
        return _failure(run, "decision", exc)
    finally:
        OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
            claim_owner=""
        )
