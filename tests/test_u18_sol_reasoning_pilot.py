"""Sol gets native reasoning settings, with measured rather than hidden cost."""
import copy

import pytest

from scripts import u18_sol_reasoning_pilot as pilot


def packet():
    return [{'tweet_id':'public-id','brand_ids':['minimax'],'text':'Visible source','context':[]}]


def test_effort_is_the_only_paired_request_difference_and_temperature_is_absent():
    low=pilot.request(packet(),'low'); high=pilot.request(packet(),'xhigh')
    assert low.pop('reasoning')=={'effort':'low','exclude':True}
    assert high.pop('reasoning')=={'effort':'xhigh','exclude':True}
    assert low==high
    assert 'temperature' not in low
    assert low['max_tokens']>=25000
    assert low['response_format']['type']=='json_schema'
    assert low['provider']['only']==['openai']
    assert low['provider']['allow_fallbacks'] is False


def test_positive_billed_reasoning_is_accepted_but_incomplete_answer_is_not():
    response={'model':pilot.ALIAS,'provider':'OpenAI',
              'usage':{'prompt_tokens':100,'completion_tokens':1200,'completion_tokens_details':{'reasoning_tokens':1000},'cost':0.0122},
              'choices':[{'finish_reason':'stop','message':{'content':'{"results":[]}'}}]}
    original=copy.deepcopy(response)
    assert pilot.parse_response(response)=={'results':[]}
    assert response==original
    response['choices'][0]['finish_reason']='length'
    with pytest.raises(AssertionError,match='incomplete'):
        pilot.parse_response(response)


def test_longer_trial_timeout_is_restored_even_if_transport_raises(monkeypatch,tmp_path):
    before=pilot.old.TIMEOUT
    def failing_transport(*_):
        assert pilot.old.TIMEOUT==pilot.TIMEOUT
        raise RuntimeError('transport failed')
    monkeypatch.setattr(pilot.old,'transport',failing_transport)
    with pytest.raises(RuntimeError,match='transport failed'):
        pilot.transport({},'never-sent-test-key',tmp_path,'fake')
    assert pilot.old.TIMEOUT==before
