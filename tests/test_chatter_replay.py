"""Offline replay uses saved evidence and refuses to repeat a possibly paid call."""
import json

import pytest

from scripts import chatter_replay as replay
from scripts.chatter_replay_score import score


def watch(path):
    rows = []
    for i,(minute,word) in enumerate([(0,'first'),(15,'middle'),(30,'later')]):
        rows.append({'slot':i,'scheduled_at_jst':f'2026-11-17T18:{minute:02}:05+09:00',
                     'observed_at_jst':f'2026-11-17T18:{minute+1:02}:00+09:00',
                     'status':200,'success':True,'payload':{'data':[{'trend_name':word}]}})
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))


class Fake:
    def __init__(self, exposure='7.19688'):
        self.calls = []
        self.exposure = exposure

    def budget_status(self):
        return dict(scope=replay.SCOPE,limit_usd='50',exposure_usd=self.exposure)

    def rank(self, *, stage, body, route, **kwargs):
        messages = body['messages']
        headings = json.loads(messages[-1]['content'])['headlines']
        self.calls.append([h['trend_name'] for h in headings])
        return {'model':route.model,'call_id':stage,'usage':{'provider_reported_cost_usd':'0.001'},
                'data':{'ranked_stories':[{'title':h['trend_name'],'headline_ids':[h['headline_id']],
                   'qualifies':True,'prior_episode_id':None,'material_change':None,'reason':'test'}
                                            for h in headings]}}


def test_chronology_cost_and_reuse(tmp_path):
    p, labels, out = [tmp_path/s for s in ('watch','labels','replay')]
    watch(p)
    labels.write_text(json.dumps({'entries':[{'row':1,'headline':'middle'}],
                                  'topics':[{'topic_key':'hidden-label','decision':'strong','headline_rows':[1]}]}))
    digest = replay.checksum(labels.read_bytes())
    fake = Fake()
    first = replay.run(p,digest,out,fake)
    assert fake.calls == [['first'],['first','middle','later']]
    assert replay.run(p,digest,out,fake) == first
    assert len(fake.calls) == 2
    result = score(p, labels, out)
    assert result['strong_hits']['hidden-label']['minutes'] == 15
    assert result['reported_usd'] == '0.002'
    assert len(result['capture_coverage']) == 7
    assert len(result['unrelated_extra_episodes']) == 2
    with pytest.raises(ValueError,match='manifest changed'):
        replay.run(p,'1'*64,out,fake)


def test_unresolved_submission_and_insufficient_balance(tmp_path):
    p,out = tmp_path/'watch', tmp_path/'replay'
    watch(p)
    fake = Fake('49')
    with pytest.raises(ValueError,match='insufficient'):
        replay.run(p,'2'*64,out,fake)
    assert not fake.calls

    def disconnect(**kwargs):
        raise TimeoutError('undetermined submission')

    fake.exposure = '5'
    fake.rank = disconnect
    with pytest.raises(TimeoutError):
        replay.run(p,'2'*64,out,fake)
    with pytest.raises(ValueError,match='receipt reconciliation'):
        replay.run(p,'2'*64,out,Fake())


def test_invalid_episode_reference_holds_one_window_without_a_second_charge(tmp_path):
    path, output = tmp_path / "watch", tmp_path / "out"
    watch(path)

    class InvalidFirst(Fake):
        def rank(self, **kwargs):
            receipt = super().rank(**kwargs)
            if len(self.calls) == 1:
                receipt["data"]["ranked_stories"][0]["prior_episode_id"] = "not-in-packet"
            return receipt

    transport = InvalidFirst()
    result = replay.run(path, "2" * 64, output, transport)
    first, second = replay.read(output / "decisions.json")["decisions"]
    assert result["calls"] == 2 and len(transport.calls) == 2
    assert first["held"] == "invalid prior episode reference" and not first["leads"]
    assert second["held"] is None and second["leads"]
    assert replay.run(path, "2" * 64, output, transport) == result
    assert len(transport.calls) == 2
