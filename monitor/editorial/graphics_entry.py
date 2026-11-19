"""Resolve one already-selected Graphics story from its saved evidence packet."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from importlib import import_module
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from core.models import OriginalContent, OriginalContentRun, Person, Post
from monitor.original_content import (
    LOCALES,
    WORKFLOWS,
    chatter_pool,
    digest,
    safe_source_url,
)

from .chatter_history import WORKFLOW as CHATTER_WORKFLOW
from .chatter_history import read_sources
from .graphics_contracts import copy_writer_route
from .voices import Voice


def _limit(value, default):
    try:
        number = Decimal(str(default if value is None else value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('invalid Graphics budget') from exc
    if not number.is_finite() or number < 0:
        raise ValueError('invalid Graphics budget')
    return str(min(number, Decimal(default)))


def _manual_evidence(selection, snapshot, run):
    ids = selection.get('post_ids')
    if not isinstance(ids, list) or not ids or len(ids) > 50 or any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError('invalid selected post IDs')
    if set(Post.objects.filter(pk__in=ids).values_list('pk', flat=True)) != set(ids):
        raise ValueError('missing selected post')
    posts, context = snapshot.get('posts'), snapshot.get('context', [])
    if not isinstance(posts, list) or not isinstance(context, list):
        raise TypeError('invalid evidence snapshot')
    by_id = {}
    for item in posts + context:
        if not isinstance(item, dict):
            raise TypeError('invalid evidence snapshot item')
        key = item.get('id')
        if key in ids:
            if key in by_id:
                raise ValueError('duplicate selected post in snapshot')
            by_id[key] = item
    if set(by_id) != set(ids):
        raise ValueError('selected post missing from snapshot')
    sources, facts = [], []
    for number, key in enumerate(ids, 1):
        source = deepcopy(by_id[key])
        url = safe_source_url(source.get('url'))
        parts = urlsplit(url)
        if parts.hostname not in {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'} or parts.path.rstrip('/').split('/')[-1] != key:
            raise ValueError('saved post URL does not match its identity')
        text = source.get('original_text')
        if not isinstance(text, str) or not text:
            raise ValueError('selected post snapshot lacks original text')
        created = source.get('created_at')
        if created:
            parsed = parse_datetime(created) if isinstance(created, str) else None
            if parsed is None or not is_aware(parsed) or parsed > run.facts_as_of:
                raise ValueError('selected post snapshot is beyond the evidence cutoff')
        sources.append(source)
        facts.append({
            'fact_id': f'F{number:02}',
            'status': 'saved_source_post',
            'supporting_passage': text,
            'source_refs': [url],
            'source_post_id': key,
            'snapshot_hash': digest(source),
        })
    return sources, facts


def _chatter_evidence(content, run, locale):
    if content.consideration_state != 'selected' or not content.development_id:
        raise ValueError('Chatter content is not a selected development')
    source_locale, group = chatter_pool(content.source_locale_id, content.editorial_group)
    # Resolve the saved voice/route directly. Loading today's profiles would change
    # an already selected story when a configuration file is edited during a run.
    try:
        config = run.config_snapshot['editorial']
        binding = f'chatter:{locale}'
        voice = Voice.model_validate(run.config_snapshot['voices'][binding])
        route = copy_writer_route(config.get('locale_routes', {}).get(binding) or config['routes']['chatter'])
        if (voice.id != config['voices'][binding] or voice.track != 'chatter'
                or voice.locale != locale or not voice.available or not voice.instructions.strip()):
            raise ValueError('invalid saved voice')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('invalid saved Chatter writer binding') from exc
    sources = read_sources(content)
    rows = list(content.consideration_sources.order_by('position'))
    if not sources or not any(row.usage == 'consideration' for row in rows):
        raise ValueError('selected Chatter story lacks considered sources')
    facts, identities = [], []
    for number, (source, row) in enumerate(zip(sources, rows, strict=True), 1):
        created = source['created_at']
        if created is not None and parse_datetime(created) > run.facts_as_of:
            raise ValueError('selected source snapshot is beyond the evidence cutoff')
        identity = {'source_id': source['id'], 'post_id': row.post_id,
                    'dossier_source_id': row.dossier_source_id,
                    'snapshot_run_id': row.snapshot_run_id, 'source_hash': row.source_hash,
                    'usage': row.usage}
        identities.append(identity)
        common = {
            'status': 'saved_source_post' if row.post_id else 'saved_source_document',
            'source_kind': source['kind'],
            'source_id': source['id'], 'source_refs': [source['url']],
            'snapshot_hash': row.source_hash, 'source_usage': row.usage,
            'snapshot_run_id': row.snapshot_run_id,
            'carrier_created_at': created, 'observed_at': source['observed_at'],
            'source_language': source['source_language'],
            'qualifiers': {key: source[key] for key in (
                'verification_basis', 'excerpt_truncated', 'is_quote', 'is_reply', 'is_retweet')},
            **({'source_post_id': row.post_id} if row.post_id else {'dossier_source_id': row.dossier_source_id}),
        }
        facts.append({**common, 'fact_id': f'F{number:02}',
                      'supporting_passage': source['original_text'], 'speaker': source['author_handle'],
                      'speaker_id': source['author_id'],
                      'source_role': 'background' if row.usage == 'background' else 'original',
                      'created_at': created,
                      'attribution_gaps': ([] if source['author_handle'] or source['author_id'] else ['speaker_unavailable'])
                      + ([] if created else ['passage_date_unavailable'])})
        for field, role, suffix, speaker, post_id in [
            ('stored_quote', 'quoted', 'Q', 'quoted_author_handle', 'quoted_post_id'),
            ('local_parent', 'parent', 'P', 'parent_author_handle', 'parent_post_id'),
        ]:
            if source[field]:
                facts.append({**common, 'fact_id': f'F{number:02}-{suffix}',
                              'supporting_passage': source[field], 'speaker': source[speaker],
                              'speaker_id': None,
                              'attributed_post_id': source[post_id] or None, 'source_role': role,
                              # Embedded evidence has no separate date in FrozenPacket.
                              'created_at': None,
                              'attribution_gaps': ['passage_date_unavailable']
                              + ([] if source[speaker] else ['speaker_unavailable'])})
    return sources, facts, voice, route, {
        'schema_version': 'graphics-chatter-source/v1', 'source_content_id': content.pk,
        'source_run_id': run.pk, 'development_id': str(content.development_id),
        'source_locale': source_locale, 'editorial_group': group, 'source_identities': identities,
    }


def prepare_selected_story(*, content_id, run_id, locale, per_story_usd=None, daily_usd=None):
    """Resolve a selected saved packet without substituting mutable source text.

    Chatter's hash-owned consideration reader and manual Graphics' Post snapshot
    remain the authoritative boundaries; caller JSON cannot select another route.
    """
    if locale not in LOCALES:
        raise ValueError('unsupported locale')
    run = OriginalContentRun.objects.filter(pk=run_id).first()
    content = OriginalContent.objects.filter(pk=content_id).first()
    if run is None or content is None or content.run_id != run.pk:
        raise ValueError('content and run do not match')
    if content.workflow_key not in WORKFLOWS.values() or content.status != 'prepared' or not content.story_id:
        raise ValueError('content is not a prepared selected editorial story')
    if not run.facts_as_of or not is_aware(run.facts_as_of):
        raise ValueError('run requires an aware evidence cutoff')
    selection, snapshot = content.selection, run.snapshot
    if not isinstance(selection, dict) or not isinstance(snapshot, dict):
        raise TypeError('invalid selected-story snapshot')
    chatter = None
    if run.workflow_key == CHATTER_WORKFLOW:
        sources, facts, voice, route, chatter = _chatter_evidence(content, run, locale)
    else:
        sources, facts = _manual_evidence(selection, snapshot, run)
    person_ids = selection.get('person_ids', [])
    if not isinstance(person_ids, list) or len(person_ids) > 5:
        raise ValueError('invalid person identities')
    try:
        found = {str(value) for value in Person.objects.filter(pk__in=person_ids).values_list('pk', flat=True)}
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValueError('invalid person identities') from exc
    if found != set(person_ids):
        raise ValueError('missing selected person identity')
    request = {
        'content_id': content.pk,
        'run_id': run.pk,
        'workflow_key': content.workflow_key,
        'story_id': str(content.story_id),
        'source_cycle_id': run.source_cycle_id,
        'source_revision': content.revision,
        'facts_as_of': run.facts_as_of.isoformat(),
        'locale': locale,
        'person_ids': person_ids,
        'sources': sources,
        'handoff': {
            'subject': (selection.get('subject') if chatter else None) or selection.get('summary') or content.subject_key,
            'locale': locale,
            'fact_items': facts,
            'evidence_status': 'saved selected source packet',
        },
        'per_story_usd': _limit(per_story_usd, '4'),
        'daily_usd': _limit(daily_usd, '40'),
    }
    if chatter is not None:
        request['chatter'] = chatter
        request['writer_route'] = route.model_dump(mode='json')
        request['handoff'].update(voice=voice.model_dump(mode='json'), voice_hash=voice.digest)
    return request


def advance_package(request):
    """Call the production package when it has been installed by integration."""
    try:
        module = import_module('monitor.editorial.graphics_packages')
    except ModuleNotFoundError as exc:
        if exc.name != 'monitor.editorial.graphics_packages':
            raise
        raise RuntimeError('Graphics package orchestration is not available') from exc
    return module.advance_package(request)


def run_selected_story(*, content_id, run_id, locale, advance=None, **limits):
    request = prepare_selected_story(content_id=content_id, run_id=run_id, locale=locale, **limits)
    return (advance or advance_package)(request)
