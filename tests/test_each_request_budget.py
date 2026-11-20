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
