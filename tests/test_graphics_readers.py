"""Graphics assets must belong to the selected, saved edition."""

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.models import ContentPicture, OriginalContentCall
from monitor.editorial.config import EditorialConfig
from tests.test_graphics_publication import publication_case  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


@pytest.fixture
def graphic_edition(publication_case, tmp_path, monkeypatch):  # noqa: F811
    from monitor.editorial.graphics_publication import publish_primary
    from monitor.original_content_readers import saved_edition

    pack, content, c1 = publication_case
    text = publish_primary(content=content, producer=c1, pack=pack, sources=[{
        'id': '123', 'url': 'https://x.com/i/status/123',
        'original_text': 'Saved source', 'author_handle': 'original',
    }])
    now = timezone.now()
    producer = OriginalContentCall.objects.create(run=content.run, stage=f'gfx:{content.run_id}:I-A', workflow_key=content.workflow_key, kind='media', request_identity=f'graphics:{content.run_id}:I-A', request_hash='a'*64, response_hash='b'*64, state='completed', reserved_at=now, sent_at=now, completed_at=now)
    image = BytesIO()
    Image.new('RGB', (2, 2), 'red').save(image, format='PNG')
    data = image.getvalue()
    (tmp_path / 'selected.png').write_bytes(data)
    picture = ContentPicture.objects.create(run=content.run, text=text, content_kind='chatter', content_id=str(text.public_id), revision_hash='1'*64, mode='derive', state='complete', generated_storage_name='selected.png', generated_sha256=hashlib.sha256(data).hexdigest(), provenance={'schema_version':'graphics-artifact/v1', 'role':'still', 'candidate_id':'A', 'mime':'image/png', 'producer_call_id':producer.pk, 'content_id':str(content.pk)})
    storage = FileSystemStorage(location=tmp_path)
    monkeypatch.setenv('ORIGINAL_CONTENT_STORAGE', 'shared')
    monkeypatch.setattr('monitor.editorial.graphics_artifacts.storages', {'editorial_media': storage})
    monkeypatch.setattr('monitor.editorial.views.storages', {'editorial_media': storage})
    monkeypatch.setattr('monitor.editorial.graphics_reading.storages', {'editorial_media': storage})
    cfg = EditorialConfig(public_enabled=True, pictures={'chatter':'select_only'})
    monkeypatch.setattr('monitor.editorial.views.load_editorial_config', lambda: cfg)
    return saved_edition(text), picture, storage, cfg


def test_selected_still_uses_generated_file_and_exact_mime(client, graphic_edition):
    from monitor.editorial.readers import edition_payload

    edition, picture, _, cfg = graphic_edition
    item = edition_payload(edition, cfg)
    assert item['asset']['type'] == 'image'
    response = client.get(item['asset']['url'], secure=True)
    assert response.status_code == 200
    assert response['Content-Type'] == 'image/png'
    assert b''.join(response.streaming_content).startswith(b'\x89PNG')
    assert picture.text_id == edition._original_content_text.pk


def test_corrupt_still_is_omitted_but_copy_remains(client, graphic_edition):
    from monitor.editorial.graphics_reading import graphics_assets
    from monitor.editorial.readers import edition_payload

    edition, picture, storage, cfg = graphic_edition
    Path(storage.path('selected.png')).write_bytes(b'not an image')
    item = edition_payload(edition, cfg)
    assert item['headline'] == 'Ram I Am' and item['asset']['type'] == 'image'
    assert graphics_assets(edition) is None
    url = reverse('editorial_asset', kwargs={'story_id':edition.story_id, 'picture_id':picture.pk, 'variant':'generated'})
    assert client.get(url, secure=True).status_code == 404


def test_cross_run_or_unselected_asset_cannot_be_served(client, graphic_edition):
    edition, picture, _, _ = graphic_edition
    picture.provenance = {**picture.provenance, 'candidate_id': 'B'}
    picture.save(update_fields=['provenance'])
    url = reverse('editorial_asset', kwargs={'story_id':edition.story_id, 'picture_id':picture.pk, 'variant':'generated'})
    assert client.get(url, secure=True).status_code == 404


def _video(graphic_edition, *, selected_hash=None):
    import subprocess

    import imageio_ffmpeg

    edition, still, storage, _ = graphic_edition
    text = edition._original_content_text
    now = timezone.now()
    call = OriginalContentCall.objects.create(run=text.narrative.run, stage=f'gfx:{text.narrative.run_id}:V1', workflow_key=text.narrative.workflow_key, kind='media', request_identity=f'graphics:{text.narrative.run_id}:V1', request_hash='c'*64, response_hash='d'*64, state='completed', reserved_at=now, sent_at=now, completed_at=now)
    output = Path(storage.path('video.mp4'))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=32x32:r=5:d=5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-y', str(output)], check=True, capture_output=True)
    data = output.read_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    receipt = {'schema_version':'graphics-video-decode/v1', 'sha256':checksum, 'mime':'video/mp4', 'run_id':str(text.narrative.run_id), 'producer_call_id':call.pk, 'duration_ms':5000, 'input_still_sha256':selected_hash or still.generated_sha256}
    return ContentPicture.objects.create(run=text.narrative.run, text=text, content_kind='chatter', content_id=str(text.public_id), revision_hash='2'*64, mode='derive', state='complete', generated_storage_name='video.mp4', generated_sha256=checksum, provenance={'schema_version':'graphics-artifact/v1', 'role':'video', 'candidate_id':'A', 'mime':'video/mp4', 'producer_call_id':call.pk, 'content_id':str(text.narrative.pk), 'decode_receipt':receipt})


def test_verified_video_uses_selected_still_as_poster(client, graphic_edition):
    from monitor.editorial.readers import edition_payload

    edition, still, _, cfg = graphic_edition
    video = _video(graphic_edition)
    item = edition_payload(edition, cfg)
    assert item['asset']['type'] == 'video'
    assert str(video.pk) in item['asset']['url']
    assert str(still.pk) in item['asset']['poster']
    response = client.get(item['asset']['url'], secure=True)
    assert response.status_code == 200 and response['Content-Type'] == 'video/mp4'
    response.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize('viewport', [{'width': 390, 'height': 844}, {'width': 1440, 'height': 900}])
def test_story_video_keeps_poster_without_prefetching(live_server, graphic_edition, settings, viewport):
    from playwright.sync_api import sync_playwright

    edition, still, storage, _ = graphic_edition
    video = _video(graphic_edition)
    Path(storage.path('video.mp4')).write_bytes(b'corrupt')
    settings.SECURE_SSL_REDIRECT = False
    requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport=viewport, extra_http_headers={'X-Forwarded-Proto': 'https'})
        page.on('request', lambda request: requests.append(request.url))
        url = live_server.url + reverse('editorial_story', kwargs={'story_id': edition.story_id})
        page.goto(url, wait_until='networkidle')
        element = page.locator('video')
        assert element.count() == 1 and element.is_visible()
        assert element.get_attribute('preload') == 'none'
        assert str(still.pk) in element.get_attribute('poster')
        assert any(str(still.pk) in url for url in requests)
        assert not any(str(video.pk) in url for url in requests)
        with page.expect_response(lambda response: str(video.pk) in response.url) as failed:
            element.evaluate('(video) => video.load()')
        assert failed.value.status == 404
        assert element.is_visible() and str(still.pk) in element.get_attribute('poster')
        browser.close()


def test_still_request_does_not_read_the_video(client, graphic_edition, monkeypatch):
    edition, still, storage, _ = graphic_edition
    _video(graphic_edition)
    opened = []
    original_open = storage.open

    def record_open(name, *args, **kwargs):
        opened.append(name)
        return original_open(name, *args, **kwargs)

    monkeypatch.setattr(storage, 'open', record_open)
    url = reverse('editorial_asset', kwargs={'story_id': edition.story_id, 'picture_id': still.pk, 'variant': 'generated'})
    response = client.get(url, secure=True)
    assert response.status_code == 200
    assert 'selected.png' in opened
    assert 'video.mp4' not in opened
    response.close()


def test_wrong_video_lineage_or_corrupt_bytes_fall_back_to_still(client, graphic_edition):
    from monitor.editorial.graphics_reading import graphics_assets
    from monitor.editorial.readers import edition_payload

    edition, still, storage, cfg = graphic_edition
    video = _video(graphic_edition, selected_hash='0'*64)
    item = edition_payload(edition, cfg)
    assert item['asset']['type'] == 'image' and str(still.pk) in item['asset']['url']
    video_url = reverse('editorial_asset', kwargs={'story_id':edition.story_id, 'picture_id':video.pk, 'variant':'generated'})
    assert client.get(video_url, secure=True).status_code == 404
    video.provenance['decode_receipt']['input_still_sha256'] = still.generated_sha256
    video.save(update_fields=['provenance'])
    Path(storage.path('video.mp4')).write_bytes(b'corrupt')
    item = edition_payload(edition, cfg)
    assert item['asset']['type'] == 'video' and str(still.pk) in item['asset']['poster']
    assert graphics_assets(edition).video is None
    assert client.get(video_url, secure=True).status_code == 404


def test_feed_does_not_open_video_but_media_request_verifies_it(client, graphic_edition, monkeypatch):
    from monitor.editorial.readers import edition_payload

    edition, _, storage, cfg = graphic_edition
    video = _video(graphic_edition)
    opened = []
    original_open = storage.open
    def record_open(name, *args, **kwargs):
        opened.append(name)
        return original_open(name, *args, **kwargs)
    monkeypatch.setattr(storage, 'open', record_open)
    item = edition_payload(edition, cfg)
    assert item['asset']['type'] == 'video' and not opened
    assert str(video.pk) in item['asset']['url']
    response = client.get(item['asset']['url'], secure=True)
    assert response.status_code == 200
    assert 'video.mp4' in opened
    response.close()


def test_video_range_requests_serve_verified_snapshot(client, graphic_edition):
    from monitor.editorial.readers import edition_payload

    edition, _, storage, cfg = graphic_edition
    _video(graphic_edition)
    data = Path(storage.path('video.mp4')).read_bytes()
    url = edition_payload(edition, cfg)['asset']['url']
    response = client.get(url, secure=True, HTTP_RANGE='bytes=7-29')
    assert response.status_code == 206
    assert response['Content-Range'] == f'bytes 7-29/{len(data)}'
    assert response['Content-Length'] == '23'
    assert b''.join(response.streaming_content) == data[7:30]
    response = client.get(url, secure=True, HTTP_RANGE='bytes=-12')
    assert response.status_code == 206 and b''.join(response.streaming_content) == data[-12:]
    response = client.get(url, secure=True, HTTP_RANGE=f'bytes={len(data)}-')
    assert response.status_code == 416 and response['Content-Range'] == f'bytes */{len(data)}'
    response = client.get(url, secure=True, HTTP_RANGE='bytes=0-9', HTTP_IF_RANGE='"different"')
    assert response.status_code == 200 and b''.join(response.streaming_content) == data


def test_remote_overwrite_after_validation_cannot_change_served_bytes(client, graphic_edition, monkeypatch):
    from monitor.editorial.readers import edition_payload

    edition, _, backing, cfg = graphic_edition
    _video(graphic_edition)
    url = edition_payload(edition, cfg)['asset']['url']
    original = Path(backing.path('video.mp4')).read_bytes()

    class MutableRemote:
        payload = original
        def __init__(self):
            self.video_reads = 0
        def open(self, name, *args, **kwargs):
            if name == 'video.mp4':
                self.video_reads += 1
                remote = self
                class MutatingSnapshot(BytesIO):
                    def close(self):
                        remote.payload = b'replaced after snapshot was read'
                        super().close()
                return MutatingSnapshot(self.payload)
            return backing.open(name, *args, **kwargs)

    remote = MutableRemote()
    for name in ('monitor.editorial.graphics_artifacts.storages',
                 'monitor.editorial.graphics_reading.storages', 'monitor.editorial.views.storages'):
        monkeypatch.setattr(name, {'editorial_media': remote})
    response = client.get(url, secure=True)
    assert remote.video_reads == 1 and response.status_code == 200 and 'Location' not in response
    assert remote.payload == b'replaced after snapshot was read'
    assert b''.join(response.streaming_content) == original
    assert client.get(url, secure=True).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_snapshot_capacity_releases_on_response_close_and_disconnect(client, graphic_edition, monkeypatch):
    from tempfile import SpooledTemporaryFile
    from threading import BoundedSemaphore

    from monitor.editorial.readers import edition_payload

    edition, _, _, cfg = graphic_edition
    _video(graphic_edition)
    url = edition_payload(edition, cfg)['asset']['url']
    monkeypatch.setattr('monitor.editorial.views._graphics_snapshot_slots', BoundedSemaphore(1))
    snapshots = []
    def make_snapshot(*args, **kwargs):
        result = SpooledTemporaryFile(*args, **kwargs)  # noqa: SIM115 -- response owns its lifetime
        snapshots.append(result)
        return result
    monkeypatch.setattr('monitor.editorial.views.SpooledTemporaryFile', make_snapshot)

    first = client.get(url, secure=True)
    assert first.status_code == 200
    busy = client.get(url, secure=True)
    assert busy.status_code == 503 and busy['Retry-After'] == '2'
    release = first._resource_closers[-1]
    first.close()
    release()  # Duplicate cleanup must not release an extra slot.

    partial = client.get(url, secure=True, HTTP_RANGE='bytes=0-9')
    assert partial.status_code == 206
    assert client.get(url, secure=True).status_code == 503
    partial.close()  # Disconnect before the body iterator is started.
    assert snapshots[-1].closed
    after_disconnect = client.get(url, secure=True)
    assert after_disconnect.status_code == 200
    after_disconnect.close()


def test_snapshot_capacity_releases_after_bad_bytes_and_invalid_range(client, graphic_edition, monkeypatch):
    from threading import BoundedSemaphore

    from monitor.editorial.readers import edition_payload

    edition, _, storage, cfg = graphic_edition
    _video(graphic_edition)
    url = edition_payload(edition, cfg)['asset']['url']
    monkeypatch.setattr('monitor.editorial.views._graphics_snapshot_slots', BoundedSemaphore(1))
    path = Path(storage.path('video.mp4'))
    original = path.read_bytes()
    path.write_bytes(b'corrupt')
    assert client.get(url, secure=True).status_code == 404
    path.write_bytes(original)
    invalid = client.get(url, secure=True, HTTP_RANGE=f'bytes={len(original)}-')
    assert invalid.status_code == 416
    # An unsatisfiable range closes its snapshot immediately.
    valid = client.get(url, secure=True)
    assert valid.status_code == 200
    valid.close()


@pytest.mark.django_db(transaction=True)
def test_wsgi_file_wrapper_close_is_not_recursive():
    from tempfile import SpooledTemporaryFile
    from threading import BoundedSemaphore

    from django.core.signals import request_finished
    from django.test import RequestFactory

    from monitor.editorial.views import _snapshot_release, graphics_snapshot_response

    slots = BoundedSemaphore(1)
    assert slots.acquire(blocking=False)
    snapshot = SpooledTemporaryFile(max_size=10, mode='w+b')  # noqa: SIM115 -- response owns it
    snapshot.write(b'valid')
    response = graphics_snapshot_response(RequestFactory().get('/'), snapshot, 5, 'a'*64,
                                          'image/png', _snapshot_release(slots))
    events = []
    def finished(**kwargs):
        events.append(1)
    request_finished.connect(finished, weak=False)
    try:
        # Django's WSGIHandler assigns exactly this callback when a server
        # supplies wsgi.file_wrapper; the server then closes the wrapped file.
        snapshot.close = response.close
        snapshot.close()
        assert snapshot.closed and response.closed and len(events) == 1
        assert slots.acquire(blocking=False)
        slots.release()
    finally:
        request_finished.disconnect(finished)


def test_missing_receipt_and_private_source_fail_closed(client, graphic_edition):
    from monitor.editorial.readers import edition_payload

    edition, _, _, cfg = graphic_edition
    video = _video(graphic_edition)
    del video.provenance['decode_receipt']
    video.save(update_fields=['provenance'])
    item = edition_payload(edition, cfg)
    assert item['asset']['type'] == 'image'
    url = reverse('editorial_asset', kwargs={'story_id':edition.story_id, 'picture_id':video.pk, 'variant':'source'})
    assert client.get(url, secure=True).status_code == 404


def test_cross_run_attachment_does_not_appear(client, graphic_edition):
    from uuid import uuid4

    from core.models import OriginalContentRun
    from monitor.editorial.readers import edition_payload

    edition, picture, _, cfg = graphic_edition
    other_run = OriginalContentRun.objects.create(source_cycle_id=str(uuid4()), workflow_key='editorial-dispatch', scope_key=str(uuid4()), facts_as_of=timezone.now(), packet_schema_version=1, snapshot={})
    picture.run = other_run
    picture.save(update_fields=['run'])
    assert edition_payload(edition, cfg)['asset'] is None
    url = reverse('editorial_asset', kwargs={'story_id':edition.story_id, 'picture_id':picture.pk, 'variant':'generated'})
    assert client.get(url, secure=True).status_code == 404
