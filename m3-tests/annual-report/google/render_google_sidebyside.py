#!/usr/bin/env python3
"""
Render the M3.0 and Gemini Google org charts side by side as a single image
suitable for an X post.

Layout:
  ┌─────────────────────────────────────────────────────┐
  │  Title (one line)                                  │
  │  Subtitle (one line, smaller)                      │
  │  ┌──────────────────┐  ┌──────────────────┐        │
  │  │   M3.0           │  │  Gemini 3.1 Pro  │        │
  │  │  <chart>         │  │  <chart>         │        │
  │  └──────────────────┘  └──────────────────┘        │
  │  Footer: source citation + small note              │
  └─────────────────────────────────────────────────────┘
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright

OUT_DIR = "/tmp/m3-test-staging/pdf_org_chart"

with open(f"{OUT_DIR}/m3_google.txt") as f:
    m3_text = f.read()
with open(f"{OUT_DIR}/gemini_google.txt") as f:
    gem_text = f.read()

# Strip the leading/trailing ``` fences from the M3 output (Gemini has none).
m3_text = re.sub(r"^```\s*\n", "", m3_text)
m3_text = re.sub(r"\n```\s*$", "", m3_text)
m3_text = m3_text.rstrip()

# Trim the M3 legend (footnotes 1-8) — the explanatory footnotes add lines
# without changing the chart. Keep the chart, drop the legend.
m3_legend_idx = m3_text.find("LEGEND")
if m3_legend_idx > 0:
    # Keep everything before "LEGEND" and the "═══════════" line just before it
    before = m3_text[:m3_legend_idx].rstrip()
    m3_text = before

# Build the HTML.
html = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>M3 vs Gemini — Google Beneficial Ownership</title>
<style>
:root {
  --bg: #ffffff;
  --fg: #111827;
  --muted: #6b7280;
  --border: #d1d5db;
  --panel: #f9fafb;
  --accent-m3: #1d4ed8;
  --accent-gem: #b91c1c;
  --line: #e5e7eb;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 36px 40px 32px 40px;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  width: 1600px;
}
.title {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.2;
  margin: 0 0 6px 0;
}
.subtitle {
  font-size: 14.5px;
  color: var(--muted);
  margin: 0 0 22px 0;
  line-height: 1.4;
}
.divider {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 0 0 22px 0;
}
.cols {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}
.col {
  flex: 1 1 0;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  padding: 14px 16px 16px 16px;
}
.col h2 {
  margin: 0 0 4px 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.col .badge {
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 50%;
}
.col .meta {
  font-size: 12.5px;
  color: var(--muted);
  margin: 0 0 12px 0;
  font-variant-numeric: tabular-nums;
}
.m3 .badge { background: var(--accent-m3); }
.gem .badge { background: var(--accent-gem); }

pre.chart {
  margin: 0;
  padding: 14px 12px;
  background: #ffffff;
  border: 1px solid var(--line);
  border-radius: 6px;
  font-family: "SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", monospace;
  font-size: 10.5px;
  line-height: 1.22;
  color: #111827;
  white-space: pre;
  overflow: hidden;
  -webkit-text-size-adjust: 100%;
}
.footer {
  margin-top: 22px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
  display: flex;
  justify-content: space-between;
  gap: 16px;
}
.footer .left { flex: 1 1 auto; }
.footer .right { flex: 0 0 auto; text-align: right; font-variant-numeric: tabular-nums; }
</style>
</head><body>
  <h1 class="title">Alphabet's beneficial ownership — M3.0 vs Gemini 3.1 Pro</h1>
  <p class="subtitle">Same prompt, same 2 pages from Alphabet's 2026 DEF 14A. Both read the filing. Both got the math right. Watch the coverage and the footnotes.</p>
  <hr class="divider" />
  <div class="cols">
    <div class="col m3">
      <h2><span class="badge"></span>M3.0</h2>
      <p class="meta">75.1s &middot; 13,655 chars &middot; thinking disabled</p>
      <pre class="chart">__M3__</pre>
    </div>
    <div class="col gem">
      <h2><span class="badge"></span>Gemini 3.1 Pro</h2>
      <p class="meta">182.0s &middot; 13,241 chars (19,612 thought tokens not shown)</p>
      <pre class="chart">__GEM__</pre>
    </div>
  </div>
  <div class="footer">
    <div class="left">Source: Alphabet Inc. 2026 Proxy Statement (DEF 14A), "Common Stock Ownership of Certain Beneficial Owners and Management," pp.&nbsp;35&ndash;36. Period ending 2026-04-06.</div>
    <div class="right">Both accurate. Different trade-offs.</div>
  </div>
</body></html>
""".replace("__M3__", m3_text).replace("__GEM__", gem_text)

out_html = f"{OUT_DIR}/google_sidebyside.html"
with open(out_html, "w") as f:
    f.write(html)
print(f"wrote {out_html} ({len(html)} bytes)", file=sys.stderr)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 2000}, device_scale_factor=2)
    page.goto(f"file://{out_html}")
    page.wait_for_load_state("networkidle")
    out_png = f"{OUT_DIR}/google_sidebyside.png"
    page.screenshot(path=out_png, full_page=True)
    print(f"wrote {out_png}", file=sys.stderr)
    browser.close()

print("done", file=sys.stderr)
