// Focused runtime contract for the shared home Chart.js + pulse lifecycle.
// Run: node tests/test_pw_chart_filter.js

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'monitor', 'static', 'pw-chart.js'),
  'utf8'
);

let passed = 0;
let failed = 0;
function assert(condition, label) {
  if (condition) {
    passed += 1;
    console.log('  PASS ' + label);
  } else {
    failed += 1;
    console.error('  FAIL ' + label);
  }
}

function payload(windowDays, count, pulseName) {
  return {
    days: ['2026-08-11T00:00:00+00:00'],
    series: { qwen: [count] },
    stacked: { qwen: {} },
    colors: { qwen: '#f97316' },
    totals: { qwen: count },
    granularity: 'minute',
    window_days: windowDays,
    computed_at: '2026-08-11T12:00:00+00:00',
    pulse: {
      window_days: windowDays,
      computed_at: '2026-08-11T12:00:00+00:00',
      entries: pulseName ? [{
        nickname: pulseName,
        display_name: pulseName,
        display_name_en: pulseName,
        display_name_zh_cn: pulseName,
        accent_color: '#f97316',
        current_count: count,
        prior_count: 1,
        delta_percent: 50,
        status: 'numeric',
        direction: 'up',
      }] : [],
    },
  };
}

function fragment(data) {
  return '<canvas class="home-chart" data-home=\'' + JSON.stringify(data) + '\'></canvas>' +
    '<p class="chart-state" data-pw-chart-status hidden></p>';
}

function parsePayload(html) {
  const match = String(html).match(/data-home='([^']+)'/);
  return match ? JSON.parse(match[1]) : null;
}

function makeCanvas(data) {
  return {
    tagName: 'CANVAS',
    _payload: data,
    getAttribute(name) { return name === 'data-home' ? JSON.stringify(this._payload) : null; },
    getContext() { return {}; },
  };
}

function makeRegion(data, isLegacy) {
  const attrs = {
    'data-pw-chart-empty-text': 'No chart data',
    'data-pw-chart-error-text': 'Chart refresh failed',
    'data-pw-pulse-empty-text': 'No pulse data',
    'data-pw-pulse-error-text': 'Pulse refresh failed',
    'data-pw-pulse-new-text': 'NEW',
    'data-pw-locale': 'en',
  };
  const status = { hidden: true, textContent: '' };
  let html = fragment(data);
  let canvas = makeCanvas(data);
  return {
    id: isLegacy ? 'home-chart' : '',
    status,
    removed: [],
    matches(selector) { return !isLegacy && selector === '.home-chart-wrap[data-pw-chart]'; },
    getAttribute(name) { return attrs[name] || null; },
    setAttribute(name, value) { attrs[name] = String(value); },
    removeAttribute(name) { this.removed.push(name); },
    querySelector(selector) {
      if (selector === 'canvas.home-chart') return canvas;
      if (selector === '[data-pw-chart-status]') return status;
      if (selector === '[data-pw-chart-legend]') return null;
      return null;
    },
    get innerHTML() { return html; },
    set innerHTML(value) {
      html = value;
      const next = parsePayload(value);
      if (next) canvas = makeCanvas(next);
    },
    get currentPayload() { return canvas._payload; },
  };
}

function makePulseBar() {
  const attrs = {};
  return {
    innerHTML: '',
    getAttribute(name) { return attrs[name] || null; },
    setAttribute(name, value) { attrs[name] = String(value); },
  };
}

function response(data, ok = true) {
  return Promise.resolve({
    ok,
    text() { return Promise.resolve(typeof data === 'string' ? data : fragment(data)); },
  });
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

function makeSandbox(options = {}) {
  const listeners = {};
  const initial = options.initial || payload(1, 2, 'initial');
  const region = makeRegion(initial, Boolean(options.legacy));
  const pulseBar = makePulseBar();
  const pulseStatus = { hidden: true, textContent: '' };
  const legend = { innerHTML: '' };
  const fetchCalls = [];
  const fetchQueue = [];
  const charts = [];
  const intervals = [];
  let filters = { brands: '__all__', window: 1 };

  function FakeChart(canvas, config) {
    this.canvas = canvas;
    this.config = config;
    this.data = config.data;
    this.destroyed = false;
    this.destroy = function () { this.destroyed = true; };
    charts.push(this);
    return this;
  }
  FakeChart.getChart = function (canvas) {
    return charts.find((chart) => chart.canvas === canvas) || null;
  };

  function FakeDOMParser() {}
  FakeDOMParser.prototype.parseFromString = function (html) {
    const parsed = parsePayload(html);
    return {
      querySelector(selector) {
        return selector === 'canvas.home-chart' && parsed ? makeCanvas(parsed) : null;
      },
    };
  };

  const document = {
    readyState: 'complete',
    addEventListener(event, fn) { (listeners[event] ||= []).push(fn); },
    dispatchEvent(event) {
      (listeners[event.type] || []).forEach((fn) => fn(event));
      return true;
    },
    querySelectorAll(selector) {
      if (selector === 'canvas.home-chart') return options.noRoot ? [] : [region.querySelector('canvas.home-chart')];
      return [];
    },
    querySelector(selector) {
      if (selector === '.home-chart-wrap[data-pw-chart]') return options.noRoot || options.legacy ? null : region;
      if (selector === '[data-pw-pulse]') return options.noRoot || options.legacy ? null : pulseBar;
      if (selector === '[data-pw-pulse-status]') return options.noRoot || options.legacy ? null : pulseStatus;
      if (selector === '[data-pw-chart-legend]') return options.noRoot || options.legacy ? null : legend;
      return null;
    },
    getElementById(id) { return options.legacy && id === 'home-chart' ? region : null; },
    body: { addEventListener() {} },
  };

  const sandbox = {
    console,
    Promise,
    JSON,
    Math,
    Number,
    Date,
    DOMParser: FakeDOMParser,
    AbortController: function () { this.signal = {}; this.abort = function () {}; },
    setTimeout,
    clearTimeout,
    setInterval(fn, ms) { intervals.push({ fn, ms }); return intervals.length; },
    clearInterval() {},
    window: { pwFilter: { get() { return JSON.parse(JSON.stringify(filters)); } } },
    document,
    Chart: FakeChart,
    CustomEvent: function (type, init) { this.type = type; this.detail = (init && init.detail) || {}; },
    getComputedStyle() { return { getPropertyValue() { return ''; } }; },
    fetch(url, init) {
      fetchCalls.push({ url, init: init || {} });
      if (!fetchQueue.length) return response(payload(filters.window || 1, 1, 'default'));
      const next = fetchQueue.shift();
      return typeof next === 'function' ? next() : next;
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: 'pw-chart.js' });
  return {
    sandbox, document, region, pulseBar, pulseStatus, legend, fetchCalls,
    fetchQueue, charts, intervals,
    setFilters(value) { filters = value; },
  };
}

function flush() { return new Promise((resolve) => setTimeout(resolve, 10)); }

(async function run() {
  console.log('--- canvas-only source contract ---');
  assert(!/SVG_NS|renderSvg|svg\.home-chart|renderer=canvas/.test(src),
    'SVG helpers and renderer query mode are absent');
  assert(/canvas\.home-chart/.test(src), 'canvas remains the sole home-chart renderer');
  assert(!src.includes('{{AGENT_ATTRIBUTION}}'), 'product source has no execution/meta placeholder');
  assert(!/home-brand-chart|brand-chart/.test(src),
    'shared home runtime does not compete with the dedicated brand-chart owner');

  console.log('--- filter request + timed refresh ownership ---');
  const base = makeSandbox();
  base.fetchQueue.push(response(payload(7, 4, 'qwen')));
  base.setFilters({ brands: ['stale'], sentiment: ['positive'], window: 1 });
  const eventFilters = { brands: ['qwen'], sentiment: ['mixed'], window: 7 };
  base.document.dispatchEvent(new base.sandbox.CustomEvent('pw:filter-change', {
    detail: { filters: eventFilters },
  }));
  await flush();
  assert(base.fetchCalls.length === 1, 'filter change starts one shared chart/pulse request');
  assert(base.fetchCalls[0].url.startsWith('/chart.html?filters='), 'request uses /chart.html');
  const baseQuery = new URLSearchParams(base.fetchCalls[0].url.split('?')[1]);
  assert(JSON.stringify(JSON.parse(baseQuery.get('filters'))) === JSON.stringify(eventFilters),
    'chart serializes the immutable event filter snapshot, not a divergent DOM read');
  assert(baseQuery.get('window') === '7', 'chart sends the active window explicitly');
  assert(!base.fetchCalls[0].url.includes('renderer='), 'request has no renderer parameter');
  assert(base.region.currentPayload.window_days === 7, 'chart commits the returned window');
  assert(base.pulseBar.getAttribute('data-pw-window') === '7', 'pulse commits the same window atomically');
  assert(base.charts[0].destroyed, 'replacing a chart fragment destroys the detached Chart.js instance');
  assert(base.intervals.length === 1 && base.intervals[0].ms === 60000,
    'pw-chart owns one 60-second refresh timer');
  assert(['hx-get', 'hx-trigger', 'hx-vals', 'hx-swap'].every((name) => base.region.removed.includes(name)),
    'racing htmx refresh attributes are disabled');

  console.log('--- latest response wins atomically ---');
  const race = makeSandbox();
  const oldRequest = deferred();
  const newRequest = deferred();
  race.fetchQueue.push(oldRequest.promise, newRequest.promise);
  race.setFilters({ window: 1, brands: ['old'] });
  race.document.dispatchEvent(new race.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  race.setFilters({ window: 7, brands: ['new'] });
  race.document.dispatchEvent(new race.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  newRequest.resolve(await response(payload(7, 7, 'new')));
  await flush();
  oldRequest.resolve(await response(payload(1, 1, 'old')));
  await flush();
  assert(race.region.currentPayload.window_days === 7, 'older chart response cannot overwrite newer state');
  assert(race.pulseBar.getAttribute('data-pw-window') === '7', 'older pulse response cannot overwrite newer state');
  assert(race.pulseBar.innerHTML.includes('new') && !race.pulseBar.innerHTML.includes('old'),
    'chart and pulse values come from the winning response only');

  console.log('--- failures preserve last-good and allow retry ---');
  const recovery = makeSandbox();
  const originalHtml = recovery.region.innerHTML;
  const originalPulse = recovery.pulseBar.innerHTML;
  recovery.fetchQueue.push(response('server error', false));
  recovery.document.dispatchEvent(new recovery.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(recovery.region.innerHTML === originalHtml, 'non-OK response preserves last-good chart');
  assert(recovery.pulseBar.innerHTML === originalPulse, 'non-OK response preserves last-good pulse');
  assert(recovery.region.status.textContent === 'Chart refresh failed' && !recovery.region.status.hidden,
    'failure exposes localized non-blocking chart state');
  assert(recovery.pulseStatus.textContent === 'Pulse refresh failed' && !recovery.pulseStatus.hidden,
    'failure exposes localized non-blocking pulse state');
  recovery.fetchQueue.push(response(payload(30, 3, 'retry')));
  recovery.document.dispatchEvent(new recovery.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(recovery.region.currentPayload.window_days === 30, 'a valid retry succeeds after failure');

  console.log('--- valid empty is distinct from malformed ---');
  const empty = makeSandbox();
  empty.fetchQueue.push(response(payload(1, 0, null)));
  empty.document.dispatchEvent(new empty.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(empty.region.status.textContent === 'No chart data' && !empty.region.status.hidden,
    'valid empty chart renders localized no-data state');
  assert(empty.pulseStatus.textContent === 'No pulse data' && !empty.pulseStatus.hidden,
    'valid empty pulse renders localized no-data state');
  const emptyHtml = empty.region.innerHTML;
  empty.fetchQueue.push(response('<canvas class="home-chart" data-home=\'{"bad":true}\'></canvas>'));
  empty.document.dispatchEvent(new empty.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(empty.region.innerHTML === emptyHtml, 'malformed payload preserves last-good empty projection');

  console.log('--- /internal fallback keeps one canvas lifecycle ---');
  const internal = makeSandbox({ legacy: true });
  internal.fetchQueue.push(response(payload(1, 2, 'internal')));
  internal.document.dispatchEvent(new internal.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(internal.fetchCalls.length === 1, 'legacy #home-chart fallback still refetches');
  assert(!internal.fetchCalls[0].url.includes('renderer='), 'legacy fallback uses the same renderer-free URL');

  console.log('');
  console.log('--- summary ---');
  console.log(passed + ' passed, ' + failed + ' failed');
  process.exit(failed === 0 ? 0 : 1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
