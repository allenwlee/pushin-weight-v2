"""Resolve only selected, verified Graphics media for one published edition."""

import hashlib
import re
from dataclasses import dataclass

from botocore.exceptions import BotoCoreError, ClientError
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import InvalidStorageError, storages

from core.models import ContentPicture, OriginalContent, OriginalContentCall
from monitor.original_content import WORKFLOWS

from .graphics_artifacts import PROVENANCE_FIELDS, validate_still

MAX_VIDEO_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class GraphicsAssets:
    still: ContentPicture
    video: ContentPicture | None = None


def _source_content(text):
    content = text.narrative
    copy = text.provenance
    if not isinstance(copy, dict) or copy.get('schema_version') != 'graphics-copy/v1':
        raise ValueError('not Graphics copy')
    candidate = copy.get('candidate_id')
    if candidate == 'A':
        return content, candidate
    if candidate != 'B' or not isinstance(content.provenance, dict):
        raise ValueError('invalid Graphics candidate')
    fallback = content.provenance
    if fallback.get('schema_version') != 'graphics-fallback/v1':
        raise ValueError('missing fallback provenance')
    original = OriginalContent.objects.filter(
        pk=fallback.get('predecessor_id'), run_id=content.run_id,
        story_id=content.story_id, workflow_key=content.workflow_key,
    ).first()
    if original is None:
        raise ValueError('invalid fallback predecessor')
    return original, candidate


def _attached(picture, text, track):
    return (
        picture.text_id == text.pk
        and picture.run_id == text.narrative.run_id
        and picture.content_kind == track
        and picture.content_id == str(text.public_id)
        and picture.state == 'complete'
    )


def _valid_video(picture, text, track, source, candidate, still, storage):
    metadata = picture.provenance
    if not isinstance(metadata, dict) or set(metadata) != PROVENANCE_FIELDS | {'decode_receipt'}:
        return False
    if (
        not _attached(picture, text, track)
        or metadata['schema_version'] != 'graphics-artifact/v1'
        or metadata['role'] != 'video'
        or metadata['candidate_id'] != candidate
        or metadata['mime'] != 'video/mp4'
        or metadata['content_id'] != str(source.pk)
        or type(metadata['producer_call_id']) is not int
        or not re.fullmatch(r'[0-9a-f]{64}', picture.generated_sha256 or '')
        or not picture.generated_storage_name
    ):
        return False
    call = OriginalContentCall.objects.filter(pk=metadata['producer_call_id']).first()
    if not call or call.run_id != source.run_id or call.workflow_key != source.workflow_key or call.kind != 'media' or call.state != 'completed':
        return False
    stages = ('V1',) if candidate == 'A' else ('V1', 'V-B')
    if not any(call.request_identity == f'graphics:{source.run_id}:{stage}' and call.stage == f'gfx:{source.run_id}:{stage}' for stage in stages):
        return False
    receipt = metadata['decode_receipt']
    if not isinstance(receipt, dict) or set(receipt) != {
        'schema_version', 'sha256', 'mime', 'run_id', 'producer_call_id',
        'duration_ms', 'input_still_sha256',
    }:
        return False
    if (
        receipt['schema_version'] != 'graphics-video-decode/v1'
        or receipt['sha256'] != picture.generated_sha256
        or receipt['mime'] != 'video/mp4'
        or receipt['run_id'] != str(source.run_id)
        or type(receipt['producer_call_id']) is not int
        or receipt['producer_call_id'] != call.pk
        or type(receipt['duration_ms']) is not int
        or not 1 <= receipt['duration_ms'] <= 15000
        or receipt['input_still_sha256'] != still.generated_sha256
    ):
        return False
    try:
        total = 0
        checksum = hashlib.sha256()
        with storage.open(picture.generated_storage_name, 'rb') as stream:
            while True:
                chunk = stream.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_VIDEO_BYTES:
                    return False
                checksum.update(chunk)
        return total > 0 and checksum.hexdigest() == picture.generated_sha256
    except (OSError, ValueError, BotoCoreError, ClientError):
        return False


def graphics_assets(edition, *, include_video=True):
    """Return validated still and optional video, never a raw source or reserve."""
    text = getattr(edition, '_original_content_text', None)
    if (text is None or text.narrative.status != 'approved' or not text.public_id
        or str(text.public_id) != str(edition.pk)
        or text.narrative.story_id != edition.story_id
        or text.narrative.workflow_key != WORKFLOWS.get(edition.track)):
        return None
    try:
        source, candidate = _source_content(text)
    except (TypeError, ValueError):
        return None
    try:
        storage = storages['editorial_media']
    except (KeyError, InvalidStorageError, ImproperlyConfigured, BotoCoreError, ClientError):
        return None
    rows = list(ContentPicture.objects.filter(
        text_id=text.pk, run_id=text.narrative.run_id,
        content_kind=edition.track, content_id=str(text.public_id), state='complete',
    ).order_by('created_at', 'pk'))
    stills = []
    for picture in rows:
        if not _attached(picture, text, edition.track):
            continue
        try:
            validate_still(picture, content=source, candidate=candidate, storage=storage)
        except (OSError, ValueError, TypeError, KeyError, BotoCoreError, ClientError):
            continue
        stills.append(picture)
    # Ambiguous attachments never silently pick the newest.
    if len(stills) != 1:
        return None
    still = stills[0]
    if not include_video:
        return GraphicsAssets(still=still)
    videos = [picture for picture in rows if _valid_video(picture, text, edition.track, source, candidate, still, storage)]
    return GraphicsAssets(still=still, video=videos[0] if len(videos) == 1 else None)


def is_graphics_edition(edition):
    text = getattr(edition, '_original_content_text', None)
    if text is None:
        return False
    provenance = text.provenance if isinstance(text.provenance, dict) else {}
    producer = text.producing_call
    return (provenance.get('schema_version') == 'graphics-copy/v1'
            or (producer is not None and producer.request_identity.startswith('graphics:')))
