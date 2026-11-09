"""Exercise the selected-story entry and actual tasks with fake providers."""

import base64
import io
import json
import subprocess

import imageio_ffmpeg
import pytest
from PIL import Image

from core.models import ContentPicture, OriginalContentCall
from monitor import tasks
from monitor.editorial import (
    graphics_dispatch,
    graphics_entry,
    graphics_pipeline,
    graphics_video,
)
from tests.editorial_support import (
    editorial_storage as editorial_storage,  # noqa: PLC0414
)
from tests.test_graphics_pipeline import c1, selected_run

pytestmark = [pytest.mark.django_db, pytest.mark.requires_postgres]


def test_selected_story_advances_through_real_tasks_with_fake_providers(editorial_storage, monkeypatch, tmp_path):
    run, _ = selected_run()
    source = run.snapshot['request']
    queued = []
    monkeypatch.setattr(graphics_dispatch, '_enqueue',
                        lambda task, args, *, queue, countdown=0: queued.append((task, args)) or True)
    discovery = {'schema_version': 'graphics-discovery/v3', 'queries': [], 'preferred_sites': [],
                 'reuse_asset_refs': [], 'approaches': [
                     {'candidate_id': label, 'approach': 'original_visual_concept',
                      'reason': 'Original idea.', 'reference_target': None} for label in ('A', 'B')]}
    design = {'schema_version': 'graphics-treatments/v2', 'source_gaps': [], 'treatments': [
        {'candidate_id': label, 'idea': 'A graphic.', 'why_it_bites': 'A joke.', 'input_asset_refs': [],
         'aspect_ratio': '1:1', 'still_prompt': 'Draw it.', 'motion_prompt': 'Move it.'} for label in ('A', 'B')]}
    responses = iter([c1(), discovery, design])
    image = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(image, format='PNG')

    def provider(url, key, body, **kwargs):
        if '/images/' in url:
            return 200, json.dumps({'data': [{'b64_json': base64.b64encode(image.getvalue()).decode()}]}).encode()
        if '/videos/' in url:
            return 200, b'{"request_id":"fake-video-job"}'
        return 200, json.dumps({'model': 'openai/gpt-6-sol', 'usage': {'cost': 0.01},
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(next(responses))}}]}).encode()

    actual_advance = graphics_pipeline.advance_step
    actual_submit = graphics_video.submit_video_job
    actual_poll = graphics_video.poll_video_job
    actual_review = graphics_pipeline.review_step
    monkeypatch.setattr(graphics_pipeline, 'advance_step', lambda run_id: actual_advance(
        run_id, keys={'OPENROUTER_API_KEY': 'fake', 'XAI_API_KEY_PW': 'fake'}, transport=provider))
    monkeypatch.setattr(graphics_video, 'submit_video_job', lambda run_id, text_id, **kwargs: actual_submit(
        run_id, text_id, api_key='fake', transport=provider, **kwargs))

    video = tmp_path / 'five-seconds.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-f', 'lavfi', '-i',
                    'color=black:s=32x32:r=5', '-t', '5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)],
                   check=True)
    monkeypatch.setattr(graphics_video, 'poll_video_job', lambda picture_id: actual_poll(
        picture_id, api_key='fake', transport=lambda *a, **kw: (200, b'{"status":"done","video":{"url":"https://example.test/video"}}'),
        fetch=lambda *a, **kw: (video.read_bytes(), 'https://example.test/video', 'video/mp4')))
    monkeypatch.setattr(graphics_pipeline, 'review_step', lambda run_id: actual_review(run_id, keys={}))

    started = graphics_entry.run_selected_story(content_id=source['content_id'], run_id=source['run_id'], locale='en')
    assert started['run_id'] == run.pk and started['state'] == 'queued'
    seen = []
    while queued and len(seen) < 30:
        task, args = queued.pop(0)
        seen.append(task.name)
        task.run(*args)
    run.refresh_from_db()
    assert run.execution_state == 'complete'
    assert tasks.submit_graphics_video.name in seen and tasks.poll_graphics_video.name in seen
    assert tasks.review_graphics_package.name in seen
    assert ContentPicture.objects.filter(run=run, provenance__role='video', state='complete').exists()
    assert OriginalContentCall.objects.filter(run=run, request_identity=f'graphics:{run.pk}:C1', state='completed').count() == 1
