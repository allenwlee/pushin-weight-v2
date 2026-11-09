"""One bounded Graphics phase at a time, resumed from persisted records."""

import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from jsonschema.exceptions import ValidationError as SchemaValidationError

from core.models import (
    ContentPicture,
    OriginalContent,
    OriginalContentCall,
    OriginalContentRun,
    OriginalContentSelection,
    PersonMedia,
    StaffMediaObject,
)
from core.staff_assets.graphics_references import read_graphics_references
from core.staff_assets.media import store_image
from monitor.original_content import WORKFLOWS, advisory_lock, digest
from monitor.trend_narrative_lifecycle import (
    fail_trend_narrative_provider_call,
    mark_trend_narrative_provider_call_ambiguous,
    mark_trend_narrative_provider_call_sent,
)

from .config import load_editorial_config
from .graphics_contracts import (
    load_pack,
    normalize_treatments,
    validate_copy_fact_ids,
    validate_stage_output,
)
from .graphics_generation import (
    MAX_INPUT_BYTES,
    build_image_request,
    build_text_request,
    create_request_recipe,
    submit_once,
)
from .graphics_packages import claim_package, release_package
from .graphics_publication import publish_fallback, publish_primary
from .graphics_search import exa_request_json, search_exa_query
from .graphics_sources import collect_sources
from .persistence import (
    BudgetHeld,
    complete_graphics_call,
    fail_graphics_presend_call,
    reserve_graphics_call,
)


def _owned(run, owner, fence):
    return (run.workflow_key == 'graphics-package' and run.execution_state == 'running'
            and run.claim_owner == owner and run.fence == fence
            and run.lease_until is not None and run.lease_until > timezone.now())


def _stage_call(run_id, stage):
    return OriginalContentCall.objects.filter(request_identity=f'graphics:{run_id}:{stage}').first()


def _run_text_stage(run, content, claim, stage, request, key, pack, *, transport=None,
                    configured_daily_limit=None, references=(), expected_review=None):
    body = json.dumps(request['body'], ensure_ascii=False)
    packet = {'schema_version': 'graphics-request/v1', 'request_json': body}
    request_hash = hashlib.sha256(body.encode()).hexdigest()
    if references:
        packet, request_hash = create_request_recipe(request['body'], references)
    is_image = stage in {'I-A', 'I-B'}
    per_run = run.config_snapshot['per_story_usd']
    daily = run.config_snapshot['daily_usd']

    def reserve(saved_packet, saved_hash):
        return reserve_graphics_call(
            run=run, stage=stage, kind='media' if is_image else 'text', request_hash=saved_hash,
            request_packet=saved_packet, provider='xai' if is_image else 'openrouter', model=request['body']['model'],
            ceiling='0.15' if is_image else '0.25', owner=claim.owner, lease_seconds=160,
            workflow_key=content.workflow_key, per_run_limit=per_run, daily_limit=daily,
            configured_daily_limit=configured_daily_limit, review=stage == 'E1',
        )

    def mark_sent(call):
        with transaction.atomic():
            current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
            if not _owned(current, claim.owner, claim.fence):
                return False
            return mark_trend_narrative_provider_call_sent(
                call.pk, owner=claim.owner, fence=call.claim_fence, now=timezone.now())

    def complete(call, payload, image, usage):
        # Files are saved before the transaction; provider I/O never holds a run lock.
        if expected_review and (payload.get('text_id'), payload.get('content_revision')) != expected_review:
            raise ValueError('review result does not match published edition')
        name = None
        if is_image:
            storage = storages['editorial_media']
            extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[payload['mime']]
            name = f"graphics/{run.pk}/{stage}-{payload['sha256']}.{extension}"
            if not storage.exists(name):
                name = storage.save(name, ContentFile(image))
        # Acquire the budget lock before the run lock, matching reservation order.
        with transaction.atomic():
            advisory_lock(f'content-budget:editorial:{call.budget_day}')
            current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
            if not _owned(current, claim.owner, claim.fence):
                return False
            cost = usage.get('estimated_cost') if isinstance(usage, dict) else None
            completed = complete_graphics_call(call.pk, owner=claim.owner, fence=call.claim_fence,
                response_hash=digest(payload), response_payload=payload, actual_usd=cost)
            if not completed:
                return False
            if is_image:
                ContentPicture.objects.create(run=run, content_kind='graphics', content_id=str(content.pk),
                    revision_hash=digest({'call': call.pk, 'sha256': payload['sha256']}),
                    mode='generated', state='complete', generated_storage_name=name,
                    generated_sha256=payload['sha256'], provenance={
                        'schema_version': 'graphics-artifact/v1', 'role': 'still',
                        'candidate_id': stage[-1], 'mime': payload['mime'],
                        'producer_call_id': call.pk, 'content_id': str(content.pk)})
            return True

    def ambiguous(call, code):
        return mark_trend_narrative_provider_call_ambiguous(
            call.pk, owner=claim.owner, fence=call.claim_fence, error_code=code, now=timezone.now())

    def fail(call, code):
        if code.startswith('pre_send:'):
            return fail_graphics_presend_call(call.pk, owner=claim.owner,
                                               fence=call.claim_fence, error_code=code)
        return fail_trend_narrative_provider_call(
            call.pk, owner=claim.owner, fence=call.claim_fence, error_code=code, now=timezone.now())

    kwargs = {'reserve': reserve, 'mark_sent': mark_sent, 'complete': complete,
              'ambiguous': ambiguous, 'fail': fail}
    if transport is not None:
        kwargs['transport'] = transport
    return submit_once(stage, request, packet, request_hash, key, pack, **kwargs)


def _asset_inputs(saved, source_record):
    assets = []
    seen = set()
    for person_id in saved.get('person_ids', []):
        pack = read_graphics_references(person_id, permitted_reuse={'unknown', 'permitted', 'restricted'})
        for ref in pack.references:
            if ref.sha256 in seen or ref.media_type not in {'image/jpeg', 'image/png', 'image/webp'}:
                continue
            row = PersonMedia.objects.select_related('media').get(pk=ref.person_media_id)
            seen.add(ref.sha256)
            assets.append({'asset_ref': f'person:{ref.person_media_id}', 'role': 'identity_reference',
                'credit': ref.credit, 'source_url': ref.source_url, 'reuse_status': ref.reuse_status,
                'sha256': ref.sha256, 'mime': ref.media_type, 'data': ref.data,
                'storage_alias': 'staff_media', 'storage_name': row.media.storage_name})
    for value in source_record.get('assets', []):
        if value['sha256'] in seen:
            continue
        try:
            media = StaffMediaObject.objects.get(pk=value['sha256'])
            with storages['staff_media'].open(media.storage_name, 'rb') as stream:
                data = stream.read(MAX_INPUT_BYTES + 1)
            if not data or len(data) > MAX_INPUT_BYTES or hashlib.sha256(data).hexdigest() != value['sha256']:
                continue
        except (OSError, StaffMediaObject.DoesNotExist):
            continue
        seen.add(value['sha256'])
        assets.append({**value, 'mime': media.media_type, 'data': data,
                       'storage_alias': 'staff_media', 'storage_name': media.storage_name})
    return assets[:12]


def _save_sources(run, content, claim, discovery, search, credentials, configured_daily_limit):
    # Mark the search before contacting an external provider. An interrupted search
    # is left unavailable rather than silently issuing another paid request.
    with transaction.atomic():
        current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
        if not _owned(current, claim.owner, claim.fence):
            return None
        decisions = dict(current.decisions)
        if 'graphics_source_search' in decisions:
            return decisions['graphics_source_search']
        decisions['graphics_source_search'] = {'schema_version': 'graphics-source-search/v1', 'state': 'started', 'assets': [],
            'evidence': {'search_status': 'interrupted_or_pending', 'queries': discovery['queries']}}
        current.decisions = decisions
        current.save(update_fields=['decisions'])
    key = credentials.get('EXA_API_KEY', '')
    query_outcomes = []
    if search is None:
        configured = getattr(settings, 'GRAPHICS_ARTWORK_SEARCH', None)
        search = import_string(configured) if isinstance(configured, str) and configured else configured
        search = search or search_exa_query

    def metered(discovery_value):
        groups = []
        for index, query in enumerate(discovery_value['queries'], 1):
            stage = f'S{index}'
            body = exa_request_json(query)
            packet = {'schema_version': 'graphics-request/v1', 'request_json': body}
            request_hash = hashlib.sha256(body.encode()).hexdigest()
            try:
                call, may_send = reserve_graphics_call(run=run, stage=stage, kind='text',
                    request_hash=request_hash, request_packet=packet, provider='exa', model='exa-auto',
                    ceiling=Decimal("0.02"), owner=claim.owner, lease_seconds=160,
                    workflow_key=content.workflow_key, per_run_limit=run.config_snapshot['per_story_usd'],
                    daily_limit=run.config_snapshot['daily_usd'], configured_daily_limit=configured_daily_limit)
            except BudgetHeld:
                groups.append({'query': query, 'results': []})
                query_outcomes.append({'query': query, 'state': 'budget_unavailable'})
                continue
            if not may_send:
                groups.append(call.response_payload if call.state == 'completed' else {'query': query, 'results': []})
                query_outcomes.append({'query': query, 'state': call.state})
                continue
            with transaction.atomic():
                current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
                sent = _owned(current, claim.owner, claim.fence) and mark_trend_narrative_provider_call_sent(
                    call.pk, owner=claim.owner, fence=call.claim_fence, now=timezone.now())
            if not sent:
                groups.append({'query': query, 'results': []})
                query_outcomes.append({'query': query, 'state': 'claim_lost'})
                continue
            try:
                group = search(query, api_key=key)
                if not isinstance(group, dict) or group.get('query') != query or not isinstance(group.get('results'), list):
                    raise ValueError('Search result does not match reserved query')
                with transaction.atomic():
                    advisory_lock(f'content-budget:editorial:{call.budget_day}')
                    current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
                    if not _owned(current, claim.owner, claim.fence):
                        raise ValueError('Search claim expired')
                    if not complete_graphics_call(call.pk, owner=claim.owner, fence=call.claim_fence,
                            response_hash=digest(group), response_payload=group):
                        raise ValueError('Search completion rejected')
                query_outcomes.append({'query': query, 'state': 'completed'})
                groups.append(group)
            except Exception:  # noqa: BLE001 -- unknown post-send cost is retained and never retried
                mark_trend_narrative_provider_call_ambiguous(call.pk, owner=claim.owner,
                    fence=call.claim_fence, error_code='search_result_unknown', now=timezone.now())
                groups.append({'query': query, 'results': []})
                query_outcomes.append({'query': query, 'state': 'ambiguous'})
        return {'provider': 'exa', 'cost_usd': None, 'queries': groups}

    result = collect_sources(discovery, search=metered if key else None)
    result['evidence']['query_outcomes'] = query_outcomes
    if key:
        result['evidence']['search_requests'] = sum(item['state'] in {'completed', 'ambiguous'} for item in query_outcomes)
        if query_outcomes and all(item['state'] == 'budget_unavailable' for item in query_outcomes):
            result['evidence']['search_status'] = 'unavailable'
    assets = []
    for asset in result['assets']:
        media = store_image(asset['data'])
        assets.append({k: v for k, v in asset.items() if k != 'data'})
        if media.sha256 != asset['sha256']:
            raise ValueError('Stored source artwork hash mismatch')
    record = {'schema_version': 'graphics-source-search/v1', 'state': 'completed', 'assets': assets, 'evidence': result['evidence']}
    with transaction.atomic():
        current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
        if not _owned(current, claim.owner, claim.fence):
            return None
        decisions = dict(current.decisions)
        decisions['graphics_source_search'] = record
        current.decisions = decisions
        current.save(update_fields=['decisions'])
    return record


def _image_request(pack, saved, source_record, g1, stage):
    treatments, _ = normalize_treatments(pack, g1.response_payload)
    treatment = next(item for item in treatments['treatments'] if item['candidate_id'] == stage[-1])
    assets = _asset_inputs(saved, source_record)
    by_ref = {asset['asset_ref']: asset for asset in assets}
    selected = []
    for ref in treatment['input_asset_refs']:
        asset = by_ref.get(ref['asset_ref'])
        if asset is None or asset['role'] != ref['role'] or asset in selected:
            raise ValueError('Treatment references unavailable or mismatched source artwork')
        selected.append(asset)
    request = build_image_request(pack, stage, treatment, assets)
    refs = [{k: asset[k] for k in ('storage_alias', 'storage_name', 'mime', 'sha256')} for asset in selected]
    return request, refs


def _skip_stage(run, claim, stage, reason):
    with transaction.atomic():
        current = OriginalContentRun.objects.select_for_update().get(pk=run.pk)
        if not _owned(current, claim.owner, claim.fence):
            return False
        decisions = dict(current.decisions)
        skipped = dict(decisions.get('graphics_skipped_stages', {}))
        skipped[stage] = reason
        decisions['graphics_skipped_stages'] = skipped
        current.decisions = decisions
        current.save(update_fields=['decisions'])
        return True


def _invalid_saved(run, claim, stage, reason):
    _skip_stage(run, claim, 'attention', f'{stage}:{reason}')
    return {'state': reason, 'stage': stage, 'next_action': None}


def advance_step(run_id, *, owner=None, keys=None, transport=None,
                 configured_daily_limit=None, search=None):
    """Advance one persisted phase without retrying a sent provider request."""
    owner = owner or f'graphics-{uuid4()}'
    claim = claim_package(run_id, owner=owner, lease_seconds=180)
    if claim is None:
        return {'state': 'busy', 'next_action': None}
    try:
        run = OriginalContentRun.objects.get(pk=run_id)
        content = OriginalContent.objects.get(run=run, output_key='graphics-primary/v1')
        saved = run.snapshot['request']
        pack = load_pack(Path(settings.BASE_DIR) / 'config/editorial_prompts/editorial-creative-roles-v1.json')
        credentials = os.environ if keys is None else keys
        config = load_editorial_config()
        if config.enabled:
            configured_daily_limit = (config.daily_usd if configured_daily_limit is None
                else min(Decimal(str(config.daily_usd)), Decimal(str(configured_daily_limit))))
        c1 = _stage_call(run_id, 'C1')
        if c1 is None:
            if 'C1' in run.decisions.get('graphics_skipped_stages', {}):
                return {'state': 'unavailable', 'stage': 'C1', 'next_action': None}
            key = credentials.get('OPENROUTER_API_KEY', '')
            if not key:
                _skip_stage(run, claim, 'C1', 'credential_unavailable')
                return {'state': 'credential_unavailable', 'stage': 'C1', 'next_action': None}
            request = build_text_request(pack, 'C1', saved['handoff'])
            try:
                outcome = _run_text_stage(run, content, claim, 'C1', request, key, pack,
                                          transport=transport, configured_daily_limit=configured_daily_limit)
            except BudgetHeld:
                _skip_stage(run, claim, 'C1', 'budget_or_capacity_unavailable')
                return {'state': 'budget_or_capacity_unavailable', 'stage': 'C1', 'next_action': None}
            return {'state': outcome['state'], 'stage': 'C1',
                    'next_action': 'advance' if outcome['state'] == 'completed' else None}
        if c1.state != 'completed':
            return {'state': c1.state, 'stage': 'C1', 'next_action': None}
        if c1.response_hash != digest(c1.response_payload):
            return _invalid_saved(run, claim, 'C1', 'invalid_saved_response')
        try:
            validate_stage_output(pack, 'C1', c1.response_payload)
            validate_copy_fact_ids(c1.response_payload, saved['handoff']['fact_items'])
        except (SchemaValidationError, ValueError, TypeError, KeyError):
            return _invalid_saved(run, claim, 'C1', 'invalid_saved_response')
        g0 = _stage_call(run_id, 'G0')
        if g0 is None and 'G0' in run.decisions.get('graphics_skipped_stages', {}):
            g0 = SimpleNamespace(state='skipped', response_payload={})
        if g0 is None:
            key = credentials.get('OPENROUTER_API_KEY', '')
            if not key:
                ok = _skip_stage(run, claim, 'G0', 'credential_unavailable')
                return {'state': 'skipped' if ok else 'claim_lost', 'stage': 'G0', 'next_action': 'advance' if ok else None}
            manifest = []
            for person_id in saved.get('person_ids', []):
                references = read_graphics_references(person_id,
                    permitted_reuse={'unknown', 'permitted', 'restricted'})
                manifest.extend({'asset_ref': f'person:{ref.person_media_id}',
                    'role': 'identity_reference', 'credit': ref.credit, 'sha256': ref.sha256}
                    for ref in references.references)
            request = build_text_request(pack, 'G0', {
                'candidates': c1.response_payload['candidates'],
                'facts': saved['handoff']['fact_items'],
                'available_assets': manifest, 'prior_searches': [],
            })
            try:
                outcome = _run_text_stage(run, content, claim, 'G0', request, key, pack,
                    transport=transport, configured_daily_limit=configured_daily_limit)
            except BudgetHeld:
                ok = _skip_stage(run, claim, 'G0', 'budget_or_capacity_unavailable')
                return {'state': 'skipped' if ok else 'claim_lost', 'stage': 'G0', 'next_action': 'advance' if ok else None}
            return {'state': outcome['state'], 'stage': 'G0',
                    'next_action': 'advance' if outcome['state'] in {'completed', 'failed', 'ambiguous'} else None}
        if g0.state not in {'completed', 'failed', 'ambiguous', 'skipped'}:
            return {'state': g0.state, 'stage': 'G0', 'next_action': None}
        if g0.state == 'completed':
            if g0.response_hash != digest(g0.response_payload):
                return _invalid_saved(run, claim, 'G0', 'invalid_saved_response')
            try:
                validate_stage_output(pack, 'G0', g0.response_payload)
            except (SchemaValidationError, ValueError, TypeError, KeyError):
                return _invalid_saved(run, claim, 'G0', 'invalid_saved_response')
        source_record = run.decisions.get('graphics_source_search')
        if source_record is None:
            discovery = g0.response_payload if g0.state == 'completed' else {'queries': []}
            source_record = _save_sources(run, content, claim, discovery, search, credentials, configured_daily_limit)
            return {'state': 'completed' if source_record else 'claim_lost',
                    'stage': 'source_lookup', 'next_action': 'advance' if source_record else None}
        if (not isinstance(source_record, dict) or set(source_record) != {'schema_version', 'state', 'assets', 'evidence'}
                or source_record['schema_version'] != 'graphics-source-search/v1'
                or source_record['state'] not in {'started', 'completed'}
                or not isinstance(source_record['assets'], list) or not isinstance(source_record['evidence'], dict)):
            return _invalid_saved(run, claim, 'source_lookup', 'invalid_saved_sources')
        g1 = _stage_call(run_id, 'G1')
        if g1 is None and 'G1' in run.decisions.get('graphics_skipped_stages', {}):
            g1 = SimpleNamespace(state='skipped', response_payload={})
        if g1 is None:
            key = credentials.get('OPENROUTER_API_KEY', '')
            if not key:
                ok = _skip_stage(run, claim, 'G1', 'credential_unavailable')
                return {'state': 'skipped' if ok else 'claim_lost', 'stage': 'G1', 'next_action': 'advance' if ok else None}
            assets = _asset_inputs(saved, source_record)
            manifest = [{k: v for k, v in a.items() if k not in {'data', 'storage_alias', 'storage_name'}} for a in assets]
            request = build_text_request(pack, 'G1', {
                'candidates': c1.response_payload['candidates'],
                'visual_approaches': g0.response_payload.get('approaches', []) if g0.state == 'completed' else [],
                'actual_asset_manifest': manifest, 'source_discovery': source_record['evidence'],
                'facts': saved['handoff']['fact_items'],
                'constraints': {'one_still_per_candidate': True, 'complete_native_lettering': True, 'video_seconds': 5},
            }, attachments=assets)
            refs = [{k: a[k] for k in ('storage_alias', 'storage_name', 'mime', 'sha256')} for a in assets]
            try:
                outcome = _run_text_stage(run, content, claim, 'G1', request, key, pack,
                    transport=transport, configured_daily_limit=configured_daily_limit, references=refs)
            except BudgetHeld:
                ok = _skip_stage(run, claim, 'G1', 'budget_or_capacity_unavailable')
                return {'state': 'skipped' if ok else 'claim_lost', 'stage': 'G1', 'next_action': 'advance' if ok else None}
            return {'state': outcome['state'], 'stage': 'G1',
                    'next_action': 'advance' if outcome['state'] in {'completed', 'failed', 'ambiguous'} else None}
        if g1.state == 'completed':
            if g1.response_hash != digest(g1.response_payload):
                return _invalid_saved(run, claim, 'G1', 'invalid_saved_response')
            try:
                normalized, _ = normalize_treatments(pack, g1.response_payload)
                validate_stage_output(pack, 'G1', normalized)
            except (SchemaValidationError, ValueError, TypeError, KeyError):
                return _invalid_saved(run, claim, 'G1', 'invalid_saved_response')
        picture = ContentPicture.objects.filter(run=run, provenance__role='still',
            provenance__candidate_id='A', provenance__content_id=str(content.pk), state='complete').first()
        image_call = _stage_call(run_id, 'I-A')
        if content.status == 'prepared' and g1.state == 'completed' and image_call is None and 'I-A' not in run.decisions.get('graphics_skipped_stages', {}):
            key = credentials.get('XAI_API_KEY_PW', '')
            if key:
                try:
                    request, refs = _image_request(pack, saved, source_record, g1, 'I-A')
                except (ValueError, OSError, StopIteration, KeyError):
                    _skip_stage(run, claim, 'I-A', 'input_unavailable')
                    return {'state': 'skipped', 'stage': 'I-A', 'next_action': 'advance'}
                try:
                    outcome = _run_text_stage(run, content, claim, 'I-A', request, key, pack,
                        transport=transport, configured_daily_limit=configured_daily_limit, references=refs)
                except BudgetHeld:
                    outcome = {'state': 'budget_or_capacity_unavailable'}
                if outcome['state'] in {'completed', 'failed', 'ambiguous'}:
                    return {'state': outcome['state'], 'stage': 'I-A', 'next_action': 'advance'}
            # No credential or budget: publish the already saved copy below.
        if content.status == 'prepared':
            scope = f'featured:{content.workflow_key}:{saved["locale"]}'
            with transaction.atomic():
                text = publish_primary(content=content, producer=c1, pack=pack, sources=saved['sources'],
                                       selected_scope=scope, fence=claim.fence)
                if picture:
                    track = next(name for name, workflow in WORKFLOWS.items() if workflow == content.workflow_key)
                    picture.text = text
                    picture.content_kind = track
                    picture.content_id = str(text.public_id)
                    picture.save(update_fields=['text', 'content_kind', 'content_id'])
            fallback_due = bool(image_call and image_call.state == 'failed' and g1.state == 'completed')
            return {'state': 'published', 'stage': 'publication', 'text_id': text.pk,
                    'next_action': 'advance' if fallback_due else ('video' if picture else 'review'),
                    'review_due': not fallback_due and not picture}
        failed_job = ContentPicture.objects.filter(run=run, provenance__schema_version='graphics-video-job/v1',
            provenance__candidate_id='A', state='failed').first()
        video_call = _stage_call(run_id, 'V1')
        failure_call = image_call if image_call and image_call.state == 'failed' else (video_call if video_call and (video_call.state == 'failed' or failed_job) else None)
        if failure_call and g1.state == 'completed':
            reserve = _stage_call(run_id, 'I-B')
            skipped = run.decisions.get('graphics_skipped_stages', {})
            if reserve is None and 'I-B' not in skipped:
                key = credentials.get('XAI_API_KEY_PW', '')
                if not key:
                    _skip_stage(run, claim, 'I-B', 'credential_unavailable')
                    return {'state': 'skipped', 'stage': 'I-B', 'next_action': 'review'}
                try:
                    request, refs = _image_request(pack, saved, source_record, g1, 'I-B')
                except (ValueError, OSError, StopIteration, KeyError):
                    _skip_stage(run, claim, 'I-B', 'input_unavailable')
                    return {'state': 'skipped', 'stage': 'I-B', 'next_action': 'review'}
                try:
                    outcome = _run_text_stage(run, content, claim, 'I-B', request, key, pack,
                        transport=transport, configured_daily_limit=configured_daily_limit, references=refs)
                except BudgetHeld:
                    _skip_stage(run, claim, 'I-B', 'budget_or_capacity_unavailable')
                    return {'state': 'skipped', 'stage': 'I-B', 'next_action': 'review'}
                return {'state': outcome['state'], 'stage': 'I-B', 'next_action': 'advance'}
            if reserve and reserve.state == 'completed':
                reserve_picture = ContentPicture.objects.filter(run=run, provenance__role='still',
                    provenance__candidate_id='B', provenance__content_id=str(content.pk), state='complete').first()
                primary_text = content.localized_texts.get(locale=saved['locale'])
                scope = f'featured:{content.workflow_key}:{saved["locale"]}'
                text = publish_fallback(primary_text=primary_text, failure_call=failure_call,
                    reserve_picture=reserve_picture, pack=pack, sources=saved['sources'],
                    selected_scope=scope, fence=claim.fence, video_job=failed_job if failure_call == video_call and failed_job else None)
                return {'state': 'published', 'stage': 'fallback', 'text_id': text.pk,
                        'next_action': 'video' if text.pk != primary_text.pk else 'review',
                        'review_due': text.pk == primary_text.pk}
        return {'state': 'published', 'stage': 'review', 'next_action': 'review', 'review_due': True}
    finally:
        release_package(run_id, owner=claim.owner, fence=claim.fence)


def review_step(run_id, *, owner=None, keys=None, transport=None, configured_daily_limit=None):
    """Record one advisory review of the saved edition; never gate publication."""
    owner = owner or f'graphics-review-{uuid4()}'
    claim = claim_package(run_id, owner=owner, lease_seconds=180)
    if claim is None:
        return {'state': 'busy'}
    try:
        run = OriginalContentRun.objects.get(pk=run_id)
        content = OriginalContent.objects.get(run=run, output_key='graphics-primary/v1')
        selected = OriginalContentSelection.objects.filter(scope_key=f'featured:{content.workflow_key}:{run.snapshot["request"]["locale"]}', text__narrative__run=run).select_related('text').first()
        text = selected.text if selected else content.localized_texts.first()
        if not text:
            return {'state': 'not_published'}
        prior = _stage_call(run_id, 'E1')
        if prior:
            return {'state': prior.state}
        credentials = os.environ if keys is None else keys
        key = credentials.get('OPENROUTER_API_KEY', '')
        if not key:
            _skip_stage(run, claim, 'E1', 'credential_unavailable')
            return {'state': 'credential_unavailable'}
        config = load_editorial_config()
        if config.enabled:
            configured_daily_limit = (config.daily_usd if configured_daily_limit is None else
                min(Decimal(str(config.daily_usd)), Decimal(str(configured_daily_limit))))
        saved = run.snapshot['request']
        publication = {'locale': text.locale, 'headline': text.headline, 'byline': text.byline, 'article': text.body}
        revision = digest({'text_id': text.pk, 'publication': publication})
        assets = _asset_inputs(saved, run.decisions.get('graphics_source_search', {'assets': []}))
        still = ContentPicture.objects.filter(run=run, text=text, provenance__role='still', state='complete').first()
        if still:
            try:
                with storages['editorial_media'].open(still.generated_storage_name, 'rb') as stream:
                    data = stream.read(MAX_INPUT_BYTES + 1)
                if not data or len(data) > MAX_INPUT_BYTES or hashlib.sha256(data).hexdigest() != still.generated_sha256:
                    raise ValueError('Published still bytes mismatch')
                assets.insert(0, {'asset_ref': 'published:still', 'role': 'generated_still',
                    'mime': still.provenance['mime'], 'sha256': still.generated_sha256, 'data': data,
                    'storage_alias': 'editorial_media', 'storage_name': still.generated_storage_name})
            except (OSError, ValueError, KeyError):
                # The review can still assess the saved copy and report the missing still.
                pass
        assets = assets[:12]
        manifest = [{k: v for k, v in a.items() if k not in {'data', 'storage_alias', 'storage_name'}} for a in assets]
        pack = load_pack(Path(settings.BASE_DIR) / 'config/editorial_prompts/editorial-creative-roles-v1.json')
        request = build_text_request(pack, 'E1', {'text_id': text.pk, 'content_revision': revision,
            'publication': publication, 'handoff': saved['handoff'], 'selected_asset_manifest': manifest},
            attachments=assets)
        refs = [{k: a[k] for k in ('storage_alias', 'storage_name', 'mime', 'sha256')} for a in assets]
        try:
            outcome = _run_text_stage(run, content, claim, 'E1', request, key, pack, transport=transport,
                configured_daily_limit=configured_daily_limit, references=refs,
                expected_review=(text.pk, revision))
        except BudgetHeld:
            _skip_stage(run, claim, 'E1', 'budget_or_capacity_unavailable')
            return {'state': 'budget_or_capacity_unavailable'}
        return {'state': outcome['state']}
    finally:
        release_package(run_id, owner=claim.owner, fence=claim.fence)


def pending_action(run_id):
    """Classify saved work without contacting the broker or a provider."""
    run = OriginalContentRun.objects.get(pk=run_id)
    if 'attention' in run.decisions.get('graphics_skipped_stages', {}):
        return None
    content = OriginalContent.objects.get(run=run, output_key='graphics-primary/v1')
    selected = OriginalContentSelection.objects.filter(scope_key=f'featured:{content.workflow_key}:{run.snapshot["request"]["locale"]}', text__narrative__run=run).select_related('text').first()
    text = selected.text if selected else content.localized_texts.first()
    if text is None:
        if 'C1' in run.decisions.get('graphics_skipped_stages', {}):
            return None
        c1 = _stage_call(run_id, 'C1')
        if c1 and c1.state not in {'completed'}:
            return None
        g0 = _stage_call(run_id, 'G0')
        if g0 and g0.state not in {'completed', 'failed', 'ambiguous'}:
            return None
        return {'action': 'advance'}
    skipped = run.decisions.get('graphics_skipped_stages', {})
    a_call = _stage_call(run_id, 'I-A')
    b_call = _stage_call(run_id, 'I-B')
    video_a = _stage_call(run_id, 'V1')
    video_failure = (video_a and video_a.state == 'failed') or ContentPicture.objects.filter(run=run, provenance__schema_version='graphics-video-job/v1', provenance__candidate_id='A', state='failed').exists()
    failed_a = (a_call and a_call.state == 'failed') or video_failure
    if failed_a and 'I-B' not in skipped and (not b_call or b_call.state == 'completed' and text.provenance.get('candidate_id') == 'A'):
        return {'action': 'advance'}
    review_due = _stage_call(run_id, 'E1') is None and 'E1' not in skipped
    still = ContentPicture.objects.filter(run=run, text=text, provenance__role='still', state='complete').first()
    video_stage = 'V-B' if text.provenance.get('candidate_id') == 'B' else 'V1'
    video = _stage_call(run_id, video_stage)
    if still and video is None and video_stage not in skipped:
        return {'action': 'video', 'text_id': text.pk, 'review_due': False}
    job = ContentPicture.objects.filter(run=run, text=text, provenance__schema_version='graphics-video-job/v1', state='pending').first()
    if job and job.next_poll_at is not None and job.poll_count < 40:
        countdown = max(0, int((job.next_poll_at - timezone.now()).total_seconds()))
        return {'action': 'poll', 'picture_id': str(job.pk), 'countdown': countdown, 'review_due': False}
    if review_due:
        return {'action': 'review', 'review_due': True}
    return None


def finalize_if_done(run_id):
    """Close a released run only when no saved stage needs dispatch."""
    with transaction.atomic():
        run = OriginalContentRun.objects.select_for_update().get(pk=run_id)
        expired = (run.execution_state == 'running' and run.lease_until is not None
                   and run.lease_until <= timezone.now())
        if run.execution_state not in {'pending', 'preparing'} and not expired:
            return False
        if pending_action(run_id) is not None:
            return False
        uncertain = OriginalContentCall.objects.filter(run=run, state__in=['reserved', 'sent', 'ambiguous']).exists()
        pending_video = ContentPicture.objects.filter(run=run, provenance__schema_version='graphics-video-job/v1', state='pending').exists()
        no_copy = not OriginalContent.objects.filter(run=run, output_key='graphics-primary/v1', status='approved').exists()
        needs_attention = uncertain or pending_video or no_copy or 'attention' in run.decisions.get('graphics_skipped_stages', {})
        run.execution_state = 'suspended' if needs_attention else 'complete'
        run.outcome = {**run.outcome, 'graphics_state': 'attention_required' if needs_attention else 'finished'}
        if expired:
            run.fence += 1
            run.claim_owner = ''
            run.lease_until = None
        run.save(update_fields=['execution_state', 'outcome', 'fence', 'claim_owner', 'lease_until', 'updated_at'])
        return True
