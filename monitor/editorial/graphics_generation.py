"""Build the accepted Graphics provider requests and poll saved video jobs.

Construction is pure; credentials and network transports are supplied at runtime.
"""

import base64
import hashlib
import json
import re

from jsonschema.exceptions import ValidationError

from core.staff_assets.public_fetch import fetch_public_response
from monitor.editorial.graphics_contracts import (
    build_messages,
    normalize_treatments,
    validate_stage_output,
)
from x_monitor.provider_http import https_request

OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
XAI_IMAGES = 'https://api.x.ai/v1/images/'
XAI_VIDEOS = 'https://api.x.ai/v1/videos/'
TEXT_MODEL = 'openai/gpt-6-sol'
IMAGE_MODEL = 'grok-imagine-image-2.0'
VIDEO_MODEL = 'grok-imagine-video-1.5-lite'
MAX_INPUT_BYTES = 12 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MIME_TYPES = frozenset({'image/jpeg', 'image/png', 'image/webp'})
TERMINAL_FAILURES = frozenset({'failed', 'expired', 'canceled', 'cancelled', 'moderated'})


def _call(pack, stage):
    call = next((value for value in pack['model_call_plan']['calls'] if value['id'] == stage), None)
    if call is None:
        raise ValueError('Unknown Graphics stage')
    return call


def _data_uri(asset):
    data = asset.get('data')
    mime = asset.get('mime')
    if not isinstance(data, bytes) or not data or len(data) > MAX_INPUT_BYTES or mime not in MIME_TYPES:
        raise ValueError('Invalid image bytes or MIME')
    if hashlib.sha256(data).hexdigest() != asset.get('sha256'):
        raise ValueError('Image hash mismatch')
    return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')


def build_text_request(pack, stage, data, *, attachments=(), instruction=None):
    if stage not in {'C1', 'G0', 'G1', 'E1'}:
        raise ValueError('Not a Graphics language-model stage')
    messages = build_messages(pack, stage, data, instruction=instruction)
    if len(attachments) > 12:
        raise ValueError('Too many image attachments')
    content = [{'type': 'text', 'text': messages['task']}]
    for index, asset in enumerate(attachments, 1):
        content.append({'type': 'text', 'text': f"Image {index}: asset_ref={asset['asset_ref']}; role={asset['role']}"})
        content.append({'type': 'image_url', 'image_url': {'url': _data_uri(asset)}})
    body = {
        'model': TEXT_MODEL,
        'messages': [
            {'role': 'system', 'content': messages['system']},
            {'role': 'user', 'content': content if attachments else messages['task']},
        ],
        'max_tokens': 4096,
        'response_format': {'type': 'json_object'},
        'reasoning': {'effort': 'medium'},
        'provider': {'allow_fallbacks': False, 'require_parameters': True,
                     'max_price': {'prompt': 2.5, 'completion': 10.0}},
    }
    return {'endpoint': OPENROUTER_URL, 'body': body, 'timeout': 140}


def build_image_request(pack, stage, treatment, assets):
    if stage not in {'I-A', 'I-B'} or treatment.get('candidate_id') != stage[-1]:
        raise ValueError('Image candidate mismatch')
    mapping = {asset['asset_ref']: asset for asset in assets}
    if len(mapping) != len(assets):
        raise ValueError('Duplicate image asset reference')
    references = treatment['input_asset_refs']
    if len(references) > pack['media_capabilities']['max_image_inputs']:
        raise ValueError('Too many selected image inputs')
    inputs = [mapping[ref['asset_ref']] for ref in references]
    ratio = treatment['aspect_ratio']
    if ratio not in pack['media_capabilities']['image_aspect_ratios']:
        raise ValueError('Unsupported image ratio')
    prefix = _call(pack, stage)['system']
    prompt = treatment['still_prompt']
    if prompt.startswith(pack['media_preamble']):
        prompt = prompt[len(pack['media_preamble']):].lstrip()
    roles = '\n'.join(f"Input {index}: {asset['asset_ref']} ({ref['role']})" for index, (asset, ref) in enumerate(zip(inputs, references), 1))
    geometry = f'Output frame: {ratio}. This output setting overrides other canvas-size wording; preserve the headline exactly.'
    body = {'model': IMAGE_MODEL, 'prompt': prefix + '\n\n' + roles + '\n\n' + prompt + '\n\n' + geometry,
            'n': 1, 'aspect_ratio': ratio, 'resolution': '1k', 'quality': 'medium', 'response_format': 'b64_json'}
    if inputs:
        body['images'] = [{'type': 'image_url', 'url': _data_uri(asset)} for asset in inputs]
    return {'endpoint': XAI_IMAGES + ('edits' if inputs else 'generations'), 'body': body, 'timeout': 140}


def build_video_request(pack, stage, treatment, still):
    expected = {'V1': 'A', 'V-B': 'B'}.get(stage)
    if expected is None or treatment.get('candidate_id') != expected:
        raise ValueError('Video candidate mismatch')
    body = {'model': VIDEO_MODEL, 'prompt': _call(pack, stage)['system'] + '\n\n' + treatment['motion_prompt'],
            'duration': 5, 'resolution': '720p', 'image': {'url': _data_uri(still)}}
    return {'endpoint': XAI_VIDEOS + 'generations', 'body': body, 'timeout': 140}


def poll_video(request_id, api_key, *, transport=https_request, fetch=fetch_public_response):
    """Poll only a previously persisted job ID; never create a provider job."""
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', request_id):
        raise ValueError('A saved provider request ID is required')
    status_code, raw = transport(XAI_VIDEOS + request_id, api_key, None, timeout=30, method='GET')
    if status_code != 200:
        return {'state': 'unknown', 'http_status': status_code}
    try:
        reply = json.loads(raw)
    except (ValueError, TypeError):
        return {'state': 'unknown', 'error': 'invalid_provider_json'}
    if not isinstance(reply, dict):
        return {'state': 'unknown', 'error': 'invalid_provider_json'}
    status = reply.get('status')
    if status in TERMINAL_FAILURES:
        return {'state': 'failed', 'provider_status': status}
    if status == 'pending':
        return {'state': 'pending'}
    if status != 'done' or not isinstance(reply.get('video'), dict) or not reply['video'].get('url'):
        return {'state': 'unknown', 'error': 'invalid_provider_status'}
    try:
        data, final_url, mime = fetch(reply['video']['url'], max_bytes=MAX_VIDEO_BYTES)
    except (OSError, ValueError, TimeoutError):
        return {'state': 'pending', 'error': 'video_download_unavailable'}
    if not data or len(data) > MAX_VIDEO_BYTES:
        return {'state': 'pending', 'error': 'video_download_invalid'}
    return {'state': 'completed', 'data': data, 'sha256': hashlib.sha256(data).hexdigest(),
            'source_url': final_url, 'content_type': mime, 'usage': reply.get('usage') or {}}


_RECIPE_FIELDS = frozenset({'schema_version', 'request_template', 'assets'})
_ASSET_FIELDS = frozenset({'placeholder', 'storage_alias', 'storage_name', 'mime', 'sha256'})
_ALLOWED_STORAGE = frozenset({'staff_media', 'editorial_media'})
_MARKER = 'graphics-asset://'
_MAX_TOTAL_INPUT_BYTES = 24 * 1024 * 1024
_MAX_TEMPLATE_BYTES = 300000


def _load_storage_bytes(alias, name):
    from django.core.files.storage import storages

    with storages[alias].open(name, 'rb') as stream:
        return stream.read(MAX_INPUT_BYTES + 1)


def _validate_reference(ref, loader):
    from pathlib import PurePosixPath

    if not isinstance(ref, dict) or set(ref) != _ASSET_FIELDS:
        raise ValueError('Invalid asset recipe fields')
    alias, name, mime, sha = (ref[key] for key in ('storage_alias', 'storage_name', 'mime', 'sha256'))
    if alias not in _ALLOWED_STORAGE or mime not in MIME_TYPES:
        raise ValueError('Invalid asset storage or MIME')
    if (not isinstance(name, str) or not name or len(name) > 1024 or '\\' in name
            or PurePosixPath(name).is_absolute() or any(part in {'.', '..'} for part in name.split('/'))):
        raise ValueError('Invalid asset storage name')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha):
        raise ValueError('Invalid asset hash')
    data = loader(alias, name)
    if not isinstance(data, bytes) or not data or len(data) > MAX_INPUT_BYTES:
        raise ValueError('Invalid stored asset size')
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError('Stored asset hash mismatch')
    return _data_uri({'data': data, 'mime': mime, 'sha256': sha}), len(data)


def _transform(value, mapping, counts, *, reject_data):
    if isinstance(value, dict):
        return {key: _transform(item, mapping, counts, reject_data=reject_data) for key, item in value.items()}
    if isinstance(value, list):
        return [_transform(item, mapping, counts, reject_data=reject_data) for item in value]
    if isinstance(value, str):
        if value in mapping:
            counts[value] += 1
            return mapping[value]
        if value.startswith(_MARKER) or (reject_data and value.startswith('data:')):
            raise ValueError('Unbound request asset')
    return value


def create_request_recipe(body, references, *, load_bytes=None):
    """Replace exact stored input data URIs with bounded, validated references.

    Returns a small JSON-safe packet and the hash of the actual HTTP JSON bytes.
    The caller must reconstruct and verify those bytes immediately before send.
    """
    if not isinstance(body, dict) or not isinstance(references, (list, tuple)) or len(references) > 12:
        raise ValueError('Invalid request recipe')
    loader = load_bytes or _load_storage_bytes
    entries, replacements = [], {}
    total = 0
    for index, value in enumerate(references):
        if not isinstance(value, dict) or set(value) != _ASSET_FIELDS - {'placeholder'}:
            raise ValueError('Invalid asset recipe fields')
        ref = {'placeholder': _MARKER + str(index), **value}
        uri, size = _validate_reference(ref, loader)
        total += size
        if uri in replacements:
            raise ValueError('Duplicate request asset')
        replacements[uri] = ref['placeholder']
        entries.append(ref)
    if total > _MAX_TOTAL_INPUT_BYTES:
        raise ValueError('Request assets exceed total size')
    counts = dict.fromkeys(replacements, 0)
    template = _transform(body, replacements, counts, reject_data=True)
    if any(count != 1 for count in counts.values()):
        raise ValueError('Each asset must have exactly one request placeholder')
    template_json = json.dumps(template, ensure_ascii=False)
    if len(template_json.encode()) > _MAX_TEMPLATE_BYTES:
        raise ValueError('Request template exceeds limit')
    packet = {'schema_version': 'graphics-request/v2', 'request_template': template_json, 'assets': entries}
    wire = json.dumps(body, ensure_ascii=False).encode()
    return packet, hashlib.sha256(wire).hexdigest()


def reconstruct_request(packet, request_hash, *, load_bytes=None):
    """Reconstruct exact request JSON from saved references and check its hash."""
    if (not isinstance(packet, dict) or set(packet) != _RECIPE_FIELDS
            or packet['schema_version'] != 'graphics-request/v2'
            or not isinstance(packet['request_template'], str)
            or len(packet['request_template'].encode()) > _MAX_TEMPLATE_BYTES
            or not isinstance(packet['assets'], list) or len(packet['assets']) > 12
            or not isinstance(request_hash, str) or not re.fullmatch(r'[0-9a-f]{64}', request_hash)):
        raise ValueError('Invalid request recipe')
    try:
        template = json.loads(packet['request_template'])
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid request template') from exc
    if not isinstance(template, dict):
        raise TypeError('Invalid request template')
    loader = load_bytes or _load_storage_bytes
    replacements, total = {}, 0
    for index, ref in enumerate(packet['assets']):
        if not isinstance(ref, dict) or ref.get('placeholder') != _MARKER + str(index):
            raise ValueError('Invalid or duplicate asset placeholder')
        uri, size = _validate_reference(ref, loader)
        total += size
        replacements[ref['placeholder']] = uri
    if total > _MAX_TOTAL_INPUT_BYTES:
        raise ValueError('Request assets exceed total size')
    counts = dict.fromkeys(replacements, 0)
    body = _transform(template, replacements, counts, reject_data=True)
    if any(count != 1 for count in counts.values()):
        raise ValueError('Each asset must have exactly one request placeholder')
    if hashlib.sha256(json.dumps(body, ensure_ascii=False).encode()).hexdigest() != request_hash:
        raise ValueError('Reconstructed request hash mismatch')
    return body


def video_decode_receipt(data, *, run_id, producer_call_id, input_still_sha256, sent_request):
    """Fully decode a bounded video before constructing its immutable receipt."""
    import subprocess
    import tempfile
    from pathlib import Path

    import imageio_ffmpeg

    if (not isinstance(data, bytes) or not data or len(data) > MAX_VIDEO_BYTES
            or not isinstance(run_id, (str, int)) or isinstance(run_id, bool) or not str(run_id)
            or type(producer_call_id) is not int or producer_call_id <= 0
            or not isinstance(input_still_sha256, str)
            or not re.fullmatch(r'[0-9a-f]{64}', input_still_sha256)):
        raise ValueError('Invalid video decode input')
    if len(data) < 12 or data[4:8] != b'ftyp' or data[8:12] == b'qt  ':
        raise ValueError('Video container is not MP4')
    try:
        uri = sent_request['image']['url']
        prefix, encoded = uri.split(',', 1)
        if prefix not in {f'data:{mime};base64' for mime in MIME_TYPES}:
            raise ValueError('Invalid sent still MIME')
        if len(encoded) > ((MAX_INPUT_BYTES + 2) // 3) * 4:
            raise ValueError('Sent still exceeds size limit')
        still_bytes = base64.b64decode(encoded, validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Invalid sent still input') from exc
    if not still_bytes or len(still_bytes) > MAX_INPUT_BYTES or hashlib.sha256(still_bytes).hexdigest() != input_still_sha256:
        raise ValueError('Sent still hash mismatch')
    with tempfile.TemporaryDirectory(prefix='graphics-video-') as tmp:
        source = Path(tmp) / 'video.mp4'
        source.write_bytes(data)
        log = Path(tmp) / 'ffmpeg.log'
        try:
            with log.open('wb') as errors:
                result = subprocess.run(
                    [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-threads', '1',
                     '-i', str(source), '-map', '0:v:0', '-an', '-f', 'null', '-'],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=errors, timeout=45, check=False,
                )
            with log.open('rb') as errors:
                details = errors.read(65536).decode('utf-8', 'replace')
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('Video decode unavailable') from exc
    if not re.search(r'Input #0, [^\n]*\bmp4\b', details):
        raise ValueError('Video container is not MP4')
    match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', details)
    frames = re.findall(r'frame=\s*(\d+)', details)
    if result.returncode != 0 or not match or not frames or int(frames[-1]) < 1:
        raise ValueError('Video decode failed')
    duration_ms = round((int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))) * 1000)
    if not 1 <= duration_ms <= 15000:
        raise ValueError('Video decode duration out of bounds')
    return {
        'schema_version': 'graphics-video-decode/v1',
        'sha256': hashlib.sha256(data).hexdigest(),
        'mime': 'video/mp4',
        'run_id': str(run_id),
        'producer_call_id': producer_call_id,
        'duration_ms': duration_ms,
        'input_still_sha256': input_still_sha256,
    }


def _wire_body(packet, request_hash, load_bytes):
    if not isinstance(packet, dict):
        raise TypeError('Invalid request packet')
    if packet.get('schema_version') == 'graphics-request/v2':
        return reconstruct_request(packet, request_hash, load_bytes=load_bytes)
    if set(packet) != {'schema_version', 'request_json'} or packet.get('schema_version') != 'graphics-request/v1':
        raise ValueError('Invalid request packet')
    raw = packet['request_json']
    if not isinstance(raw, str) or len(raw.encode()) > _MAX_TEMPLATE_BYTES:
        raise ValueError('Invalid request packet')
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise ValueError('Invalid request packet JSON') from exc
    if not isinstance(body, dict) or hashlib.sha256(json.dumps(body, ensure_ascii=False).encode()).hexdigest() != request_hash:
        raise ValueError('Request hash mismatch')
    _transform(body, {}, {}, reject_data=True)
    return body


def submit_once(stage, request, packet, request_hash, api_key, pack, *, reserve,
                mark_sent, complete, ambiguous, fail, transport=https_request, load_bytes=None):
    """Run one guarded provider submission; callbacks own durable state transitions.

    The reservation callback returns ``(call, may_send)``. ``complete`` receives
    the call, decoded provider payload, image bytes (or None), and provider usage;
    it must save image bytes before committing the call. No exception triggers a resend.
    """
    if stage not in {'C1', 'G0', 'G1', 'E1', 'I-A', 'I-B', 'V1', 'V-B'}:
        raise ValueError('Unknown Graphics stage')
    if (not isinstance(request, dict) or not isinstance(request.get('endpoint'), str)
            or type(request.get('timeout')) is not int or not 120 <= request['timeout'] <= 150
            or not isinstance(api_key, str) or not api_key):
        raise ValueError('Invalid Graphics provider route')
    # Verify reference availability/hash and exact route before reserving budget.
    body = _wire_body(packet, request_hash, load_bytes)
    if stage in {'C1', 'G0', 'G1', 'E1'}:
        expected_url, expected_model = OPENROUTER_URL, TEXT_MODEL
    elif stage in {'I-A', 'I-B'}:
        expected_url = XAI_IMAGES + ('edits' if body.get('images') else 'generations')
        expected_model = IMAGE_MODEL
    else:
        expected_url, expected_model = XAI_VIDEOS + 'generations', VIDEO_MODEL
    if request['endpoint'] != expected_url or body.get('model') != expected_model or request.get('body') != body:
        raise ValueError('Invalid Graphics provider route or request body')
    call, may_send = reserve(packet, request_hash)
    if not may_send:
        return {'state': 'already_reserved', 'call': call}
    # Re-read the stored input bytes immediately before marking sent and transport.
    try:
        body = _wire_body(packet, request_hash, load_bytes)
    except (OSError, ValueError, TypeError):
        fail(call, 'pre_send:request_reconstruction')
        return {'state': 'failed', 'error': 'request_reconstruction'}
    if not mark_sent(call):
        return {'state': 'stale_claim', 'call': call}
    try:
        status, raw = transport(request['endpoint'], api_key, body, timeout=request['timeout'], max_bytes=24 * 1024 * 1024)
    except Exception:  # noqa: BLE001 -- an unknown post-send outcome must not be retried
        ambiguous(call, 'provider_transport_unknown')
        return {'state': 'ambiguous', 'error': 'provider_transport_unknown'}
    if not 200 <= status < 300:
        if status in {400, 401, 403, 404, 422}:
            fail(call, f'provider_http_{status}')
            return {'state': 'failed', 'http_status': status}
        ambiguous(call, f'provider_http_{status}')
        return {'state': 'ambiguous', 'http_status': status}
    try:
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise TypeError('provider response must be an object')
        image_bytes = None
        if stage in {'C1', 'G0', 'G1', 'E1'}:
            if decoded.get('model') != TEXT_MODEL:
                raise ValueError('provider model mismatch')
            choices = decoded.get('choices')
            if not isinstance(choices, list) or len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                raise ValueError('provider completion incomplete')
            payload = json.loads(choices[0]['message']['content'])
            if not isinstance(payload, dict):
                raise TypeError('provider output must be an object')
            normalized = normalize_treatments(pack, payload)[0] if stage == 'G1' else payload
            validate_stage_output(pack, stage, normalized)
        elif stage in {'I-A', 'I-B'}:
            from io import BytesIO

            from PIL import Image

            outputs = decoded.get('data')
            if not isinstance(outputs, list) or len(outputs) != 1:
                raise ValueError('Expected one image')
            image_bytes = base64.b64decode(outputs[0]['b64_json'], validate=True)
            if not image_bytes or len(image_bytes) > MAX_INPUT_BYTES:
                raise ValueError('Generated image size invalid')
            with Image.open(BytesIO(image_bytes)) as image:
                image.verify()
                fmt = image.format
            mime = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}.get(fmt)
            if mime is None:
                raise ValueError('Generated image type unsupported')
            payload = {'sha256': hashlib.sha256(image_bytes).hexdigest(), 'mime': mime,
                       'usage': decoded.get('usage') or {}}
        else:
            request_id = decoded.get('request_id')
            if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', request_id):
                raise ValueError('Missing provider request ID')
            payload = {'request_id': request_id, 'usage': decoded.get('usage') or {}}
    except (ValueError, TypeError, KeyError, IndexError, OSError, ValidationError):
        # A 200 response with an unusable job ID could still have accepted work.
        if stage in {'V1', 'V-B'}:
            ambiguous(call, 'provider_response_invalid')
            return {'state': 'ambiguous', 'error': 'provider_response_invalid'}
        fail(call, 'provider_response_invalid')
        return {'state': 'failed', 'error': 'provider_response_invalid'}
    try:
        if complete(call, payload, image_bytes, decoded.get('usage') or {}) is False:
            raise ValueError('result persistence rejected')
    except Exception:  # noqa: BLE001 -- provider accepted; preserve charge and never resubmit
        ambiguous(call, 'result_persistence_unknown')
        return {'state': 'ambiguous', 'error': 'result_persistence_unknown'}
    return {'state': 'completed', 'call': call, 'payload': payload, 'usage': decoded.get('usage') or {}}
