"""Durable rolling selection over the official receipts archived by capture runs."""

from datetime import timedelta
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.models import OriginalContent, OriginalContentCall, OriginalContentRun
from monitor.original_content import advisory_lock, digest, shared_storage

from .chatter_accounting import call_once
from .chatter_history import locked_run
from .chatter_trends import (
    CAPTURE_SCOPE,
    DECISION_SCOPE,
    ROLLING_LANE,
    WINDOW_RANK_STAGE,
    _headlines,
    _save,
    _saved_observation,
    checkpoint,
    envelope_for,
    runs_in_trial,
    supported_version,
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
from .persistence import CapacityHeld
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


def _admission_has_unresolved_work(run):
    from monitor.editorial.chatter_sources import source_resume_is_safe

    if not source_resume_is_safe(run):
        return True
    if OriginalContentCall.objects.filter(
        Q(run=run) | Q(run__workflow_key="graphics-package", run__snapshot__request__run_id=run.pk),
        state__in=(OriginalContentCall.State.RESERVED, OriginalContentCall.State.SENT,
                   OriginalContentCall.State.AMBIGUOUS),
    ).exists():
        return True
    return OriginalContentRun.objects.filter(
        workflow_key="graphics-package", snapshot__request__run_id=run.pk,
        execution_state__in=("preparing", "running"),
    ).exists()


def _reopen_unpublished_episodes(previous, cutoff):
    """Freeze failed or finished admissions that never reached publication."""
    if previous is None:
        return []
    admitted = previous.outcome["window_result"]["history"].get("admitted", [])
    identities = {entry["episode_id"] for entry in admitted}
    if not identities:
        return []
    published = set(
        OriginalContent.objects.filter(
            workflow_key="social-brief", published_at__lte=cutoff,
            selection__episode_id__in=identities,
        ).values_list("selection__episode_id", flat=True)
    )
    unpublished = identities - published
    if not unpublished:
        return []
    owner = {}
    runs = OriginalContentRun.objects.filter(
        scope_key=DECISION_SCOPE, interval__lte=previous.interval,
        interval__gt=cutoff - HORIZON,
    ).order_by("-interval").only(
        "outcome", "execution_state", "scope_key", "workflow_key", "interval",
        "facts_as_of", "cycle_started_at", "source_cycle_id", "snapshot",
    )
    for prior in runs:
        for admission in prior.outcome.get("window_result", {}).get("admissions", []):
            identity = admission.get("episode_id")
            if identity in unpublished:
                owner.setdefault(identity, prior)
    retry = []
    unresolved = {}
    for identity in unpublished:
        prior = owner.get(identity)
        if prior and (prior.outcome.get("phase") == "held"
                      or prior.execution_state in {"completed", "failed"}):
            if prior.pk not in unresolved:
                unresolved[prior.pk] = _admission_has_unresolved_work(prior)
            if not unresolved[prior.pk]:
                retry.append(identity)
    return sorted(retry)


def _admitted_after_reopening(history, selected_developments, reopen_episode_ids):
    reopened = set(reopen_episode_ids or [])
    admitted = {e["episode_id"]: e for e in history.get("admitted", []) if e["episode_id"] not in reopened}
    for selected in selected_developments:
        if selected.episode_id in reopened:
            continue
        admitted.setdefault(
            selected.episode_id,
            {
                "episode_id": selected.episode_id,
                "title": selected.title,
                "last_seen": selected.selected_at.isoformat(),
                "wordings": selected.wordings,
            },
        )
    return list(admitted.values())


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
    history = {**history, "admitted": _admitted_after_reopening(
        history, state.selected_developments, state.reopen_episode_ids
    )}
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
    request = selection_request(packet, person_hints=run.workflow_version == workflow_version(ROLLING_LANE))
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


def _finish_capacity_wait(run, state):
    _save(
        run,
        state,
        phase="held",
        error_code="ranking_capacity_expired",
        deferred_until=None,
    )
    OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
        discovery_state="failed"
    )
    return {
        "status": "held",
        "error_code": "ranking_capacity_expired",
        "run_id": run.pk,
    }


def _defer_capacity(run, state):
    from .dispatch import dispatch_chatter_stage

    with transaction.atomic():
        current = locked_run(run.pk, run.fence)
        if OriginalContentCall.objects.filter(
            run=current, stage=WINDOW_RANK_STAGE
        ).exists():
            _save(
                run,
                state,
                phase="held",
                error_code="ranking_send_requires_reconciliation",
            )
            return {
                "status": "held",
                "run_id": run.pk,
                "error_code": "ranking_send_requires_reconciliation",
            }
        now = timezone.now()
        deadline = run.interval + 2 * QUARTER
        if now >= deadline:
            return _finish_capacity_wait(run, state)
        due = min(now + timedelta(minutes=1), deadline)
        _save(
            run,
            state,
            phase="ranking",
            error_code="ranking_capacity_busy",
            deferred_until=due.isoformat(),
        )
        dispatch_chatter_stage(
            "discover", envelope_for(run), countdown=(due - now).total_seconds()
        )
        return {
            "status": "waiting_capacity",
            "run_id": run.pk,
            "retry_at": due.isoformat(),
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
        if not supported_version(run.workflow_version, state.lane):
            raise ValueError("window_prompt_changed")
        if state.committed_at:
            read_window_batch(run, state)
            return {"status": state.phase, "run_id": run.pk}
        now = timezone.now()
        if (
            state.error_code == "ranking_capacity_busy"
            and state.deferred_until
            and now < state.deferred_until
        ):
            return {
                "status": "waiting_capacity",
                "run_id": run.pk,
                "retry_at": state.deferred_until.isoformat(),
            }
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
        trial = run.config_snapshot["editorial"]["chatter"].get("trial") or {}
        if (
            runs_in_trial(decisions, trial.get("scope"))
            .filter(
                interval__lt=run.interval,
                outcome__trends__phase__in=["ranking", "queued"],
            )
            .exclude(
                Q(claim_owner="") | Q(lease_until__lte=now),
                outcome__trends__error_code="ranking_capacity_busy",
                interval__lte=now - 2 * QUARTER,
            )
            .exists()
        ):
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
        if (
            state.error_code == "ranking_capacity_busy"
            and now >= run.interval + 2 * QUARTER
            and not run.provider_calls.filter(stage=WINDOW_RANK_STAGE).exists()
        ):
            OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
                claim_owner=""
            )
            return _finish_capacity_wait(run, state)
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
                reopen_episode_ids=_reopen_unpublished_episodes(previous, freeze),
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
                error_code="",
                deferred_until=None,
            )
        return {"status": phase, "run_id": run.pk}
    except CapacityHeld:
        return _defer_capacity(run, state)
    except Exception as exc:  # noqa: BLE001 - persist failure at the queued boundary
        from .chatter_chain import _failure

        _save(run, state, phase="held", error_code="window_decision_failed")
        return _failure(run, "decision", exc)
    finally:
        OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
            claim_owner=""
        )
