// U2 unit tests for formatRelative / formatLocalTooltip.
// Runs under Node (no JSDOM needed; the formatters are pure).
// Run: node tests/test_pw_feed_formatter.js
// Exits 0 on success, 1 on failure.

const path = require('path');
const fs = require('fs');

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
const { formatRelative, formatLocalTooltip, enrichmentStatusHtml } = sandbox.exports;

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

console.log('\n--- enrichmentStatusHtml ---');
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
    { cursor: '2026-07-15T20:00:00+00:00|tweet1', sort: 'created_at', order: 'asc', limit: 25 }
  );
  assertEq(out3.indexOf('cursor=2026-07-15T20') >= 0, true, 'buildQuery includes cursor');
  assertEq(out3.indexOf('order=asc') >= 0, true, 'buildQuery includes order=asc');
}

// v22 uses a data hook without a root id; legacy /internal still has #feed.
const apostrophe = String.fromCharCode(39);
const rootSelector = "return $(" + apostrophe + "[data-pw-feed]" + apostrophe + ") || $(" + apostrophe + "#feed" + apostrophe + ");";
console.log("\n--- getFeedRoot selector migration ---");
assertEq(feedSrc.includes(rootSelector), true, "getFeedRoot prefers data-pw-feed with #feed fallback");

console.log('\n--- summary ---');
console.log(passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
