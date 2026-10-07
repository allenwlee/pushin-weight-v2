"""Render the verified series without remote scripts or executable source text."""

import json
from pathlib import Path
from types import SimpleNamespace

from .identity import write_new


def render_report(data, output):
    comparison = data.get("database_comparison", {})
    if comparison.get("chart_kind") == "release_response_v1":
        from django.template.loader import render_to_string

        from monitor.benchmark_views import pulse_labels

        payload = (
            json.dumps(comparison, ensure_ascii=False, allow_nan=False)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        preset = {
            **comparison,
            "arena_line": comparison.get("arena_panel"),
            "usage_provider_options": {},
        }
        template = render_to_string(
            "monitor/benchmark_pulse.html",
            {
                "comparison": preset,
                "contract": SimpleNamespace(pk=comparison["contract_id"]),
                "preset": "offline",
                "comparisons": {},
                "pulse_labels": pulse_labels(),
            },
        )
        static = Path(__file__).resolve().parents[2] / "monitor" / "static"
        import re

        template = re.sub(
            r'<link rel="stylesheet" href="[^"]*benchmark-pulse[^\"]*\.css">',
            lambda _: (
                "<style>" + (static / "benchmark-pulse.css").read_text() + "</style>"
            ),
            template,
        )
        template = re.sub(
            r'<script defer src="[^"]*benchmark-pulse[^\"]*\.js"></script>',
            "",
            template,
        )
        template = template.replace(
            "</body>",
            '<script id="pulse-preloaded" type="application/json">'
            + payload
            + "</script><script>"
            + (static / "benchmark-pulse.js").read_text()
            + "</script></body>",
        )
        write_new(output, template)
        return
    payload = (
        json.dumps(data, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = Path(__file__).with_name("report.html").read_text(encoding="utf-8")
    write_new(output, template.replace("__REPORT_DATA__", payload))
