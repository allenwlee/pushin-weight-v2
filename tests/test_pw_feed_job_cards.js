const fs = require('fs');
const path = require('path');
const Module = require('module');

global.window = { pwIcon: require('../monitor/static/pw-icons.js') };
global.document = {
  body: { getAttribute: name => name === 'data-pw-locale' ? 'en' : null },
  getElementById: () => null,
  querySelector: () => null,
};

const src = fs.readFileSync(path.join(__dirname, '..', 'monitor', 'static', 'pw-feed.js'), 'utf8');
const marker = "if (typeof module !== 'undefined' && module.exports)";
const index = src.indexOf(marker);
if (index < 0) throw new Error('module.exports guard not found');
const sandbox = new Module('pw-feed-job-card');
sandbox._compile(src.substring(0, index) + '\n' + src.substring(index) + '\n', 'pw-feed.js');

const html = sandbox.exports.renderRowHtml({
  source_kind: 'official_job',
  source_name: 'Qwen',
  source_url: 'https://talent.quark.cn/jobs/one',
  application_url: 'https://talent.quark.cn/jobs/one/apply',
  title: '<img src=x onerror=alert(1)> Researcher',
  text_original: '<script>alert(2)</script> Build models',
  location_text: '杭州',
  ts_abs_text: '2026-09-12',
  tint_class: 'tint-neutral',
});

function expect(condition, message) {
  if (!condition) throw new Error(message);
}

expect(html.includes('https://talent.quark.cn/jobs/one/apply'), 'official application link missing');
expect(html.includes('View official job'), 'localized action missing');
expect(html.includes('&lt;img src=x onerror=alert(1)&gt;'), 'title was not escaped');
expect(html.includes('&lt;script&gt;alert(2)&lt;/script&gt;'), 'description was not escaped');
expect(!html.includes('x.com'), 'job card must not invent an X link');
expect(!html.includes('follower-magnitude'), 'job card must not invent followers');
expect(!html.includes('icon-heart'), 'job card must not invent engagement');
expect(!html.includes('synthesis-status'), 'job card must not request synthesis');

const tableHtml = sandbox.exports.renderOfficialJobTableRowHtml({
  source_kind: 'official_job',
  source_name: 'Qwen',
  source_url: 'https://talent.quark.cn/jobs/one',
  application_url: 'https://talent.quark.cn/jobs/one/apply',
  title: '<img src=x onerror=alert(1)> Researcher',
  text_original: '<script>alert(2)</script> Build models',
  job_meta_text: '杭州 · 研究 · 全职',
  brands: [{ display_name: 'Qwen' }],
});
expect(tableHtml.includes('official-job-table-title'), 'brand table job title missing');
expect(tableHtml.includes('https://talent.quark.cn/jobs/one/apply'), 'brand table official link missing');
expect(tableHtml.includes('&lt;img src=x onerror=alert(1)&gt;'), 'brand table title was not escaped');
expect(tableHtml.includes('&lt;script&gt;alert(2)&lt;/script&gt;'), 'brand table description was not escaped');
expect(!tableHtml.includes('x.com'), 'brand table job must not invent an X link');

console.log('official job card renderer: PASS');
