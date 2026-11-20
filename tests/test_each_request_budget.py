"""A chain of database statements shares one elapsed request allowance."""
from unittest.mock import patch

import pytest

from monitor.each_request_budget import EachChartUnavailable, EachRequestBudget


def test_nested_budget_keeps_original_deadline():
    clock = [100.0]
    with patch('monitor.each_request_budget.monotonic', side_effect=lambda: clock[0]), EachRequestBudget(seconds=15) as outer:
        clock[0] += 9
        with EachRequestBudget(seconds=15) as inner:
            assert inner is outer
            assert inner.remaining_ms() == 6000
            clock[0] += 7
            with pytest.raises(EachChartUnavailable):
                inner.remaining_ms()

def test_each_query_uses_remaining_time_and_shorter_lock_limit():
    clock = [100.0]
    with patch('monitor.each_request_budget.monotonic', side_effect=lambda: clock[0]):
        budget = EachRequestBudget(seconds=15)
        calls = []
        def execute(sql, params, many, context):
            calls.append((sql, params))
            return 'query-result'
        assert budget.guard(execute, 'SELECT 1', [], False, {}) == 'query-result'
        assert calls[0][1] == ['15000ms', '250ms']
        clock[0] += 9
        budget.guard(execute, 'SELECT 2', [], False, {})
        assert calls[2][1] == ['6000ms', '250ms']
        clock[0] += 5.9
        budget.guard(execute, 'SELECT 3', [], False, {})
        assert calls[4][1] == ['99ms', '99ms']
        clock[0] += 1
        with pytest.raises(EachChartUnavailable):
            budget.guard(execute, 'SELECT 4', [], False, {})
        assert not any(sql == 'SELECT 4' for sql, _ in calls)


def test_snapshot_setup_precedes_any_timeout_setting_query():
    budget = EachRequestBudget()
    calls = []
    def execute(sql, params, many, context):
        calls.append(sql)
    sql = 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'
    budget.guard(execute, sql, [], False, {})
    assert calls == [sql]


@pytest.mark.parametrize('sql', ['ROLLBACK TO SAVEPOINT proof', 'RELEASE SAVEPOINT proof', 'ROLLBACK'])
def test_transaction_cleanup_is_allowed_after_request_deadline(sql):
    clock = [100.0]
    with patch('monitor.each_request_budget.monotonic', side_effect=lambda: clock[0]):
        budget = EachRequestBudget(seconds=1)
        clock[0] += 2
        calls = []
        budget.guard(lambda statement, *args: calls.append(statement), sql, [], False, {})
        assert calls == [sql]


def test_tighter_child_lock_cap_survives_an_earlier_parent_deadline():
    with (patch('monitor.each_request_budget.monotonic', return_value=100.0),
          EachRequestBudget(seconds=.2), EachRequestBudget(seconds=.25, lock_seconds=.15) as child):
        calls = []
        child.guard(lambda sql, params, *args: calls.append((sql, params)), 'SELECT 1', [], False, {})
        assert calls[0][1][1] == '150ms'
        assert int(calls[0][1][0][:-2]) <= 200


def test_sequential_nine_second_queries_cannot_receive_fresh_allowances():
    clock = [100.0]
    limits = []

    def execute(sql, params, many, context):
        if sql.startswith('SELECT set_config'):
            limits.append(params)
        else:
            clock[0] += 9

    with (patch('monitor.each_request_budget.monotonic', side_effect=lambda: clock[0]),
          EachRequestBudget(seconds=15) as budget):
        budget.guard(execute, 'SELECT first', [], False, {})
        with pytest.raises(EachChartUnavailable):
            budget.guard(execute, 'SELECT second', [], False, {})
    assert limits == [['15000ms', '250ms'], ['6000ms', '250ms']]


@pytest.mark.parametrize('failure', [None, RuntimeError, KeyboardInterrupt])
def test_scope_restores_caller_settings_after_success_failure_and_cancellation(failure):
    from contextlib import contextmanager

    from monitor import each_request_budget

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params=None):
            if params:
                database.limits = params[0], params[2]

        def fetchall(self):
            return [('statement_timeout', 40), ('lock_timeout', 30)]

    class Database:
        vendor = 'postgresql'
        in_atomic_block = False
        needs_rollback = False
        connection = object()
        limits = '40ms', '30ms'

        def cursor(self):
            return Cursor()

        @contextmanager
        def execute_wrapper(self, guard):
            self.guard = guard
            yield

    database = Database()

    @contextmanager
    def no_network(self):
        yield

    with (patch.object(each_request_budget, 'connection', database),
          patch.object(EachRequestBudget, '_connection_io_scope', no_network)):
        def work():
            with EachRequestBudget(seconds=15) as budget, budget.query_scope():
                database.limits = '1ms', '1ms'
                if failure:
                    raise failure()
        if failure:
            with pytest.raises(failure):
                work()
        else:
            work()
    assert database.limits == ('40ms', '30ms')
    assert each_request_budget.current_budget() is None
    assert each_request_budget._query_connection.get() is None


def test_headline_projection_and_visible_touch_share_three_second_budget(monkeypatch):
    from types import SimpleNamespace

    from monitor import each_headline
    from monitor.each_request_budget import current_budget

    clock = [100.0]
    calls = []
    config = SimpleNamespace(demand_shaping_enabled=True)

    def projection(window, **kwargs):
        calls.append(('projection', window, kwargs['selected_brand_keys']))
        assert current_budget().remaining_ms() == 3000
        clock[0] += 2
        return {'headline': 'Saved headline'}

    def touch(**kwargs):
        calls.append(('touch', kwargs['window_days'], kwargs['brand_keys']))
        assert current_budget().remaining_ms() == 1000

    monkeypatch.setattr(each_headline, 'load_config', lambda path: SimpleNamespace(headline_narrative=config))
    monkeypatch.setattr(each_headline, 'project_trend_narrative', projection)
    monkeypatch.setattr(each_headline, 'record_visible_trend_narrative_demand', touch)
    with (patch('monitor.each_request_budget.monotonic', side_effect=lambda: clock[0]),
          patch('monitor.each_request_budget.connection.vendor', 'sqlite')):
        result = each_headline.headline_context(brand='deepseek', window_days=7, locale='zh_hans')
    assert result['trend_narrative'] == {'headline': 'Saved headline'}
    assert result['is_zh_chrome'] is True
    assert calls == [('projection', 7, ['deepseek']), ('touch', 7, ['deepseek'])]


@pytest.mark.parametrize('failure', [None, EachChartUnavailable])
def test_visible_touch_reuses_existing_writer_and_bounds_transaction_io(monkeypatch, failure):
    from contextlib import contextmanager

    from monitor import trend_narrative_demand
    from monitor.each_request_budget import current_budget

    events = []
    configuration = object()

    @contextmanager
    def query_scope(self):
        events.append('query-enter')
        yield
        events.append('query-exit')

    @contextmanager
    def atomic():
        events.append('transaction-enter')
        try:
            yield
        finally:
            # Both successful commits and failed rollback still own the guard.
            assert current_budget().remaining_ms() == 250
            events.append('transaction-exit')

    def writer(**kwargs):
        assert kwargs == {
            'reason': 'visible', 'brand_keys': ['llama'], 'window_days': 7,
            'config': configuration,
        }
        assert current_budget().remaining_ms() == 250
        assert current_budget().lock_ms == 150
        events.append('existing-writer')
        if failure:
            raise failure()
        return 1

    monkeypatch.setattr(EachRequestBudget, 'query_scope', query_scope)
    monkeypatch.setattr(trend_narrative_demand.transaction, 'atomic', atomic)
    monkeypatch.setattr(trend_narrative_demand, 'record_trend_narrative_demand', writer)
    with patch('monitor.each_request_budget.monotonic', return_value=100):
        result = trend_narrative_demand.record_visible_trend_narrative_demand(
            brand_keys=['llama'], window_days=7, config=configuration,
        )
    assert result == (0 if failure else 1)
    assert events[:4] == [
        'query-enter', 'transaction-enter', 'existing-writer', 'transaction-exit',
    ]
    if not failure:
        assert events[-1] == 'query-exit'
