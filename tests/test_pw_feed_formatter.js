// U2 unit tests for formatRelative / formatLocalTooltip.
// Runs under Node (no JSDOM needed; the formatters are pure).
// Run: node tests/test_pw_feed_formatter.js
// Exits 0 on success, 1 on failure.

const path = require('path');
const fs = require('fs');
const pwIcon = require('../monitor/static/pw-icons.js');
global.window = { pwIcon };

// Load the formatter by reading the file and stripping the IIFE wrapper.
// (We can't require the file directly because it's wrapped in an IIFE.)
const src = fs.readFileSync(
  path.join(__dirname, '..', 'monitor', 'static', 'pw-feed.js'),
  'utf8'
);

// Locate the module.exports guard; require it via a small eval-sandbox.
const exportMarker = "if (typeof module !== 'undefined' && module.exports)";
const idx = src.indexOf(exportMarker);
if (idx < 0) {
  console.error('FAIL: module.exports guard not found in pw-feed.js');
  process.exit(1);
}
const head = src.substring(0, idx);
const tail = src.substring(idx);
// Eval the head (defines formatRelative + formatLocalTooltip) and the
// tail (assigns to module.exports).
const Module = require('module');
const sandbox = new Module('pw-feed-formatter');
sandbox._compile(head + '\n' + tail + '\n', 'pw-feed.js');
const {
  createRequestGate,
  formatRelative,
  formatLocalTooltip,
  enrichmentStatusHtml,
  textLayers,
  hydrateRows,
  replaceRows,
  isFeedPayload,
  renderRowHtml,
} = sandbox.exports;

let passed = 0;
let failed = 0;
function assertEq(actual, expected, label) {
  const ok = actual === expected;
  if (ok) {
    passed++;
    console.log(`  PASS ${label}: got ${JSON.stringify(actual)}`);
  } else {
    failed++;
    console.error(
      `  FAIL ${label}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

console.log('--- Cyber-Quan icon renderer ---');
assertEq(pwIcon.render('not-approved', 'safe'), '', 'unknown symbol fails closed');
assertEq(
  pwIcon.render('icon-heart', 'safe bad\" onclick=alert(1)'),
  '<svg class="pw-icon safe" aria-hidden="true" focusable="false"><use href="#icon-heart"></use></svg>',
  'class tokens are allowlisted by syntax'
);
assertEq(pwIcon.isAllowed('icon-heart'), true, 'approved symbol is recognized');
assertEq(pwIcon.isAllowed('not-approved'), false, 'unknown symbol is rejected');

// Anchor `now` so the tests are deterministic.
const now = new Date('2026-07-15T21:00:00+00:00');

console.log('--- formatRelative ---');
assertEq(formatRelative(null, now), '', 'null input');
assertEq(formatRelative(undefined, now), '', 'undefined input');
assertEq(formatRelative('not a date', now), '', 'invalid date string');
assertEq(formatRelative(new Date(now.getTime() - 5 * 1000), now), 'just now', '5s ago');
assertEq(formatRelative(new Date(now.getTime() - 30 * 1000), now), 'just now', '30s ago');
assertEq(formatRelative(new Date(now.getTime() - 60 * 1000), now), '1m ago', '1m ago');
assertEq(formatRelative(new Date(now.getTime() - 5 * 60 * 1000), now), '5m ago', '5m ago');
assertEq(formatRelative(new Date(now.getTime() - 60 * 60 * 1000), now), '1h ago', '1h ago');
assertEq(formatRelative(new Date(now.getTime() - 3 * 60 * 60 * 1000), now), '3h ago', '3h ago');
assertEq(formatRelative(new Date(now.getTime() - 24 * 60 * 60 * 1000), now), 'Wed', '24h ago = weekday (under 7d)');
assertEq(formatRelative(new Date('2026-07-15T14:00:00+00:00'), now), '7h ago', '7h ago (under 24h)');
assertEq(formatRelative(new Date(now.getTime() + 30 * 1000), now), 'just now', 'future timestamp clamps to just now');
assertEq(formatRelative(new Date('2026-01-15T12:00:00+00:00'), now).length > 0, true, '6 months ago: non-empty string');

console.log('\n--- formatLocalTooltip ---');
assertEq(formatLocalTooltip(null), '', 'null input');
assertEq(formatLocalTooltip('not a date'), '', 'invalid string');
assertEq(formatLocalTooltip('2026-07-15T21:00:00+00:00').length > 0, true, 'ISO input: non-empty tooltip');

console.log('\\n--- enrichmentStatusHtml ---');
assertEq(
  enrichmentStatusHtml({ enrichment_status: 'pending', enrichment_status_label: 'enrichment pending' }),
  '<span class="enrichment-status enrichment-status-pending" role="status">enrichment pending</span>',
  'pending state is visible and accessible'
);
assertEq(
  enrichmentStatusHtml({ enrichment_status: 'failed', enrichment_status_label: '<failed>' }),
  '<span class="enrichment-status enrichment-status-failed" role="status">&lt;failed&gt;</span>',
  'failed state escapes its accessible label'
);
assertEq(
  enrichmentStatusHtml({ enrichment_status: 'succeeded', enrichment_status_label: 'done' }),
  '',
  'succeeded state clears the signal'
);

console.log('\n--- feed row identity and follower lead ---');
assertEq(typeof renderRowHtml, 'function', 'renderRowHtml is available to contract tests');
if (typeof renderRowHtml === 'function') {
  global.document = {
    body: { getAttribute: () => 'en' },
    querySelector: () => null,
  };
  const rowHtml = renderRowHtml({
    account: {
      handle: '@account_handle',
      display_name: 'Account Name',
      followers_pretty: '52.1k',
    },
    follower_bin: '50k-plus',
    followers_label: '52.1k followers',
    engagement_pretty: { followers: '52.1k', likes: '3', retweets: '2', replies: '1' },
  });
  assertEq(rowHtml.includes('class="follower-lead follower-bin-50k-plus"'), true,
    'feed row reserves a fixed follower lead column');
  assertEq(rowHtml.includes('class="follower-glyph"'), true,
    'feed row shows a size-binned follower symbol');
  assertEq(rowHtml.includes('href="#icon-followers-4"'), true,
    'highest follower bin uses the approved four-person symbol');
  assertEq(rowHtml.includes('href="#icon-heart"') && rowHtml.includes('href="#icon-repost"') &&
    rowHtml.includes('href="#icon-reply"'), true,
    'client-created rows use the approved engagement symbols');
  assertEq(rowHtml.includes('class="follower-count">52.1k</span>'), true,
    'follower count sits directly under the emoji');
  assertEq(rowHtml.includes('>Account Name</a>'), true,
    'visible account link uses the display name');
  assertEq(rowHtml.includes('href="https://x.com/account_handle"'), true,
    'display-name link still targets the account handle');
  assertEq(rowHtml.includes('class="followers"'), false,
    'engagement no longer duplicates the follower count');

  const unknownFollowerHtml = renderRowHtml({
    account: { handle: '@unknown' },
    follower_bin: '0-1k',
    followers_label: '0 followers',
    engagement_pretty: { followers: '0' },
  });
  assertEq(unknownFollowerHtml.includes('class="follower-count">0</span>'), true,
    'rows without account metadata still show their zero follower count');
}

// (summary + process.exit moved to end after U4 buildQuery tests)


// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// U4 (2026-07-16): pw-feed.js fetchBatch builds the right query with the
// current filter. We extract the buildQuery function and test it
// directly — no browser needed.
// ---------------------------------------------------------------------------

const feedSrc = fs.readFileSync(
  path.join(__dirname, '..', 'monitor', 'static', 'pw-feed.js'),
  'utf8'
);
const bqMatch = feedSrc.match(/function buildQuery\([^)]*\)\s*\{[\s\S]*?\n  \}/m);
if (!bqMatch) {
  console.error('  FAIL: buildQuery not found in pw-feed.js');
  failed++;
} else {
  const bqSandbox = new Module('buildQuery');
  bqSandbox._compile(bqMatch[0] + '\nmodule.exports = buildQuery;\n', 'buildQuery.js');
  const buildQuery = bqSandbox.exports;

  console.log('\n--- buildQuery encodes filters ---');
  const out1 = buildQuery(
    { brands: ['qwen'] },
    { cursor: null, sort: 'created_at', order: 'desc', limit: 50 }
  );
  assertEq(
    out1.indexOf('filters=' + encodeURIComponent(JSON.stringify({ brands: ['qwen'] }))) >= 0,
    true,
    'buildQuery encodes brands filter into filters= param'
  );
  assertEq(out1.indexOf('cursor=null') < 0, true, 'buildQuery omits null cursor');
  assertEq(out1.indexOf('limit=50') >= 0, true, 'buildQuery includes limit');
  assertEq(out1.indexOf('sort=created_at') >= 0, true, 'buildQuery includes sort');
  assertEq(out1.indexOf('window=1') >= 0, true, 'buildQuery includes the active window');

  console.log('\n--- buildQuery handles empty filters ---');
  const out2 = buildQuery(
    {},
    { cursor: null, sort: 'created_at', order: 'desc', limit: 50 }
  );
  assertEq(
    out2.indexOf('filters=' + encodeURIComponent('{}')) >= 0,
    true,
    'buildQuery encodes empty filters as {}'
  );

  console.log('\n--- buildQuery forwards cursor, order ---');
  const out3 = buildQuery(
    { brands: ['minimax'] },
    {
      cursor: '2026-07-15T20:00:00+00:00|tweet1',
      sort: 'created_at',
      order: 'asc',
      limit: 25,
      locale: 'zh_hans',
    }
  );
  assertEq(out3.indexOf('cursor=2026-07-15T20') >= 0, true, 'buildQuery includes cursor');
  assertEq(out3.indexOf('order=asc') >= 0, true, 'buildQuery includes order=asc');
  assertEq(out3.indexOf('locale=zh_hans') >= 0, true, 'buildQuery includes locale snapshot');
}

// v22 uses a data hook without a root id; legacy /internal still has #feed.
const apostrophe = String.fromCharCode(39);
const rootSelector = "return $(" + apostrophe + "[data-pw-feed]" + apostrophe + ") || $(" + apostrophe + "#feed" + apostrophe + ");";
console.log("\n--- getFeedRoot selector migration ---");
assertEq(feedSrc.includes(rootSelector), true, "getFeedRoot prefers data-pw-feed with #feed fallback");

// ---------------------------------------------------------------------------
// V22 feed metadata: the server owns tint selection.  The browser only paints
// marker symbols from raw attributes, even when those attributes intentionally
// disagree with the server-provided tint class.
// ---------------------------------------------------------------------------

function classList(initial) {
  const values = new Set(initial || []);
  return {
    add: (name) => values.add(name),
    remove: (name) => values.delete(name),
    has: (name) => values.has(name),
  };
}

function markerRow(attrs, serverTint) {
  const shell = { className: 'feed-row-shell ' + serverTint };
  const sentiment = { textContent: '', innerHTML: '' };
  const postType = { textContent: '', innerHTML: '' };
  const nationalism = { textContent: '', innerHTML: '', classList: classList() };
  const unsanctioned = { textContent: '', innerHTML: '', classList: classList() };
  const nodes = {
    '.feed-row-shell': shell,
    '[data-sig-sentiment]': sentiment,
    '[data-sig-post-type]': postType,
    '[data-sig-nat]': nationalism,
    '[data-sig-unsanctioned]': unsanctioned,
  };
  return {
    shell,
    sentiment,
    getAttribute: (name) => attrs[name] || '',
    querySelector: (selector) => nodes[selector] || null,
    querySelectorAll: () => [],
  };
}

console.log('\n--- server-owned tint and marker hydration ---');
const serverTintRow = markerRow(
  {
    'data-sentiments': 'negative',
    'data-post-types': 'buzz_releases',
    'data-nat-cn': 'mild_pro',
    'data-unsanctioned': '1',
  },
  'tint-pos-mixed'
);
hydrateRows([serverTintRow]);
assertEq(
  serverTintRow.shell.className.includes('tint-pos-mixed'),
  true,
  'hydrateRows preserves the server-owned tint when raw sentiments differ'
);
assertEq(
  serverTintRow.sentiment.innerHTML.includes('href="#icon-sentiment-negative"'),
  true,
  'hydrateRows paints the approved negative-sentiment symbol'
);

console.log('\n--- valid empty and malformed payload handling ---');
const feedRoot = { getAttribute: (name) => name === 'data-pw-empty-text' ? 'no posts in window' : '' };
global.document = { querySelector: (selector) => selector === '[data-pw-feed]' ? feedRoot : null };
const emptyBody = { innerHTML: 'existing classified row' };
replaceRows(emptyBody, []);
assertEq(
  emptyBody.innerHTML.includes('no posts in window'),
  true,
  'a valid empty payload renders the localized empty state'
);
assertEq(isFeedPayload({ rows: [] }), true, 'an empty rows array is a valid feed payload');
assertEq(isFeedPayload({ rows: null }), false, 'a malformed rows value is rejected before replacement');
assertEq(isFeedPayload({ rows: [null] }), false, 'a null row is rejected before hydration');
assertEq(
  isFeedPayload({ rows: [{ tweet_id: 'optional-only' }], next_cursor: null }),
  true,
  'optional row data remains valid'
);

console.log('\n--- commentary text layers ---');
const textElement = (attrs) => ({
  getAttribute: (name) => Object.prototype.hasOwnProperty.call(attrs, name) ? attrs[name] : null,
});
global.document.body = { getAttribute: (name) => name === 'data-pw-locale' ? 'zh_cn' : null };
let layers = textLayers(textElement({
  'data-commentary-zh-cn': '中文综合',
  'data-commentary-en': '',
  'data-literal-cn': '中文直译',
  'data-text-en': 'English',
  'data-text-source': 'English source',
}));
assertEq(
  layers.map((layer) => layer.key).join(','),
  'synthesis,literal_cn,en',
  'zh-CN cycles commentary, literal translation, then English'
);
layers = textLayers(textElement({
  'data-commentary-zh-cn': '',
  'data-commentary-en': '',
  'data-literal-cn': 'same text',
  'data-text-en': 'same text',
  'data-text-source': 'same text',
}));
assertEq(
  layers.map((layer) => layer.key).join(','),
  'literal_cn',
  'missing commentary and duplicate translations do not create fake layers'
);
global.document.body = { getAttribute: (name) => name === 'data-pw-locale' ? 'en' : null };
layers = textLayers(textElement({
  'data-commentary-zh-cn': '中文综合',
  'data-commentary-en': '',
  'data-literal-cn': '中文直译',
  'data-text-en': 'English',
  'data-text-source': 'Source',
}));
assertEq(
  layers.map((layer) => layer.key).join(','),
  'en,source',
  'blank commentary_en leaves the English cycle unchanged'
);
assertEq(
  isFeedPayload({ rows: [], next_cursor: { stale: true } }),
  false,
  'a malformed cursor cannot corrupt pagination state'
);

console.log('\n--- latest-request gate and timeout cancellation ---');
const controllers = [];
const timers = [];
const clearedTimers = [];
const gate = createRequestGate({
  createController: () => {
    const controller = {
      signal: {},
      aborted: false,
      abort() { this.aborted = true; },
    };
    controllers.push(controller);
    return controller;
  },
  setTimer: (fn) => {
    timers.push(fn);
    return timers.length;
  },
  clearTimer: (id) => clearedTimers.push(id),
});
const oldTicket = gate.start(15000);
const newTicket = gate.start(15000);
assertEq(controllers[0].aborted, true, 'starting a newer request aborts the older request');
assertEq(gate.isCurrent(oldTicket), false, 'older request token becomes stale');
assertEq(gate.isCurrent(newTicket), true, 'latest request token may commit');
assertEq(gate.finish(oldTicket), false, 'stale completion cannot release latest request state');
assertEq(gate.isCurrent(newTicket), true, 'stale completion leaves the latest request active');
timers[1]();
assertEq(controllers[1].aborted, true, 'timeout aborts the current request');
assertEq(gate.finish(newTicket), true, 'current completion releases request state');
assertEq(gate.isCurrent(newTicket), false, 'finished request cannot commit again');
assertEq(clearedTimers.includes(2), true, 'finishing clears the active timeout');

console.log('\n--- summary ---');
console.log(passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
