"""The adaptation may change envelopes, never evidence, identity or scoring."""
import copy

import pytest

from scripts import u18_nemo_adaptation_pilot as pilot


def packets():
    return [
        {'tweet_id': 'long-id-a', 'text': 'An actual source', 'brand_ids': ['minimax'], 'context': [], 'affiliations': [{'role': 'staff'}]},
        {'tweet_id': 'long-id-b', 'text': 'Another source', 'brand_ids': ['deepseek'], 'context': [{'text': 'Quoted evidence'}]},
    ]


def row(**changes):
    return {'outcome': 'classified', 'post_types': ['opinions_reactions'], 'product_labels': [],
            'sentiment': 'neutral', 'china_nationalism': 'none', 'us_nationalism': 'none',
            'unsanctioned_flags': [], **changes}


def test_schema_only_preserves_entire_old_request_except_response_format():
    source = packets()
    original = pilot.old.request_body(pilot.PROVIDERS['deka'], source)
    adapted = pilot.request(source)
    assert adapted.pop('response_format')['type'] == 'json_schema'
    original.pop('response_format')
    assert adapted == original


def test_short_ids_restore_correct_brands_even_if_model_reorders_keys():
    source = packets()
    inputs = pilot.short_inputs(source)
    assert inputs['r2']['text'] == source[1]['text']
    assert inputs['r2']['context'] == source[1]['context']
    assert 'affiliations' not in inputs['r1']  # R101 did not supply this evidence.
    payload = {'r2': row(sentiment='positive'), 'r1': row()}
    frozen = copy.deepcopy(payload)
    canonical = pilot.normalize(payload, source, True)
    validated = pilot.validate(canonical, source)
    assert validated['long-id-b']['by_brand']['deepseek']['sentiment'] == 'positive'
    assert validated['long-id-a']['by_brand']['minimax']['sentiment'] == 'neutral'
    assert payload == frozen
    with pytest.raises(ValueError, match='IDs'):
        pilot.normalize({'r1': row()}, source, True)


@pytest.mark.parametrize('bad', [
    row(sentiment='null'), row(post_types=['other', 'opinions_reactions']),
    row(outcome='context_missing', post_types=['opinions_reactions']),
    row(unsanctioned_flags=['invented_flag']),
])
def test_compact_decoder_does_not_repair_illegal_semantics(bad):
    source = packets()[:1]
    canonical = pilot.normalize({'r1': bad}, source, True)
    with pytest.raises(ValueError):
        pilot.validate(canonical, source)


def test_missing_rows_never_receive_credit_for_empty_reference_labels(monkeypatch):
    reference = {'rows': [{'example_id': 'example', 'brand_id': 'minimax', 'case_id': 'case',
                           'classification': {k: v for k, v in row().items() if k in pilot.AXES}}]}
    monkeypatch.setattr(pilot.old, 'read', lambda path: reference if path == pilot.old.DEFAULT_REFERENCE else {})
    score = pilot.metrics([])
    assert score['rows'] == 1
    assert score['valid_rows'] == 0
    assert score['correct_by_axis'] == dict.fromkeys(pilot.AXES, 0)
    assert score['labels']['post_types']['fn'] == 1
