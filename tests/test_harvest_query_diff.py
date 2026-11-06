"""The comparison must prove actual conjunctions, never mere token presence."""
import importlib.util
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('query_diff', ROOT / '.claude/skills/change-harvester/subskills/harvest-query-diff/scripts/query_diff.py')
diff = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diff)


def branches(query):
    return diff.expand(diff.parse(query))


def manifest(query):
    return {'queries': [{'call_id': 'C2', 'query': query}]}


def test_every_cartesian_product_and_proposed_addition_is_visible(tmp_path):
    old = '(CUDA OR CUTLASS) (llm OR model)'
    new = '(CUDA OR CUTLASS) (llm OR model OR inference)'
    assert branches(old) == [('CUDA', 'llm'), ('CUDA', 'model'), ('CUTLASS', 'llm'), ('CUTLASS', 'model')]
    out = tmp_path / 'review.html'
    result = diff.write_report(manifest(old), manifest(new), out, [])
    assert result['current_branches'] == 4
    assert result['proposed_branches'] == 6
    assert result['counts']['Added alternative'] == 2
    class Rows(HTMLParser):
        count = 0
        def handle_starttag(self, tag, attrs):
            if tag == 'tr' and 'data-status' in dict(attrs):
                assert 'hidden' not in dict(attrs)
                self.count += 1
    reader = Rows()
    reader.feed(out.read_text())
    assert reader.count == 6
    assert 'CUTLASS AND inference' in out.read_text()
    assert out.with_suffix('.csv').read_text().count('\n') == 7


def test_nested_phrases_negation_duplicates_and_filters():
    original = '(CUDA OR CUTLASS) (llm OR model) OR "dots studio" -from:spam'
    formatted = diff.pretty(original)
    assert '\n' in formatted
    assert diff.parse(formatted) == diff.parse(original)
    assert branches('((a OR a) (b OR "c d")) -from:spam since_time:123') == [
        ('a', 'b', '-from:spam', 'since_time:123'), ('a', '"c d"', '-from:spam', 'since_time:123'),
        ('a', 'b', '-from:spam', 'since_time:123'), ('a', '"c d"', '-from:spam', 'since_time:123'),
    ]
    assert branches('a -(b OR c)') == [('a', '-b', '-c')]
    assert branches('a NOT (b AND c)') == [('a', '-b'), ('a', '-c')]
    assert diff.canonical(('MiMo-V2.5',)) == diff.canonical(('MiMo', 'V2.5'))
    assert diff.canonical(('"dots studio"',)) != diff.canonical(('dots', 'studio'))
    assert diff.canonical(('Z.ai',)) != diff.canonical(('Z', 'ai'))


@pytest.mark.parametrize('query', ['a OR', 'a OR OR b', '(a', 'a)', '"unclosed', 'a AND', '()'])
def test_malformed_queries_cannot_silently_lose_branches(query):
    with pytest.raises(ValueError):
        branches(query)


def test_broader_narrower_and_missing_are_not_equivalent():
    assert diff.compare(manifest('NVIDIA model'), manifest('NVIDIA'))['counts']['Broader'] == 1
    assert diff.compare(manifest('NVIDIA'), manifest('NVIDIA model'))['counts']['Narrower'] == 1
    assert diff.compare(manifest('dots studio'), manifest('"dots studio"'))['counts']['Narrower'] == 1
    assert diff.compare(manifest('NVIDIA model'), manifest('CUDA model'))['counts']['Not guaranteed'] == 1


def test_compaction_preserves_every_alias_context_pair():
    from x_monitor.harvest_policy import load_policy
    from x_monitor.query_packing import _group_spec, brand_query_blocks
    from x_monitor.query_plan import _build_query
    policy = load_policy(ROOT / 'config/harvest_policy.yaml')
    blocks = {b.name: b for brand in policy.brands.values() for b in brand_query_blocks(brand)}
    for pool in policy.query_pools:
        for group in pool.groups:
            owned = [blocks[n] for n in group.blocks]
            unpacked = set()
            for block in owned:
                # Historical noncompact renderer is the independent before
                # representation. The comparison ignores only zero-like floor.
                unpacked.update(diff.canonical(b) for b in branches(_build_query(block.spec)))
            compact = {diff.canonical(b) for b in branches(_build_query(_group_spec(group.call_id, owned)))}
            assert compact == unpacked, group.call_id


def test_longer_phrase_implies_contiguous_subphrase_but_not_reverse():
    old = manifest('"I\'ve joined @deepseek_ai"')
    new = manifest('"I\'ve joined" @deepseek_ai')
    assert diff.compare(old, new)['counts']['Broader'] == 1
    assert diff.compare(new, old)['counts']['Narrower'] == 1
    interrupted = manifest('"I\'ve just joined @deepseek_ai"')
    assert diff.compare(interrupted, new)['counts']['Not guaranteed'] == 1


def planned_queries():
    from django.test import override_settings

    from monitor.cycle import plan_calls_for_cycle
    from x_monitor.config import load_config
    cfg = load_config(ROOT / 'config.yaml')
    with override_settings(X_MONITOR_LIST_ID='2067062923525275922', X_MONITOR_CYCLE_BRAND_FILTER=''):
        return [c for c in plan_calls_for_cycle(cfg, scheduled_exclusions=True) if c.call_id != 'A']


@pytest.mark.parametrize('text', [
    'NVIDIA shares fell today', 'NVIDIA AI', '英伟达股价今日下跌', '輝達股票', '英偉達股價', 'エヌビディアの株価',
    'Mistral winds are strong', 'Ernie and Bert are puppets', 'Upstage the actors tonight',
    'Sakana is delicious fish', 'Namazu is a legendary catfish', 'Connect the dots',
    'I like the dots in my art studio', 'Xiaomi phone model launch',
    'Yi Qin writes on the Dicke model', 'MiMo is a lovely gift', 'Kimi wins the race',
    'Ring the alarm for AI doom', 'Clara is doing AI research', 'AI investments drive growth',
    'Earth-2 weather forecasting', 'The weather on Earth 2 is changing',
])
def test_real_planner_does_not_reintroduce_unqualified_collision(text):
    from scripts.harvest_db_replay import Matcher
    matcher = Matcher([{'call_id': c.call_id, 'query': c.query_string} for c in planned_queries()])
    assert matcher.calls(text, 'neutral') == []


@pytest.mark.parametrize('text', [
    'ChatGLM', 'GLM4', 'GLM5', 'GLM-4', 'GLM 5', 'MiMo-V2.5', 'MiMo 7B',
    'dots studio', 'dots Xiaohongshu', 'dots RedNote', 'dots 小红书',
    'Sakana AI', 'SakanaAI', 'NVIDIA AI Factory', 'NVIDIA H200', '英伟达模型', 'Upstage API', 'ERNIE llm',
    'Mistral huggingface', 'Yi Coder', 'Ring 1T', 'Ling flash', 'Ming lite',
    'NVIDIA Earth-2', 'Step 3.5 Flash', 'Step 3.7 Flash',
])
def test_real_planner_retains_qualified_products_and_versions(text):
    from scripts.harvest_db_replay import Matcher
    matcher = Matcher([{'call_id': c.call_id, 'query': c.query_string} for c in planned_queries()])
    assert matcher.calls(text, 'neutral')


def test_all_official_mentions_are_independent_and_all_wire_requests_fit():
    from scripts.harvest_db_replay import Matcher
    from x_monitor.harvest_policy import load_policy
    from x_monitor.x_client import XClient
    calls = planned_queries()
    matcher = Matcher([{'call_id': c.call_id, 'query': c.query_string} for c in calls])
    policy = load_policy(ROOT / 'config/harvest_policy.yaml')
    for brand in policy.brands.values():
        for handle in brand.handles:
            assert matcher.calls('@' + handle, 'neutral'), handle
    for call in calls:
        wire = XClient._effective_search_query(call.query_string, since=None, since_time=9999999099, until_time=9999999999)
        assert len(wire.encode('utf-8')) <= 512, call.call_id


@pytest.mark.parametrize('text,call_id', [
    ("I've joined the team at @GoogleDeepMind", 'SPECIALEVENTS1'),
    ("I've joined the team at @deepseek_ai", 'SPECIALEVENTS1'),
    ("I've joined @OpenAI", 'SPECIALEVENTS1'),
    ("I've joined @AnthropicAI", 'SPECIALEVENTS1'),
    ('发布模型', 'SPECIALEVENTS2'),
    ('モデルを公開', 'SPECIALEVENTS2'),
    ('开源权重', 'SPECIALEVENTS2'),
])
def test_bounded_discovery_additions_retain_required_conjunction(text, call_id):
    from scripts.harvest_db_replay import Matcher
    from x_monitor.special_events_search import QUERIES
    # These controls exercise text branches only. The replay tool deliberately
    # rejects URL operators; remove the unchanged independent URL alternatives.
    matcher = Matcher([
        {'call_id': c, 'query': q.replace(' OR url:huggingface.co OR url:hf.co', '')}
        for c, q in QUERIES.items()
    ])
    assert call_id in matcher.calls(text, 'neutral')
    assert not matcher.calls('@GoogleDeepMind', 'neutral')
    assert not matcher.calls('模型', 'neutral')


def test_saved_relevant_cuda_kernels_and_kimi_examples_keep_a_route():
    import json

    from scripts.harvest_db_replay import Matcher
    from x_monitor.attribution import compile_keyword_index, detect_brand_mentions
    from x_monitor.harvest_policy import load_policy
    from x_monitor.specs_from_policy import active_policy_tokens
    policy = load_policy(ROOT / 'config/harvest_policy.yaml')
    index = compile_keyword_index([(b,t,False) for b,ts in active_policy_tokens(policy).items() for t in ts], policy=policy)
    matcher = Matcher([{'call_id': c.call_id, 'query': c.query_string} for c in planned_queries()])
    posts = json.loads((ROOT / 'tests/fixtures/contextual_saved_positive_controls.json').read_text())
    assert len(posts) == 5
    for post in posts:
        text = (post['text'] or '') + '\n' + (post['quoted_text'] or '')
        assert matcher.calls(text, 'neutral'), post['tweet_id']
        assert post['brand_id'] in detect_brand_mentions(text, index), post['tweet_id']
