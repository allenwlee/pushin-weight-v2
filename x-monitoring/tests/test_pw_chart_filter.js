// U3 unit tests for pw-chart.js filter-change wiring.
// Runs under Node with a minimal browser stub.
// Run: node tests/test_pw_chart_filter.js
// Exits 0 on success, 1 on failure.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const listeners = {};
let pwFilterStore = { brands: '__all__' };
let fetchCalls = [];
const fetchResponseBody = '<canvas class="home-chart" data-home=\'{"days":["2026-07-15"],"series":{},"stacked":{},"colors":{},"totals":{}}\'></canvas>';

function makeElement(id, tag) {
  return {
    id: id || '',
    tagName: (tag || 'DIV').toUpperCase(),
    children: [],
    innerHTML: '',
    _attrs: {},
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k]; },
    querySelector(sel) {
      if (sel === 'canvas' || sel === 'canvas.home-chart' || sel === 'canvas.home-brand-chart') {
        return makeElement(null, 'canvas');
      }
      return null;
    },
    addEventListener(ev, fn) {
      if (!listeners[ev]) listeners[ev] = [];
      listeners[ev].push({ target: this, fn: fn });
    },
    appendChild() {},
    removeChild() {},
    destroy() {},
    getContext() { return {}; },
  };
}

const fakeChartInstances = [];
function FakeChart(canvas, config) {
  this.canvas = canvas;
  this.config = config;
  this.data = config && config.data ? config.data : { datasets: [] };
  this.update = function () {};
  this.destroy = function () {};
  fakeChartInstances.push(this);
  return this;
}
FakeChart.getChart = function (canvas) {
  return fakeChartInstances.find(function (c) { return c.canvas === canvas; }) || null;
};

function makeSandbox(homeChartPresent, brandChartPresent) {
  return {
    console: console,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    setInterval: setInterval,
    clearInterval: clearInterval,
    window: { pwFilter: { get: function () { return JSON.parse(JSON.stringify(pwFilterStore)); } } },
    document: {
      readyState: 'complete',
      addEventListener(ev, fn) {
        if (!listeners[ev]) listeners[ev] = [];
        listeners[ev].push({ target: 'document', fn: fn });
      },
      dispatchEvent(ev) {
        const handlers = listeners[ev.type] || [];
        handlers.forEach(function (h) { try { h.fn(ev); } catch (e) {} });
        return true;
      },
      querySelectorAll() { return []; },
      body: { addEventListener() {} },
      getElementById(id) {
        if (id === 'home-chart') return homeChartPresent ? makeElement(id, 'section') : null;
        if (id === 'brand-chart') return brandChartPresent ? makeElement(id, 'section') : null;
        return null;
      },
      createElement(tag) { return makeElement(null, tag); },
    },
    fetch: function (url, opts) {
      fetchCalls.push({ url: url, opts: opts || {} });
      return Promise.resolve({ text: function () { return Promise.resolve(fetchResponseBody); } });
    },
    Chart: FakeChart,
    CustomEvent: function (type, init) { this.type = type; this.detail = (init && init.detail) || {}; },
    getComputedStyle: function () { return { getPropertyValue: function () { return ''; } }; },
  };
}

let passed = 0;
let failed = 0;
function assert(cond, label) {
  if (cond) {
    passed++;
    console.log('  PASS ' + label);
  } else {
    failed++;
    console.error('  FAIL ' + label);
  }
}
function resetListeners() { Object.keys(listeners).forEach(function (k) { delete listeners[k]; }); }

const src = fs.readFileSync(
  path.join(__dirname, '..', 'x_monitor', 'static', 'pw-chart.js'),
  'utf8'
);

// ---- Test 1: filter change with #home-chart present fires fetch ----
console.log('--- pw-chart.js subscribes to pw:filter-change ---');
resetListeners();
let sandbox = makeSandbox(true, false);
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: 'pw-chart.js' });

fetchCalls = [];
pwFilterStore = { brands: ['qwen'] };
sandbox.document.dispatchEvent(new sandbox.CustomEvent('pw:filter-change', { detail: { filters: pwFilterStore } }));

setTimeout(function () {
  assert(fetchCalls.length === 1, 'fetch was called once on filter change');
  if (fetchCalls[0]) {
    const url = fetchCalls[0].url;
    assert(url.indexOf('/api/v1/home.chart.html') === 0, 'fetched the chart HTML endpoint');
    assert(url.indexOf('filters=') > 0, 'filters query param present');
    assert(url.indexOf(encodeURIComponent(JSON.stringify({ brands: ['qwen'] }))) > 0,
      'filters JSON encodes the active brand list');
  }

  // ---- Test 2: empty brand list still produces a fetch ----
  console.log('--- empty brand list still produces a fetch with filters= ---');
  fetchCalls = [];
  pwFilterStore = { brands: [] };
  sandbox.document.dispatchEvent(new sandbox.CustomEvent('pw:filter-change', { detail: { filters: pwFilterStore } }));
  setTimeout(function () {
    assert(fetchCalls.length === 1, 'fetch fired for empty brands');
    if (fetchCalls[0]) {
      assert(fetchCalls[0].url.indexOf(encodeURIComponent('"brands":[]')) > 0,
        'empty brands array encoded in query');
    }

    // ---- Test 3: __all__ sentinel ----
    console.log('--- __all__ sentinel still triggers a fetch ---');
    fetchCalls = [];
    pwFilterStore = { brands: '__all__' };
    sandbox.document.dispatchEvent(new sandbox.CustomEvent('pw:filter-change', { detail: { filters: pwFilterStore } }));
    setTimeout(function () {
      assert(fetchCalls.length === 1, 'fetch fired for __all__ sentinel');

      // ---- Test 4: missing pwFilter ----
      console.log('--- missing window.pwFilter gracefully no-ops ---');
      fetchCalls = [];
      sandbox.window.pwFilter = undefined;
      sandbox.document.dispatchEvent(new sandbox.CustomEvent('pw:filter-change', { detail: {} }));
      setTimeout(function () {
        assert(fetchCalls.length === 1, 'fetch still fires (with empty filters {}) when pwFilter is missing');

        // ---- Test 5 (H1 regression): no #home-chart → no fetch ----
        console.log('--- H1: pw-chart no-ops when only #brand-chart exists ---');
        resetListeners();
        let h1Sandbox = makeSandbox(false, true);
        vm.createContext(h1Sandbox);
        vm.runInContext(src, h1Sandbox, { filename: 'pw-chart-h1.js' });
        fetchCalls = [];
        h1Sandbox.document.dispatchEvent(new h1Sandbox.CustomEvent('pw:filter-change', { detail: {} }));
        setTimeout(function () {
          assert(fetchCalls.length === 0, 'no fetch fires when #home-chart is absent (single-brand page)');

          console.log('');
          console.log('--- summary ---');
          console.log(passed + ' passed, ' + failed + ' failed');
          process.exit(failed === 0 ? 0 : 1);
        }, 30);
      }, 30);
    }, 30);
  }, 30);
}, 30);
