"""Publish Graphics copy through the shared immutable content publisher.

The C1 response and its evidence are read from the saved provider call.  Local
trial files, arbitrary caller copy and unrecorded source links are not accepted.
"""

import hashlib
import json
from urllib.parse import urlsplit

from django.db import transaction

from core.models import OriginalContent, OriginalContentCall, OriginalContentRun, Post
from monitor.original_content import WORKFLOWS, digest, publish_content

from .graphics_contracts import build_publication, validate_copy_fact_ids


def _saved_c1(content, producer, pack):
    call = OriginalContentCall.objects.select_for_update().get(pk=producer.pk)
    if (
        call.run_id != content.run_id
        or call.workflow_key != content.workflow_key
        or call.kind != 'text'
        or call.state != 'completed'
        or call.stage != f'gfx:{content.run_id}:C1'
        or call.request_identity != f'graphics:{content.run_id}:C1'
    ):
        raise ValueError('C1 producer does not match content')
    packet = call.request_packet
    if not isinstance(packet, dict) or set(packet) != {'schema_version', 'request_json'} or packet['schema_version'] != 'graphics-request/v1':
        raise ValueError('invalid saved C1 request packet')
    wire = packet['request_json']
    if not isinstance(wire, str) or hashlib.sha256(wire.encode()).hexdigest() != call.request_hash:
        raise ValueError('saved C1 request hash mismatch')
    if not isinstance(call.response_payload, dict) or digest(call.response_payload) != call.response_hash:
        raise ValueError('saved C1 response hash mismatch')
    body = json.loads(wire)
    user_messages = [item for item in body['messages'] if item.get('role') == 'user']
    if len(user_messages) != 1:
        raise ValueError('invalid C1 user message')
    user = user_messages[0]['content']
    if isinstance(user, list):
        text_parts = [item.get('text') for item in user if item.get('type') == 'text']
        user = text_parts[0] if text_parts else None
    marker = '\n\nSUPPLIED INPUTS:\n'
    if not isinstance(user, str) or user.count(marker) != 1:
        raise ValueError('missing C1 evidence handoff')
    handoff, _ = json.JSONDecoder().raw_decode(user.split(marker, 1)[1])
    facts = handoff.get('fact_items') if isinstance(handoff, dict) else None
    if not isinstance(facts, list):
        raise TypeError('missing C1 fact items')
    validate_copy_fact_ids(call.response_payload, facts)
    copy = build_publication(pack, call.response_payload, [], [])
    return call, copy, facts


def _citations(sources, facts):
    allowed = {}
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        post_id = fact.get('source_post_id')
        snapshot_hash = fact.get('snapshot_hash')
        for url in fact.get('source_refs', []):
            if isinstance(url, str) and isinstance(post_id, str):
                allowed.setdefault((post_id, url), set()).add(snapshot_hash)
    if not sources:
        raise ValueError('editorial output requires citations')
    out = []
    for source in sources:
        post_id = str(source.get('post_id') or source.get('id') or '').removeprefix('x:')
        url = source.get('url')
        expected = allowed.get((post_id, url))
        if not post_id or not expected:
            raise ValueError('citation is not in saved C1 handoff')
        parts = urlsplit(url)
        if parts.hostname in {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'} and parts.path.rstrip('/').split('/')[-1] != post_id:
            raise ValueError('citation post identity mismatch')
        if not Post.objects.filter(pk=post_id).exists():
            raise ValueError('missing cited posts: ' + post_id)
        # The exact writing-time snapshot is signed by the C1 handoff.  The
        # current Post is used only for identity, never to reconstruct evidence.
        if len(expected) != 1 or digest(source) not in expected:
            raise ValueError('citation source snapshot does not match C1 handoff')
        if not isinstance(source.get('original_text'), str) or not source['original_text']:
            raise ValueError('citation source snapshot lacks original text')
        out.append({
            'post_id': post_id,
            'url': url,
            'original_text': source['original_text'],
            'author_handle': source.get('author_handle') or source.get('author_label') or '',
            '_writing_projection': source,
        })
    return out


def publish_primary(*, content, producer, pack, sources, selected_scope=None, fence=None):
    """Publish saved A copy and source snapshots, without a review gate."""
    with transaction.atomic():
        OriginalContentRun.objects.select_for_update().get(pk=content.run_id)
        row = OriginalContent.objects.select_for_update().get(pk=content.pk)
        if row.run_id != content.run_id or row.workflow_key not in WORKFLOWS.values():
            raise ValueError('invalid Graphics content identity')
        call, copy, facts = _saved_c1(row, producer, pack)
        citations = _citations(sources, facts)
        (text,) = publish_content(row, [{
            'locale': copy['locale'], 'headline': copy['headline'],
            'byline': copy['byline'], 'body': copy['article'],
            'producing_call': call, 'sources': citations,
            'provenance': {'schema_version': 'graphics-copy/v1', 'candidate_id': 'A', 'c1_request_hash': call.request_hash, 'c1_response_hash': call.response_hash},
        }], selected_scope=selected_scope, fence=fence)
        return text


def publish_fallback(*, primary_text, failure_call, reserve_picture, pack, sources, selected_scope=None, fence=None, storage=None, video_job=None):
    """Save B once after a definite A failure, without displacing a newer pointer.

    A missing, invalid or mismatched reserve file retains the A edition. An
    ambiguous/sent call is not a definite media failure and never enables B.
    """
    from core.models import (
        ContentPicture,
        OriginalContentSelection,
        OriginalContentText,
    )
    from monitor.original_content import advisory_lock

    from .graphics_artifacts import validate_failed_video_job, validate_still

    with transaction.atomic():
        OriginalContentRun.objects.select_for_update().get(pk=primary_text.narrative.run_id)
        primary = OriginalContent.objects.select_for_update().get(pk=primary_text.narrative_id)
        a_text = OriginalContentText.objects.select_for_update().get(pk=primary_text.pk)
        if (
            primary.workflow_key not in WORKFLOWS.values()
            or primary.status != 'approved'
            or a_text.narrative_id != primary.pk
            or a_text.provenance.get('schema_version') != 'graphics-copy/v1'
            or a_text.provenance.get('candidate_id') != 'A'
            or a_text.producing_call_id is None
        ):
            raise ValueError('invalid Graphics primary edition')
        producer, _, facts = _saved_c1(primary, a_text.producing_call, pack)
        citations = _citations(sources, facts)
        failure = OriginalContentCall.objects.select_for_update().get(pk=failure_call.pk)
        identities = {f'graphics:{primary.run_id}:I-A', f'graphics:{primary.run_id}:V1'}
        if (
            failure.run_id != primary.run_id or failure.workflow_key != primary.workflow_key
            or failure.kind != 'media'
            or failure.request_identity not in identities
            or failure.stage != 'gfx:' + failure.request_identity.removeprefix('graphics:')
        ):
            raise ValueError('fallback requires a definite same-run A media failure')
        is_video_job_failure = failure.request_identity.endswith(':V1') and failure.state == 'completed'
        if is_video_job_failure:
            job = ContentPicture.objects.select_for_update().filter(pk=getattr(video_job, 'pk', None)).first()
            if job is None:
                raise ValueError('fallback requires a definite same-run A media failure')
            try:
                validate_failed_video_job(job, content=primary, primary_text=a_text, producer_call=failure, storage=storage)
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError('fallback requires a definite same-run A media failure') from exc
        elif failure.state != 'failed':
            raise ValueError('fallback requires a definite same-run A media failure')
        fallback_provenance = {
            'schema_version': 'graphics-fallback/v1',
            'predecessor_id': primary.pk,
            'failure_call_id': failure.pk,
        }
        if is_video_job_failure:
            fallback_provenance['video_job_id'] = str(job.pk)
        if selected_scope is not None:
            if selected_scope != f'featured:{primary.workflow_key}:{a_text.locale}':
                raise ValueError('invalid featured selection scope')
            advisory_lock('selection:' + selected_scope)
            pointer = OriginalContentSelection.objects.select_for_update().filter(scope_key=selected_scope).first()
        else:
            pointer = None
        key = f'graphics-fallback:{primary.pk}'
        prior = OriginalContent.objects.filter(run_id=primary.run_id, workflow_key=primary.workflow_key, output_key=key).first()
        if prior is not None:
            if prior.provenance != fallback_provenance:
                raise ValueError('existing fallback identity mismatch')
            existing = prior.localized_texts.filter(locale=a_text.locale, producing_call=producer).first()
            if existing is None:
                raise ValueError('existing fallback incomplete')
            return existing
        if selected_scope is not None and (pointer is None or pointer.text_id != a_text.pk):
            return a_text
        if reserve_picture is None:
            return a_text
        picture = ContentPicture.objects.select_for_update().filter(pk=reserve_picture.pk).first()
        if picture is None or picture.text_id is not None:
            return a_text
        try:
            validate_still(picture, content=primary, candidate='B', storage=storage)
        except ValueError:
            return a_text
        candidate = next(item for item in producer.response_payload['candidates'] if item['id'] == 'B')
        b = OriginalContent.objects.create(
            run_id=primary.run_id, workflow_key=primary.workflow_key, output_key=key,
            subject_key=primary.subject_key, story_id=primary.story_id,
            revision=primary.revision + 1, occurred_at=primary.occurred_at,
            importance=primary.importance, fingerprint=primary.fingerprint,
            brand_id=primary.brand_id, brand_key_snapshot=primary.brand_key_snapshot,
            selection=primary.selection, status='prepared', attempted_at=primary.attempted_at,
            provenance=fallback_provenance,
        )
        (text,) = publish_content(b, [{
            'locale': a_text.locale, 'headline': candidate['headline'], 'byline': candidate['byline'],
            'body': producer.response_payload['article'], 'producing_call': producer, 'sources': citations,
            'provenance': {'schema_version': 'graphics-copy/v1', 'candidate_id': 'B', 'c1_request_hash': producer.request_hash, 'c1_response_hash': producer.response_hash},
        }], selected_scope=selected_scope, fence=fence)
        # Preserve A's writing-time source snapshots even if the Post has since changed.
        originals = {source.post_id: source for source in a_text.sources.all()}
        for source in text.sources.all():
            old = originals.get(source.post_id)
            if old is None:
                raise ValueError('fallback citations differ from primary edition')
            source.url_snapshot = old.url_snapshot
            source.author_label_snapshot = old.author_label_snapshot
            source.source_hash = old.source_hash
            source.hash_basis = old.hash_basis
            source.save(update_fields=['url_snapshot', 'author_label_snapshot', 'source_hash', 'hash_basis'])
        if set(originals) != set(text.sources.values_list('post_id', flat=True)):
            raise ValueError('fallback citations differ from primary edition')
        picture.text = text
        picture.content_id = str(text.public_id)
        picture.content_kind = next(track for track, workflow in WORKFLOWS.items() if workflow == primary.workflow_key)
        picture.save(update_fields=['text', 'content_id', 'content_kind'])
        return text
