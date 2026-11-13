"""Resolve one already-selected Graphics story from its saved evidence packet."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from importlib import import_module
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from core.models import OriginalContent, OriginalContentRun, Person, Post
from monitor.original_content import LOCALES, WORKFLOWS, digest, safe_source_url


def _limit(value, default):
    try:
        number = Decimal(str(default if value is None else value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('invalid Graphics budget') from exc
    if not number.is_finite() or number < 0:
        raise ValueError('invalid Graphics budget')
    return str(min(number, Decimal(default)))


def prepare_selected_story(*, content_id, run_id, locale, per_story_usd=None, daily_usd=None):
    """Read a selected prepared output and bind its original packet to Post IDs.

    This boundary neither selects another story nor persists or submits work.
    The current Post's text is deliberately not substituted for the saved packet.
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
    person_ids = selection.get('person_ids', [])
    if not isinstance(person_ids, list) or len(person_ids) > 5:
        raise ValueError('invalid person identities')
    try:
        found = {str(value) for value in Person.objects.filter(pk__in=person_ids).values_list('pk', flat=True)}
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValueError('invalid person identities') from exc
    if found != set(person_ids):
        raise ValueError('missing selected person identity')
    return {
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
            'subject': selection.get('summary') or content.subject_key,
            'locale': locale,
            'fact_items': facts,
            'evidence_status': 'saved selected source packet',
        },
        'per_story_usd': _limit(per_story_usd, '4'),
        'daily_usd': _limit(daily_usd, '40'),
    }


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
