"""Resolve Graphics' immutable link to the original Chatter consideration."""

from core.models import OriginalContent
from monitor.original_content import digest, publication_scope


def source_for_run(run):
    """Validate stored origin against source-owned evidence, never caller flags."""
    saved = run.snapshot.get('request', {})
    binding = saved.get('chatter')
    if binding is None:
        return None
    from .chatter_history import WORKFLOW
    from .graphics_entry import prepare_selected_story

    if run.workflow_key != 'graphics-package' or not isinstance(binding, dict):
        raise ValueError('invalid Graphics Chatter origin')
    source = OriginalContent.objects.select_related('run').filter(pk=saved.get('content_id')).first()
    if (source is None or source.run_id != saved.get('run_id')
            or source.run.workflow_key != WORKFLOW
            or source.consideration_state != 'selected'
            or prepare_selected_story(content_id=source.pk, run_id=source.run_id,
                locale=saved.get('locale'), per_story_usd=saved.get('per_story_usd'),
                daily_usd=saved.get('daily_usd')) != saved):
        raise ValueError('Graphics Chatter origin differs from saved source')
    output = OriginalContent.objects.filter(run=run, output_key='graphics-primary/v1').first()
    expected = {'schema_version': 'graphics-source/v1', 'source_run_id': source.run_id,
                'source_content_id': source.pk, 'source_revision': source.revision,
                'snapshot_hash': digest(saved)}
    if (output is None or output.selection != source.selection or not same_publication_story(output, source)
            or output.source_locale_id != source.source_locale_id
            or output.editorial_group != source.editorial_group
            or output.provenance != expected):
        raise ValueError('Graphics output differs from saved source pool')
    return source


def same_publication_story(output, source):
    if output.story_id == source.story_id and output.development_id == source.development_id:
        return True
    coverage = source.selection.get('event_coverage')
    if not coverage or output.story_id != output.development_id or not output.development.event_dossier_id:
        return False
    from core.product_release_pipeline import canonical_dossier

    from .chatter_coverage import admission_identity

    dossier = output.development.event_dossier
    keys = {coverage['identity'], admission_identity(source.selection, coverage)}
    if dossier.identity_key in keys or any(p['story_id'] == str(output.story_id) for p in coverage['prior']):
        return True
    from core.models import EditorialStory, EventDossier, OriginalContentText

    bound = set(EventDossier.objects.filter(identity_key__in=keys).values_list('pk', flat=True))
    if coverage['same_dossier']:
        bound.add(coverage['same_dossier'])
    historic = [p['story_id'] for p in coverage['prior']]
    bound.update(EditorialStory.objects.filter(pk__in=historic, event_dossier__isnull=False)
                 .values_list('event_dossier_id', flat=True))
    if episode := source.selection.get('episode_id'):
        bound.update(OriginalContentText.objects.filter(narrative__workflow_key='social-brief',
            narrative__status='approved', narrative__selection__episode_id=episode,
            narrative__development__event_dossier__isnull=False).exclude(narrative=output)
            .values_list('narrative__development__event_dossier_id', flat=True))
    target = canonical_dossier(dossier.pk).pk
    return any(canonical_dossier(pk).pk == target for pk in bound)


def record_repeat(package):
    from django.db import transaction
    from django.utils import timezone

    from core.models import OriginalContentRun

    package.refresh_from_db()
    source = source_for_run(package)
    if source is None or not package.decisions.get('chatter_repeat'):
        raise ValueError('missing Chatter repeat decision')
    status = 'reconsider' if package.decisions['chatter_repeat'] == 'coverage_changed' else 'repeat'
    key = f"{source.pk}:{package.snapshot['request']['locale']}"
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=source.run_id)
        if run.outcome.get('writers', {}).get(key) == status:
            return status
        writers = {**run.outcome.get('writers', {}), key: status}
        run.outcome = {**run.outcome, 'writers': writers}
        if status == 'repeat' and (episode := source.selection.get('episode_id')):
            run.outcome['covered_episode_ids'] = sorted({*run.outcome.get('covered_episode_ids', []), episode})
        if set(run.outcome.get('planned_writers', [])) <= writers.keys():
            run.execution_state = 'completed'
            run.outcome.update(phase='complete', healthy_at=run.outcome.get('healthy_at') or timezone.now().isoformat())
        run.save(update_fields=['outcome', 'execution_state', 'updated_at'])
    return status


def published_text(run, content):
    """Resolve this package's edition even after another package takes the pool."""
    from core.models import OriginalContentSelection, OriginalContentText

    locale = run.snapshot['request']['locale']
    selected = OriginalContentSelection.objects.filter(
        scope_key=publication_scope(content, locale), text__narrative__run=run,
    ).select_related('text').first()
    if selected:
        return selected.text
    if content.source_locale_id is not None:
        return OriginalContentText.objects.filter(narrative__run=run, locale=locale).order_by(
            '-narrative__revision', '-pk').first()
    return content.localized_texts.first()


def accounting_config(run):
    """Only the registered personalized source lane owns the routine exception."""
    from .chatter_trends import DECISION_SCOPE, RANKED_SCOPES, ROLLING_LANE
    from .config import EditorialConfig

    source = source_for_run(run)
    if source is None or source.run.scope_key not in RANKED_SCOPES:
        return None
    cfg = EditorialConfig.model_validate(source.run.config_snapshot['editorial'])
    expected = ROLLING_LANE if source.run.scope_key == DECISION_SCOPE else 'personalized-trends-v1'
    if cfg.chatter.discovery_lane != expected:
        raise ValueError('invalid personalized Chatter origin')
    return cfg


def record_ready(text):
    """Observe readable Graphics copy after publication releases its run locks."""
    from django.db import transaction

    from core.models import OriginalContentRun

    from .chatter_chain import _record_ready
    from .chatter_trends import RANKED_SCOPES

    package = text.narrative.run
    source = source_for_run(package)
    if source is None or source.run.scope_key not in RANKED_SCOPES:
        return
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=source.run_id)
        key = f'{source.pk}:{text.locale}'
        if run.outcome.get('writers', {}).get(key) == 'published' and run.outcome.get('healthy_at'):
            return
        # This observes completed work; an expired discovery lease is not a new
        # provider claim and must not hide already published copy.
        _record_ready(run, text, require_live=False)
        run.refresh_from_db()
        writers = {**run.outcome.get('writers', {}), f'{source.pk}:{text.locale}': 'published'}
        run.outcome = {**run.outcome, 'writers': writers}
        if set(run.outcome.get('planned_writers', [])) <= writers.keys():
            run.execution_state = 'completed'
            run.outcome['phase'] = 'complete'
        run.save(update_fields=['outcome', 'execution_state', 'updated_at'])
