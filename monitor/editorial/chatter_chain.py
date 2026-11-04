"""Persisted Chatter stages shared by the queue, CLI and deterministic transports."""

import json
import re
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.models import (
    EditorialStory,
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentSelection,
    OriginalContentText,
)
from monitor.original_content import (
    WORKFLOWS,
    digest,
    featured_scope,
    publish_content,
    shared_storage,
)
from x_monitor.twitterapi_credentials import TwitterApiCredentialPurpose

from .chatter_accounting import call_once
from .chatter_discovery import (
    keep_fingerprint,
    prompts,
    semantic_request,
    validate_selection,
    validate_semantic,
)
from .chatter_history import (
    SCOPE,
    WORKFLOW,
    attach_sources,
    competition_board,
    locked_run,
    reference_sources,
    resolved_sources,
    save_query,
    validated_packet,
)
from .chatter_inputs import (
    _expanded_history,
    _selection_packet,
    _selection_request,
    reconstruct_selection_request,  # noqa: F401 - existing reconstruction entry point
    reconstruct_writer_request,  # noqa: F401 - existing reconstruction entry point
    writer_input,
)
from .chatter_sources import SourceSession
from .config import EditorialConfig, load_editorial_config
from .contracts import ProviderReplyError, interval_start
from .providers import json_call
from .voices import load_bound_voices
from .writing import validate_copy


def enqueue(stage, *args):
    from .dispatch import dispatch_chatter_stage

    dispatch_chatter_stage(stage, *args)


def _saved_config(run, cfg):
    current = cfg or load_editorial_config()
    if not current.chatter.enabled:
        return None
    saved = EditorialConfig.model_validate(run.config_snapshot["editorial"])
    if run.workflow_version != digest(prompts()):
        raise ValueError("Chatter prompt version changed during this run")
    return saved


def _update(run, **changes):
    with transaction.atomic():
        current = locked_run(run.pk, run.fence)
        current.outcome = {**current.outcome, **changes}
        current.save(update_fields=["outcome", "updated_at"])
        run.outcome = current.outcome


def _failure(run, stage, exc):
    code = getattr(exc, "code", type(exc).__name__)
    if not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9_:-]{1,64}", code):
        code = "stage_failure"
    try:
        _update(run, failed_stage=stage, error_code=code, phase="held")
        if stage == "discovery":
            OriginalContentRun.objects.filter(pk=run.pk, fence=run.fence).update(
                discovery_state="failed"
            )
    except ValueError:
        return {"status": "stale", "stage": stage, "run_id": run.pk}
    return {"status": "held", "stage": stage, "error_code": code, "run_id": run.pk}


def _incumbents():
    selected = {}
    for pointer in OriginalContentSelection.objects.filter(
        scope_key__startswith="featured:social-brief:",
        text__narrative__development__isnull=False,
    ).select_related("text__narrative__development"):
        parent = pointer.text.narrative
        if parent.source_locale_id is None or parent.editorial_group is None:
            continue
        pool = f"{parent.source_locale_id.casefold()}-{parent.editorial_group}"
        prior = selected.get(pool)
        if prior is None or pointer.text.locale == "en":
            selected[pool] = parent
    return selected


def _history(cutoff):
    rows = competition_board(cutoff)
    incumbents = _incumbents()
    by_development = {str(row.development_id): row for row in rows}
    by_development.update({str(row.development_id): row for row in incumbents.values()})
    recent = list(
        OriginalContentRun.objects.filter(
            workflow_key=WORKFLOW,
            scope_key=SCOPE,
            discovery_state="complete",
            facts_as_of__lt=cutoff,
        )
        .only("pk", "facts_as_of")
        .order_by("-facts_as_of")[:8]
    )
    searches = []
    for call in OriginalContentCall.objects.filter(
        run__in=recent, stage="discovery", state="completed"
    ).only("response_payload", "run_id"):
        reply = call.response_payload or {}
        searches.append(
            {
                "run_id": call.run_id,
                "tool_activity": reply.get("search_activity", []),
                "stories": [
                    {"subject": item.get("subject"), "story_ref": item.get("story_ref")}
                    for item in reply.get("data", {}).get("stories", [])
                ],
                "keyword_query": reply.get("data", {}).get("keyword_query"),
                "tool_results": "unavailable unless explicitly captured",
            }
        )
    context = [
        {
            "development_id": identity,
            "subject": row.selection.get("subject", "Saved development"),
            "last_considered_at": row.attempted_at.isoformat(),
            "last_reason": row.consideration_reason,
            "pool": f"{row.source_locale_id}-{row.editorial_group}"
            if row.source_locale_id
            else None,
        }
        for identity, row in by_development.items()
    ]
    return (
        by_development,
        incumbents,
        {
            "subjects": context,
            "recent_searches": searches,
            "board_may_be_capped": len(rows) == 200,
        },
    )


def _borrow(run, previous):
    if previous.consideration_state is None:
        return []  # A legacy public copy is memory, never a fabricated frozen packet.
    return reference_sources(run, previous, fence=run.fence)


@transaction.atomic
def _consider(run, story, pitch, source_ids, kind, call, position=None):
    story = EditorialStory.objects.select_for_update().get(pk=story.pk)
    revision = (
        OriginalContent.objects.filter(story_id=story.pk).aggregate(n=Max("revision"))[
            "n"
        ]
        or 0
    ) + 1
    now = timezone.now()
    row, created = OriginalContent.objects.get_or_create(
        run=run,
        development=story,
        defaults={
            "workflow_key": WORKFLOWS["chatter"],
            "output_key": str(story.pk),
            "subject_key": story.development_key,
            "story_id": story.pk,
            "brand_key_snapshot": "",
            "status": "prepared",
            "attempted_at": now,
            "revision": revision,
            "consideration_state": "pending",
            "appearance_kind": kind,
            "discovery_call": call if kind == "semantic_shortlist" else None,
            "shortlist_position": position,
            "selection": pitch,
        },
    )
    if not created and kind == "semantic_shortlist" and row.appearance_kind != kind:
        row.appearance_kind, row.discovery_call, row.shortlist_position = (
            kind,
            call,
            position,
        )
        row.selection = pitch
        row.save(
            update_fields=[
                "appearance_kind",
                "discovery_call",
                "shortlist_position",
                "selection",
            ]
        )
    packet = {
        "sources": resolved_sources(OriginalContentRun.objects.get(pk=run.pk).snapshot)
    }
    ids = list(
        dict.fromkeys(
            identity for identity in source_ids if identity in packet["sources"]
        )
    )
    if ids:
        attach_sources(row, ids, fence=run.fence)
    return row


def run_chatter(envelope, *, cfg=None, transport=None, x_client=None, enqueue=enqueue):
    configured = cfg is not None
    cfg = cfg or load_editorial_config()
    if not cfg.chatter.enabled:
        return {"status": "disabled"}
    if not shared_storage():
        raise ValueError("Chatter workflow requires shared content storage")
    if envelope.get("schema_version") != 1 or envelope.get("dry_run") is not False:
        return {"status": "ineligible"}
    cutoff = datetime.fromisoformat(envelope["cutoff"])
    started = datetime.fromisoformat(envelope["cycle_started_at"])
    now = timezone.now()
    if (
        cutoff.tzinfo is None
        or started.tzinfo is None
        or cutoff > now + timedelta(minutes=1)
        or cutoff < now - timedelta(days=8)
    ):
        raise ValueError("invalid Chatter cutoff")
    voices = load_bound_voices(cfg)
    with transaction.atomic():
        run, created = OriginalContentRun.objects.get_or_create(
            scope_key=SCOPE,
            interval=interval_start(started),
            defaults={
                "source_cycle_id": str(envelope["source_cycle_id"]),
                "workflow_key": WORKFLOW,
                "workflow_version": digest(prompts()),
                "facts_as_of": cutoff,
                "cycle_started_at": started,
                "packet_schema_version": 1,
                "snapshot": {"schema_version": 1, "sources": {}},
                "config_snapshot": {
                    "schema_version": 1,
                    "editorial": cfg.model_dump(mode="json"),
                    "voices": {
                        key: voice.model_dump(mode="json")
                        for key, voice in voices.items()
                    },
                },
                "execution_state": "running",
                "lease_until": now + timedelta(hours=2),
                "discovery_state": "pending",
                "outcome": {"phase": "discovering"},
            },
        )
    if not created:
        if run.outcome.get("phase") == "discovered":
            enqueue("select", run.pk)
        if run.outcome.get("phase") in {
            "discovered",
            "selected",
            "writing",
            "complete",
        }:
            return {"status": "already_discovered", "run_id": run.pk}
        return {"status": "already_dispatched", "run_id": run.pk}
    sources = None
    try:
        previous, incumbents, history = _history(cutoff)
        from .chatter_releases import admit_releases, prepare_releases

        releases = prepare_releases(cutoff)
        history["required_releases"] = [
            {
                "development_id": identity,
                "subject": row["subject"],
                "post_ids": [s["id"] for s in row["sources"]],
            }
            for identity, row in releases.items()
        ]
        purpose = TwitterApiCredentialPurpose(envelope["credential_purpose"])
        if cfg.chatter.trial and purpose != TwitterApiCredentialPurpose.ON_DEMAND:
            raise ValueError("explicit validation requires the on-demand purpose")
        sources = SourceSession(
            run,
            cfg,
            purpose=purpose,
            client=x_client,
            transport=transport,
            policy_reader=(lambda: cfg) if configured else load_editorial_config,
        )
        reply = json_call(
            run,
            "discovery",
            cfg.chatter.discovery,
            semantic_request(cutoff, history, cfg),
            cfg,
            transport=sources.transport,
            reservation=call_once,
        )
        result = validate_semantic(reply, set(previous) | set(releases))
        sources.tools(reply)
        ids = list(
            dict.fromkeys(
                identity for item in result["stories"] for identity in item["post_ids"]
            )
        )
        incumbent_ids = []
        for incumbent in incumbents.values():
            incumbent_ids.extend(
                identity
                for identity in incumbent.consideration_sources.values_list(
                    "post_id", flat=True
                )
                if identity
            )
        ids = list(dict.fromkeys(incumbent_ids + ids))
        keyword_ids = []
        previous_cutoff = (
            OriginalContentRun.objects.filter(
                workflow_key=WORKFLOW,
                scope_key=SCOPE,
                discovery_state="complete",
                facts_as_of__lt=cutoff,
            )
            .order_by("-facts_as_of")
            .values_list("facts_as_of", flat=True)
            .first()
        )
        keyword_start = max(
            previous_cutoff or cutoff - timedelta(minutes=15),
            cutoff - timedelta(hours=24),
        )
        keyword_coverage = {
            "start": keyword_start.isoformat(),
            "end_exclusive": cutoff.isoformat(),
            "more_available": False,
        }
        query = result["keyword_query"]
        if query:
            pages = list(
                sources.client.run_search_pages(
                    query,
                    max_results=20,
                    max_pages=1,
                    max_per_page=20,
                    since_time=int(keyword_start.timestamp()),
                    until_time=int(cutoff.timestamp()),
                )
            )
            for page in pages:
                sources.ingest(page.items)
                keyword_ids.extend(item["id"] for item in page.items)
                keyword_coverage["more_available"] |= (
                    page.has_more or page.clipped or page.continuation_invalid
                )
        packet = validated_packet(OriginalContentRun.objects.get(pk=run.pk).snapshot)[
            "sources"
        ]
        missing = [identity for identity in ids if identity not in packet]
        if missing:
            fetched = sources.client.get_posts_by_ids(
                missing[: cfg.chatter.source_post_limit]
            )
            sources.ingest(list(fetched.values()))
        sources.close(success=True)
        sources = None
        producing = run.provider_calls.get(stage="discovery")
        # Preserve the board without counting carried memory as a fresh appearance.
        for identity, previous_row in previous.items():
            with transaction.atomic():
                old_ids = _borrow(run, previous_row)
                _consider(
                    run,
                    previous_row.development,
                    previous_row.selection,
                    old_ids,
                    "memory_only",
                    producing,
                )
        assigned = set()
        assigned_stories = set()
        for position, item in enumerate(result["stories"], 1):
            prior = item["prior_development_id"]
            story = (
                (
                    previous[prior].development
                    if prior in previous
                    else releases[prior]["story"]
                )
                if prior
                else None
            )
            if story is None:
                from .service import find_story

                key = "chatter:" + digest(sorted(item["post_ids"]))
                story = find_story(
                    SimpleNamespace(story_id=None, key=key, post_ids=item["post_ids"])
                )
            if story is None:
                story, _ = EditorialStory.objects.get_or_create(
                    development_key=key,
                    defaults={"anchor_ids": item["post_ids"]},
                )
            if story.pk in assigned_stories:
                raise ProviderReplyError("ambiguous_development_identity", {})
            assigned_stories.add(story.pk)
            _consider(
                run,
                story,
                {
                    "schema_version": 1,
                    "subject": item["subject"],
                    "angle": item["angle"],
                    "story_ref": item["story_ref"],
                },
                item["post_ids"],
                "semantic_shortlist",
                producing,
                position,
            )
            save_query(item["keyword_query"], development=story)
            assigned.update(item["post_ids"])
        for identity in dict.fromkeys(keyword_ids):
            if identity in assigned:
                continue
            story, _ = EditorialStory.objects.get_or_create(
                development_key="chatter-source:" + digest(identity),
                defaults={"anchor_ids": [identity]},
            )
            _consider(
                run,
                story,
                {
                    "schema_version": 1,
                    "subject": "Additional keyword source",
                    "angle": "Evaluate the supplied original post.",
                    "story_ref": None,
                },
                [identity],
                "keyword_only",
                producing,
            )
        admit_releases(run, producing, _consider, releases)
        _update(
            run,
            phase="discovered",
            keyword_coverage=keyword_coverage,
            discovery_rejections=result["rejections"],
            history_coverage={
                "board_may_be_capped": history["board_may_be_capped"],
                "history_requests": result["history_requests"],
            },
            tool_detail_visibility=result["tool_detail_visibility"],
            lookup_omitted=max(0, len(missing) - cfg.chatter.source_post_limit),
            incumbent_refs={
                pool: str(row.development_id) for pool, row in incumbents.items()
            },
        )
        with transaction.atomic():
            current = locked_run(run.pk, run.fence)
            current.discovery_state = "complete"
            current.save(update_fields=["discovery_state"])
        enqueue("select", run.pk)
        return {"status": "discovered", "run_id": run.pk}
    except Exception as exc:  # noqa: BLE001 - queued boundary records a bounded hold; never retries a paid call
        if sources is not None:
            sources.close(success=False)
        return _failure(run, "discovery", exc)


def select_chatter(run_id, *, cfg=None, transport=None, enqueue=enqueue):
    run = OriginalContentRun.objects.get(pk=run_id)
    cfg = _saved_config(run, cfg)
    if cfg is None:
        return {"status": "disabled"}
    if run.discovery_state != "complete":
        return {
            "status": "held",
            "stage": "selection",
            "error_code": "discovery_not_complete",
            "run_id": run.pk,
        }
    if run.decisions:
        _queue_writers(run, cfg, enqueue)
        return {"status": "already_selected"}
    try:
        payload = _selection_packet(run, cfg)
        built, payload = _selection_request(run, "selector:0", payload, cfg)
        fingerprint = keep_fingerprint(payload)
        prior = (
            OriginalContentRun.objects.filter(
                workflow_key=WORKFLOW,
                scope_key=SCOPE,
                discovery_state="complete",
                facts_as_of__lt=run.facts_as_of,
            )
            .order_by("-facts_as_of")
            .first()
        )
        reuse = bool(
            fingerprint
            and prior
            and prior.outcome.get("comparison_fingerprint") == fingerprint
            and prior.decisions
            and prior.outcome.get("decision_call_id")
        )
        result = deepcopy(prior.decisions) if reuse else None
        if reuse:
            for group in result["group_decisions"]:
                if (
                    group["lead_ref"] is None
                    and payload["incumbents"].get(group["scope_ref"]) is not None
                ):
                    reuse = False
                    break
                if group["lead_ref"] is not None:
                    if (
                        payload["incumbents"].get(group["scope_ref"])
                        != group["lead_ref"]
                    ):
                        reuse = False
                        break
                    group["lead_action"], group["incumbent_ref"] = (
                        "keep",
                        group["lead_ref"],
                    )
        if not reuse:
            result = json_call(
                run,
                "selector:0",
                cfg.chatter.selector,
                built,
                cfg,
                transport=transport,
                reservation=call_once,
            )["data"]
        result = validate_selection(
            result,
            payload["candidates"],
            payload["incumbents"],
            payload["giant_group_policy"]["policy_ref"],
        )
        if result.get("history_requests"):
            payload["expanded_history"] = _expanded_history(
                result["history_requests"], run
            )
            payload["history_expansion_complete"] = True
            built, payload = _selection_request(run, "selector:1", payload, cfg)
            result = json_call(
                run,
                "selector:1",
                cfg.chatter.selector,
                built,
                cfg,
                transport=transport,
                reservation=call_once,
            )["data"]
            result = validate_selection(
                result,
                payload["candidates"],
                payload["incumbents"],
                payload["giant_group_policy"]["policy_ref"],
            )
            if result.get("history_requests"):
                raise ValueError("selector history expansion limit exceeded")
        decision_call = (
            OriginalContentCall.objects.get(pk=prior.outcome["decision_call_id"])
            if reuse
            else run.provider_calls.filter(
                stage__startswith="selector:", state="completed"
            )
            .order_by("-pk")
            .first()
        )
        tags = {row["candidate_ref"]: row for row in result["candidate_tags"]}
        ranked = {
            entry["candidate_ref"]: entry
            for group in result["group_decisions"]
            for entry in group["ranked_candidates"]
        }
        leads = {
            group["lead_ref"]: group
            for group in result["group_decisions"]
            if group["lead_ref"] is not None
        }
        selected = []
        with transaction.atomic():
            current = locked_run(run.pk, run.fence)
            for row in OriginalContent.objects.select_for_update().filter(run=run):
                ref = str(row.development_id)
                tag, rank = tags[ref], ranked.get(ref)
                row.source_locale_id = {"en": "en", "ja": "ja", "zh-cn": "zh-CN"}.get(
                    tag["dominant_source_language"]
                )
                row.editorial_group = (
                    tag["editorial_group"]
                    if tag["editorial_group"] in {"giant", "rest"}
                    else None
                )
                row.consideration_state = (
                    "ineligible" if rank is None else rank["outcome"]
                )
                row.consideration_reason = (
                    rank["reason"]
                    if rank
                    else tag["language_reason"] + " " + tag["group_reason"]
                )
                if ref in leads and leads[ref]["lead_action"] == "keep":
                    row.consideration_state = "kept"
                    row.consideration_reason = leads[ref]["reason"]
                row.decision_call = decision_call
                row.save(
                    update_fields=[
                        "source_locale",
                        "editorial_group",
                        "consideration_state",
                        "consideration_reason",
                        "decision_call",
                    ]
                )
                if row.consideration_state == "selected":
                    selected.append(row)
            for group in result["group_decisions"]:
                if group["lead_action"] != "none":
                    continue
                language, editorial_group = group["scope_ref"].rsplit("-", 1)
                OriginalContent.objects.get_or_create(
                    run=run,
                    output_key="empty:" + group["scope_ref"],
                    workflow_key="social-brief",
                    defaults={
                        "brand_key_snapshot": "",
                        "status": "no_content",
                        "attempted_at": timezone.now(),
                        "source_locale_id": "zh-CN"
                        if language == "zh-cn"
                        else language,
                        "editorial_group": editorial_group,
                        "consideration_state": "no_story",
                        "consideration_reason": group["reason"],
                        "decision_call": decision_call,
                    },
                )
            current.decisions = result
            current.outcome = {
                **current.outcome,
                "phase": "selected",
                "selected": len(selected),
                "comparison_fingerprint": fingerprint,
                "decision_call_id": decision_call.pk,
                "decision_mode": "audited_code_keep" if reuse else "model",
            }
            if not selected and not any(
                not row["eligible"] for row in payload["candidates"]
            ):
                current.outcome["healthy_at"] = timezone.now().isoformat()
                current.outcome["phase"] = "complete"
            current.save(update_fields=["decisions", "outcome", "updated_at"])
        _queue_writers(run, cfg, enqueue)
        if not selected:
            _complete(run)
        return {"status": "selected", "selected": len(selected), "run_id": run.pk}
    except Exception as exc:  # noqa: BLE001 - queued boundary preserves the last selected story
        return _failure(run, "selection", exc)


def _queue_writers(run, cfg, enqueue):
    if run.execution_state != "running":
        return
    selected = list(
        OriginalContent.objects.filter(
            run=run, consideration_state="selected"
        ).order_by("pk")
    )
    selected.sort(
        key=lambda row: (
            row.source_locale_id != "en",
            row.editorial_group != "rest",
            row.pk,
        )
    )
    locales = [
        binding.split(":")[1]
        for binding in cfg.voices
        if binding.startswith("chatter:")
    ]
    locales.sort(key=lambda locale: locale != "en")
    planned = [f"{row.pk}:{locale}" for locale in locales for row in selected]
    _update(run, planned_writers=planned)
    for locale in locales:
        for row in selected:
            if not row.localized_texts.filter(locale=locale).exists():
                enqueue("write", row.pk, locale)
    if planned and set(planned) <= run.outcome.get("writers", {}).keys():
        enqueue("review", run.pk)


def _complete(run):
    with transaction.atomic():
        current = locked_run(run.pk, run.fence)
        current.execution_state = "completed"
        current.outcome = {**current.outcome, "phase": "complete"}
        current.save(update_fields=["execution_state", "outcome", "updated_at"])


def write_chatter(content_id, locale, *, cfg=None, transport=None, enqueue=enqueue):
    row = OriginalContent.objects.select_related("run").get(pk=content_id)
    run = row.run
    cfg = _saved_config(run, cfg)
    if cfg is None:
        return {"status": "disabled"}
    if row.localized_texts.filter(locale=locale).exists():
        if run.execution_state == "running" and run.lease_until > timezone.now():
            _record_ready(run, row.localized_texts.get(locale=locale))
            _writer_finished(run, f"{row.pk}:{locale}", "published", enqueue)
        return {"status": "already_published"}
    key = f"{row.pk}:{locale}"
    status = "failed"
    try:
        if row.consideration_state != "selected":
            raise ValueError("only selected developments can be written")
        built, subject, packet, voice = writer_input(row, locale, cfg)
        stage = f"writer:{row.pk}:{locale}"
        reply = json_call(
            run,
            stage,
            cfg.writer_route("chatter", locale),
            built,
            cfg,
            transport=transport,
            reservation=call_once,
        )
        copy = validate_copy(reply["data"], subject, locale, packet=packet)
        source_map = {source["id"]: source for source in packet["posts"]}
        (text,) = publish_content(
            row,
            [
                {
                    "locale": locale,
                    "headline": copy.headline,
                    "byline": copy.byline,
                    "body": copy.article,
                    "producing_call": run.provider_calls.get(stage=stage),
                    "sources": [source_map[identity] for identity in copy.post_ids],
                    "provenance": {
                        "voice": {
                            "id": voice.id,
                            "version": voice.version,
                            "hash": voice.digest,
                        },
                        "model": reply["model"],
                    },
                }
            ],
            fence=run.fence,
            selected_scope=featured_scope(
                "social-brief",
                locale,
                source_locale=row.source_locale_id,
                editorial_group=row.editorial_group,
            ),
        )
        _record_ready(run, text)
        status = "published"
        from .graphics_contract import make_request, no_art, receive_result

        try:
            graphics_request = make_request(text)
            receive_result(graphics_request, no_art(graphics_request))
        except ValueError:
            _update(run, graphics_error="graphics_boundary_failure")
        return {"status": status, "text_id": str(text.public_id), "run_id": run.pk}
    except Exception as exc:  # noqa: BLE001 - one locale cannot cancel a published sibling
        return _failure(run, "writer:" + key, exc)
    finally:
        if run.execution_state == "running" and run.lease_until > timezone.now():
            _writer_finished(run, key, status, enqueue)


def _writer_finished(run, key, status, enqueue):
    try:
        with transaction.atomic():
            current = locked_run(run.pk, run.fence)
            finished = {**current.outcome.get("writers", {}), key: status}
            current.outcome = {**current.outcome, "writers": finished}
            all_finished = (
                set(current.outcome.get("planned_writers", [])) <= finished.keys()
            )
            review = all_finished and not current.outcome.get("review_queued")
            if review:
                current.outcome["review_queued"] = True
            current.save(update_fields=["outcome", "updated_at"])
        if review:
            enqueue("review", run.pk)
    except ValueError:
        return  # A stale worker cannot mutate a newer fence or replace its outcome.


def _record_ready(run, text):
    from .readers import find_saved_edition

    edition = find_saved_edition(
        text.narrative.story_id, "chatter", locale=text.locale, pinned=text.public_id
    )
    if edition is None or edition.pk != text.public_id:
        raise ValueError("published text is unavailable from its saved reader")
    observed = timezone.now()
    elapsed = (text.created_at - run.cycle_started_at).total_seconds()
    reader_elapsed = (observed - run.cycle_started_at).total_seconds()
    with transaction.atomic():
        current = locked_run(run.pk, run.fence)
        outcome = dict(current.outcome)
        outcome.setdefault("healthy_at", observed.isoformat())
        outcome.setdefault("first_text_at", text.created_at.isoformat())
        outcome.setdefault(
            "first_text_seconds", round(elapsed, 3) if elapsed >= 0 else None
        )
        outcome.setdefault("first_reader_at", observed.isoformat())
        outcome.setdefault(
            "first_reader_seconds",
            round(reader_elapsed, 3) if reader_elapsed >= 0 else None,
        )
        outcome.setdefault(
            "first_text_target_missed", reader_elapsed > 300 or reader_elapsed < 0
        )
        current.outcome = outcome
        current.save(update_fields=["outcome", "updated_at"])


def review_chatter(run_id, *, cfg=None, transport=None):
    """One advisory batch after independent publication; a verdict never rewrites copy."""
    from .contracts import Copy
    from .grounding import strict_schema
    from .reviewing import Review, review_request, validate_review

    run = OriginalContentRun.objects.get(pk=run_id)
    cfg = _saved_config(run, cfg)
    if cfg is None:
        return {"status": "disabled"}
    if run.execution_state == "completed":
        return {"status": "already_reviewed"}
    texts = list(
        OriginalContentText.objects.filter(narrative__run=run)
        .select_related("narrative__run", "producing_call")
        .order_by("pk")
    )
    if not texts or cfg.reviewer is None:
        _complete(run)
        return {"status": "unavailable"}
    if len(texts) > 18:
        return _failure(run, "advisory", ValueError("advisory capacity exceeded"))
    try:
        entries, packets, inputs, identities = [], {}, {}, {}
        for text in texts:
            built, _, packet, voice = writer_input(text.narrative, text.locale, cfg)
            copy = Copy.model_validate(text.producing_call.response_payload["data"])
            request, identity = review_request(
                copy,
                packet,
                voice,
                text.producing_call.model,
                built,
                cfg,
                advisory=True,
            )
            packets[str(text.narrative_id)] = packet
            entries.append(
                {
                    "text_id": str(text.public_id),
                    "draft": copy.model_dump(mode="json"),
                    "evidence_ref": str(text.narrative_id),
                    "requested_voice": voice.instructions,
                    "review_identity": identity,
                }
            )
            inputs[str(text.public_id)] = (copy, packet)
            identities[str(text.public_id)] = identity
        schema = {
            "type": "object",
            "properties": {
                "reviews": {
                    "type": "array",
                    "maxItems": 18,
                    "items": {
                        "type": "object",
                        "properties": {
                            "text_id": {"type": "string"},
                            "review": Review.model_json_schema(),
                        },
                        "required": ["text_id", "review"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["reviews"],
            "additionalProperties": False,
        }
        # Keep Review's local references at the root of the complete batch schema.
        review_schema = schema["properties"]["reviews"]["items"]["properties"]["review"]
        schema["$defs"] = review_schema.pop("$defs", {})
        request = {
            **request,
            "system": request["system"]
            + "\nReview every supplied text once. Return {reviews:[{text_id,review}]} using each evidence_ref. Your findings are advisory after publication.",
            "user": json.dumps(
                {
                    "reviews": entries,
                    "evidence": packets,
                    "output_schema": strict_schema(schema),
                },
                ensure_ascii=False,
            ),
            "response_schema": strict_schema(schema),
            "images": [],
            "input_reference": {"run_id": run.pk, "builder": "chatter-review-v1"},
        }
        response = json_call(
            run,
            "advisory",
            cfg.reviewer,
            request,
            cfg,
            transport=transport,
            reservation=call_once,
        )
        from jsonschema import Draft202012Validator

        result = response["data"]
        if list(Draft202012Validator(schema).iter_errors(result)):
            raise ValueError("invalid advisory batch")
        reviews = result["reviews"]
        if len(reviews) != len(inputs) or {r["text_id"] for r in reviews} != set(
            inputs
        ):
            raise ValueError("advisory batch identities mismatch")
        validated = {
            r["text_id"]: {
                **identities[r["text_id"]],
                "result": validate_review(
                    r["review"], *inputs[r["text_id"]]
                ).model_dump(mode="json"),
            }
            for r in reviews
        }
        _update(run, senior_reviews=validated)
        status = "reviewed"
    except Exception as exc:  # noqa: BLE001 - advisory failure cannot veto published text
        _update(run, advisory_error=getattr(exc, "code", type(exc).__name__))
        status = "advisory_failed"
    _complete(run)
    return {"status": status, "run_id": run.pk}
