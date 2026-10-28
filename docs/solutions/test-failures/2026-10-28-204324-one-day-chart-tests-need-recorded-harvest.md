---
title: "Homepage 1-day chart tests need a recorded scheduled harvest, not just seeded posts"
date: 2026-10-28
category: test-failures
module: monitor/harvest_coverage
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "Payload totals are 0 for a brand that has a seeded post (AssertionError: 0 not greater than 0, 0 != 1)"
  - "JS RangeError: Invalid time value in the 1-day chart"
  - "JS TypeError: Cannot read properties of undefined (reading 'options') because the xComparison scale is absent when the days list has fewer than 2 buckets"
root_cause: incomplete_setup
resolution_type: test_fix
related_components:
  - frontend
  - background_job
tags:
  - harvest-coverage
  - one-day-chart
  - browser-tests
  - test-fixtures
  - collection-run
  - chart-js
  - silent-test-rot
---

# Homepage 1-day chart tests need a recorded scheduled harvest, not just seeded posts

## Problem

The homepage's 1-day "posts by brand" chart (and the 1-day chart on `/dashboard/each`) no longer plots "everything up to now". Since commit `8b146658` ("fix(charts): end daily series at completed harvest coverage", already on `main` and shipped in deployed `e5edf737`), the chart ends at the last *completed scheduled X harvest*. A test that seeds posts but never records a harvest therefore renders an empty or truncated chart. Nothing in the failure points at harvests, and six browser tests quietly broke for a release.

In plain terms: the code now asks "up to which moment do we know our collection finished?" and only draws that far. A test database has no collection history unless the test creates one.

## Symptoms

Failures show up far from the cause (observed in this session's investigation):

- Python assertions on the chart payload: `AssertionError: 0 not greater than 0`, `0 != 1`, because a brand that clearly has a seeded post shows a total of 0.
- Browser console errors: `RangeError: Invalid time value` and `Cannot read properties of undefined (reading 'options')`. The comparison x-axis scale (`xComparison`) is missing when the payload's days list has fewer than 2 buckets, so the chart script falls over.

At `e5edf737` these tests in `tests/test_home_v22_browser.py` were already failing for this reason. They were not in the UI-assurance gate's test list, so nobody noticed:

- `PublicTrackedBrandsBrowserTests.test_anonymous_menus_pulse_and_window_switches_use_configured_subjects`
- `HomeV22BrowserTests.test_one_day_chart_uses_dual_time_axes_and_full_width`
- `test_v24_timezone_pill_keeps_both_clocks_and_geometry`
- `test_california_browser_compares_against_localized_beijing_time`
- `HomeV22MetadataParityBrowserTests.test_stepfun_is_single_nonempty_browser_identity`
- `test_japanese_processing_language_and_hover_visuals_survive_feed_replacement`

An earlier commit (`60474f2f`) had added `record_harvest` to only two tests in `tests/test_home_v22_browser.py` (the hover-freeze tests) and to a `/dashboard/each` browser test.

## What Didn't Work

- Reading the JS errors as chart-library or timezone bugs. The `RangeError` and `options` errors are downstream symptoms of an empty payload, not defects in the chart script.
- Seeding posts (`seed_real_home_orm` or `seed_v22_metadata_regression_orm` from `tests/v22_support.py`, or a `Post` at `timezone.now() - 2 minutes`) and assuming that is enough. Posts alone do not create coverage.
- Posting at "now minus 2 minutes" once a harvest *is* recorded. Coverage is floored to a five-minute boundary, so a post two minutes old can still fall after the cutoff.
- Deleting and re-recording `CollectionRun` rows mid-test to change the coverage time. `CollectionAttempt.run` is a PROTECTED foreign key, so deletion fails.
- Blaming this for `test_activated_geopolitical_and_promotion_controls_round_trip_in_browser`. That test still fails for a different reason (its untracked-brand post never reaches the feed) and is unrelated to harvest coverage.

## Solution

How the cutoff works (current tree):

- `monitor/harvest_coverage.py:17` `closed_five_minute_boundary(at)` rounds a time down to the previous five-minute mark in UTC.
- `monitor/harvest_coverage.py:22` `latest_scheduled_coverage(at)` finds the latest settled scheduled run (`job__source_id="x"`, `purpose="content"`, `operation="x_cycle"`, `mode="recurring"`, with `scheduled_slot_at` set, not `running`, finished within the last day) whose ordinary frozen targets all completed, and returns a dict including `run_id` and `chart_end_at`. It returns `None` when there is no such run.
- `monitor/views.py:3461-3465` applies it only for `window_days == 1`: `chart_start` is the closed boundary minus one day, and `chart_end` is the coverage `chart_end_at` (never earlier than `chart_start`); with no coverage, `chart_end = chart_start`, an empty range. The payload carries it as `harvest_coverage` (`monitor/views.py:3723`). The dashboard-each path does the same at `monitor/views.py:4169-4177`.

Fix on this branch (pending on `feat/homepage-general-style-20261028`; no PR yet): make every such test record a harvest.

1. A module helper in `tests/test_home_v22_browser.py:211`:

```python
def _record_current_harvest() -> None:
    """Certify scheduled coverage through now; the 1-day chart ends at coverage."""
    from tests.test_chart_harvest_coverage import record_harvest

    now = datetime.now(UTC)
    record_harvest(now, finished_at=now, staggered=False)
```

   It is called at the start of each affected test (call sites at lines 518, 1488, 3568, 3724, 4096, 5835).

2. A shared seeding helper, `tests/general_style_browser.py:35`, `seed_general_style_home(test_case, *, harvested_at=None)`, which seeds the deterministic fixture **and** records a harvest (default: now):

```python
seed_real_home_orm(fixture_from_oracle())
harvested_at = harvested_at or timezone.now()
record_harvest(harvested_at, finished_at=harvested_at, staggered=False)
```

3. Posts created inside a test are dated before the latest closed boundary, for example `now - 10 minutes`, not `now - 2 minutes`.

4. A test that wants a specific coverage end passes that time instead. `tests/test_home_chart_style_browser.py` (`HomeChartCoverageAxisBrowserTests`, around line 193) sets `self.harvested = timezone.now() - timedelta(minutes=47)` in `setUp`, calls `seed_general_style_home(self, harvested_at=self.harvested)`, and asserts `payload.harvest_coverage.chart_end_at` equals `closed_five_minute_boundary(self.harvested)` and that the axis's last tick label matches that instant's clock text.

`record_harvest` itself is defined in `tests/test_chart_harvest_coverage.py:36` with the signature `record_harvest(end, *, incomplete=None, missing=None, optional=False, running=False, finished_at=None, staggered=True)`. It builds a real scheduled lineage (calls `A` and `B1`), so it passes the same filters production code uses. Use `staggered=False` so every scope ends exactly at `end`.

## Why This Works

The chart's right edge is now data-driven: it is the finish time of a real scheduled run, not the wall clock. A recorded run gives `latest_scheduled_coverage` something to return, so `chart_end_at` lands near "now" and the one-day range has enough buckets for the comparison axis to exist. Dating posts before the floored boundary keeps them inside the plotted range. Setting the harvest time in `setUp` sidesteps the protected-foreign-key limit on deleting runs.

## Prevention

- Treat "seeds posts for the 1-day chart" and "records a harvest" as one step. Prefer `seed_general_style_home(self)` over calling `seed_real_home_orm` directly in browser tests.
- Date test posts at least 10 minutes in the past, and always before `closed_five_minute_boundary(harvested)`.
- Keep 1-day chart browser tests in the UI-assurance gate's test lists so rot is caught in one release, not several. The six tests above were outside both lists; this change added four of them (the 1-day axes, clock pill, California comparison and Japanese processing tests) to the gate's candidate list in `tests/ui_assurance/gate.py`.
- Add a cheap guard that fails with a clear message instead of a JS error. Example:

```python
def test_seeded_home_has_scheduled_coverage(self):
    seed_general_style_home(self)
    now = timezone.now()
    coverage = latest_scheduled_coverage(now)
    self.assertIsNotNone(coverage, "record a scheduled harvest before rendering the 1-day chart")
    self.assertGreaterEqual(
        datetime.fromisoformat(coverage["chart_end_at"]),
        closed_five_minute_boundary(now) - timedelta(minutes=5),
    )
```

- When debugging an empty 1-day chart with zero totals or `xComparison` errors, check `payload.harvest_coverage` first. If it is `null`, the test (or environment) has no completed scheduled harvest.
