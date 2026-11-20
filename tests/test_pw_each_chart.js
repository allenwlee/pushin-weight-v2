// Runtime contract for the Each chart renderer and interactive category legend.
// Run: node tests/test_pw_each_chart.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../monitor/static/pw-each-chart.js'), 'utf8');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.dataset = {}; this.attributes = {};
    this.children = []; this.listeners = {}; this.hidden = false; this.checked = false;
    this.style = { setProperty(key, value) { this[key] = value; } };
    this.classList = { add() {}, remove() {}, toggle() {} }; this._text = '';
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  appendChild(child) { this.children.push(child); child.parentElement = this; return child; }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  replaceChildren(...children) { this._text = ''; this.children = []; this.append(...children); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key] ?? null; }
  removeAttribute(key) { delete this.attributes[key]; }
  addEventListener(key, callback) { (this.listeners[key] ||= []).push(callback); }
  fire(key) { (this.listeners[key] || []).forEach(fn => fn({ target: this })); }
  click() { this.fire('click'); }
  focus() { this.fire('focus'); }
  getBoundingClientRect() { return { top: 0, bottom: 24, height: 24, width: 120 }; }
  querySelector() { return null; }
  querySelectorAll(selector) { return selector === '[data-each-category]' ? this.children.filter(child => child.dataset.eachCategory) : []; }
}

function fixture({ brand = 'llama', tab = 'product_labels', translated = false, keys } = {}) {
  const entries = (keys || ['__unclassified__', '__no_product_signal__', 'bug', 'complaint']).map((key, index) => ({
    key, label: translated ? ['未分类', '无产品信号', '错误', '投诉'][index] : key,
    color: ['#cbd5e1', '#000000', '#ff7018', '#eb3568'][index % 4],
  }));
  return { brand, tab, entries, series: Object.fromEntries(entries.map((entry, index) => [entry.key, [index + 1, index + 3]])),
    totals: [10, 18], days: ['2026-11-18', '2026-11-19'], window_days: 7,
    granularity: 'day', counting_unit: 'label_assignments',
    bucket_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone };
}

function harness(data = fixture(), options = {}) {
  const nodes = Object.fromEntries(['root', 'canvas', 'panel', 'face', 'legend', 'status', 'box', 'headline', 'headlineStatus', 'bucketNote'].map(key => [key, new Element()]));
  nodes.root.dataset = { selectedBrand: data.brand, selectedTab: data.tab, chartUrl: '/chart/', chartError: 'Refresh failed', chartEmpty: 'Empty', chartLoading: 'Loading' };
  const modes = ['percent', 'volume'].map(value => Object.assign(new Element('input'), { value, checked: value === 'percent' }));
  const locale = options.locale || 'en';
  const tabLabels = {
    en: { sentiment: 'Sentiment', product_labels: 'Product', role: 'Role' },
    zh_cn: { sentiment: '情绪', product_labels: '产品', role: '角色' },
    ja: { sentiment: '感情', product_labels: '製品', role: '役割' },
  };
  const tabs = ['sentiment', 'product_labels', 'role'].map(tab => {
    const node = new Element('button'); node.dataset.eachTab = tab;
    node.textContent = tabLabels[locale][tab]; return node;
  });
  const pulses = ['llama', 'deepseek'].map(brand => { const node = new Element('button'); node.dataset.pwPulseEntry = brand; return node; });
  const selectors = { '[data-each-canvas]': nodes.canvas, '.each-chart-panel': nodes.panel, '.each-chart-face': nodes.face,
    '[data-each-legend]': nodes.legend, '[data-each-status]': nodes.status, '.pw-canvas-box': nodes.box, '[data-each-bucket-note]': nodes.bucketNote };
  nodes.root.querySelector = selector => selectors[selector] || null;
  nodes.root.querySelectorAll = selector => selector === '[data-each-tab]' ? tabs : selector === '[data-each-mode]' ? modes : [];
  nodes.face.querySelector = selector => selectors[selector] || null;
  nodes.headline.querySelector = selector => selector === '[data-pw-headline-status]' ? nodes.headlineStatus : null;
  const requests = [], charts = [], timers = [];
  function Chart(canvas, config) {
    this.canvas = canvas; this.config = config; this.data = config.data; this.options = config.options;
    this.chartArea = { top: 12, bottom: 288 }; this.destroyed = false;
    this.destroy = () => { this.destroyed = true; };
    this.update = () => { (config.plugins || []).forEach(plugin => plugin.afterLayout && plugin.afterLayout(this)); };
    charts.push(this); this.update();
  }
  const document = {
    body: { dataset: { pwWindow: String(data.window_days), pwLocale: locale } },
    querySelector: selector => selector === '[data-pw-each-chart]' ? nodes.root : selector === '[data-pw-headline]' ? nodes.headline : null,
    querySelectorAll: selector => selector === '[data-pw-pulse-entry]' ? pulses : [],
    getElementById: id => id === 'each-initial-chart' ? { textContent: JSON.stringify(data) } : null,
    createElement: tag => new Element(tag), createTextNode: value => ({ textContent: value }),
    addEventListener() {}, dispatchEvent() {},
  };
  const window = { Chart, matchMedia: () => ({ matches: true }),
    location: { href: 'https://example.test/dashboard/each?brand=' + data.brand },
    history: { replaceState() {}, pushState() {} }, addEventListener() {},
    setTimeout: (fn, delay) => { timers.push({ fn, delay, cancelled: false }); return timers.length; },
    clearTimeout: id => { if (timers[id - 1]) timers[id - 1].cancelled = true; }, requestAnimationFrame: callback => callback(),
  };
  if (options.time) window.pwTime = options.time;
  let receivedPayload;
  const json = Object.create(JSON);
  json.parse = text => { receivedPayload = JSON.parse(text); return receivedPayload; };
  vm.runInNewContext(source, { document, window, JSON: json, Intl, URL, URLSearchParams, AbortController, console,
    CustomEvent: function () {}, fetch: (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })) });
  const getChart = () => charts.at(-1);
  const button = key => nodes.legend.children.find(child => child.dataset.eachCategory === key);
  const switchMode = value => { modes.forEach(node => { node.checked = node.value === value; }); modes.find(node => node.value === value).fire('change'); };
  return { nodes, requests, charts, getChart, button, switchMode, tabs, pulses, timers, getPayload: () => receivedPayload };
}

function plain(value) { return JSON.parse(JSON.stringify(value)); }
const settled = () => new Promise(resolve => setImmediate(resolve));

test('B treatment preserves bottom-to-top datasets while reversing legend and tooltip', () => {
  const data = fixture(), h = harness(data), chart = h.getChart();
  assert.deepEqual(plain(chart.data.datasets.map(d => d.label)), data.entries.map(e => e.label));
  assert.deepEqual(h.nodes.legend.children.map(b => b.textContent), data.entries.map(e => e.label).reverse());
  assert.ok(h.nodes.legend.children.every(button => button.tagName === 'BUTTON'));
  assert.equal(chart.data.datasets[0].backgroundColor, 'rgba(130,144,167,0.34)');
  assert.equal(chart.data.datasets[2].borderColor, '#ff7018');
  assert.equal(chart.data.datasets[2].borderWidth, 2);
  assert.equal(chart.options.scales.x.grid.display, false);
  const items = [0, 1, 2, 3].map(datasetIndex => ({ datasetIndex }));
  items.sort(chart.options.plugins.tooltip.itemSort);
  assert.deepEqual(items.map(item => item.datasetIndex), [3, 2, 1, 0]);
  assert.equal(h.requests.length, 0);
});

test('legend centers span exact plot bounds for changing classifier category counts', () => {
  for (const count of [1, 4, 7, 10, 14, 18]) {
    const h = harness(fixture({ keys: Array.from({ length: count }, (_, index) => 'category_' + index) }));
    const chart = h.getChart();
    assert.equal(h.nodes.face.style['--each-plot-height'], undefined, 'legend count must not resize the plot');
    chart.chartArea = { top: 21, bottom: 421 }; chart.update();
    assert.deepEqual(h.nodes.legend.children.map(button => parseFloat(button.style.top)),
      Array.from({ length: count }, (_, index) => count === 1 ? 221 : 21 + index * 400 / (count - 1)));
  }
});

test('hover emphasizes a category without hiding or changing a single data value', () => {
  const h = harness(), chart = h.getChart(), before = JSON.stringify(chart.data.datasets.map(d => d.data));
  h.button('bug').fire('pointerenter');
  assert.equal(chart.data.datasets[2].backgroundColor, 'rgba(255,112,24,0.48)');
  assert.equal(chart.data.datasets[0].backgroundColor, 'rgba(130,144,167,0.055)');
  assert.equal(chart.data.datasets[0].borderColor, 'rgba(130,144,167,0.17)');
  assert.ok(chart.data.datasets.every(dataset => !dataset.hidden));
  assert.equal(JSON.stringify(chart.data.datasets.map(d => d.data)), before);
  h.button('bug').fire('pointerleave');
  assert.equal(chart.data.datasets[2].backgroundColor, 'rgba(255,112,24,0.34)');
  assert.equal(h.requests.length, 0);
});

test('click pins, temporary hover restores a pin, and second click clears it', () => {
  const h = harness(), chart = h.getChart(), bug = h.button('bug'), other = h.button('complaint');
  bug.click(); assert.equal(bug.getAttribute('aria-pressed'), 'true');
  other.fire('pointerenter'); assert.equal(chart.data.datasets[3].borderWidth, 2.7);
  other.fire('pointerleave'); assert.equal(chart.data.datasets[2].borderWidth, 2.7);
  bug.click(); assert.equal(bug.getAttribute('aria-pressed'), 'false');
  assert.ok(chart.data.datasets.every(dataset => dataset.borderWidth === 2));
  assert.equal(h.requests.length, 0);
});

test('focus emphasizes translated categories using stable keys', () => {
  const h = harness(fixture({ translated: true })), button = h.button('__unclassified__');
  button.focus(); assert.equal(h.getChart().data.datasets[0].backgroundColor, 'rgba(130,144,167,0.48)');
  button.fire('blur'); assert.equal(h.getChart().data.datasets[0].backgroundColor, 'rgba(130,144,167,0.34)');
});

test('local volume redraw preserves the pin, counts, order and request count', () => {
  const data = fixture(), h = harness(data);
  h.button('bug').click(); h.switchMode('volume');
  assert.equal(h.button('bug').getAttribute('aria-pressed'), 'true');
  assert.deepEqual(plain(h.getChart().data.datasets.map(d => d.data)), data.entries.map(entry => data.series[entry.key]));
  h.switchMode('percent');
  assert.equal(h.button('bug').getAttribute('aria-pressed'), 'true');
  assert.equal(h.requests.length, 0);
});

test('pending and failed requests retain committed chart and pin', async () => {
  const h = harness(), old = h.getChart(); h.button('bug').click();
  h.pulses[1].click(); assert.equal(old.destroyed, false);
  assert.equal(h.nodes.root.dataset.selectedBrand, 'llama');
  assert.equal(h.button('bug').getAttribute('aria-pressed'), 'true');
  h.requests.find(request => request.url.startsWith('/chart/')).reject(new Error('network'));
  await settled();
  assert.equal(old.destroyed, false);
  h.switchMode('volume'); assert.equal(h.button('bug').getAttribute('aria-pressed'), 'true');
  assert.match(h.nodes.status.textContent, /^Refresh failed Showing previous result \(llama, Product, 7d\)$/);
});

test('new committed identity clears pin and stale legend handlers cannot affect it', async () => {
  const h = harness(), oldButton = h.button('bug'); oldButton.click(); h.pulses[1].click();
  const request = h.requests.find(item => item.url.startsWith('/chart/'));
  request.resolve({ ok: true, json: async () => fixture({ brand: 'deepseek' }) });
  await settled();
  assert.equal(h.button('bug').getAttribute('aria-pressed'), 'false');
  oldButton.click(); assert.equal(h.button('bug').getAttribute('aria-pressed'), 'false');
});


test('brand refresh requests a narrow headline fragment and labels the old chart', () => {
  const h = harness(fixture());
  h.pulses[1].click();
  assert.ok(h.requests[1].url.includes('/api/v2/dashboard/each/headline/'));
  assert.ok(h.nodes.status.textContent.includes('llama'));
  assert.ok(h.nodes.status.textContent.includes('7'));
  assert.ok(h.requests[1].options.signal);
});

test('own chart deadline shows a failure while preserving data and category pin', async () => {
  const h = harness(fixture());
  h.button('bug').click();
  const previous = h.getChart();
  h.tabs[2].click();
  const deadline = h.timers.find(timer => timer.delay === 18000 && !timer.cancelled);
  assert.ok(deadline, 'chart has an 18-second deadline');
  deadline.fn();
  const error = new Error('aborted'); error.name = 'AbortError';
  h.requests[0].reject(error);
  await settled();
  assert.equal(h.getChart(), previous);
  assert.equal(h.button('bug').getAttribute('aria-pressed'), 'true');
  assert.match(h.nodes.status.textContent, /previous|failed|long|timeout/i);
});


test('server chart_timeout uses the specific timeout copy with previous-result identity', async () => {
  const h = harness(fixture());
  h.nodes.root.dataset.chartTimeout = 'Chart took too long';
  h.pulses[1].click();
  h.requests[0].resolve({ ok: false, status: 503, json: async () => ({ error: 'chart_timeout' }) });
  await settled();
  assert.match(h.nodes.status.textContent, /^Chart took too long Showing previous result \(llama, Product, 7d\)$/);
});

test('narrow mobile plot thins daily ticks while retaining first and latest ticks', () => {
  const data = fixture();
  data.days = Array.from({ length: 7 }, (_, i) => '2026-11-' + (13 + i));
  const h = harness(data, { time: { dateLabel: value => value, dateTickIndices: days => days.map((_, i) => i) } });
  const axis = { width: 190, ticks: [] };
  h.getChart().options.scales.x.afterBuildTicks(axis);
  assert.ok(axis.ticks.length <= 3, JSON.stringify(axis.ticks));
  assert.equal(axis.ticks[0].value, 0);
  assert.equal(axis.ticks.at(-1).value, 6);
});


for (const [locale, productLabel, roleLabel] of [
  ['en', 'Product', 'Role'], ['zh_cn', '产品', '角色'], ['ja', '製品', '役割'],
]) {
  test('failed same-brand tab switch names the retained category in ' + locale, async () => {
    const h = harness(fixture(), { locale }), oldChart = h.getChart();
    h.tabs.find(tab => tab.dataset.eachTab === 'role').click();
    assert.ok(h.nodes.status.textContent.includes(productLabel), h.nodes.status.textContent);
    assert.ok(!h.nodes.status.textContent.includes(roleLabel), h.nodes.status.textContent);
    h.requests[0].reject(new Error('network'));
    await settled();
    assert.equal(h.getChart(), oldChart);
    assert.ok(h.nodes.status.textContent.includes(productLabel), h.nodes.status.textContent);
    assert.ok(!h.nodes.status.textContent.includes(roleLabel), h.nodes.status.textContent);
    assert.equal(h.nodes.root.dataset.committedTab, 'product_labels');
    h.switchMode('volume');
    assert.ok(h.nodes.status.textContent.includes(productLabel));
  });

  test('canvas accessible label keeps the committed tab during a failed switch in ' + locale, async () => {
    const h = harness(fixture(), { locale });
    assert.ok(h.nodes.canvas.getAttribute('aria-label').includes(productLabel), h.nodes.canvas.getAttribute('aria-label'));
    h.tabs.find(tab => tab.dataset.eachTab === 'role').click();
    h.requests[0].reject(new Error('network'));
    await settled();
    h.switchMode('volume');
    const label = h.nodes.canvas.getAttribute('aria-label');
    assert.ok(label.includes(productLabel), label);
    assert.ok(!label.includes(roleLabel), label);
  });
}


test('headline previous-result notice omits chart category when no tab belongs to it', () => {
  const h = harness(fixture());
  h.pulses[1].click();
  assert.equal(h.nodes.headlineStatus.textContent, 'Loading Showing previous result (llama, 7d)');
  assert.ok(!h.nodes.headlineStatus.textContent.includes('Product'));
});


function sparseOneDayFixture() {
  const data = fixture({ keys: ['bug', 'complaint'] });
  data.window_days = 1;
  data.granularity = 'minute';
  data.days = Array.from({ length: 288 }, (_, i) => new Date(Date.UTC(2026, 10, 18, 9, 40) + i * 300000).toISOString());
  data.series = { bug: Array(288).fill(0), complaint: Array(288).fill(0) };
  data.series.bug[0] = 1;
  data.series.complaint[1] = 9;
  data.series.bug[12] = 3;
  data.series.complaint[23] = 1;
  data.series.complaint[287] = 2;
  data.totals = data.days.map((_, i) => data.series.bug[i] + data.series.complaint[i]);
  return data;
}

test('one-day area uses hourly sums and weighted percentages without changing raw payload or fetching again', () => {
  const data = sparseOneDayFixture(), raw = JSON.stringify(data), h = harness(data);
  let chart = h.getChart();
  assert.equal(chart.config.type, 'line');
  assert.equal(chart.data.labels.length, 24, 'sparse five-minute buckets must not draw 288 narrow columns');
  assert.deepEqual(plain(chart.data.datasets.map(d => d.data.slice(0, 3))), [[10, 75, null], [90, 25, null]]);
  assert.deepEqual(plain(chart.data.datasets.map(d => d.data.at(-1))), [0, 100]);
  assert.equal(h.nodes.bucketNote.hidden, false);
  h.switchMode('volume');
  chart = h.getChart();
  assert.deepEqual(plain(chart.data.datasets.map(d => d.data.slice(0, 3))), [[1, 3, 0], [9, 1, 0]]);
  assert.deepEqual(plain(chart.data.datasets.map(d => d.data.reduce((a, b) => a + b, 0))), [4, 12]);
  assert.deepEqual(plain(chart.data.datasets.map(d => d.data.at(-1))), [0, 2], 'the last harvested five-minute sample stays included');
  h.switchMode('percent');
  assert.equal(h.getChart().data.labels.length, 24, 'mode redraw must aggregate the original payload only once');
  assert.deepEqual(plain(h.getChart().data.datasets.map(d => d.data.slice(0, 3))), [[10, 75, null], [90, 25, null]]);
  assert.equal(JSON.stringify(h.getPayload()), raw, 'the actual parsed payload cached by the renderer stays at five-minute precision');
  assert.equal(h.requests.length, 0);
});

test('hourly tooltip identifies the full interval and exact label-assignment counts', () => {
  const data = sparseOneDayFixture(), h = harness(data), chart = h.getChart();
  const callbacks = chart.options.plugins.tooltip.callbacks;
  const item = { datasetIndex: 0, dataIndex: 0, parsed: { y: 10 } };
  const start = new Date(data.days[0]).toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' });
  const end = new Date(Date.parse(data.days[0]) + 3600000).toLocaleTimeString('en', { hour: 'numeric', minute: '2-digit' });
  assert.equal(callbacks.title([item]), start + ' – ' + end);
  assert.equal(callbacks.label(item), 'bug: 1 (10.0%)');
  assert.equal(callbacks.footer([item]), '10 label assignments');
});

test('daily charts preserve original points and values and keep the standard tooltip title', () => {
  for (const window of [7, 30, 365]) {
    const data = fixture(); data.window_days = window;
    const h = harness(data), chart = h.getChart();
    assert.equal(chart.data.labels.length, data.days.length);
    assert.equal(h.nodes.bucketNote.hidden, true);
    assert.equal(chart.options.plugins.tooltip.callbacks.title, undefined);
    h.switchMode('volume');
    assert.deepEqual(plain(h.getChart().data.datasets.map(d => d.data)), Object.values(data.series));
  }
});


test('partial hourly coverage keeps the real harvest end on the axis and tooltip after mode redraws', () => {
  const timeContext = { module: { exports: {} }, document: { querySelector: () => null }, window: { Intl }, Intl };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../monitor/static/pw-tz.js'), 'utf8'), timeContext);
  const time = timeContext.module.exports;
  for (const size of [286, 287]) {
    const data = sparseOneDayFixture();
    data.days = data.days.slice(0, size); data.totals = data.totals.slice(0, size);
    for (const key of Object.keys(data.series)) data.series[key] = data.series[key].slice(0, size);
    const h = harness(data, { time });
    const expectedEnd = time.clockText(new Date(Date.parse(data.days.at(-1)) + 300000), 'en');
    for (const mode of ['percent', 'volume', 'percent']) {
      h.switchMode(mode);
      const chart = h.getChart(), axis = { width: 600, ticks: [] };
      chart.options.scales.x.afterBuildTicks(axis);
      assert.equal(axis.ticks.at(-1).value, 23);
      const text = chart.options.scales.x.ticks.callback.call({}, 23, axis.ticks.length - 1);
      assert.equal(text, expectedEnd, 'a partial hour must not label unharvested time as covered');
      assert.ok(chart.options.plugins.tooltip.callbacks.title([{ dataIndex: 23 }]).endsWith(' – ' + expectedEnd));
    }
  }
});


test('short harvest coverage keeps raw points until hourly aggregation can draw at least two points', () => {
  for (const size of [1, 11, 12, 13]) {
    const data = sparseOneDayFixture();
    data.days = data.days.slice(0, size); data.totals = data.totals.slice(0, size);
    for (const key of Object.keys(data.series)) data.series[key] = data.series[key].slice(0, size);
    const h = harness(data);
    for (const mode of ['percent', 'volume', 'percent']) {
      h.switchMode(mode);
      const chart = h.getChart();
      assert.equal(chart.data.labels.length, size <= 12 ? size : 2, `covered buckets: ${size}`);
      assert.equal(h.nodes.bucketNote.hidden, size <= 12);
      if (mode === 'volume') {
        assert.deepEqual(plain(chart.data.datasets.map(d => d.data.reduce((a,b) => a+b, 0))), Object.values(data.series).map(values => values.reduce((a,b) => a+b, 0)));
      }
    }
  }
});
