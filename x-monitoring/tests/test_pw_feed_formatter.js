// U2 unit tests for formatRelative / formatLocalTooltip.
// Runs under Node (no JSDOM needed; the formatters are pure).
// Run: node tests/test_pw_feed_formatter.js
// Exits 0 on success, 1 on failure.

const path = require('path');
const fs = require('fs');

// Load the formatter by reading the file and stripping the IIFE wrapper.
// (We can't require the file directly because it's wrapped in an IIFE.)
const src = fs.readFileSync(
  path.join(__dirname, '..', 'x_monitor', 'static', 'pw-feed.js'),
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
const { formatRelative, formatLocalTooltip } = sandbox.exports;

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

console.log('\n--- summary ---');
console.log(`${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
