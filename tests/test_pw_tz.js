// Deterministic contract for the dynamic homepage comparison timezone.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'monitor', 'static', 'pw-tz.js'),
  'utf8'
);

const moduleShim = { exports: {} };
vm.runInNewContext(src, {
  console,
  Date,
  Intl,
  Number,
  module: moduleShim,
  document: { querySelector() { return null; } },
  window: { Intl },
});

const { comparisonForLocalTimezone, timezoneCopy } = moduleShim.exports;
let failures = 0;

function assert(condition, message) {
  if (condition) console.log('  PASS ' + message);
  else {
    failures += 1;
    console.error('  FAIL ' + message);
  }
}

const tokyo = comparisonForLocalTimezone('Asia/Tokyo');
assert(tokyo.key === 'california', 'Tokyo compares against California');
assert(tokyo.timezone === 'America/Los_Angeles', 'California uses its IANA zone');
assert(tokyo.iconClass === 'tz-ca-icon' && tokyo.iconSymbol === 'icon-california', 'California uses the Cyber-Quan outline');

const california = comparisonForLocalTimezone('America/Los_Angeles');
assert(california.key === 'beijing', 'California compares against Beijing');
assert(california.timezone === 'Asia/Shanghai', 'Beijing uses the Asia/Shanghai IANA zone');
assert(california.iconClass === 'tz-bj-icon' && california.iconSymbol === 'icon-beijing', 'Beijing uses the rough 京 symbol');

assert(timezoneCopy('en', california).shortLabel === 'Beijing', 'English chart row says Beijing');
assert(timezoneCopy('zh_cn', california).shortLabel === '北京', 'Chinese chart row says 北京');
assert(timezoneCopy('zh_cn', tokyo).shortLabel === '加州', 'Chinese California row says 加州');
assert(
  timezoneCopy('en', california).toggleTitle === 'Toggle local ⇄ Beijing time',
  'English Beijing toggle has an accessible name'
);
assert(
  timezoneCopy('zh_cn', california).toggleTitle === '切换 本地 ⇄ 北京时间',
  'Chinese Beijing toggle has an accessible name'
);

if (failures) process.exit(1);
