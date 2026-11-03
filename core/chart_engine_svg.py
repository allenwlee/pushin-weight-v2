"""Render an in-memory chart from the caller's already calculated values."""

from html import escape
from math import isfinite
from textwrap import wrap

COLORS = ("#316bea", "#13a889", "#ed8c33", "#a459c9", "#e35b65")


def render_svg(chart):
    title = escape(str(chart["title"]))
    lines = chart.get("lines", [])
    values = [
        float(p["value"])
        for line in lines
        for p in line["points"]
        if p.get("value") is not None and isfinite(float(p["value"]))
    ]
    days = [
        p["day"]
        for line in lines
        for p in line["points"]
        if p.get("value") is not None and isfinite(float(p["value"]))
    ]
    low, high = (min(0, min(values)), max(0, max(values))) if values else (0, 1)
    if low == high:
        high = low + 1
    first, last = (min(days), max(days)) if days else (0, 1)
    if first == last:
        last = first + 1
    x = lambda day: 90 + (day - first) * 700 / (last - first)
    y = lambda value: 360 - (float(value) - low) * 265 / (high - low)
    warning_lines = [
        part
        for warning in chart.get("warnings", [])
        for part in wrap(str(warning), width=48)
    ]
    height = max(540, 470 + 30 * len(lines) + 28 * len(warning_lines))
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 {height}" role="img" aria-label="{title}">',
        "<style>@media (max-width: 600px) { text { font-size: 25px; } }</style>",
        f'<rect width="900" height="{height}" rx="16" fill="#fff"/>',
        f'<text x="40" y="38" font-size="23" fill="#17243a">{title}</text>',
        f'<text x="90" y="65" font-size="12" fill="#53647a">{escape(str(chart.get("unit", "Value")))}</text>',
    ]
    if first <= 0 <= last:
        out.append(
            f'<path d="M{x(0):.1f} 95 V360" stroke="#a0aabb" stroke-dasharray="3 4"/><text x="{x(0) + 4:.1f}" y="90" font-size="12">Release</text>'
        )
    if first <= 7 and last >= 1:
        left, right = x(max(first, 1)), x(min(last, 7))
        out.append(
            f'<rect x="{left:.1f}" y="95" width="{right - left:.1f}" height="265" fill="#316bea" opacity="0.06"/>'
        )
    out.append(
        '<text x="440" y="410" text-anchor="middle" font-size="12">Days from release</text>'
    )
    for i in range(5):
        value = low + (high - low) * i / 4
        yy = y(value)
        out.append(
            f'<path d="M90 {yy:.1f} H790" stroke="#e5ebf1"/><text x="82" y="{yy + 4:.1f}" text-anchor="end" font-size="12">{value:.1f}</text>'
        )
        day = first + (last - first) * i / 4
        out.append(
            f'<text x="{x(day):.1f}" y="378" text-anchor="middle" font-size="12">{day:.0f}</text>'
        )
    for i, line in enumerate(lines):
        color = COLORS[i % len(COLORS)]
        label = escape(str(line["label"]))
        out.append(
            f'<text x="90" y="{445 + i * 30}" font-size="16" fill="{color}">{label}</text>'
        )
        segment = []
        for p in line["points"] + [{"value": None}]:
            if p.get("value") is None or not isfinite(float(p["value"])):
                if segment:
                    path = " ".join(
                        ("M" if j == 0 else "L")
                        + f"{x(pt['day']):.1f},{y(pt['value']):.1f}"
                        for j, pt in enumerate(segment)
                    )
                    dash = ' stroke-dasharray="6 4"' if line.get("forecast") else ""
                    out.append(
                        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"{dash}/>'
                    )
                    for pt in segment:
                        value = escape(str(pt["value"]))
                        point_date = escape(str(pt.get("date", f"day {pt['day']}")))
                        out.append(
                            f'<circle cx="{x(pt["day"]):.1f}" cy="{y(pt["value"]):.1f}" r="3" fill="{color}"><title>{label}, {point_date}: {value}</title></circle>'
                        )
                    segment = []
            else:
                segment.append(p)
    if not values:
        out.append(
            '<text x="450" y="220" text-anchor="middle">No data available</text>'
        )
    for i, warning in enumerate(warning_lines):
        out.append(
            f'<text x="40" y="{480 + len(lines) * 30 + i * 28}" font-size="14" fill="#7b4b00">{escape(str(warning))}</text>'
        )
    out.append("</svg>")
    return "".join(out)
