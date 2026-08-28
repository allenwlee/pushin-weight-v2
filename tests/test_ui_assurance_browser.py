"""Isolated Playwright + Hypothesis checks against the real filter-store runtime."""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    rule,
    run_state_machine_as_test,
)
from playwright.sync_api import Browser, Page, sync_playwright

from tests.ui_assurance.covering import covering_rows
from tests.ui_assurance.reference import (
    ALL,
    MULTI_CONTROLS,
    initial_state,
    set_control,
    toggle_pulse_brand,
)

ROOT = Path(__file__).resolve().parents[1]
FILTER_STORE = ROOT / "monitor/static/pw-filter-store.js"
DEFAULT_FILTERS = initial_state()["filters"]
DECLARATION = json.loads(
    (ROOT / "tests/fixtures/ui_assurance/declaration.json").read_text(
        encoding="utf-8"
    )
)
CONTROL_VALUES = {
    control["id"]: control["values"] for control in DECLARATION["controls"]
}
RUNTIME_FILTER_KEYS = {
    "brands": "brands",
    "sentiment": "sentiment",
    "post_type": "post_types",
    "lang": "lang",
    "role": "role",
    "nationalism_cn": "cn_nationalism",
    "nationalism_us": "us_nationalism",
    "discourse": "discourse",
    "unsanctioned": "unsanctioned",
    "window": "window",
}
STATEFUL_ACTIONS = [
    (control, value)
    for control, values in CONTROL_VALUES.items()
    if control != "bulk_action"
    for value in values
]


def _html(namespace: str) -> str:
    filters = json.dumps(DEFAULT_FILTERS, separators=(",", ":"))
    filter_inputs = "".join(
        f'<input type="checkbox" data-pw-filter-group="{RUNTIME_FILTER_KEYS[control]}" '
        f'value="{value}" checked>'
        for control in MULTI_CONTROLS
        for value in CONTROL_VALUES[control]
        if value != ALL
    )
    return f"""<!doctype html>
<html><body data-pw-preferences-namespace="{namespace}"
  data-pw-filters='{filters}' data-pw-window="1" data-pw-locale="en">
  <nav class="filter-bar"><div id="control-panel">
    {filter_inputs}
    <input type="checkbox" data-pw-filter-group="unsanctioned" value="only">
  </div></nav>
  <button data-pw-pulse-entry="deepseek" aria-pressed="false">DeepSeek</button>
  <button data-pw-pulse-entry="mimo" aria-pressed="false">MiMo</button>
  <button data-pw-window-btn="1" aria-pressed="false">1d</button>
  <button data-pw-window-btn="7" aria-pressed="false">7d</button>
  <button data-pw-window-btn="30" aria-pressed="false">30d</button>
  <button data-pw-window-btn="365" aria-pressed="false">365d</button>
  <div data-lens-pair="open,closed"><div class="dd-lens-body" data-active-lens="open"></div>
    <button data-lens="open"></button><button data-lens="closed"></button></div>
  <div data-lens-pair="us,cn"><div class="dd-lens-body" data-active-lens="us"></div>
    <button data-lens="us"></button><button data-lens="cn"></button></div>
</body></html>"""


def _new_page(browser: Browser, namespace: str) -> tuple[object, Page]:
    context = browser.new_context()
    context.route(
        "http://assurance.test/**",
        lambda route: route.fulfill(status=200, content_type="text/html", body=_html(namespace)),
    )
    page = context.new_page()
    page.goto("http://assurance.test/")
    page.add_script_tag(path=str(FILTER_STORE))
    return context, page


def _browser_snapshot(page: Page) -> dict:
    return page.evaluate(
        """() => ({
          filters: window.pwFilter.get(),
          preferences: window.pwFilter.getPreferences(),
          pressed: [...document.querySelectorAll('[data-pw-pulse-entry]')]
            .filter(node => node.getAttribute('aria-pressed') === 'true')
            .map(node => node.getAttribute('data-pw-pulse-entry')),
          activeWindow: Number(document.querySelector(
            '[data-pw-window-btn][aria-pressed="true"]'
          ).getAttribute('data-pw-window-btn'))
        })"""
    )


def _assert_browser_matches_reference(actual: dict, expected: dict) -> None:
    for reference_key, runtime_key in RUNTIME_FILTER_KEYS.items():
        assert actual["filters"][runtime_key] == expected["filters"][reference_key]
    assert sorted(actual["pressed"]) == sorted(expected["pulse_brands"])
    assert actual["activeWindow"] == expected["filters"]["window"]
    assert actual["preferences"]["locale"] == expected["locale"]
    assert actual["preferences"]["timezone"] == expected["timezone"]
    assert actual["preferences"]["lens"] == {
        "brands": expected["brand_lens"],
        "nationalism": expected["nationalism_lens"],
    }


def _apply_reference_action(state: dict, control: str, value: str) -> dict:
    return set_control(state, control, value)


def test_stateful_filter_actions_keep_browser_and_reference_model_aligned() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        class FilterStoreMachine(RuleBasedStateMachine):
            def __init__(self) -> None:
                super().__init__()
                self.context, self.page = _new_page(browser, "state-machine")
                self.expected = initial_state()

            @rule(brand=st.sampled_from(["deepseek", "mimo"]))
            def pulse_brand(self, brand: str) -> None:
                self.page.locator(f'[data-pw-pulse-entry="{brand}"]').click()
                self.expected = toggle_pulse_brand(self.expected, brand)

            @rule(window=st.sampled_from([1, 7, 30, 365]))
            def window(self, window: int) -> None:
                self.page.locator(f'[data-pw-window-btn="{window}"]').click()
                self.expected = set_control(self.expected, "window", window)

            @rule(mode=st.sampled_from(["off", "only"]))
            def unsanctioned(self, mode: str) -> None:
                self.page.locator('[data-pw-filter-group="unsanctioned"]').set_checked(
                    mode == "only"
                )
                self.expected = set_control(self.expected, "unsanctioned", mode)

            @rule(locale=st.sampled_from(["en", "zh_cn", "original"]))
            def locale(self, locale: str) -> None:
                self.page.evaluate("value => window.pwFilter.setPreference('locale', value)", locale)
                self.expected = set_control(self.expected, "locale", locale)

            @rule(timezone=st.sampled_from(["local", "ca"]))
            def timezone(self, timezone: str) -> None:
                self.page.evaluate(
                    "value => window.pwFilter.setPreference('timezone', value)", timezone
                )
                self.expected = set_control(self.expected, "timezone", timezone)

            @rule(action=st.sampled_from(STATEFUL_ACTIONS))
            def declared_control(self, action: tuple[str, str]) -> None:
                control, value = action
                if control in MULTI_CONTROLS:
                    runtime_key = RUNTIME_FILTER_KEYS[control]
                    browser_value: str | list[str] = ALL if value == ALL else [value]
                    self.page.evaluate(
                        "([key, nextValue]) => window.pwFilter.set(key, nextValue)",
                        [runtime_key, browser_value],
                    )
                elif control == "unsanctioned":
                    self.page.locator(
                        '[data-pw-filter-group="unsanctioned"]'
                    ).set_checked(value == "only")
                elif control == "window":
                    self.page.locator(f'[data-pw-window-btn="{value}"]').click()
                elif control in {"locale", "timezone"}:
                    self.page.evaluate(
                        "([key, nextValue]) => window.pwFilter.setPreference(key, nextValue)",
                        [control, value],
                    )
                elif control == "brand_lens":
                    self.page.evaluate(
                        "value => window.pwFilter.setLens('brands', value)", value
                    )
                elif control == "nationalism_lens":
                    self.page.evaluate(
                        "value => window.pwFilter.setLens('nationalism', value)", value
                    )
                else:
                    raise AssertionError(f"unmapped declared control: {control}")
                self.expected = _apply_reference_action(
                    self.expected, control, value
                )

            @invariant()
            def projections_agree(self) -> None:
                _assert_browser_matches_reference(
                    _browser_snapshot(self.page), self.expected
                )

            def teardown(self) -> None:
                self.context.close()

        run_state_machine_as_test(
            FilterStoreMachine,
            settings=settings(
                max_examples=12,
                stateful_step_count=12,
                deadline=None,
                derandomize=True,
                suppress_health_check=[HealthCheck.too_slow],
            ),
        )
        browser.close()


def test_every_covering_row_executes_against_the_browser_store() -> None:
    """The generated t-way suite must reach runtime code, not only its oracle."""

    rows = covering_rows(DECLARATION)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context, page = _new_page(browser, "covering-rows")
        try:
            actual_rows = page.evaluate(
                """({rows, defaults, runtimeKeys, multiControls}) => {
                  const reset = () => {
                    Object.entries(runtimeKeys).forEach(([control, runtimeKey]) => {
                      if (!(control in defaults)) return;
                      window.pwFilter.set(runtimeKey, defaults[control]);
                    });
                    window.pwFilter.setPreference('locale', 'en');
                    window.pwFilter.setPreference('timezone', 'local');
                    window.pwFilter.setLens('brands', 'open');
                    window.pwFilter.setLens('nationalism', 'us');
                  };
                  const apply = (control, value) => {
                    if (multiControls.includes(control)) {
                      window.pwFilter.set(
                        runtimeKeys[control], value === '__all__' ? '__all__' : [value]
                      );
                    } else if (control === 'unsanctioned') {
                      window.pwFilter.set('unsanctioned', value);
                    } else if (control === 'window') {
                      window.pwFilter.set('window', Number(value));
                    } else if (control === 'locale' || control === 'timezone') {
                      window.pwFilter.setPreference(control, value);
                    } else if (control === 'brand_lens') {
                      window.pwFilter.setLens('brands', value);
                    } else if (control === 'nationalism_lens') {
                      window.pwFilter.setLens('nationalism', value);
                    } else {
                      throw new Error('unmapped covering control: ' + control);
                    }
                  };
                  return rows.map((row) => {
                    reset();
                    Object.entries(row).forEach(([control, value]) => apply(control, value));
                    return {
                      filters: window.pwFilter.get(),
                      preferences: window.pwFilter.getPreferences(),
                      pressed: [...document.querySelectorAll('[data-pw-pulse-entry]')]
                        .filter(node => node.getAttribute('aria-pressed') === 'true')
                        .map(node => node.getAttribute('data-pw-pulse-entry')),
                      activeWindow: Number(document.querySelector(
                        '[data-pw-window-btn][aria-pressed="true"]'
                      ).getAttribute('data-pw-window-btn')),
                    };
                  });
                }""",
                {
                    "rows": rows,
                    "defaults": DEFAULT_FILTERS,
                    "runtimeKeys": RUNTIME_FILTER_KEYS,
                    "multiControls": list(MULTI_CONTROLS),
                },
            )
            assert len(actual_rows) == len(rows)
            for row, actual in zip(rows, actual_rows, strict=True):
                expected = initial_state()
                for control, value in row.items():
                    expected = _apply_reference_action(expected, control, value)
                _assert_browser_matches_reference(actual, expected)
        finally:
            context.close()
            browser.close()


def test_seeded_reversals_and_context_isolation_use_real_browser_state() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        first_context, first = _new_page(browser, "owner-a")

        first.locator('[data-pw-pulse-entry="deepseek"]').click()
        assert first.evaluate("window.pwFilter.get().brands") == ["deepseek"]
        assert first.locator('[data-pw-pulse-entry="deepseek"]').get_attribute(
            "aria-pressed"
        ) == "true"
        first.locator('[data-pw-pulse-entry="deepseek"]').click()
        assert first.evaluate("window.pwFilter.get().brands") == "__all__"
        assert first.evaluate("window.pwFilter.getPulseBrands()") == []

        first.locator('[data-pw-filter-group="unsanctioned"]').check()
        assert first.evaluate("window.pwFilter.get().unsanctioned") == "only"
        first.locator('[data-pw-filter-group="unsanctioned"]').uncheck()
        assert first.evaluate("window.pwFilter.get().unsanctioned") == "off"

        second_context, second = _new_page(browser, "owner-b")
        assert second.evaluate("window.pwFilter.get().brands") == "__all__"
        assert second.evaluate("window.pwFilter.get().unsanctioned") == "off"

        first_context.close()
        second_context.close()
        browser.close()
