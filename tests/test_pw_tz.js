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

const { comparisonForLocalTimezone, timezoneCopy, clockText, oneDayTicks, dateLabel, dateTickIndices } = moduleShim.exports;
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
assert(timezoneCopy('ja', tokyo).localLabel === '現地', 'Japanese local timestamp says 現地');
assert(
  timezoneCopy('en', california).toggleTitle === 'Toggle local ⇄ Beijing time',
  'English Beijing toggle has an accessible name'
);
assert(
  timezoneCopy('zh_cn', california).toggleTitle === '切换 本地 ⇄ 北京时间',
  'Chinese Beijing toggle has an accessible name'
);

// Owner item 19: English 12-hour, Chinese and Japanese 24-hour.
const morning = new Date('2026-10-28T05:36:00+09:00');
const evening = new Date('2026-10-28T20:03:00+09:00');
assert(clockText(morning, 'en', 'Asia/Tokyo') === '5:36am', 'English morning reads 5:36am');
assert(clockText(evening, 'en', 'Asia/Tokyo') === '8:03pm', 'English evening reads 8:03pm');
assert(clockText(morning, 'zh_cn', 'Asia/Tokyo') === '05:36', 'Chinese uses the 24-hour clock');
assert(clockText(evening, 'ja', 'Asia/Tokyo') === '20:03', 'Japanese uses the 24-hour clock');
assert(clockText(evening, 'en', 'America/Los_Angeles') === '4:03am', 'comparison zone keeps the English 12-hour clock');
assert(clockText('not a date', 'en') === '', 'invalid instants format to an empty string');

// Owner items 25 and 29: one-day ticks end at the last bucket and step back whole hours.
const start = Date.parse('2026-10-27T21:20:00Z');
const labels = Array.from({ length: 288 }, (_, index) => new Date(start + index * 300000).toISOString());
const lastEnd = start + 288 * 300000;
const twoHour = oneDayTicks(labels, 840);
assert(twoHour.length === 12, 'at 840px the axis steps every 2 hours');
assert(twoHour[twoHour.length - 1].instant === lastEnd && twoHour[twoHour.length - 1].value === 287,
  'the last tick is the end of the last bucket');
assert(twoHour.every((tick, index) => index === 0 || tick.instant - twoHour[index - 1].instant === 7200000),
  'ticks step back exactly two hours');
assert(oneDayTicks(labels, 1200).length === 24, 'wide charts tick every hour');
assert(oneDayTicks(labels, 840, 8).length === 8 &&
  oneDayTicks(labels, 840, 8)[7].instant === lastEnd, 'a tick cap of 8 keeps the newest tick');
const trimmed = labels.slice(0, 280);
assert(oneDayTicks(trimmed, 840).pop().instant === start + 280 * 300000,
  'a harvest-trimmed series ends its axis at its own last bucket');
assert(oneDayTicks(['2026-10-27T21:20:00Z'], 840).length === 0 && oneDayTicks([], 840).length === 0,
  'fewer than two buckets produce no ticks');

// Localized date axes for 7/30/365 days.
assert(dateLabel('2026-10-18', 'en', false) === 'Oct 18', 'English day label');
assert(dateLabel('2026-10-18', 'zh_cn', false) === '10月18日', 'Chinese day label');
assert(dateLabel('2026-10-18', 'ja', false) === '10月18日', 'Japanese day label');
assert(dateLabel('2025-12-01', 'en', true) === 'Dec 2025', 'English month label');
assert(dateLabel('2025-12-01', 'ja', true) === '2025年12月', 'Japanese month label');
const week = Array.from({ length: 7 }, (_, index) => '2026-10-' + String(21 + index));
assert(JSON.stringify(dateTickIndices(week)) === JSON.stringify([0, 1, 2, 3, 4, 5, 6]), '7 days tick every day');
const month = Array.from({ length: 30 }, (_, index) => 'day-' + index);
assert(JSON.stringify(dateTickIndices(month)) === JSON.stringify([4, 9, 14, 19, 24, 29]), '30 days tick every 5 days from the latest');
const year = [];
for (let day = Date.parse('2025-10-29'); year.length < 365; day += 86400000) {
  year.push(new Date(day).toISOString().slice(0, 10));
}
const yearTicks = dateTickIndices(year).map((index) => year[index]);
assert(yearTicks.every((label) => label.endsWith('-01')) &&
  yearTicks[yearTicks.length - 1] === '2026-10-01' && yearTicks.length === 6,
  '365 days tick every other month start counted back from the latest');

if (failures) process.exit(1);
