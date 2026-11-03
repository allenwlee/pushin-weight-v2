from core.chart_engine_svg import render_svg


def test_svg_contains_matching_values_and_escapes_labels():
    svg = render_svg(
        {
            "title": "<DeepSeek> & comparison",
            "lines": [
                {
                    "label": "Historical",
                    "points": [{"day": 0, "value": 100}, {"day": 1, "value": 150}],
                },
                {
                    "label": "Temporary prediction",
                    "forecast": True,
                    "points": [{"day": 1, "value": 140}],
                },
            ],
            "warnings": ["Coverage may be incomplete"],
        }
    )
    assert "&lt;DeepSeek&gt; &amp; comparison" in svg
    assert "150" in svg and "140" in svg
    assert "stroke-dasharray" in svg
    assert "Coverage may be incomplete" in svg
    assert "<DeepSeek>" not in svg


def test_empty_chart_explains_absent_data():
    assert "No data available" in render_svg({"title": "Empty", "lines": []})
