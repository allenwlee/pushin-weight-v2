"""Resumable import of saved editorial history into existing headline tables."""

from collections import defaultdict
from datetime import UTC
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from django.db import transaction

from core.models import (
    ContentPicture,
    EditorialAssessment,
    EditorialBudget,
    EditorialCall,
    EditorialHero,
    EditorialStory,
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentSelection,
    OriginalContentSource,
    OriginalContentText,
    Post,
)
from monitor.editorial.contracts import digest as editorial_digest
from monitor.original_content import (
    WORKFLOWS,
    advisory_lock,
    citation_values,
    digest,
    publish_content,
)


def workflow_for_stage(stage, kind):
    if kind == "media":
        return "media-derivative"
    for track, key in WORKFLOWS.items():
        if stage.startswith(f"writer:{track}:"):
            return key
    return "editorial-dispatch"


def import_assessment(row):
    """Called inside the owner's short transaction for overlap-safe mirroring."""
    row = EditorialAssessment.objects.select_for_update().get(pk=row.pk)
    outcome = dict(row.outcome)
    receipt = "external_reserved_usd" in outcome
    day = row.interval.astimezone(UTC).date()
    workflow = "reservation-carryforward" if receipt else "editorial-dispatch"
    if receipt:
        if outcome.get("provider_send") is not False or not outcome.get("sources"):
            raise ValueError("external spend lacks zero-send provenance")
        if (
            Decimal(str(outcome["external_reserved_usd"])) < 0
            or int(outcome["external_calls"]) < 0
        ):
            raise ValueError("invalid external spend")
        outcome["external_reserved_usd"] = str(outcome["external_reserved_usd"])
        outcome.update(budget_scope="editorial", budget_day=day.isoformat())
    outcome["legacy_assessment_id"] = row.pk
    run, created = OriginalContentRun.objects.get_or_create(
        source_cycle_id=f"legacy-editorial:{row.pk}",
        scope_key=f"budget:editorial:{day}" if receipt else row.scope,
        workflow_key=workflow,
        defaults={
            "window_days": None,
            "facts_as_of": row.cutoff,
            "packet_schema_version": 1,
            "snapshot": row.packet,
            "interval": None if receipt else row.interval,
            "decisions": row.decisions,
            "outcome": outcome,
            "execution_state": row.state,
            "fence": row.fence,
            "lease_until": row.lease_until,
            "workflow_version": "legacy-editorial-v1",
        },
    )
    if not created:
        if receipt and run.outcome != outcome:
            raise ValueError("immutable external receipt changed")
        if not receipt:
            OriginalContentRun.objects.filter(pk=run.pk).update(
                snapshot=row.packet,
                decisions=row.decisions,
                outcome=outcome,
                execution_state=row.state,
                fence=row.fence,
                lease_until=row.lease_until,
            )
            run.refresh_from_db()
    else:
        OriginalContentRun.objects.filter(pk=run.pk).update(created_at=row.created_at)
    return run


def import_call(call, run=None, *, request_metadata=None, finished_at=None):
    run = run or import_assessment(call.assessment)
    identity = f"legacy-editorial-call:{call.pk}"
    target = OriginalContentCall.objects.filter(request_identity=identity).first()
    failure = call.response.get("failure", {})
    metadata = request_metadata or {}
    usage = call.response.get("usage", {})
    known_hash = metadata.get("request_hash") or failure.get("request_sha256")
    values = {
        "run": run,
        "stage": call.stage,
        "batch_key": "",
        "request_identity": identity,
        "request_hash": known_hash,
        "response_payload": call.response,
        "response_hash": digest(call.response) if call.state == "complete" else "",
        "state": "completed" if call.state == "complete" else call.state,
        "reserved_at": call.created_at,
        "sent_at": call.created_at,
        "completed_at": None,
        "kind": call.kind,
        "workflow_key": workflow_for_stage(call.stage, call.kind),
        "workflow_version": metadata.get("workflow_version", "legacy-editorial-v1"),
        "model": metadata.get("model") or call.response.get("model", ""),
        "provider": metadata.get("provider", ""),
        "budget_scope": "editorial",
        "budget_day": call.budget_day,
        "reserved_usd": call.reserved_usd,
        "error_code": call.error_code[:64],
        "legacy_import": not bool(request_metadata),
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
        "request_packet": metadata.get("request_packet"),
        "provenance": {
            "legacy_call_id": call.pk,
            "completion_time": "unknown",
            "usage": usage,
            "rates": metadata.get("rates", {}),
        },
    }
    if target and not target.legacy_import:
        for key in (
            "request_hash",
            "request_packet",
            "workflow_version",
            "provider",
            "model",
            "legacy_import",
            "provenance",
        ):
            values[key] = getattr(target, key)
        values["completed_at"] = target.completed_at
    if not values["legacy_import"] and values["state"] == "completed":
        values["completed_at"] = finished_at or values["completed_at"]
        if values["completed_at"] is None:
            raise ValueError("fresh completed call lacks completion time")
    if target:
        if target.state == "completed" and values["state"] != "completed":
            raise ValueError("cannot downgrade completed call")
        OriginalContentCall.objects.filter(pk=target.pk).update(**values)
        target.refresh_from_db()
    else:
        target = OriginalContentCall.objects.create(**values)
        OriginalContentCall.objects.filter(pk=target.pk).update(
            created_at=call.created_at
        )
    return target


def writing_call(edition, run):
    """Only an exact saved stage key proves attribution; no closest-call guesses."""
    key = edition.selection.get("key")
    voice_hash = edition.voice.get("hash")
    if not key or not voice_hash:
        return None
    stage = (
        f"writer:{edition.track}:{edition.locale}:{editorial_digest([key, voice_hash])}"
    )
    return OriginalContentCall.objects.filter(
        run=run,
        stage=stage,
        state="completed",
        workflow_key=WORKFLOWS[edition.track],
    ).first()


def import_edition(edition, run=None, *, legacy=True, producer=None):
    run = run or import_assessment(edition.assessment)
    prior = (
        OriginalContentText.objects.filter(public_id=edition.pk)
        .select_related("narrative")
        .prefetch_related("sources")
        .first()
    )
    sources = edition.evidence.get("sources", [])
    values = citation_values(sources, legacy=legacy)
    if not values:
        raise ValueError("editorial output requires saved citations")
    if prior:
        if (prior.headline, prior.secondary, prior.body, prior.locale) != (
            edition.headline,
            edition.byline,
            edition.article,
            edition.locale,
        ):
            raise ValueError("conflicting immutable imported edition")
        if [(s.post_id, s.url_snapshot) for s in prior.sources.all()] != [
            (s["post_id"], s["url_snapshot"]) for s in values
        ]:
            raise ValueError("conflicting imported citations")
        return prior
    content = OriginalContent.objects.create(
        run=run,
        workflow_key=WORKFLOWS[edition.track],
        output_key=str(edition.pk),
        subject_key=edition.story.development_key,
        story_id=edition.story_id,
        revision=edition.revision,
        occurred_at=edition.occurred_at,
        published_at=edition.published_at,
        importance=edition.importance,
        fingerprint=edition.fingerprint,
        status="prepared",
        attempted_at=edition.assessment.cutoff,
        brand_key_snapshot="",
        brand_name_en_snapshot="",
        brand_name_zh_cn_snapshot="",
        selection=edition.selection,
        provenance={
            "legacy_edition_id": str(edition.pk),
            "evidence": edition.evidence,
            "anchor_ids": edition.story.anchor_ids,
            "model": edition.model,
        },
    )
    (text,) = publish_content(
        content,
        [
            {
                "locale": edition.locale,
                "headline": edition.headline,
                "byline": edition.byline,
                "body": edition.article,
                "public_id": edition.pk,
                "sources": sources,
                "producing_call": producer or writing_call(edition, run),
                "provenance": {
                    "voice": edition.voice,
                    "legacy_edition_id": str(edition.pk),
                    "producer_basis": "exact_stage"
                    if producer or writing_call(edition, run)
                    else "legacy_unknown",
                },
            }
        ],
        legacy=legacy,
    )
    OriginalContentText.objects.filter(pk=text.pk).update(
        created_at=edition.published_at
    )
    return text


def import_hero(hero):
    hero = EditorialHero.objects.select_for_update().get(pk=hero.pk)
    if hero.edition_id is None or hero.key == "provider-lock":
        return
    text = OriginalContentText.objects.select_related("narrative__run").get(
        public_id=hero.edition_id
    )
    scope = f"featured:{text.narrative.workflow_key}:{text.locale}"
    advisory_lock("selection:" + scope)
    current = OriginalContentSelection.objects.filter(scope_key=scope).first()
    if current and current.facts_as_of > text.narrative.run.facts_as_of:
        return
    OriginalContentSelection.objects.update_or_create(
        scope_key=scope,
        defaults={
            "text": text,
            "run": None,
            "window_days": None,
            "facts_as_of": text.narrative.run.facts_as_of,
            "activated_at": text.narrative.published_at,
        },
    )


def reconcile_budgets():
    totals = defaultdict(lambda: [Decimal(0), 0, 0])
    for call in EditorialCall.objects.all().iterator(chunk_size=500):
        day = call.budget_day
        totals[day][0] += call.reserved_usd
        totals[day][1] += 1
        totals[day][2] += int(call.kind == "media")
    for row in EditorialAssessment.objects.filter(
        outcome__has_key="external_reserved_usd"
    ):
        outcome = row.outcome
        day = row.interval.astimezone(UTC).date()
        if outcome.get("provider_send") is not False or not outcome.get("sources"):
            raise ValueError("external spend lacks zero-send provenance")
        totals[day][0] += Decimal(str(outcome["external_reserved_usd"]))
        totals[day][1] += int(outcome["external_calls"])
        totals[day][2] += int(outcome.get("external_media_calls", 0))
    discrepancies = []
    budgets = {row.day: row for row in EditorialBudget.objects.all()}
    for day in sorted(set(totals) | set(budgets)):
        row = budgets.get(day)
        actual = (
            [row.reserved_usd, row.calls, row.media_calls]
            if row
            else [Decimal(0), 0, 0]
        )
        if totals[day] != actual:
            discrepancies.append(
                {
                    "kind": "budget",
                    "id": day.isoformat(),
                    "expected": list(map(str, totals[day])),
                    "stored": list(map(str, actual)),
                }
            )
    return discrepancies


def headline_history(*, batch_size=200):
    """Stream one run's headlines without repeating its large context JSON.

    PostgreSQL materializes Django's holdable cursors outside a transaction.
    Joining each headline to its complete run snapshot can spill many GB to
    temporary disk. Defer that snapshot, load it only if citations need it,
    and share the same run object until its headlines have been processed.
    """
    runs = (
        OriginalContentRun.objects.filter(window_days__isnull=False)
        .only("id", "window_days", "facts_as_of")
        .order_by("pk")
    )
    for run in runs.iterator(chunk_size=batch_size):
        headlines = OriginalContent.objects.filter(run_id=run.pk).order_by("pk")
        for headline in headlines.iterator(chunk_size=batch_size):
            headline.run = run
            yield headline


def backfill_original_content(
    *, apply=False, batch_size=200, after_assessment=0, limit=None
):
    if (
        not 1 <= batch_size <= 2000
        or after_assessment < 0
        or (limit is not None and limit < 1)
    ):
        raise ValueError("invalid backfill bounds")
    report = {
        "apply": apply,
        "ready": False,
        "exceptions": [],
        "assessments": 0,
        "editions": 0,
        "calls": 0,
        "last_assessment": after_assessment,
    }
    report["exceptions"].extend(reconcile_budgets())
    for headline in headline_history(batch_size=batch_size):
        try:
            citation_values(headline_citations(headline), legacy=True)
            for text in headline.localized_texts.all():
                if text.locale in {"en", "zh-cn"}:
                    suffix = text.locale.replace("-", "_")
                    if (text.headline, text.secondary) != (
                        getattr(headline, f"headline_{suffix}"),
                        getattr(headline, f"secondary_{suffix}"),
                    ):
                        raise ValueError("conflicting saved headline locale")
        except ValueError as exc:
            report["exceptions"].append(
                {"kind": "headline", "id": str(headline.pk), "error": str(exc)}
            )
    query = EditorialAssessment.objects.filter(pk__gt=after_assessment).order_by("pk")
    if limit is not None:
        query = query[:limit]
    for assessment in query.iterator(chunk_size=batch_size):
        with transaction.atomic():
            if apply:
                advisory_lock("original-content-backfill")
                assessment = EditorialAssessment.objects.select_for_update().get(
                    pk=assessment.pk
                )
                run = import_assessment(assessment)
                for call in assessment.calls.order_by("pk"):
                    import_call(call, run)
                    report["calls"] += 1
            else:
                report["calls"] += assessment.calls.count()
            for edition in assessment.editions.select_related(
                "story", "assessment"
            ).order_by("published_at", "pk"):
                try:
                    with transaction.atomic():
                        if apply:
                            import_edition(edition, run)
                        else:
                            if not citation_values(
                                edition.evidence.get("sources", []), legacy=True
                            ):
                                raise ValueError(
                                    "editorial output requires saved citations"
                                )
                    report["editions"] += 1
                except ValueError as exc:
                    report["exceptions"].append(
                        {"kind": "edition", "id": str(edition.pk), "error": str(exc)}
                    )
            report["assessments"] += 1
            report["last_assessment"] = assessment.pk
    if apply:
        if not any(e["kind"] == "headline" for e in report["exceptions"]):
            import_headline_metadata()
        for hero in EditorialHero.objects.exclude(edition=None).select_related(
            "edition"
        ):
            try:
                with transaction.atomic():
                    advisory_lock("original-content-backfill")
                    import_hero(hero)
            except OriginalContentText.DoesNotExist:
                report["exceptions"].append(
                    {"kind": "hero", "id": hero.key, "error": "edition not imported"}
                )
        for picture in ContentPicture.objects.filter(
            assessment__isnull=False
        ).select_related("assessment"):
            run = OriginalContentRun.objects.filter(
                source_cycle_id=f"legacy-editorial:{picture.assessment_id}"
            ).first()
            text = (
                OriginalContentText.objects.filter(public_id=picture.content_id).first()
                if picture.content_kind in WORKFLOWS
                else None
            )
            if run:
                ContentPicture.objects.filter(pk=picture.pk).update(run=run, text=text)
        unpublished = list(
            EditorialStory.objects.filter(editions__isnull=True).values(
                "id", "development_key", "anchor_ids", "created_at"
            )
        )
        if unpublished:
            # Explicit zero-send audit, not a placeholder source/publication.
            first = unpublished[0]["created_at"]
            outcome = [
                {**s, "id": str(s["id"]), "created_at": s["created_at"].isoformat()}
                for s in unpublished
            ]
            OriginalContentRun.objects.update_or_create(
                source_cycle_id="legacy-unpublished-stories",
                scope_key="legacy-unpublished-stories",
                workflow_key="editorial-dispatch",
                defaults={
                    "facts_as_of": first,
                    "packet_schema_version": 1,
                    "snapshot": {},
                    "execution_state": "complete",
                    "outcome": {"unpublished_stories": outcome, "provider_send": False},
                },
            )
    report["ready"] = not report["exceptions"]
    return report


def headline_citations(row):
    """Resolve opaque evidence by stored binding or its original ID algorithm."""
    packet = row.selected_evidence_packet or []
    evidence = packet.get("evidence", []) if isinstance(packet, dict) else packet
    if not row.cited_evidence_ids:
        return []
    snapshots = {}
    for dossier in row.run.snapshot.get("dossiers", []) + row.run.snapshot.get(
        "candidates", []
    ):
        for item in dossier.get("evidence", []):
            snapshots[item["evidence_id"]] = (
                item,
                dossier.get("source_row_provenance", {}).get("candidate_id")
                or dossier.get("candidate_id"),
            )
    selected = {s["evidence_id"]: s for s in evidence}
    sources = []
    for alias in row.cited_evidence_ids:
        source = selected.get(alias)
        if source is None:
            raise ValueError(f"missing saved headline evidence: {row.pk}:{alias}")
        private, candidate = snapshots.get(alias, (source, None))
        key = private.get("post_id")
        if not key:
            if not candidate or not source.get("created_at"):
                raise ValueError(f"unresolved headline source: {row.pk}:{alias}")
            matches = []
            ids = Post.objects.filter(
                created_at=source["created_at"], fetched_at__lte=row.run.facts_as_of
            ).values_list("pk", flat=True)[:201]
            if len(ids) > 200:
                raise ValueError("legacy source lookup exceeded bound")
            for pk in ids:
                for occurrence in {
                    source.get("occurrence_source"),
                    "original_post",
                    "quoted_source",
                } - {None}:
                    identity = (
                        "e_"
                        + sha256(
                            "\x1f".join(
                                [candidate, str(pk), occurrence, source["excerpt"]]
                            ).encode()
                        ).hexdigest()[:24]
                    )
                    if identity == alias:
                        matches.append(pk)
            if len(set(matches)) != 1:
                raise ValueError(f"unresolved headline source: {row.pk}:{alias}")
            key = matches[0]
        sources.append(
            {
                **source,
                "post_id": str(key),
                "_writing_projection": source,
                "url": private.get("url") or f"https://x.com/i/status/{key}",
            }
        )
    return sources


def import_headline_metadata():
    """Preserve primary keys, parent-only bilingual copy and current window pointers."""
    for run in (
        OriginalContentRun.objects.filter(window_days__isnull=False)
        .only("id", "window_days")
        .iterator(chunk_size=200)
    ):
        OriginalContentRun.objects.filter(pk=run.pk).update(
            workflow_key="brand-window",
            scope_key=f"trend-window:{run.window_days}",
        )
    for historical in headline_history():
        with transaction.atomic():
            row = OriginalContent.objects.select_for_update().get(pk=historical.pk)
            row.run = historical.run
            OriginalContent.objects.filter(pk=row.pk).update(
                workflow_key="brand-window",
                output_key=row.brand_key_snapshot,
                subject_key=row.brand_key_snapshot,
            )
            for locale, suffix in (("en", "en"), ("zh-cn", "zh_cn")):
                headline, byline = (
                    getattr(row, f"headline_{suffix}"),
                    getattr(row, f"secondary_{suffix}"),
                )
                if not headline or not byline:
                    continue
                text, _ = OriginalContentText.objects.get_or_create(
                    narrative=row,
                    locale=locale,
                    defaults={"headline": headline, "secondary": byline},
                )
                if (text.headline, text.secondary) != (headline, byline):
                    raise ValueError(
                        f"conflicting saved headline locale: {row.pk}:{locale}"
                    )
            for text in row.localized_texts.all():
                if text.public_id is None:
                    OriginalContentText.objects.filter(pk=text.pk).update(
                        public_id=uuid5(
                            NAMESPACE_URL, f"pushinweight:headline-text:{text.pk}"
                        ),
                        provenance={"producer_basis": "legacy_unknown"},
                    )
                values = citation_values(headline_citations(row), legacy=True)
                if not text.sources.exists():
                    OriginalContentSource.objects.bulk_create(
                        [OriginalContentSource(text=text, **v) for v in values]
                    )
                elif [(s.post_id, s.url_snapshot) for s in text.sources.all()] != [
                    (v["post_id"], v["url_snapshot"]) for v in values
                ]:
                    raise ValueError(
                        f"conflicting saved headline citations: {row.pk}:{text.locale}"
                    )
    for pointer in OriginalContentSelection.objects.filter(window_days__isnull=False):
        OriginalContentSelection.objects.filter(pk=pointer.pk).update(
            scope_key=f"trend-window:{pointer.window_days}"
        )
