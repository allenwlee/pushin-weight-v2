"""Search-only exclusions must reach both cycle and backfill planning safely."""
from pathlib import Path

import pytest

from tests.test_harvest_query_diff import branches, diff
from x_monitor.attribution import compile_keyword_index, detect_brand_mentions
from x_monitor.harvest_policy import load_policy
from x_monitor.query_packing import TIME_BOUNDS


def test_cycle_and_backfill_planners_scope_exclusions_to_meta(settings):
    from monitor.cycle import CycleRunner, plan_calls_for_cycle
    from x_monitor.config import load_config

    cfg = load_config(Path('config.yaml'))
    cfg.x_monitor_list_id = 2067062923525275922
    cfg.discovery.rare_types.enabled = False
    settings.X_MONITOR_CYCLE_BRAND_FILTER = None
    runner = CycleRunner(cfg=cfg, dry_run=True, cycle_kind='scheduled')
    scheduled = {c.call_id: c for c in runner._plan_calls()}
    assert not runner._errors
    # The backfill command uses this shared planner with scheduled_exclusions=False.
    backfill = {c.call_id: c for c in plan_calls_for_cycle(cfg)}
    assert len(scheduled) == len(backfill) == 16
    b1 = scheduled['B1'].query_string
    assert backfill['B1'].query_string == b1.removesuffix(' -from:xxyweb3')
    assert len((b1 + TIME_BOUNDS).encode('utf-8')) <= 512
    terms = [diff.canonical(b) for b in branches(b1)]
    assert any({'meta', 'model', '-$meta', '-"meta analysis"'} <= b for b in terms)
    assert any({'muse', 'model'} <= b and '-$meta' not in b for b in terms)
    assert any({'llama', 'model'} <= b and '-$meta' not in b for b in terms)
    assert any('@aiatmeta' in b and '-$meta' not in b for b in terms)
    assert any('exaone' in b and '-$meta' not in b for b in terms)


def test_search_exclusions_do_not_change_brand_attribution():
    policy = load_policy(Path('config/harvest_policy.yaml'))
    index = compile_keyword_index([('llama', 'meta', False)], policy=policy)
    assert 'llama' in detect_brand_mentions('Meta AI improves $META ads', index)
    assert 'llama' not in detect_brand_mentions('Meta in ordinary text', index)


@pytest.mark.parametrize('term', ['x OR y', 'x) -from:someone', ''])
def test_search_exclusions_reject_query_syntax(term):
    from x_monitor.harvest_policy import SearchAliasExclusion
    with pytest.raises(ValueError):
        SearchAliasExclusion('Meta', (term,))
