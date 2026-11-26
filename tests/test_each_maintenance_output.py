"""Preserve the deployed command's homepage result while maintaining caches."""
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from monitor.management.commands import refresh_materializations

HOME = 'home.brand_time_counts.v1'
EACH = 'each.brand_post_facts.v1'
SENTIMENT = 'home.post_sentiment_facts.v1'


@pytest.mark.parametrize('failure', [None, HOME, EACH, SENTIMENT])
def test_legacy_status_and_all_dataset_results_share_one_refresh_path(monkeypatch, failure):
    calls = []

    def refresh(definition):
        calls.append(definition.dataset_key)
        if definition.dataset_key == failure:
            raise RuntimeError('Fixture failure')
        return {'status': 'skipped', 'cutoff': '2026-11-19T00:00:00+00:00'}

    monkeypatch.setattr(refresh_materializations, 'refresh_materialization', refresh)
    output = StringIO()
    if failure:
        with pytest.raises(CommandError):
            call_command('refresh_home_counts', stdout=output)
    else:
        call_command('refresh_home_counts', stdout=output)
    result = json.loads(output.getvalue())
    assert calls == [HOME, EACH, SENTIMENT]
    assert result['status'] == ('unavailable' if failure == HOME else 'skipped')
    assert set(result['materializations']) == {HOME, EACH, SENTIMENT}
    if failure:
        assert result['materializations'][failure] == {'status': 'unavailable', 'error': 'RuntimeError'}
