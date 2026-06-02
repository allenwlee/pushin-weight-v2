#!/usr/bin/env python3
"""
Extract the "Common Stock Ownership of Certain Beneficial Owners and Management"
section of the Google DEF 14A (goog-20260424.htm) and render it as PNG images
for M3 and Gemini to read.

Strategy:
1. Find the section's byte offset in the raw HTML.
2. Slice the HTML from that point to ~12,000 chars (covers the table + footnotes).
3. Write a minimal standalone HTML wrapper around it.
4. Use Playwright to render and screenshot at A4 size.
"""
import os
import re
import sys

SRC = "/tmp/google_10q_unzipped.htm"
OUT_DIR = "/tmp/m3-test-staging/pdf_org_chart"
SECTION_HEADER = "Common Stock Ownership of Certain Beneficial Owners and Management"

# The second occurrence in the clean text is the actual section (the first is the
# TOC reference). In the raw HTML, the second occurrence is later. Find both.
with open(SRC, "r") as f:
    raw = f.read()

# Find offsets in the raw HTML (not clean text)
offsets = [m.start() for m in re.finditer(re.escape(SECTION_HEADER), raw)]
print(f"raw offsets: {offsets}", file=sys.stderr)
assert len(offsets) >= 2, "Expected at least 2 occurrences (TOC + actual section)"

# The actual section starts at the second offset.
section_start = offsets[1]
# The actual section runs ~66K chars. Take a generous slice.
section_end = min(section_start + 75000, len(raw))
section_html = raw[section_start:section_end]

# Wrap in a minimal standalone HTML doc with a stylesheet to make it readable.
wrapper = f"""<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Google Beneficial Ownership</title>
<style>
body {{ font-family: 'Times New Roman', Times, serif; font-size: 12pt; line-height: 1.35; max-width: 7.5in; margin: 0.5in auto; padding: 0 0.5in; color: #000; background: #fff; }}
h1, h2, h3 {{ font-family: Arial, Helvetica, sans-serif; }}
h1 {{ font-size: 16pt; text-align: center; margin-top: 0.4in; }}
h2 {{ font-size: 13pt; margin-top: 0.25in; }}
h3 {{ font-size: 11.5pt; margin-top: 0.2in; }}
p, li, td, th {{ font-size: 10.5pt; }}
table {{ border-collapse: collapse; width: 100%; margin: 0.2in 0; font-size: 10pt; }}
th, td {{ padding: 5px 8px; vertical-align: top; }}
th {{ background: #f2f2f2; text-align: left; font-weight: bold; border-bottom: 1.5pt solid #000; }}
td {{ border-bottom: 0.5pt solid #ccc; }}
.fn {{ font-size: 9pt; color: #333; line-height: 1.3; }}
.fn-list {{ list-style: none; padding-left: 0; }}
.fn-list li {{ margin-bottom: 6pt; padding-left: 1.5em; text-indent: -1.5em; }}
.asterisk {{ color: #666; }}
hr {{ margin: 0.3in 0; border: 0; border-top: 1pt solid #000; }}
</style>
</head><body>
{section_html}
</body></html>
"""
out_html = f"{OUT_DIR}/google_section.html"
with open(out_html, "w") as f:
    f.write(wrapper)
print(f"wrote {out_html} ({len(wrapper)} bytes)", file=sys.stderr)

# Now render to images using Playwright.
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(f"file://{out_html}")
    page.wait_for_load_state("networkidle")
    # Render to PDF first for stable pagination, then convert pages to PNGs.
    pdf_path = f"{OUT_DIR}/google_section.pdf"
    page.pdf(path=pdf_path, format="A3", print_background=True, margin={"top": "0.4in", "bottom": "0.4in", "left": "0.4in", "right": "0.4in"})
    print(f"wrote {pdf_path}", file=sys.stderr)
    browser.close()

# Convert PDF to PNGs with pypdfium2 (same as the MiniMax test).
import pypdfium2 as pdfium

pdf = pdfium.PdfDocument(f"{OUT_DIR}/google_section.pdf")
print(f"PDF has {len(pdf)} page(s)", file=sys.stderr)
for i, page_pdf in enumerate(pdf):
    img = page_pdf.render(scale=2).to_pil()
    out_png = f"{OUT_DIR}/google_page-{i+1}.png"
    img.save(out_png)
    print(f"wrote {out_png} ({os.path.getsize(out_png)} bytes)", file=sys.stderr)

print("done", file=sys.stderr)
