// Focused runtime contract for the shared home Chart.js + pulse lifecycle.
// Run: node tests/test_pw_chart_filter.js

const fs = require('fs');
const path = require('path');
const vm = require('vm');

process.env.TZ = 'Asia/Tokyo';

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
  const computedAt = '2026-08-10T20:34:00+00:00';
  const days = windowDays === 1
    ? Array.from({ length: 288 }, (_, index) =>
      new Date(Date.parse(computedAt) - (288 - index) * 5 * 60 * 1000).toISOString())
    : Array.from({ length: windowDays }, (_, index) =>
      new Date(Date.parse(computedAt) - (windowDays - index - 1) * 24 * 60 * 60 * 1000)
        .toISOString().slice(0, 10));
  return {
    days,
    series: { qwen: days.map((_, index) => index === days.length - 1 ? count : 0) },
    stacked: { qwen: {} },
    colors: { qwen: '#f97316' },
    totals: { qwen: count },
    granularity: 'minute',
    window_days: windowDays,
    computed_at: computedAt,
    pulse: {
      window_days: windowDays,
      computed_at: computedAt,
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
    trend_narrative: {
      schema_version: 2,
      window_days: windowDays,
      computed_at: computedAt,
      state: 'available',
      state_label: 'Available',
      body: (pulseName || 'No trend') + ' leads attention.',
      body_prefix: '',
      body_remainder: 'leads attention.',
      observations: pulseName ? [
        'Attention rises and then holds.',
        'Engagement remains elevated.',
      ] : [],
      subjects: pulseName ? [{
        position: 0,
        support_type: 'measured_candidate',
        entity_type: 'brand',
        identity_type: 'brand',
        key: pulseName,
        display_name: pulseName,
        url: '/brands/' + pulseName + '/',
      }] : [],
      primary_brand: pulseName ? {
        key: pulseName,
        display_name: pulseName,
        url: '/brands/' + pulseName + '/',
      } : null,
      generated_at: computedAt,
      checked_at: computedAt,
      facts_as_of: computedAt,
      coverage_state: 'sufficient',
    },
    top_voices: {
      window_days: windowDays,
      computed_at: computedAt,
      entries: pulseName ? [{ handle: pulseName, voice_star: count }] : [],
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

function makeRegion(data, isLegacy, legend) {
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
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null; },
    setAttribute(name, value) { attrs[name] = String(value); },
    removeAttribute(name) { this.removed.push(name); },
    querySelector(selector) {
      if (selector === 'canvas.home-chart') return canvas;
      if (selector === '[data-pw-chart-status]') return status;
      if (selector === '[data-pw-chart-legend]') return legend;
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
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
    },
    setAttribute(name, value) { attrs[name] = String(value); },
  };
}

function makeNode() {
  const attrs = {};
  return {
    children: [],
    hidden: true,
    textContent: '',
    className: '',
    tagName: 'SPAN',
    href: '',
    target: '',
    rel: '',
    parentNode: null,
    get firstChild() { return this.children[0] || null; },
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    removeChild(child) { this.children = this.children.filter((item) => item !== child); },
    insertBefore(child) { return this.appendChild(child); },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
    },
    setAttribute(name, value) { attrs[name] = String(value); },
  };
}

function makeHeadline() {
  const root = makeNode();
  const bodyParent = makeNode();
  const prefix = makeNode();
  const body = makeNode();
  const state = makeNode();
  const voices = makeNode();
  voices.setAttribute('data-pw-empty-text', 'no top voices this period');
  const observations = makeNode();
  const status = makeNode();
  body.parentNode = bodyParent;
  root.querySelector = function (selector) {
    if (selector === '[data-pw-headline-prefix]') return prefix;
    if (selector === '[data-pw-headline-body]') return body;
    if (selector === '[data-pw-headline-state]') return state;
    if (selector === '[data-pw-headline-brand]') {
      return bodyParent.children.find((node) =>
        node.getAttribute('data-pw-headline-brand') !== null) || null;
    }
    if (selector === '[data-pw-headline-voice-entries]') return voices;
    if (selector === '[data-pw-headline-observations]') return observations;
    return null;
  };
  return { root, prefix, body, state, voices, observations, status };
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
  const legend = { innerHTML: '' };
  const region = makeRegion(initial, Boolean(options.legacy), legend);
  const pulseBar = makePulseBar();
  const pulseStatus = { hidden: true, textContent: '' };
  const headline = makeHeadline();
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
  FakeChart.defaults = { color: '#666666' };

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
      if (selector === '[data-pw-headline]') return options.noRoot || options.legacy ? null : headline.root;
      if (selector === '[data-pw-headline-status]') return options.noRoot || options.legacy ? null : headline.status;
      return null;
    },
    createElement(tagName) {
      const node = makeNode();
      node.tagName = String(tagName || 'span').toUpperCase();
      return node;
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
    sandbox, document, region, pulseBar, pulseStatus, headline, legend, fetchCalls,
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

  console.log('--- one-day axes + legend ordering ---');
  const oneDay = payload(1, 4, 'deepseek');
  oneDay.series = {
    qwen: oneDay.days.map(() => 1),
    deepseek: oneDay.days.map(() => 2),
    minimax: oneDay.days.map(() => 3),
    chart_only: oneDay.days.map(() => 4),
  };
  oneDay.stacked = { qwen: {}, deepseek: {}, minimax: {}, chart_only: {} };
  oneDay.colors = {
    qwen: '#f97316', deepseek: '#3b82f6', minimax: '#22c55e', chart_only: '#9ca3af',
  };
  oneDay.totals = { qwen: 1, deepseek: 2, minimax: 3, chart_only: 4 };
  oneDay.pulse.entries = ['deepseek', 'minimax', 'qwen'].map((nickname, index) => ({
    nickname,
    display_name: nickname,
    display_name_en: nickname,
    display_name_zh_cn: nickname,
    accent_color: oneDay.colors[nickname],
    current_count: 10 - index,
    prior_count: 1,
    delta_percent: 50,
    status: 'numeric',
    direction: 'up',
  }));
  const axis = makeSandbox({ initial: oneDay });
  const scales = axis.charts[0].config.options.scales;
  assert(JSON.stringify(Object.keys(scales).sort()) === JSON.stringify(['x', 'xCalifornia', 'y']),
    '1d config creates local, California, and y scales');
  assert(scales.x.position === 'bottom' && scales.xCalifornia.position === 'bottom',
    'local and California time are both below the plot');
  assert(scales.x.weight < scales.xCalifornia.weight,
    'local time is the inner bottom axis immediately above California time');
  assert(scales.x.ticks.autoSkip === false && scales.xCalifornia.ticks.autoSkip === false,
    'both 1d axes keep the fixed 24 ticks at narrow widths');
  const localScale = { ticks: [], getLabelForValue(value) { return oneDay.days[value]; } };
  const californiaScale = { ticks: [], getLabelForValue(value) { return oneDay.days[value]; } };
  scales.x.afterBuildTicks(localScale);
  scales.xCalifornia.afterBuildTicks(californiaScale);
  assert(localScale.ticks.length === 24 && californiaScale.ticks.length === 24,
    'both 1d scales build exactly 24 positions');
  const localLabels = localScale.ticks.map((tick, index, ticks) =>
    scales.x.ticks.callback.call(localScale, tick.value, index, ticks));
  const californiaLabels = californiaScale.ticks.map((tick, index, ticks) =>
    scales.xCalifornia.ticks.callback.call(californiaScale, tick.value, index, ticks));
  assert(JSON.stringify(localLabels) === JSON.stringify([
    '6:00', '', '8:00', '', '10:00', '', '12:00', '', '14:00', '', '16:00', '',
    '18:00', '', '20:00', '', '22:00', '', '0:00', '', '2:00', '', '4:00', '',
  ]), 'local labels cover the next whole hour through the current hour');
  assert(californiaLabels.length === 24 && californiaLabels.every((label) => label === '' || /^\d{1,2}:00$/.test(label)),
    'California labels show only even wall-clock hours with minute suffixes');
  assert(scales.x.grid.drawTicks === true && scales.xCalifornia.grid.drawTicks === true &&
    scales.x.grid.drawOnChartArea === false && scales.xCalifornia.grid.drawOnChartArea === false,
    'odd hours retain hash marks without adding vertical plot grid lines');
  assert(scales.x.ticks.color === '#666666' && scales.xCalifornia.ticks.color === 'rgba(251, 191, 36, 0.45)',
    'axis colors retain the chart default locally and dim the CA pill tint below');
  assert(
    axis.legend.innerHTML.indexOf('data-pw-chart-brand="deepseek"') <
      axis.legend.innerHTML.indexOf('data-pw-chart-brand="minimax"') &&
    axis.legend.innerHTML.indexOf('data-pw-chart-brand="minimax"') <
      axis.legend.innerHTML.indexOf('data-pw-chart-brand="qwen"') &&
    axis.legend.innerHTML.indexOf('data-pw-chart-brand="qwen"') <
      axis.legend.innerHTML.indexOf('data-pw-chart-brand="chart_only"'),
    'legend follows pulse ranking before deterministic chart-only brands'
  );

  const dstPayload = payload(1, 4, 'qwen');
  const dstEnd = Date.parse('2026-11-01T12:34:00+00:00');
  dstPayload.days = Array.from({ length: 288 }, (_, index) =>
    new Date(dstEnd - (288 - index) * 5 * 60 * 1000).toISOString());
  dstPayload.series.qwen = dstPayload.days.map(() => 1);
  const dst = makeSandbox({ initial: dstPayload });
  const dstScale = dst.charts[0].config.options.scales.xCalifornia;
  const dstRuntime = { ticks: [] };
  dstScale.afterBuildTicks(dstRuntime);
  const dstLabels = dstRuntime.ticks.map((tick, index, ticks) =>
    dstScale.ticks.callback.call(dstRuntime, tick.value, index, ticks));
  assert(dstLabels.length === 24 && dstLabels.filter((label) => label === '').length >= 12,
    'California fall-back keeps 24 real tick instants while suppressing odd-hour labels');

  const sevenDay = makeSandbox({ initial: payload(7, 4, 'qwen') });
  assert(JSON.stringify(Object.keys(sevenDay.charts[0].config.options.scales).sort()) === JSON.stringify(['x', 'y']),
    'non-1d config keeps the existing single date axis');

  console.log('--- filter request + timed refresh ownership ---');
  const base = makeSandbox();
  const focusedBrand = base.headline.root.querySelector('[data-pw-headline-brand]');
  const refreshedPayload = payload(7, 4, 'qwen');
  refreshedPayload.top_voices.entries = [
    { handle: 'first', voice_star: 4 },
    { handle: 'second', voice_star: 3 },
    { handle: 'third', voice_star: 2 },
  ];
  base.fetchQueue.push(response(refreshedPayload));
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
  assert(baseQuery.get('locale') === 'en', 'chart sends the active locale explicitly');
  assert(!base.fetchCalls[0].url.includes('renderer='), 'request has no renderer parameter');
  assert(base.region.currentPayload.window_days === 7, 'chart commits the returned window');
  assert(base.pulseBar.getAttribute('data-pw-window') === '7', 'pulse commits the same window atomically');
  assert(base.headline.root.getAttribute('data-pw-window') === '7', 'headline commits the same window atomically');
  assert(base.headline.body.textContent === 'leads attention.',
    'headline commits the matching narrative body remainder without duplicating its anchor');
  assert(base.headline.root.querySelector('[data-pw-headline-brand]').textContent === 'qwen',
    'headline commits the matching primary subject anchor');
  assert(base.headline.root.querySelector('[data-pw-headline-brand]') === focusedBrand,
    'refresh reconciles the brand anchor in place so keyboard focus can survive');
  const contextual = makeSandbox();
  const contextualPayload = payload(7, 4, 'MiniMax');
  contextualPayload.trend_narrative.body =
    'In a mostly unremarkable week, MiniMax led with a small rise.';
  contextualPayload.trend_narrative.body_prefix = 'In a mostly unremarkable week, ';
  contextualPayload.trend_narrative.body_remainder = ' led with a small rise.';
  contextual.fetchQueue.push(response(contextualPayload));
  contextual.document.dispatchEvent(
    new contextual.sandbox.CustomEvent('pw:filter-change', { detail: {} })
  );
  await flush();
  assert(contextual.headline.prefix.textContent === 'In a mostly unremarkable week, ' &&
    contextual.headline.body.textContent === ' led with a small rise.',
    'headline keeps context on both sides of the linked primary brand');
  assert(contextual.headline.root.querySelector('[data-pw-headline-brand]').textContent === 'MiniMax',
    'contextual headline links the in-place primary brand exactly once');
  assert(base.headline.observations.children.length === 2 &&
    base.headline.observations.children[0].textContent === 'Attention rises and then holds.' &&
    base.headline.observations.children[1].textContent === 'Engagement remains elevated.',
    'headline commits both analytical observations from the matching response');
  assert(!base.headline.observations.hidden,
    'headline exposes its observation list when observations are present');
  const refreshedVoiceNodes = base.headline.voices.children;
  assert(refreshedVoiceNodes.length === 5,
    'refresh inserts one separator sibling between each pair of voice links');
  assert(refreshedVoiceNodes.filter((node) => node.tagName === 'A').length === 3,
    'refresh keeps every voice as a separate link');
  assert(refreshedVoiceNodes.filter((node) => node.className === 'voice-separator').length === 2,
    'voice separators are non-link siblings');
  assert(refreshedVoiceNodes[1].textContent === ', ' && refreshedVoiceNodes[3].textContent === ', ',
    'voice separators preserve readable punctuation and spacing');
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
  assert(race.headline.root.getAttribute('data-pw-window') === '7', 'older headline response cannot overwrite newer state');
  assert(race.pulseBar.innerHTML.includes('new') && !race.pulseBar.innerHTML.includes('old'),
    'chart and pulse values come from the winning response only');

  console.log('--- failures preserve last-good and allow retry ---');
  const recovery = makeSandbox();
  const originalHtml = recovery.region.innerHTML;
  const originalPulse = recovery.pulseBar.innerHTML;
  const originalHeadline = recovery.headline.body.textContent;
  recovery.fetchQueue.push(response('server error', false));
  recovery.document.dispatchEvent(new recovery.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(recovery.region.innerHTML === originalHtml, 'non-OK response preserves last-good chart');
  assert(recovery.pulseBar.innerHTML === originalPulse, 'non-OK response preserves last-good pulse');
  assert(recovery.headline.body.textContent === originalHeadline, 'non-OK response preserves last-good headline');
  assert(recovery.region.status.textContent === 'Chart refresh failed' && !recovery.region.status.hidden,
    'failure exposes localized non-blocking chart state');
  assert(recovery.pulseStatus.textContent === 'Pulse refresh failed' && !recovery.pulseStatus.hidden,
    'failure exposes localized non-blocking pulse state');
  assert(recovery.headline.status.textContent.includes('Trend summary refresh failed') && !recovery.headline.status.hidden,
    'failure exposes localized non-blocking headline state');
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
  assert(empty.headline.voices.children.length === 1 &&
    empty.headline.voices.children[0].className === 'muted' &&
    empty.headline.voices.children[0].textContent === 'no top voices this period',
    'valid empty voices render the localized SSR-equivalent fallback');
  assert(empty.headline.observations.children.length === 0 && empty.headline.observations.hidden,
    'valid empty narrative hides an empty observation list');
  empty.fetchQueue.push(response(payload(1, 0, null)));
  empty.document.dispatchEvent(new empty.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(empty.headline.voices.children.length === 1,
    'repeated empty refresh does not duplicate the Top Voices fallback');
  const emptyHtml = empty.region.innerHTML;
  empty.fetchQueue.push(response('<canvas class="home-chart" data-home=\'{"bad":true}\'></canvas>'));
  empty.document.dispatchEvent(new empty.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(empty.region.innerHTML === emptyHtml, 'malformed payload preserves last-good empty projection');
  const malformedChild = payload(7, 9, 'broken');
  malformedChild.top_voices.entries = [null];
  empty.fetchQueue.push(response(malformedChild));
  empty.document.dispatchEvent(new empty.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(empty.region.innerHTML === emptyHtml,
    'malformed nested projection preserves the complete last-good projection');
  const priorObservationText = base.headline.observations.children.map((node) => node.textContent).join('|');
  const malformedObservations = payload(30, 8, 'bad-observations');
  malformedObservations.trend_narrative.observations = ['valid', 42];
  base.fetchQueue.push(response(malformedObservations));
  base.document.dispatchEvent(new base.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(base.region.currentPayload.window_days === 7 &&
    base.headline.observations.children.map((node) => node.textContent).join('|') === priorObservationText,
    'malformed observations preserve every last-good projection');

  console.log('--- schema-one headline fallback remains compatible ---');
  const schemaOne = makeSandbox();
  const legacyPayload = payload(7, 3, 'legacy');
  legacyPayload.trend_narrative.schema_version = 1;
  delete legacyPayload.trend_narrative.body_remainder;
  delete legacyPayload.trend_narrative.observations;
  schemaOne.fetchQueue.push(response(legacyPayload));
  schemaOne.document.dispatchEvent(new schemaOne.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(schemaOne.headline.body.textContent === legacyPayload.trend_narrative.body,
    'schema-one narrative without body_remainder renders its full body');

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
