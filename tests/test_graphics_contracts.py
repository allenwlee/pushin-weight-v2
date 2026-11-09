import json
from pathlib import Path

import pytest

from monitor.editorial.graphics_contracts import build_messages, load_pack


def test_messages_have_one_schema_and_preserve_approaches():
    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    approaches = [{'candidate_id': 'A', 'approach': 'original_visual_concept'}, {'candidate_id': 'B', 'approach': 'cultural_reference'}]
    messages = build_messages(pack, 'G1', {'visual_approaches': approaches})
    task = messages['task']
    assert task.count('OUTPUT JSON SCHEMA FOR THIS REQUEST:') == 1
    inputs = json.loads(task.split('SUPPLIED INPUTS:\n', 1)[1].split('\n\nOUTPUT JSON SCHEMA FOR THIS REQUEST:', 1)[0])
    assert inputs['visual_approaches'] == approaches
    assert messages['system']


def test_unknown_stage_is_rejected():
    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    with pytest.raises(ValueError):
        build_messages(pack, 'C2', {})


def test_shared_validation_rejects_duplicate_candidate_approaches():
    from monitor.editorial.graphics_contracts import validate_stage_output

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    response = {
        'schema_version': 'graphics-discovery/v3',
        'queries': [],
        'preferred_sites': [],
        'reuse_asset_refs': [],
        'approaches': [
            {'candidate_id': 'A', 'approach': 'original_visual_concept', 'reason': 'Original idea.', 'reference_target': None},
            {'candidate_id': 'A', 'approach': 'original_visual_concept', 'reason': 'Another idea.', 'reference_target': None},
        ],
    }
    with pytest.raises(ValueError, match='one.*A.*B'):
        validate_stage_output(pack, 'G0', response)
    response['approaches'][1]['candidate_id'] = 'B'
    assert validate_stage_output(pack, 'G0', response) == response


def test_shared_validation_requires_ranked_copy_candidates():
    from monitor.editorial.graphics_contracts import validate_stage_output

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    candidate = {'id': 'A', 'headline': 'Ram I Am', 'byline': 'The story.', 'wordplay_meaning': 'A pun.', 'cultural_reference': None, 'used_fact_ids': ['F01']}
    response = {'schema_version': 'copy-proposals/v3', 'locale': 'en', 'candidates': [candidate, {**candidate, 'id': 'A'}], 'article': 'A story.', 'used_fact_ids': ['F01'], 'evidence_gaps': []}
    with pytest.raises(ValueError, match='candidate A.*B'):
        validate_stage_output(pack, 'C1', response)
    response['candidates'][1]['id'] = 'B'
    assert validate_stage_output(pack, 'C1', response) == response


def _copy_fixture():
    candidate = {
        'id': 'A', 'headline': 'Sam I RAM', 'byline': 'Exact supporting line.',
        'wordplay_meaning': 'A pun.', 'cultural_reference': None,
        'used_fact_ids': ['F02'],
    }
    return {
        'schema_version': 'copy-proposals/v3', 'locale': 'en',
        'candidates': [candidate, {**candidate, 'id': 'B', 'headline': 'Memory Lane'}],
        'article': 'An exact article.', 'used_fact_ids': ['F01'], 'evidence_gaps': [],
    }


def test_saved_primary_copy_is_unchanged_even_when_b_is_available():
    from monitor.editorial.graphics_contracts import build_publication

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    c1 = _copy_fixture()
    reserve = {'candidate_id': 'B', 'asset_ref': 'image:B', 'input_asset_refs': []}
    result = build_publication(pack, c1, [reserve], [])
    assert result['headline'] == 'Sam I RAM'
    assert result['article'] == 'An exact article.'
    assert result['used_asset_refs'] == []
    assert result['used_fact_ids'] == ['F01', 'F02']


@pytest.mark.parametrize('state', ['pending', 'ambiguous', 'sent', 'completed', None])
def test_reserve_requires_definite_failure(state):
    from monitor.editorial.graphics_contracts import build_publication

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    reserve = {'candidate_id': 'B', 'asset_ref': 'image:B', 'input_asset_refs': []}
    with pytest.raises(RuntimeError, match='definite'):
        build_publication(pack, _copy_fixture(), [reserve], [], selected='B', fallback_stage='V1', failure_state=state)


def test_definite_failure_falls_back_only_with_reserve_image():
    from monitor.editorial.graphics_contracts import build_publication

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    with pytest.raises(RuntimeError, match='reserve still'):
        build_publication(pack, _copy_fixture(), [], [], selected='B', fallback_stage='V1', failure_state='failed', previous_selection='A')
    reserve = {'candidate_id': 'B', 'asset_ref': 'image:B', 'input_asset_refs': []}
    result = build_publication(pack, _copy_fixture(), [reserve], [], selected='B', fallback_stage='V1', failure_state='failed', previous_selection='A')
    assert result['headline'] == 'Memory Lane'
    assert result['article'] == 'An exact article.'
    assert result['used_asset_refs'] == ['image:B']


def test_repeat_selection_does_not_replace_an_existing_edition():
    from monitor.editorial.graphics_contracts import build_publication

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    with pytest.raises(RuntimeError, match='already saved'):
        build_publication(pack, _copy_fixture(), [], [], previous_selection='A')


def test_treatments_must_cover_both_candidates():
    from monitor.editorial.graphics_contracts import validate_stage_output

    pack = load_pack(Path(__file__).resolve().parents[1] / 'config/editorial_prompts/editorial-creative-roles-v1.json')
    treatment = {
        'candidate_id': 'A', 'idea': 'A scene', 'why_it_bites': 'The pun',
        'input_asset_refs': [], 'aspect_ratio': '1:1', 'still_prompt': 'Draw', 'motion_prompt': 'Move',
    }
    response = {'schema_version': 'graphics-treatments/v2', 'treatments': [treatment, dict(treatment)], 'source_gaps': []}
    with pytest.raises(ValueError, match='treatment.*A.*B'):
        validate_stage_output(pack, 'G1', response)
    response['treatments'][1]['candidate_id'] = 'B'
    assert validate_stage_output(pack, 'G1', response) == response


def test_copy_fact_references_must_belong_to_the_handoff():
    from monitor.editorial.graphics_contracts import validate_copy_fact_ids

    copy = _copy_fixture()
    validate_copy_fact_ids(copy, [{'fact_id': 'F01'}, {'fact_id': 'F02'}])
    copy['candidates'][1]['used_fact_ids'] = ['F99']
    with pytest.raises(ValueError, match='Unknown fact reference'):
        validate_copy_fact_ids(copy, [{'fact_id': 'F01'}, {'fact_id': 'F02'}])
