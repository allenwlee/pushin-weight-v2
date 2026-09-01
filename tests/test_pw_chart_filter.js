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
    granularity: windowDays === 1 ? 'minute' : 'day',
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

function payloadV3(windowDays, brands) {
  const data = payload(windowDays, 8, brands[0]);
  const computedAt = data.computed_at;
  data.trend_narrative = {
    schema_version: 3,
    window_days: windowDays,
    computed_at: computedAt,
    facts_as_of: computedAt,
    state: brands.length > 1 ? 'mixed' : 'available',
    state_label: brands.length > 1 ? 'Mixed' : 'Available',
    items: brands.map((brand, index) => ({
      id: 'brand-trend:' + (index + 1),
      brand: {
        key: brand,
        display_name: brand,
        url: '/brands/' + brand + '/',
      },
      state: index === 1 ? 'stale' : 'available',
      state_label: index === 1
        ? 'Stale · last verified 10 min ago'
        : 'Available',
      headline: brand + ' conversation focused on hands-on use.',
      secondary: 'Users discussed setup and performance tradeoffs.',
      verified_at: computedAt,
      attempted_at: computedAt,
      freshness: {
        kind: 'verified',
        relative: 'last verified 10 min ago',
        absolute: 'Aug 10, 2026, 20:34 UTC',
        absolute_iso: computedAt,
      },
    })),
    selection: {
      mode: 'explicit',
      requested_count: brands.length,
      returned_count: Math.min(2, brands.length),
      truncated: brands.length > 2,
      summary: brands.length > 2 ? '2 of ' + brands.length + ' selected' : '',
    },
    body: brands[0] + ' conversation focused on hands-on use.',
    body_prefix: '',
    body_remainder: ' conversation focused on hands-on use.',
    observations: ['Users discussed setup and performance tradeoffs.'],
    subjects: [],
    primary_brand: {
      key: brands[0],
      display_name: brands[0],
      url: '/brands/' + brands[0] + '/',
    },
    generated_at: computedAt,
    checked_at: computedAt,
    coverage_state: 'unknown',
  };
  return data;
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
  const attrs = {};
  return {
    tagName: 'CANVAS',
    _payload: data,
    getAttribute(name) {
      if (name === 'data-home') return JSON.stringify(this._payload);
      return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
    },
    setAttribute(name, value) { attrs[name] = String(value); },
    removeAttribute(name) { delete attrs[name]; },
    getContext() { return {}; },
  };
}

function makeLocaleButton(active) {
  const attrs = {};
  let isActive = Boolean(active);
  return {
    classList: {
      contains(name) { return name === 'is-active' && isActive; },
      remove(name) { if (name === 'is-active') isActive = false; },
      toggle(name, force) {
        if (name === 'is-active') isActive = force === undefined ? !isActive : Boolean(force);
      },
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
    },
    setAttribute(name, value) { attrs[name] = String(value); },
    removeAttribute(name) { delete attrs[name]; },
  };
}

function makeRegion(data, isLegacy, legend) {
  const attrs = {
    'data-pw-chart-empty-text': 'No chart data',
    'data-pw-chart-error-text': 'Chart refresh failed',
    'data-pw-pulse-empty-text': 'No pulse data',
    'data-pw-pulse-error-text': 'Pulse refresh failed',
    'data-pw-pulse-new-text': 'NEW',
    'data-pw-headline-updated-text': 'Trend summaries updated',
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
  let ownText = '';
  const node = {
    children: [],
    hidden: true,
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
  Object.defineProperty(node, 'textContent', {
    get() {
      return ownText + this.children.map((child) => child.textContent).join('');
    },
    set(value) {
      ownText = String(value || '');
      this.children = [];
    },
  });
  return node;
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
  const items = makeNode();
  const selection = makeNode();
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
    if (selector === '[data-pw-headline-items]') return items;
    if (selector === '[data-pw-headline-selection]') return selection;
    if (selector === '[data-pw-headline-legacy]') return bodyParent;
    return null;
  };
  return { root, prefix, body, state, voices, observations, status, items, selection, bodyParent };
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
  const dispatched = [];
  const localeButtons = [makeLocaleButton(true), makeLocaleButton(false), makeLocaleButton(false)];
  let filters = { brands: '__all__', window: 1 };
  let tzMode = options.tzMode || 'local';
  const comparison = options.comparison || {
    key: 'california',
    timezone: 'America/Los_Angeles',
    label: 'California',
    shortLabel: 'CA',
    shortLabelZh: '加州',
  };

  function FakeChart(canvas, config) {
    this.canvas = canvas;
    this.config = config;
    this.data = config.data;
    this.destroyed = false;
    this.activeElements = [];
    this.tooltipActiveElements = [];
    this.hitElements = [];
    this.updateCalls = [];
    this.setActiveElements = function (elements) { this.activeElements = elements; };
    this.tooltip = {
      setActiveElements: (elements, position) => {
        this.tooltipActiveElements = elements;
        this.tooltipPosition = position;
      },
    };
    this.getElementsAtEventForMode = function (_event, mode, options) {
      this.lastHitMode = mode;
      this.lastHitOptions = options;
      return this.hitElements;
    };
    this.getDatasetMeta = function (datasetIndex) {
      return {
        hidden: false,
        data: this.data.datasets[datasetIndex].data.map((value, index) => ({
          x: index,
          y: Number(value) || 0,
          getCenterPoint() { return { x: this.x, y: this.y }; },
        })),
      };
    };
    this.isDatasetVisible = function () { return true; };
    this.update = function (mode) { this.updateCalls.push(mode); };
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
      dispatched.push(event);
      (listeners[event.type] || []).forEach((fn) => fn(event));
      return true;
    },
    querySelectorAll(selector) {
      if (selector === 'canvas.home-chart') return options.noRoot ? [] : [region.querySelector('canvas.home-chart')];
      if (selector === '[data-pw-locale-btn]') return localeButtons;
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
    body: (() => {
      const attrs = { 'data-pw-locale': options.locale || 'en' };
      return {
      addEventListener() {},
      getAttribute(name) {
        return Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null;
      },
      setAttribute(name, value) { attrs[name] = String(value); },
      removeAttribute(name) { delete attrs[name]; },
      };
    })(),
    documentElement: { getAttribute() { return null; } },
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
    clearInterval(id) {
      if (intervals[id - 1]) intervals[id - 1].cleared = true;
    },
    window: {
      pwFilter: { get() { return JSON.parse(JSON.stringify(filters)); } },
      pwIcon: {
        render(symbolId, className) {
          return '<svg class="pw-icon ' + className + '" aria-hidden="true"><use href="#' +
            symbolId + '"></use></svg>';
        },
      },
      __pwTz: {
        get mode() { return tzMode; },
        getComparison() {
          const zh = (options.locale || 'en') === 'zh_cn';
          return Object.assign({}, comparison, {
            localLabel: zh ? '本地' : 'local',
            shortLabel: zh && comparison.shortLabelZh
              ? comparison.shortLabelZh
              : comparison.shortLabel,
          });
        },
        comparisonHour(timestamp) {
          return Number(new Intl.DateTimeFormat('en-US', {
            timeZone: comparison.timezone,
            hour: 'numeric',
            hourCycle: 'h23',
          }).format(new Date(timestamp)));
        },
      },
    },
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
    fetchQueue, charts, intervals, localeButtons, dispatched,
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
  oneDay.pulse.entries = ['deepseek', 'qwen', 'minimax'].map((nickname, index) => ({
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
  const oneDayTotal = axis.charts[0].config.data.datasets[0];
  assert(oneDayTotal.borderWidth === 4 / 3,
    'one-day total-series stroke is reduced by exactly one third');
  assert(oneDayTotal.pointRadius === 1,
    'one-day total-series point radius is reduced by exactly one third');
  assert(oneDayTotal.pointHitRadius === 8,
    'one-day point hit radius remains unchanged');
  assert(JSON.stringify(Object.keys(scales).sort()) === JSON.stringify(['x', 'xComparison', 'y']),
    '1d config creates local, comparison, and y scales');
  assert(scales.x.position === 'bottom' && scales.xComparison.position === 'bottom',
    'local and comparison time are both below the plot');
  assert(scales.x.weight < scales.xComparison.weight,
    'local time is the inner bottom axis immediately above comparison time');
  assert(scales.x.ticks.autoSkip === false && scales.xComparison.ticks.autoSkip === false,
    'both 1d axes keep the fixed 24 ticks at narrow widths');
  const localScale = { ticks: [], getLabelForValue(value) { return oneDay.days[value]; } };
  const comparisonScale = { ticks: [], getLabelForValue(value) { return oneDay.days[value]; } };
  scales.x.afterBuildTicks(localScale);
  scales.xComparison.afterBuildTicks(comparisonScale);
  assert(localScale.ticks.length === 24 && comparisonScale.ticks.length === 24,
    'both 1d scales build exactly 24 positions');
  const localLabels = localScale.ticks.map((tick, index, ticks) =>
    scales.x.ticks.callback.call(localScale, tick.value, index, ticks));
  const comparisonLabels = comparisonScale.ticks.map((tick, index, ticks) =>
    scales.xComparison.ticks.callback.call(comparisonScale, tick.value, index, ticks));
  assert(JSON.stringify(localLabels) === JSON.stringify([
    '6:00', '', '8:00', '', '10:00', '', '12:00', '', '14:00', '', '16:00', '',
    '18:00', '', '20:00', '', '22:00', '', '0:00', '', '2:00', '', '4:00', '',
  ]), 'local labels cover the next whole hour through the current hour');
  assert(comparisonLabels.length === 24 && comparisonLabels.every((label) => label === '' || /^\d{1,2}:00$/.test(label)),
    'comparison labels show only even wall-clock hours with minute suffixes');
  assert(scales.x.grid.drawTicks === true && scales.x.grid.drawOnChartArea === false,
    'local odd hours retain hash marks without adding vertical plot grid lines');
  assert(scales.xComparison.grid.display === false && scales.xComparison.grid.drawTicks === false,
    'comparison time draws no hourly hash marks');
  assert(scales.x.border.display === true && scales.xComparison.border.display === false,
    'only the local time row draws a horizontal axis baseline');
  assert(scales.x.title.text === 'local' && scales.xComparison.title.text === 'CA' &&
    scales.x.title.display === false && scales.xComparison.title.display === false,
    'one-day row labels do not consume separate full-width title rows');
  assert(axis.charts[0].config.plugins.some((plugin) => plugin.id === 'pwTimezoneRowLabels') &&
    axis.charts[0].config.options.plugins.pwTimezoneRowLabels.display === true,
    'compact timezone labels are drawn inline with their time rows');
  assert(scales.x.ticks.color === '#666666' && scales.xComparison.ticks.color === 'rgba(251, 191, 36, 0.45)',
    'local mode keeps local fully opaque and dims the comparison row');

  const comparisonMode = makeSandbox({ initial: oneDay, tzMode: 'ca' });
  const comparisonModeScales = comparisonMode.charts[0].config.options.scales;
  assert(comparisonModeScales.x.ticks.color === 'rgba(102, 102, 102, 0.55)' &&
    comparisonModeScales.xComparison.ticks.color === 'rgba(251, 191, 36, 1)',
    'comparison mode makes its row fully opaque and dims local lettering');

  const beijing = makeSandbox({
    initial: oneDay,
    locale: 'zh_cn',
    comparison: {
      key: 'beijing',
      timezone: 'Asia/Shanghai',
      label: 'Beijing',
      shortLabel: 'Beijing',
      shortLabelZh: '北京',
    },
  });
  const beijingScales = beijing.charts[0].config.options.scales;
  assert(beijingScales.x.title.text === '本地' && beijingScales.xComparison.title.text === '北京',
    'Chinese California-local browsers label local and Beijing rows');
  assert(
    axis.legend.innerHTML.indexOf('data-pw-chart-brand="deepseek"') <
      axis.legend.innerHTML.indexOf('data-pw-chart-brand="qwen"') &&
    axis.legend.innerHTML.indexOf('data-pw-chart-brand="qwen"') <
      axis.legend.innerHTML.indexOf('data-pw-chart-brand="minimax"') &&
    axis.legend.innerHTML.indexOf('data-pw-chart-brand="minimax"') <
      axis.legend.innerHTML.indexOf('data-pw-chart-brand="chart_only"'),
    'legend keeps the fixed DeepSeek, Qwen, MiniMax order before chart-only brands'
  );

  const dstPayload = payload(1, 4, 'qwen');
  const dstEnd = Date.parse('2026-11-01T12:34:00+00:00');
  dstPayload.days = Array.from({ length: 288 }, (_, index) =>
    new Date(dstEnd - (288 - index) * 5 * 60 * 1000).toISOString());
  dstPayload.series.qwen = dstPayload.days.map(() => 1);
  const dst = makeSandbox({ initial: dstPayload });
  const dstScale = dst.charts[0].config.options.scales.xComparison;
  const dstRuntime = { ticks: [] };
  dstScale.afterBuildTicks(dstRuntime);
  const dstLabels = dstRuntime.ticks.map((tick, index, ticks) =>
    dstScale.ticks.callback.call(dstRuntime, tick.value, index, ticks));
  assert(dstLabels.length === 24 && dstLabels.filter((label) => label === '').length >= 12,
    'California fall-back keeps 24 real tick instants while suppressing odd-hour labels');

  const sevenDay = makeSandbox({ initial: payload(7, 4, 'qwen') });
  const sevenDayTotal = sevenDay.charts[0].config.data.datasets[0];
  assert(sevenDayTotal.borderWidth === 2 && sevenDayTotal.pointRadius === 0,
    'non-one-day total-series stroke and point radius remain unchanged');
  assert(JSON.stringify(Object.keys(sevenDay.charts[0].config.options.scales).sort()) === JSON.stringify(['x', 'y']),
    'non-1d config keeps the existing single date axis');

  console.log('--- one-day hover freeze lifecycle ---');
  const freezePayload = payload(1, 9, 'qwen');
  freezePayload.series.qwen[freezePayload.days.length - 2] = 3;
  const freeze = makeSandbox({ initial: freezePayload });
  const freezeChart = freeze.charts[0];
  const freezeIndex = freezePayload.days.length - 1;
  const priorIndex = freezeIndex - 1;
  const tooltipTitle = freezeChart.config.options.plugins.tooltip.callbacks.title([{
    dataIndex: freezeIndex,
    label: freezePayload.days[freezeIndex],
  }]);
  assert(Array.isArray(tooltipTitle) && tooltipTitle.length === 2 &&
    tooltipTitle[0].startsWith('Local: ') && tooltipTitle[1].startsWith('Beijing: '),
    'one-day tooltip identifies prettified browser-local and Beijing datetimes');
  assert(tooltipTitle.every((line) => !line.includes('T') && !line.includes('Z')),
    'tooltip does not expose raw ISO datetime text');
  const zhFreeze = makeSandbox({ initial: freezePayload, locale: 'zh_cn' });
  const zhTooltipTitle = zhFreeze.charts[0].config.options.plugins.tooltip.callbacks.title([{
    dataIndex: freezeIndex,
    label: freezePayload.days[freezeIndex],
  }]);
  assert(zhTooltipTitle[0].startsWith('本地 ') && zhTooltipTitle[1].startsWith('北京 '),
    'zh-CN tooltip identifies local and Beijing datetime rows in Chinese');

  freezeChart.hitElements = [{ datasetIndex: 0, index: freezeIndex }];
  freezeChart.config.options.onClick({ native: { type: 'click' } }, [], freezeChart);
  const startEvents = freeze.dispatched.filter((event) => event.type === 'pw:hover-freeze-start');
  assert(startEvents.length === 1 &&
    startEvents[0].detail.start === new Date(freezePayload.days[freezeIndex]).toISOString() &&
    Date.parse(startEvents[0].detail.end) - Date.parse(startEvents[0].detail.start) === 5 * 60 * 1000,
    'clicking an exact one-day point emits its half-open five-minute range');
  assert(freezeChart.lastHitMode === 'nearest' &&
    freezeChart.lastHitOptions.intersect === true &&
    freezeChart.lastHitOptions.axis === 'xy',
  'dense phone points resolve by nearest exact geometry instead of first overlapping index');
  assert(startEvents[0].detail.title.includes('Local: ') &&
    startEvents[0].detail.title.includes('Beijing: '),
    'frozen feed title uses the same local and Beijing datetime');
  assert(freeze.document.body.getAttribute('data-pw-hover-freeze') === 'true' &&
    freeze.region.querySelector('canvas.home-chart').getAttribute('data-pw-hover-freeze-index') === String(freezeIndex),
    'frozen state is exposed on the body and exact canvas point');
  assert(freeze.localeButtons.every((button) =>
    !button.classList.contains('is-active') && button.getAttribute('aria-pressed') === 'false'),
    'locale controls are visually and semantically unselected while frozen');
  assert(freeze.intervals[0].cleared === true,
    'starting hover freeze pauses the owned chart refresh timer');
  assert(freezeChart.activeElements.length === 1 &&
    freezeChart.tooltipActiveElements.length === 1,
    'the selected chart point and tooltip remain programmatically active');

  freeze.document.dispatchEvent(new freeze.sandbox.CustomEvent('pw:filter-change', {
    detail: { filters: { brands: ['qwen'], sentiment: ['negative'], window: 1 } },
  }));
  assert(freeze.fetchCalls.length === 0,
    'filter changes cannot replace the chart while hover freeze is active');
  freeze.localeButtons[1].classList.toggle('is-active', true);
  freeze.document.dispatchEvent(new freeze.sandbox.CustomEvent('pw:locale-change', {
    detail: { locale: 'zh_cn' },
  }));
  assert(freeze.fetchCalls.length === 0 && freeze.localeButtons.every((button) =>
    !button.classList.contains('is-active')),
  'programmatic locale changes neither refetch nor expose a selected locale while frozen');
  freezeChart.activeElements = [];
  freezeChart.tooltipActiveElements = [];
  const freezePlugin = freezeChart.config.plugins.find((plugin) => plugin.id === 'pwHoverFreeze');
  const pluginArgs = {};
  freezePlugin.afterEvent(freezeChart, pluginArgs);
  assert(freezeChart.activeElements.length === 1 &&
    freezeChart.tooltipActiveElements.length === 1 && pluginArgs.changed === true,
    'chart events reassert the frozen point and persistent tooltip');

  freezeChart.config.options.onClick({ native: { type: 'click' } }, [], freezeChart);
  assert(freeze.dispatched.filter((event) => event.type === 'pw:hover-freeze-end').length === 0 &&
    freeze.document.body.getAttribute('data-pw-hover-freeze') === 'true',
    'clicking the same frozen point keeps hover freeze active');

  freezeChart.hitElements = [{ datasetIndex: 0, index: priorIndex }];
  freezeChart.config.options.onClick({ native: { type: 'click' } }, [], freezeChart);
  assert(freeze.dispatched.filter((event) => event.type === 'pw:hover-freeze-end').length === 1 &&
    freeze.document.body.getAttribute('data-pw-hover-freeze') === null,
    'clicking a different chart point releases instead of silently switching the bucket');
  assert(freeze.localeButtons[0].classList.contains('is-active') &&
    freeze.localeButtons.slice(1).every((button) => !button.classList.contains('is-active')) &&
    freeze.localeButtons.every((button) => button.getAttribute('aria-pressed') === null),
    'release restores the exact locale selection and original ARIA state');
  assert(freeze.intervals.length === 2 && !freeze.intervals[1].cleared,
    'release restarts exactly one chart refresh timer');

  freezeChart.hitElements = [{ datasetIndex: 0, index: freezeIndex }];
  freezeChart.config.options.onClick({ native: { type: 'click' } }, [], freezeChart);
  freeze.document.dispatchEvent({ type: 'click', target: {} });
  assert(freeze.dispatched.filter((event) => event.type === 'pw:hover-freeze-end').length === 2,
    'a click outside the frozen canvas releases the view before downstream handlers');

  freezeChart.hitElements = [{ datasetIndex: 0, index: freezeIndex }];
  freezeChart.config.options.onClick({ native: { type: 'click' } }, [], freezeChart);
  freezeChart.hitElements = [];
  freezeChart.config.options.onClick({ native: { type: 'click' } }, [], freezeChart);
  assert(freeze.dispatched.filter((event) => event.type === 'pw:hover-freeze-end').length === 3,
    'clicking empty chart space also releases hover freeze');
  assert(freeze.intervals.length === 4 &&
    freeze.intervals.slice(0, -1).every((timer) => timer.cleared) &&
    !freeze.intervals[freeze.intervals.length - 1].cleared,
  'repeated freeze cycles retain one and only one live chart refresh timer');

  const freezeRace = makeSandbox({ initial: freezePayload });
  const staleChartResponse = deferred();
  freezeRace.fetchQueue.push(staleChartResponse.promise);
  freezeRace.document.dispatchEvent(new freezeRace.sandbox.CustomEvent('pw:filter-change', {
    detail: { filters: { brands: ['qwen'], window: 7 } },
  }));
  const freezeRaceChart = freezeRace.charts[0];
  freezeRaceChart.hitElements = [{ datasetIndex: 0, index: freezeIndex }];
  freezeRaceChart.config.options.onClick(
    { native: { type: 'click' } }, [], freezeRaceChart
  );
  staleChartResponse.resolve(await response(payload(7, 12, 'stale')));
  await flush();
  assert(freezeRace.region.currentPayload.window_days === 1 &&
    freezeRace.document.body.getAttribute('data-pw-hover-freeze') === 'true',
  'an in-flight chart response cannot replace a newly frozen one-day chart');
  freezeRace.document.dispatchEvent({ type: 'click', target: {} });

  const noFreezePayload = payload(7, 4, 'qwen');
  const noFreeze = makeSandbox({ initial: noFreezePayload });
  const noFreezeChart = noFreeze.charts[0];
  noFreezeChart.hitElements = [{ datasetIndex: 0, index: noFreezePayload.days.length - 1 }];
  noFreezeChart.config.options.onClick({ native: { type: 'click' } }, [], noFreezeChart);
  assert(noFreeze.dispatched.every((event) => event.type !== 'pw:hover-freeze-start'),
    '7/30/365-style non-one-day payloads cannot enter hover freeze');

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

  console.log('--- DTO v3 per-brand narrative cards ---');
  const cards = makeSandbox();
  cards.fetchQueue.push(response(payloadV3(7, ['deepseek', 'minimax'])));
  cards.document.dispatchEvent(new cards.sandbox.CustomEvent('pw:filter-change', { detail: {} }));
  await flush();
  assert(cards.headline.items.children.length === 2,
    'DTO v3 renders one semantic card for each returned brand');
  assert(cards.headline.items.children.every((node) => node.tagName === 'ARTICLE'),
    'DTO v3 brand narratives render as semantic articles');
  assert(cards.headline.items.children[0].getAttribute('data-pw-brand-key') === 'deepseek' &&
    cards.headline.items.children[1].getAttribute('data-pw-brand-key') === 'minimax',
    'DTO v3 preserves the server-selected brand order');
  assert(cards.headline.items.children[1].textContent.includes('Stale · last verified 10 min ago'),
    'each card exposes its own stale relative timestamp');
  assert(cards.headline.items.children[1].getAttribute('data-pw-verified-at') ===
    '2026-08-10T20:34:00+00:00',
    'each card retains the exact absolute verification timestamp');
  const firstHeadline = cards.headline.items.children[0].children[1];
  const firstDisclosure = firstHeadline.children[0];
  const firstSecondary = cards.headline.items.children[0].children[2];
  const firstSecondaryCopy = firstSecondary.children[0];
  assert(firstDisclosure.textContent === 'more' &&
    firstDisclosure.getAttribute('aria-expanded') === 'false',
    'replacement headlines start behind one collapsed more control');
  assert(firstSecondary.hidden && firstSecondary.children.length === 1,
    'replacement secondary copy starts hidden without a second hide control');
  assert(firstSecondaryCopy.getAttribute('role') === null &&
    firstSecondaryCopy.getAttribute('tabindex') === null,
    'replacement secondary copy remains plain selectable text');
  const zhCards = makeSandbox({ locale: 'zh_cn' });
  zhCards.fetchQueue.push(response(payloadV3(7, ['deepseek'])));
  zhCards.document.dispatchEvent(
    new zhCards.sandbox.CustomEvent('pw:filter-change', { detail: {} })
  );
  await flush();
  assert(zhCards.headline.items.children[0].children[1].children[0].textContent === '更多',
    'replacement headlines use the collapsed zh-CN disclosure label');
  assert(cards.headline.bodyParent.hidden,
    'DTO v3 hides the legacy shared-headline body');

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

  const obsoleteFailure = makeSandbox();
  const obsoleteRequest = deferred();
  const winningRequest = deferred();
  obsoleteFailure.fetchQueue.push(obsoleteRequest.promise, winningRequest.promise);
  obsoleteFailure.setFilters({ window: 7, brands: ['mimo'] });
  obsoleteFailure.document.dispatchEvent(
    new obsoleteFailure.sandbox.CustomEvent('pw:filter-change', { detail: {} })
  );
  obsoleteFailure.setFilters({ window: 1, brands: ['mimo'] });
  obsoleteFailure.document.dispatchEvent(
    new obsoleteFailure.sandbox.CustomEvent('pw:filter-change', { detail: {} })
  );
  winningRequest.resolve(await response(payload(1, 5, 'mimo')));
  await flush();
  obsoleteRequest.reject(new Error('obsolete seven-day request failed'));
  await flush();
  assert(obsoleteFailure.region.currentPayload.window_days === 1,
    'Mimo 7d to 1d keeps the successful one-day chart after an obsolete failure');
  assert(obsoleteFailure.region.status.hidden && obsoleteFailure.pulseStatus.hidden,
    'an obsolete Mimo failure cannot surface stale chart or pulse warnings');

  const aborted = makeSandbox();
  const abortedRequest = deferred();
  aborted.fetchQueue.push(abortedRequest.promise);
  aborted.document.dispatchEvent(
    new aborted.sandbox.CustomEvent('pw:filter-change', { detail: {} })
  );
  const abortError = new Error('request aborted');
  abortError.name = 'AbortError';
  abortedRequest.reject(abortError);
  await flush();
  assert(aborted.region.status.hidden && aborted.pulseStatus.hidden,
    'an aborted chart request does not masquerade as a refresh failure');

  const duplicate = makeSandbox();
  const firstDuplicate = deferred();
  const secondDuplicate = deferred();
  duplicate.fetchQueue.push(firstDuplicate.promise, secondDuplicate.promise);
  duplicate.setFilters({ window: 1, brands: ['mimo'] });
  duplicate.document.dispatchEvent(
    new duplicate.sandbox.CustomEvent('pw:filter-change', { detail: {} })
  );
  duplicate.document.dispatchEvent(
    new duplicate.sandbox.CustomEvent('pw:filter-change', { detail: {} })
  );
  secondDuplicate.resolve(await response(payload(1, 9, 'mimo')));
  await flush();
  firstDuplicate.resolve(await response(payload(1, 2, 'mimo')));
  await flush();
  assert(duplicate.region.currentPayload.totals.qwen === 9,
    'a duplicate older request cannot commit after the latest duplicate intent');

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
  const internalTotal = internal.charts[0].config.data.datasets[0];
  assert(internalTotal.borderWidth === 2 && internalTotal.pointRadius === 1.5,
    'one-day sizing delta is confined to the public homepage');
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
