"""Render the verified series without remote scripts or executable source text."""

import json
from pathlib import Path

from .identity import write_new


def render_report(data, output):
    payload = (
        json.dumps(data, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = Path(__file__).with_name("report.html").read_text(encoding="utf-8")
    write_new(output, template.replace("__REPORT_DATA__", payload))
