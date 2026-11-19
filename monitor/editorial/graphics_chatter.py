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
    if (output is None or output.story_id != source.story_id
            or output.development_id != source.development_id
            or output.source_locale_id != source.source_locale_id
            or output.editorial_group != source.editorial_group
            or output.provenance != expected):
        raise ValueError('Graphics output differs from saved source pool')
    return source


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
    from .chatter_trends import TRENDS_SCOPE
    from .config import EditorialConfig

    source = source_for_run(run)
    if source is None or source.run.scope_key != TRENDS_SCOPE:
        return None
    cfg = EditorialConfig.model_validate(source.run.config_snapshot['editorial'])
    if cfg.chatter.discovery_lane != 'personalized-trends-v1':
        raise ValueError('invalid personalized Chatter origin')
    return cfg


def record_ready(text):
    """Observe readable Graphics copy after publication releases its run locks."""
    from django.db import transaction

    from core.models import OriginalContentRun

    from .chatter_chain import _record_ready
    from .chatter_trends import TRENDS_SCOPE

    package = text.narrative.run
    source = source_for_run(package)
    if source is None or source.run.scope_key != TRENDS_SCOPE:
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
