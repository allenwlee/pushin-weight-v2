"""Provider request contracts; every transport is fake and offline."""

import base64
import hashlib
from pathlib import Path

import pytest

from monitor.editorial.graphics_contracts import load_pack
from monitor.editorial.graphics_generation import (
    build_image_request,
    build_text_request,
    build_video_request,
    poll_video,
)

PACK = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')


def asset(data=b'source image'):
    return {'asset_ref': 'person:1', 'role': 'identity_reference', 'data': data,
            'sha256': hashlib.sha256(data).hexdigest(), 'mime': 'image/jpeg'}


def test_c1_uses_one_schema_and_explicit_provider_route():
    request = build_text_request(PACK, 'C1', {'fact_items': []})
    assert request['endpoint'] == 'https://openrouter.ai/api/v1/chat/completions'
    assert request['body']['model'] == 'openai/gpt-6-sol'
    assert request['body']['provider']['allow_fallbacks'] is False
    assert request['body']['messages'][1]['content'].count('OUTPUT JSON SCHEMA FOR THIS REQUEST:') == 1


def test_image_prompt_and_real_reference_bytes_are_preserved():
    treatment = {'candidate_id': 'A', 'still_prompt': 'Draw the exact headline.',
                 'aspect_ratio': '3:4', 'input_asset_refs': [{'asset_ref': 'person:1', 'role': 'identity_reference'}]}
    request = build_image_request(PACK, 'I-A', treatment, [asset()])
    assert request['timeout'] >= 120
    assert request['endpoint'] == 'https://api.x.ai/v1/images/edits'
    assert request['body']['prompt'].startswith(PACK['media_preamble'])
    assert request['body']['images'][0]['url'] == 'data:image/jpeg;base64,' + base64.b64encode(b'source image').decode()
    assert request['body']['resolution'] == '1k'
    bad = asset(); bad['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='hash'):
        build_image_request(PACK, 'I-A', treatment, [bad])


def test_video_uses_exact_selected_still_and_five_seconds():
    treatment = {'candidate_id': 'A', 'motion_prompt': 'Blink once.'}
    request = build_video_request(PACK, 'V1', treatment, asset())
    assert request['body']['model'] == 'grok-imagine-video-1.5-lite'
    assert request['body']['duration'] == 5
    assert request['body']['resolution'] == '720p'
    assert base64.b64decode(request['body']['image']['url'].split(',', 1)[1]) == b'source image'
    with pytest.raises(ValueError, match='candidate'):
        build_video_request(PACK, 'V-B', treatment, asset())


def test_poll_requires_saved_id_and_never_submits_again():
    calls = []
    def transport(endpoint, key, payload, **kwargs):
        calls.append((endpoint, kwargs['method']))
        return 200, b'{"status":"pending"}'
    with pytest.raises(ValueError, match='request ID'):
        poll_video('', 'fake', transport=transport)
    assert not calls
    result = poll_video('saved-123', 'fake', transport=transport)
    assert result['state'] == 'pending'
    assert calls == [('https://api.x.ai/v1/videos/saved-123', 'GET')]


def test_request_recipe_roundtrip_checks_bytes_and_contains_no_embedded_images():
    from monitor.editorial.graphics_generation import (
        create_request_recipe,
        reconstruct_request,
    )

    body = {'model': 'example', 'image': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b'fixture').decode()}}
    entry = {'storage_alias': 'staff_media', 'storage_name': 'sha256/ab/file.jpg', 'mime': 'image/jpeg', 'sha256': hashlib.sha256(b'fixture').hexdigest()}
    packet, request_hash = create_request_recipe(body, [entry], load_bytes=lambda alias, name: b'fixture')
    assert 'Zml4dHVyZQ==' not in str(packet)
    assert reconstruct_request(packet, request_hash, load_bytes=lambda alias, name: b'fixture') == body
    with pytest.raises(ValueError, match='hash'):
        reconstruct_request(packet, request_hash, load_bytes=lambda alias, name: b'changed')
    with pytest.raises(ValueError):
        create_request_recipe(body, [{**entry, 'storage_alias': 'default'}], load_bytes=lambda alias, name: b'fixture')


def test_xai_uses_the_existing_bounded_authenticated_transport(monkeypatch):
    from x_monitor.provider_http import https_request

    calls = []
    class Connection:
        status = 200
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ('api.x.ai', 443, 140)
        def request(self, method, path, body, headers):
            assert method == 'POST' and path == '/v1/images/generations'
            calls.append('sent')
        def getresponse(self):
            return self
        def read(self, maximum):
            return b'{}'
        def close(self):
            calls.append('closed')
    monkeypatch.setattr('x_monitor.provider_http.http.client.HTTPSConnection', Connection)
    assert https_request('https://api.x.ai/v1/images/generations', 'test-only', {}, timeout=140) == (200, b'{}')
    assert calls == ['sent', 'closed']


def test_video_decode_receipt_requires_real_decodable_file(tmp_path):
    import subprocess

    import imageio_ffmpeg

    from monitor.editorial.graphics_generation import video_decode_receipt

    path = tmp_path / 'fixture.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=32x32:r=5', '-t', '5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
    data = path.read_bytes()
    sent = {'image': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b'still').decode()}}
    still_sha = hashlib.sha256(b'still').hexdigest()
    receipt = video_decode_receipt(data, run_id=42, producer_call_id=17, input_still_sha256=still_sha, sent_request=sent)
    assert receipt['sha256'] == hashlib.sha256(data).hexdigest()
    assert receipt['run_id'] == '42' and receipt['producer_call_id'] == 17
    assert receipt['input_still_sha256'] == still_sha
    with pytest.raises(ValueError, match='still'):
        video_decode_receipt(data, run_id=42, producer_call_id=17, input_still_sha256='a' * 64, sent_request=sent)
    assert 4500 <= receipt['duration_ms'] <= 5500
    with pytest.raises(ValueError, match='container|decode'):
        video_decode_receipt(b'not a video', run_id=42, producer_call_id=17, input_still_sha256=still_sha, sent_request=sent)
    short = tmp_path / 'short.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i',
                    'color=black:s=32x32:r=5', '-t', '1', '-c:v', 'libx264', str(short)], check=True)
    with pytest.raises(ValueError, match='duration'):
        video_decode_receipt(short.read_bytes(), run_id=42, producer_call_id=17,
                             input_still_sha256=still_sha, sent_request=sent)


def test_submit_once_reserves_marks_sent_and_never_resubmits_after_timeout():
    import json

    from monitor.editorial.graphics_generation import submit_once

    request = build_text_request(PACK, 'C1', {'fact_items': []})
    raw = json.dumps(request['body'], ensure_ascii=False)
    packet = {'schema_version': 'graphics-request/v1', 'request_json': raw}
    request_hash = hashlib.sha256(raw.encode()).hexdigest()
    events = []
    def reserve(*_args):
        events.append('reserve')
        return object(), events.count('reserve') == 1
    def mark_sent(_call):
        events.append('sent')
        return True
    def send(*_args, **_kwargs):
        events.append('network')
        raise TimeoutError('simulated')
    def ambiguous(_call, code):
        events.append(('ambiguous', code))
    def complete(*_args):
        pytest.fail('timed out request cannot complete')
    def fail(*_args):
        pytest.fail('timeout is not definite failure')
    kwargs = {'reserve': reserve, 'mark_sent': mark_sent, 'complete': complete,
              'ambiguous': ambiguous, 'fail': fail, 'transport': send}
    assert submit_once('C1', request, packet, request_hash, 'fake', PACK, **kwargs)['state'] == 'ambiguous'
    assert submit_once('C1', request, packet, request_hash, 'fake', PACK, **kwargs)['state'] == 'already_reserved'
    assert events.count('network') == 1
    assert events[:3] == ['reserve', 'sent', 'network']


def test_shared_geometry_normalization_preserves_original_and_records_adjustment():
    from monitor.editorial.graphics_contracts import normalize_treatments
    raw = {'treatments': [{'candidate_id': 'A', 'aspect_ratio': '7:9',
                           'still_prompt': 'Use a locked 7:9 frame.',
                           'motion_prompt': 'Keep a fixed 7:9 frame.'}]}
    normalized, adjustments = normalize_treatments(PACK, raw)
    assert raw['treatments'][0]['aspect_ratio'] == '7:9'
    assert normalized['treatments'][0]['aspect_ratio'] in PACK['media_capabilities']['image_aspect_ratios']
    assert adjustments[0]['requested'] == '7:9'
    assert adjustments[0]['submitted'] == normalized['treatments'][0]['aspect_ratio']


def test_submission_rejects_wrong_endpoint_before_reserving():
    import json

    from monitor.editorial.graphics_generation import submit_once

    request = build_text_request(PACK, 'C1', {'fact_items': []})
    raw = json.dumps(request['body'], ensure_ascii=False)
    packet = {'schema_version': 'graphics-request/v1', 'request_json': raw}
    request_hash = hashlib.sha256(raw.encode()).hexdigest()
    request['endpoint'] += '-not-the-api'
    def unexpected(*_args, **_kwargs):
        pytest.fail('no reservation or network request expected')
    with pytest.raises(ValueError, match='route'):
        submit_once('C1', request, packet, request_hash, 'fake', PACK,
                    reserve=unexpected, mark_sent=unexpected, complete=unexpected,
                    ambiguous=unexpected, fail=unexpected, transport=unexpected)


def test_video_decode_rejects_non_mp4_container_even_when_decodable(tmp_path):
    import subprocess

    import imageio_ffmpeg

    from monitor.editorial.graphics_generation import video_decode_receipt

    path = tmp_path / 'fixture.mkv'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i', 'color=black:s=32x32:r=5', '-t', '1', '-c:v', 'libx264', str(path)], check=True)
    sent = {'image': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b'still').decode()}}
    with pytest.raises(ValueError, match='container'):
        video_decode_receipt(path.read_bytes(), run_id=42, producer_call_id=17, input_still_sha256=hashlib.sha256(b'still').hexdigest(), sent_request=sent)
