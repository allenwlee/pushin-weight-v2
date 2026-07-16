// U3 unit tests for pw-chart.js filter-change wiring.
// Runs under Node with a minimal browser stub.
// Run: node tests/test_pw_chart_filter.js
// Exits 0 on success, 1 on failure.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// ---------------------------------------------------------------------------
// Minimal browser stub: document, window, fetch, Chart, getComputedStyle
// ---------------------------------------------------------------------------

const listeners = {};   // event -> [{target, fn}]
let pwFilterStore = { brands: '__all__' };
let fetchCalls = [];
const fetchResponseBody = '<canvas class="home-chart" data-home=\'{"days":["2026-07-15"],"series":{},"stacked":{},"colors":{},"totals":{}}\'></canvas>';

function makeElement(id, tag) {
  const el = {
    id: id || '',
    tagName: (tag || 'DIV').toUpperCase(),
    children: [],
    innerHTML: '',
    _attrs: {},
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k]; },
    querySelector(sel) {
      if (sel === 'canvas' || sel === 'canvas.home-chart') {
        return makeElement(null, 'canvas');
      }
      return null;
    },
    addEventListener(ev, fn) {
      if (!listeners[ev]) listeners[ev] = [];
      listeners[ev].push({ target: el, fn: fn });
    },
    appendChild() {},
    removeChild() {},
    destroy() {},
    getContext() { return {}; },
  };
  return el;
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

const sandbox = {
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: setInterval,
  clearInterval: clearInterval,
  window: {},
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
      if (id === 'home-chart' || id === 'brand-chart') return makeElement(id, 'section');
      return null;
    },
    createElement(tag) { return makeElement(null, tag); },
  },
  fetch: function (url, opts) {
    fetchCalls.push({ url: url, opts: opts || {} });
    return Promise.resolve({
      text: function () { return Promise.resolve(fetchResponseBody); },
    });
  },
  Chart: FakeChart,
  CustomEvent: function (type, init) {
    this.type = type;
    this.detail = (init && init.detail) || {};
  },
  getComputedStyle: function () { return { getPropertyValue: function () { return ''; } }; },
};
sandbox.window.pwFilter = {
  get: function () { return JSON.parse(JSON.stringify(pwFilterStore)); },
};

const dispatchedEvents = [];
const origDispatch = sandbox.document.dispatchEvent;
sandbox.document.dispatchEvent = function (ev) {
  dispatchedEvents.push({ type: ev.type, detail: ev.detail });
  return origDispatch.call(this, ev);
};

const src = fs.readFileSync(
  path.join(__dirname, '..', 'x_monitor', 'static', 'pw-chart.js'),
  'utf8'
);

vm.createContext(sandbox);
try {
  vm.runInContext(src, sandbox, { filename: 'pw-chart.js' });
} catch (e) {
  console.error('FAIL: pw-chart.js failed to evaluate:', e.message);
  process.exit(1);
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
function reset() {
  fetchCalls = [];
  dispatchedEvents.length = 0;
}

console.log('--- pw-chart.js subscribes to pw:filter-change ---');
reset();
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

  console.log('--- empty brand list still produces a fetch with filters= ---');
  reset();
  pwFilterStore = { brands: [] };
  sandbox.document.dispatchEvent(new sandbox.CustomEvent('pw:filter-change', { detail: { filters: pwFilterStore } }));
  setTimeout(function () {
    assert(fetchCalls.length === 1, 'fetch fired for empty brands');
    if (fetchCalls[0]) {
      assert(fetchCalls[0].url.indexOf(encodeURIComponent('"brands":[]')) > 0,
        'empty brands array encoded in query');
    }

    console.log('--- __all__ sentinel still triggers a fetch ---');
    reset();
    pwFilterStore = { brands: '__all__' };
    sandbox.document.dispatchEvent(new sandbox.CustomEvent('pw:filter-change', { detail: { filters: pwFilterStore } }));
    setTimeout(function () {
      assert(fetchCalls.length === 1, 'fetch fired for __all__ sentinel');

      console.log('--- missing window.pwFilter gracefully no-ops ---');
      reset();
      sandbox.window.pwFilter = undefined;
      sandbox.document.dispatchEvent(new sandbox.CustomEvent('pw:filter-change', { detail: {} }));
      setTimeout(function () {
        assert(fetchCalls.length === 1, 'fetch still fires (with empty filters {}) when pwFilter is missing');
        if (fetchCalls[0]) {
          const url = fetchCalls[0].url;
          assert(url.indexOf(encodeURIComponent('{}')) > 0 || url.indexOf('filters=' + encodeURIComponent('{}')) > 0,
            'filters query param is empty-object JSON when pwFilter missing');
        }

        console.log('');
        console.log('--- summary ---');
        console.log(passed + ' passed, ' + failed + ' failed');
        process.exit(failed === 0 ? 0 : 1);
      }, 30);
    }, 30);
  }, 30);
}, 30);
